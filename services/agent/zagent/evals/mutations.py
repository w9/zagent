import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg

from zagent.faults import MUTATIONS

EXPECTED = {
    "tokenizer_off": ["REQ-PHI-02"],
    "tripwire_off": ["REQ-META-02"],
    "submit_tool_on": ["REQ-JOB-01", "REQ-JOB-02"],
    "guard_off": ["REQ-SCOPE-01"],
    "resume_off": ["REQ-STREAM-02"],
    "drop_events": ["REQ-STREAM-01"],
    "zones_off": ["REQ-PHI-05"],
    "rls_off": ["REQ-ISO-01", "REQ-ISO-02"],
    "validator_off": ["REQ-VALID-01"],
    "acl_off": ["REQ-ACL-01"],
    "trust_unsigned_context": ["REQ-ACL-02"],
    "broker_tokenize_off": ["REQ-KB-02"],
    "ignore_snapshot_pin": ["REQ-KB-03"],
    "skip_contract_pin": ["REQ-KB-04"],
    "kb_direct_route": ["REQ-KB-01"],
}
ZONE_MUTATIONS = ("zones_off", "kb_direct_route")
KNOWLEDGE_MUTATIONS = (
    "acl_off",
    "trust_unsigned_context",
    "broker_tokenize_off",
    "ignore_snapshot_pin",
    "skip_contract_pin",
)


@asynccontextmanager
async def disposable_database(source: str):
    location = urlsplit(source)
    if not location.path.endswith("_test"):
        raise ValueError("Mutation experiments require a test database as their admin connection")
    name = f"zagent_mutation_{uuid4().hex}"
    admin = await asyncpg.connect(source)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        try:
            yield urlunsplit(location._replace(path=f"/{name}"))
        finally:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:
        await admin.close()


async def prepare_draft(environment, *, invalid=False, patient_mrn=None):
    from zagent.tools import ClinicalTools

    store = environment.app.state.store
    clinical = environment.app.state.clinical
    await clinical.seed()
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Prepare an analysis draft")
    tools = ClinicalTools(clinical)
    patients = await tools.dispatch(
        session.id,
        "find_patients",
        {
            "mrn": patient_mrn or ("NGC-0041875" if invalid else "NGC-0041873"),
        },
    )
    specimens = await tools.dispatch(
        session.id,
        "find_specimens",
        {
            "patient_handle": patients["handle"],
            "received_within": "P7D",
        },
    )
    draft = await environment.app.state.drafts.update(
        session.id,
        conversation_turn_id=turn.conversation_turn_id,
        app_id="somatic-snv" if invalid else "readqc",
        specimen_handle=specimens["handle"],
    )
    return turn, draft


