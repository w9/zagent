from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from zagent.scope import ReasonCode


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Threshold(StrictModel):
    metric: Literal["pass_rate"] = "pass_rate"
    min_lower_bound: float = Field(ge=0, le=1)
    trials: int = Field(ge=1)


class Requirement(StrictModel):
    id: str = Field(pattern=r"^REQ-[A-Z0-9-]+$")
    tier: Literal["invariant", "measured"]
    statement: str = Field(min_length=1)
    verification: Literal["standard", "chaos"] = "standard"
    cases: list[str] = Field(default_factory=list)
    enforced_by: list[str] = Field(default_factory=list)
    mutations: list[str] = Field(default_factory=list)
    threshold: Threshold | None = None

    @model_validator(mode="after")
    def validate_tier(self) -> "Requirement":
        if self.tier == "invariant" and (not self.enforced_by or not self.mutations):
            raise ValueError("Invariants must name enforcement sites and detecting mutations")
        if self.tier == "measured" and self.threshold is None:
            raise ValueError("Measured requirements must define a threshold")
        if self.tier == "invariant" and self.threshold is not None:
            raise ValueError("Invariant requirements do not use a measured threshold")
        if len(self.cases) != len(set(self.cases)):
            raise ValueError("A requirement cannot link the same case twice")
        return self


class ConversationTurn(StrictModel):
    user: str = Field(min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def nonblank(self) -> "ConversationTurn":
        if not self.user.strip():
            raise ValueError("A conversation turn cannot have a blank message")
        return self


class ContextMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


ScopeBucket = Literal[
    "clearly_off_topic",
    "clearly_in_scope",
    "contextual_continuations",
    "near_boundary_in_scope",
    "near_boundary_off_topic",
    "scope_wrappers",
]


class ScopeExample(StrictModel):
    id: str = Field(pattern=r"^SCOPE-[A-Z]+-[0-9]{3}$")
    user: str = Field(min_length=1, max_length=20000)
    label: ReasonCode | Literal["none"]
    context: list[ContextMessage] = Field(default_factory=list, max_length=20)
    draft: dict[str, Any] | None = None


class ScopeCorpus(StrictModel):
    buckets: dict[ScopeBucket, list[ScopeExample]]


class SimulatorGoal(StrictModel):
    app_id: str
    parameters: dict[str, Any]
    max_turns: int = Field(default=5, ge=2, le=8)


class ExecutionWorkflow(StrictModel):
    followups: list[ConversationTurn] = Field(default_factory=list, max_length=3)
    confirm_rerun: bool = False
    interrupt: Literal["text_delta", "tool_result"] | None = None
    kb_version: str = Field(pattern=r"^[a-f0-9]{64}$")


class AdversarialSpec(StrictModel):
    family: Literal[
        "prompt_injection",
        "scope_wrappers",
        "confirmation_bypass",
        "obfuscated_identifiers",
        "groundedness_pressure",
    ]
    ingress: Literal["user_message", "job_log", "kb_document", "tool_result", "specimen_note"] = (
        "user_message"
    )
    payload: str | None = Field(default=None, max_length=1500)
    marker: str | None = None
    setup: Literal["empty", "draft", "failed_job"] = "empty"
    label_source: Literal["agent_authored", "human_reviewed"] = "agent_authored"


class Case(StrictModel):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9-]+$")
    requirement: str
    agent: str = Field(pattern=r"^(scripted|llm|guard|detector):[a-z][a-z0-9_-]*$")
    conversation_turns: list[ConversationTurn] = Field(min_length=1)
    expect: dict[str, Any]
    bucket: ScopeBucket | None = None
    context: list[ContextMessage] = Field(default_factory=list)
    draft: dict[str, Any] | None = None
    simulator: SimulatorGoal | None = None
    execution: ExecutionWorkflow | None = None
    adversarial: AdversarialSpec | None = None
    workflow_actions: list[
        Literal[
            "edit",
            "read_draft",
            "stale_confirm",
            "confirm",
            "confirm_again",
            "confirm_all",
            "show_jobs",
        ]
    ] = Field(default_factory=list)
    session_checks: bool = False


class CaseGroup(StrictModel):
    cases: list[Case]


class Suite(StrictModel):
    requirements: list[Requirement]
    cases: list[Case]

    @model_validator(mode="after")
    def validate_links(self) -> "Suite":
        requirements = {requirement.id: requirement for requirement in self.requirements}
        cases = {case.id: case for case in self.cases}
        if len(requirements) != len(self.requirements) or len(cases) != len(self.cases):
            raise ValueError("Requirement and case IDs must be unique")
        for requirement in self.requirements:
            missing = set(requirement.cases) - cases.keys()
            if missing:
                raise ValueError(f"{requirement.id}: unknown cases {sorted(missing)}")
        for case in self.cases:
            if case.requirement not in requirements:
                raise ValueError(f"{case.id}: unknown requirement {case.requirement}")
            if case.id not in requirements[case.requirement].cases:
                raise ValueError(f"{case.id}: requirement {case.requirement} must link this case")
        return self


