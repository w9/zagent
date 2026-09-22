from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class Case(StrictModel):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9-]+$")
    requirement: str
    agent: str = Field(pattern=r"^scripted:[a-z][a-z0-9_-]*$")
    conversation_turns: list[ConversationTurn] = Field(min_length=1)
    expect: dict[str, Any]


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
    script_sha256: str
    seed: int
    clock: datetime
    mode: Literal["replay"] = "replay"
    delay_scale: float = 0.04
    coalesce_seconds: float = 0.008
    model: str | None = None
    prompt_hash: str | None = None
    tool_schema_hash: str | None = None
    kb_version: str | None = None


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

    @model_validator(mode="after")
    def outcome_matches_failures(self) -> "TrialResult":
        if self.passed == bool(self.failures):
            raise ValueError("Pass/fail must agree with recorded assertion failures")
        if self.seed != self.provenance.seed:
            raise ValueError("Trial and provenance seeds must agree")
        return self


class Report(StrictModel):
    schema_version: Literal[1] = 1
    created_at: datetime
    duration_seconds: float = Field(ge=0)
    requirements: list[Requirement]
    cases: list[Case]
    verifications: list[Literal["standard", "chaos"]]
    results: list[TrialResult]
    pass_streak: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def unique_trials(self) -> "Report":
        keys = {(result.case_id, result.verification, result.seed) for result in self.results}
        if len(keys) != len(self.results):
            raise ValueError("Duplicate case/mode/seed outcomes would inflate trial counts")
        return self