async def probe(name: str, root: Path) -> dict:
    from httpx_sse import aconnect_sse

    from zagent.agent import ScriptedAgent
    from zagent.evals.environment import local_api
    from zagent.evals.privacy import (
        FixturePrivacy,
        fixture_identifiers,
        fixture_tripwire,
    )
    from zagent.evals.runner import capture_case
    from zagent.evals.schema import load_suite
    from zagent.evals.scope import case_events
    from zagent.events import Event
    from zagent.privacy import Detector, EgressBlocked
    from zagent.scope import ScopeGuard
    from zagent.tools import TOOL_DEFINITIONS, McpToolClient, ToolsGateway, create_mcp_server

    outcomes, controls, observed = {}, {}, {}
    database = os.environ["ZAGENT_TEST_DATABASE_URL"]
    suite = load_suite(root)
    async with local_api(database, ScriptedAgent(delay_scale=0)) as environment:
        client, store = environment.client, environment.app.state.store
        controls["http_health_before"] = (await client.get("/health")).status_code == 200
        await environment.app.state.clinical.seed()
        if name in {"tokenizer_off", "resume_off", "drop_events"}:
            case = next(case for case in suite.cases if case.id == "STREAM-001")
            if name == "tokenizer_off":
                case = case.model_copy(
                    update={
                        "conversation_turns": [
                            case.conversation_turns[0].model_copy(
                                update={"user": "Find NGC-0041872"}
                            )
                        ]
                    }
                )
            try:
                evidence = await capture_case(client, case)
            except AssertionError as error:
                if name != "drop_events" or "noncontiguous SSE cursor" not in str(error):
                    raise
                outcomes["REQ-STREAM-01"] = False
                observed["noncontiguous_events"] = True
            else:
                if name == "tokenizer_off":
                    leaked = Detector(fixture_identifiers()).contains(
                        [event.payload for event in evidence.events]
                    )
                    outcomes["REQ-PHI-02"] = not leaked
                    observed["identifier_in_events"] = leaked
                elif name == "drop_events":
                    outcomes["REQ-STREAM-01"] = True
                    observed["noncontiguous_events"] = False
                else:
                    cursor = evidence.events[2].seq
                    received = []
                    async with aconnect_sse(
                        client,
                        "GET",
                        f"/sessions/{evidence.projection.session_id}/events",
                        params={"from": 0, "representation": "model"},
                        headers={"Last-Event-ID": str(cursor)},
                    ) as stream:
                        async for frame in stream.aiter_sse():
                            if frame.event == "log":
                                received.append(Event.model_validate_json(frame.data).seq)
                    expected = [event.seq for event in evidence.events if event.seq > cursor]
                    outcomes["REQ-STREAM-02"] = received == expected
                    observed.update(resumed_events=len(received), expected_events=len(expected))
        elif name == "tripwire_off":
            tripwire = fixture_tripwire()
            tripwire({"content": "ordinary control request"})
            controls["ordinary_egress_allowed"] = True
            try:
                tripwire({"content": "NGC-0041872"})
            except EgressBlocked:
                blocked = True
            else:
                blocked = False
            outcomes["REQ-META-02"] = blocked
            observed["raw_identifier_blocked"] = blocked
        elif name == "guard_off":
            privacy = FixturePrivacy()
            from zagent.gateway import configured_gateway

            gateway = configured_gateway(
                "replay", egress_check=fixture_tripwire(), protect_response=privacy.protect_response
            )
            selected = [
                next(case for case in suite.cases if case.bucket == bucket)
                for bucket in ("clearly_off_topic", "clearly_in_scope")
            ]
            classifications = []
            for case in selected:
                events = privacy.protect_events(case_events(case))
                classifications.append(
                    await ScopeGuard(gateway).classify(
                        events,
                        sample=0,
                        metadata={
                            "session_id": str(events[0].session_id),
                            "conversation_turn_id": str(events[-1].conversation_turn_id),
                        },
                    )
                )
            controls["in_scope_allowed"] = classifications[1] is None
            outcomes["REQ-SCOPE-01"] = classifications[0] is not None
            observed["out_of_scope_refused"] = classifications[0] is not None
        elif name == "rls_off":
            async with environment.app.state.clinical.site_connection("northgate") as connection:
                own = await connection.fetchval(
                    "SELECT count(*) FROM patients WHERE site_id='northgate'"
                )
                foreign = await connection.fetchval(
                    "SELECT count(*) FROM patients WHERE site_id='lakeside'"
                )
            controls["own_site_readable"] = own > 0
            outcomes["REQ-ISO-01"] = foreign == 0
            try:
                async with store.pool.acquire() as connection, connection.transaction():
                    await connection.execute("SET LOCAL ROLE zagent_runtime")
                    accessible = await connection.fetchval("SELECT count(*) FROM patients")
            except asyncpg.InsufficientPrivilegeError:
                accessible = 0
            outcomes["REQ-ISO-02"] = accessible == 0
            observed.update(foreign_site_rows=foreign, runtime_clinical_rows=accessible)
        elif name in {"submit_tool_on", "validator_off"}:
            turn, draft = await prepare_draft(environment, invalid=name == "validator_off")
            if name == "submit_tool_on":
                gateway = ToolsGateway(
                    store, McpToolClient(server=create_mcp_server(environment.app.state.clinical))
                )
                await gateway.execute(
                    turn,
                    "submit_job",
                    json.dumps(
                        {
                            "draft_id": draft.draft_id,
                            "content_hash": draft.content_hash,
                        }
                    ),
                )
                jobs = await store.pool.fetchval(
                    "SELECT count(*) FROM jobs WHERE session_id=$1", turn.id
                )
                exposed = any(tool["function"]["name"] == "submit_job" for tool in TOOL_DEFINITIONS)
                outcomes.update({"REQ-JOB-01": jobs == 0, "REQ-JOB-02": not exposed and jobs == 0})
                observed.update(jobs_without_confirmation=jobs, submit_tool_exposed=exposed)
                controls["valid_draft"] = not draft.validation
            else:
                response = await client.post(
                    f"/sessions/{turn.id}/drafts/{draft.draft_id}/confirm",
                    json={"content_hash": draft.content_hash},
                )
                outcomes["REQ-VALID-01"] = response.status_code == 422 and any(
                    issue.code == "missing_matched_normal" for issue in draft.validation
                )
                observed.update(
                    confirm_status=response.status_code,
                    issues=[issue.code for issue in draft.validation],
                )
            await store.finish_conversation_turn(turn.id, turn.conversation_turn_id)
            valid_turn, valid = await prepare_draft(environment)
            response = await client.post(
                f"/sessions/{valid_turn.id}/drafts/{valid.draft_id}/confirm",
                json={"content_hash": valid.content_hash},
            )
            controls["human_confirm_works"] = response.status_code == 200
            await store.finish_conversation_turn(valid_turn.id, valid_turn.conversation_turn_id)
        elif name in KNOWLEDGE_MUTATIONS:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from mcp.server.fastmcp import FastMCP
            from zknowledge.index import build_index
            from zknowledge.snapshot import corpus_root

            from zagent.broker import KnowledgeBroker
            from zagent.evals.local_knowledge import local_broker
            from zagent.identity import CallerSigner

            session, signer = await store.create_session(), CallerSigner.configured()

            async def ask(broker, tool, arguments, persona="analyst", key=signer, snapshot=None):
                turn_id = uuid4()
                token = key.mint(
                    session_id=session.id, turn_id=turn_id, site="northgate", persona=persona
                )
                return await broker.dispatch(session.id, turn_id, tool, arguments, token, snapshot)

            broker = local_broker(store.privacy)
            draft = {"document": "sop-qc-001-v4"}
            if name in {"acl_off", "trust_unsigned_context"}:
                result = await ask(broker, "get_document", draft, "qa-officer")
                controls["qa_officer_reads_draft"] = "error" not in result
                if name == "acl_off":
                    leaked = "error" not in await ask(broker, "get_document", draft)
                    outcomes["REQ-ACL-01"] = not leaked
                    observed["analyst_reads_restricted_draft"] = leaked
                else:
                    forged = CallerSigner(Ed25519PrivateKey.generate())
                    accepted = "error" not in await ask(
                        broker, "get_document", draft, "qa-officer", forged
                    )
                    outcomes["REQ-ACL-02"] = not accepted
                    observed["forged_context_accepted"] = accepted
            elif name == "broker_tokenize_off":
                result = await ask(
                    broker,
                    "read_document",
                    {"document": "inc-0142", "start_line": 1, "end_line": 16},
                )
                controls["incident_read"] = "error" not in result
                raw = "NGC-0041872" in json.dumps(result)
                outcomes["REQ-KB-02"] = not raw
                observed["raw_identifier_left_the_broker"] = raw
            elif name == "ignore_snapshot_pin":
                with TemporaryDirectory(prefix="zagent-snapshots-") as directory:
                    snapshots, corpus = Path(directory) / "snapshots", Path(directory) / "corpus"
                    pinned, _ = await asyncio.to_thread(build_index, corpus_root(), snapshots)
                    shutil.copytree(corpus_root(), corpus)
                    page = corpus / "wiki/pages/40218.xhtml"
                    page.write_text(page.read_text() + "\n<p>Republished for review.</p>\n")
                    newer, _ = await asyncio.to_thread(build_index, corpus, snapshots)
                    broker = local_broker(store.privacy, snapshots)
                    query = {"query": "tumor coverage minimum"}
                    current = await ask(broker, "search_knowledge", query)
                    controls["newer_snapshot_is_current"] = current.get("snapshot") == newer
                    held = await ask(broker, "search_knowledge", query, snapshot=pinned)
                    outcomes["REQ-KB-03"] = held.get("snapshot") == pinned
                    observed["served_snapshot"] = held.get("snapshot")
            else:
                changed = FastMCP("changed-knowledge")

                @changed.tool(name="search_knowledge")
                def search_knowledge(
                    query: str,
                    include_inactive: bool = False,
                    limit: int = 5,
                    every_site: bool = False,
                ) -> dict[str, Any]:
                    return {"snapshot": "a" * 64, "expanded_terms": [], "matches": [], "counts": {}}

                result = await ask(broker, "search_knowledge", {"query": "tumor coverage minimum"})
                controls["published_contract_accepted"] = "error" not in result
                result = await ask(
                    KnowledgeBroker(McpToolClient(server=changed), store.privacy),
                    "search_knowledge",
                    {"query": "tumor coverage minimum"},
                )
                refused = result.get("error", {}).get("code") == "unavailable"
                outcomes["REQ-KB-04"] = refused
                observed["changed_contract_served"] = not refused
        else:
            raise ValueError("The zones mutation requires the running Compose stack probe")
        controls["http_health_after"] = (await client.get("/health")).status_code == 200
    return {
        "healthy": all(controls.values()),
        "controls": controls,
        "requirements": outcomes,
        "observed": observed,
    }