def load_suite(root: Path) -> Suite:
    requirements = yaml.safe_load((root / "requirements.yaml").read_text())
    cases = []
    for path in sorted((root / "cases").glob("*.yaml")):
        group = CaseGroup.model_validate(yaml.safe_load(path.read_text()))
        cases.extend(group.cases)
    scope_path = root / "scope.yaml"
    if scope_path.exists():
        corpus = ScopeCorpus.model_validate(yaml.safe_load(scope_path.read_text()))
        for bucket, examples in corpus.buckets.items():
            for example in examples:
                requirement = "REQ-SCOPE-02" if example.label == "none" else "REQ-SCOPE-01"
                cases.append(
                    Case(
                        id=example.id,
                        requirement=requirement,
                        agent="guard:default",
                        conversation_turns=[{"user": example.user}],
                        expect={
                            "refusal": "none"
                            if example.label == "none"
                            else {"code": example.label}
                        },
                        bucket=bucket,
                        context=example.context,
                        draft=example.draft,
                    )
                )
                for entry in requirements:
                    if entry["id"] in {requirement, "REQ-SCOPE-03"}:
                        entry.setdefault("cases", []).append(example.id)
    if any(entry["id"] == "REQ-PHI-04" for entry in requirements):
        from zagent.cohort import FROZEN_NOW, generate_cohort

        for index, patient in enumerate(generate_cohort(FROZEN_NOW)["patients"], 1):
            for label, field in (("MRN", "mrn"), ("NAME", "display_name")):
                identity = f"DETECT-{label}-{index:03d}"
                cases.append(
                    Case(
                        id=identity,
                        requirement="REQ-PHI-04",
                        agent="detector:default",
                        conversation_turns=[
                            {"user": f"Find {patient[field]} in this site's records."}
                        ],
                        expect={"detected": [patient[field]]},
                    )
                )
                next(entry for entry in requirements if entry["id"] == "REQ-PHI-04")[
                    "cases"
                ].append(identity)
    for case in cases:
        if case.adversarial:
            for entry in requirements:
                if (
                    entry["id"] in {case.requirement, "REQ-JOB-04"}
                    and case.id not in entry["cases"]
                ):
                    entry["cases"].append(case.id)
    return Suite(requirements=requirements, cases=cases)


def fixture_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Fixture path must stay inside {root}: {relative}")
    return path


class Provenance(StrictModel):
    commit: str | None
    dirty_worktree: bool | None
    agent_implementation: str
    script_sha256: str | None = None
    seed: int
    clock: datetime
    mode: Literal["replay", "record", "live"] = "replay"
    delay_scale: float = 0
    coalesce_seconds: float = 0.008
    model: str | None = None
    prompt_hash: str | None = None
    tool_schema_hash: str | None = None
    kb_version: str | None = None
    scope_hash: str | None = None
    independent_sample: int | None = None
    mutation: str | None = None
    simulator_model: str | None = None
    simulator_prompt_hash: str | None = None
    corpus_hash: str | None = None
    prompt_version: str | None = None
    label_source: str | None = None


class ScopeOutcome(StrictModel):
    expected: ReasonCode | None
    actual: ReasonCode | None
    error: bool = False
    structured: bool = True
    gateway_calls: int = Field(default=0, ge=0)
    provider_calls: int = Field(default=0, ge=0)


class TrialResult(StrictModel):
    case_id: str
    verification: Literal["standard", "chaos"]
    seed: int
    passed: bool
    failures: list[str] = Field(default_factory=list)
    transcript: str = ""
    session_id: str | None = None
    duration_seconds: float = Field(ge=0)
    executions: int = Field(ge=0)
    provenance: Provenance
    interruption: dict[str, Any] | None = None
    scope: ScopeOutcome | None = None
    requirement_outcomes: dict[str, bool] = Field(default_factory=dict)
    privacy_requests: int = Field(default=0, ge=0)
    tripwire_hits: int = Field(default=0, ge=0)
    slot_app: str | None = None
    slot_turns: int = 0
    adversarial: dict[str, Any] | None = None
    judge: dict[str, Any] | None = None

    @model_validator(mode="after")
    def outcome_matches_failures(self) -> "TrialResult":
        if self.passed == bool(self.failures):
            raise ValueError("Pass/fail must agree with recorded assertion failures")
        if self.seed != self.provenance.seed:
            raise ValueError("Trial and provenance seeds must agree")
        return self


class PrivacyScan(StrictModel):
    cassettes: int = 0
    goldens: int = 0
    stored_events: int = 0
    recorded_requests: int = 0
    job_logs: int = 0
    checkpoints: int = 0
    tool_receipts: int = 0
    violations: list[str] = Field(default_factory=list)
    legacy_archive: str = "privacy.legacy_events (clinical-only)"


class Report(StrictModel):
    schema_version: Literal[1] = 1
    created_at: datetime
    duration_seconds: float = Field(ge=0)
    requirements: list[Requirement]
    cases: list[Case]
    verifications: list[Literal["standard", "chaos"]]
    results: list[TrialResult]
    pass_streak: int = Field(default=3, ge=1)
    privacy_scan: PrivacyScan | None = None
    mutations: dict[str, Any] | None = None
    judge_calibration: dict[str, Any] | None = None
    matrix: dict[str, Any] | None = None
    findings_review: dict[str, Any] | None = None

    @model_validator(mode="after")
    def unique_trials(self) -> "Report":
        keys = {(result.case_id, result.verification, result.seed) for result in self.results}
        if len(keys) != len(self.results):
            raise ValueError("Duplicate case/mode/seed outcomes would inflate trial counts")
        return self