async def run_probe(name: str, database_url: str, root: Path, *, mutate: bool) -> dict:
    root = await asyncio.to_thread(root.resolve)
    async with disposable_database(database_url) as target:
        with TemporaryDirectory(prefix="zagent-mutation-") as directory:
            environment = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith(("OTEL_", "ZAGENT_PRIVACY_"))
            }
            environment.update(
                {
                    "ZAGENT_MUTATION": name if mutate else "",
                    "ZAGENT_TEST_MODE": "mutation",
                    "ZAGENT_LLM_MODE": "replay",
                    "ZAGENT_AGENT": "scripted",
                    "ZAGENT_DISPLAY_MODE": "1",
                    "DATABASE_URL": target,
                    "ZAGENT_TEST_DATABASE_URL": target,
                    "OPENROUTER_API_KEY_FILE": "/dev/null",
                    "OPENAI_API_KEY_FILE": "/dev/null",
                    "ZAGENT_GATEWAY_AUDIT": str(Path(directory) / "gateway.sqlite3"),
                }
            )
            for key in (
                "OPENROUTER_API_KEY",
                "OPENAI_API_KEY",
                "ZAGENT_RUNTIME_URL",
                "ZAGENT_SCRIPT",
            ):
                environment.pop(key, None)
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "zagent.evals.mutations",
                "--probe",
                name,
                "--root",
                str(root),
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
            except TimeoutError:
                process.kill()
                await process.communicate()
                return {"healthy": False, "error": "probe_timeout", "requirements": {}}
            if process.returncode:
                return {
                    "healthy": False,
                    "error": "probe_failed",
                    "requirements": {},
                    "diagnostic": stderr.decode()[-2000:],
                }
            return json.loads(stdout)


def compare_mutation(name: str, control: dict, mutant: dict) -> dict:
    expected = EXPECTED[name]
    detected = sorted(
        identity
        for identity, passed in mutant.get("requirements", {}).items()
        if not passed and control.get("requirements", {}).get(identity) is True
    )
    valid = (
        control["healthy"]
        and mutant["healthy"]
        and all(control.get("requirements", {}).get(identity) is True for identity in expected)
    )
    return {
        "name": name,
        "expected": expected,
        "detected_by": detected,
        "unexpected": sorted(set(detected) - set(expected)),
        "status": "detected"
        if valid and set(expected) <= set(detected)
        else "survived"
        if valid
        else "invalid",
        "control": control,
        "mutant": mutant,
    }


async def evaluate_mutations(database_url: str, root: Path, selection="all") -> dict:
    from zagent.evals.runner import git_provenance

    root = await asyncio.to_thread(root.resolve)
    selected = list(MUTATIONS) if selection == "all" else selection.split(",")
    if not selected or set(selected) - set(MUTATIONS) or len(selected) != len(set(selected)):
        raise ValueError("Unknown or repeated mutation selection")
    started = time.monotonic()
    results = []
    for name in selected:
        if name in ZONE_MUTATIONS:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(root.parent / "deploy/compose/zones.py"),
                "mutation",
                name,
                cwd=root.parent,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode:
                control = mutant = {
                    "healthy": False,
                    "requirements": {},
                    "error": "zones_probe_failed",
                    "diagnostic": stderr.decode()[-2000:],
                }
            else:
                response = json.loads(stdout)
                control, mutant = response["control"], response["mutant"]
        else:
            control = await run_probe(name, database_url, root, mutate=False)
            mutant = await run_probe(name, database_url, root, mutate=True)
        result = compare_mutation(name, control, mutant)
        results.append(result)
        print(f"{name}: {result['status']} ({', '.join(result['detected_by'])})", file=sys.stderr)
    commit, dirty = git_provenance(root)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "seconds": time.monotonic() - started,
        "provenance": {
            "commit": commit,
            "dirty_worktree": dirty,
            "provider_calls": 0,
            "mode": "replay",
            "isolation": "one disposable database per probe",
        },
        "passed": all(result["status"] == "detected" for result in results),
        "results": results,
    }


def evidence_report(measurement: dict):
    from zagent.evals.schema import Case, Provenance, Report, Requirement, TrialResult

    cases, results = [], []
    clock = datetime.fromisoformat(measurement["created_at"])
    for outcome in measurement["results"]:
        identity = "MUT-" + outcome["name"].upper().replace("_", "-")
        cases.append(
            Case(
                id=identity,
                requirement="REQ-META-02",
                agent="scripted:default",
                conversation_turns=[{"user": f"Exercise {outcome['name']}"}],
                expect={},
            )
        )
        passed = outcome["status"] == "detected"
        results.append(
            TrialResult(
                case_id=identity,
                verification="standard",
                seed=0,
                passed=passed,
                failures=[] if passed else [f"{identity}: mutation {outcome['status']}"],
                transcript=json.dumps(outcome, indent=2),
                duration_seconds=0,
                executions=2,
                provenance=Provenance(
                    commit=measurement["provenance"]["commit"],
                    dirty_worktree=measurement["provenance"]["dirty_worktree"],
                    agent_implementation="Paired enforcement probe",
                    seed=0,
                    clock=clock,
                    mutation=outcome["name"],
                ),
            )
        )
    return Report(
        created_at=clock,
        duration_seconds=measurement["seconds"],
        requirements=[
            Requirement(
                id="REQ-META-02",
                tier="invariant",
                statement="Every selected enforcement mutation is detected "
                "with healthy positive controls.",
                cases=[case.id for case in cases],
                enforced_by=["zagent.evals.mutations"],
                mutations=[outcome["name"] for outcome in measurement["results"]],
            )
        ],
        cases=cases,
        results=results,
        verifications=["standard"],
        mutations=measurement,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", choices=MUTATIONS)
    parser.add_argument("--root", type=Path, default=Path("evals"))
    parser.add_argument("--selection", default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.probe:
        print(json.dumps(asyncio.run(probe(args.probe, args.root))))
        return
    result = asyncio.run(
        evaluate_mutations(os.environ["ZAGENT_TEST_DATABASE_URL"], args.root, args.selection)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
