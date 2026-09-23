import asyncio
import json
import os
import time
from pathlib import Path

import httpx
from zagent.cohort import ClinicalStore, configured_clock
from zagent.draft_store import DraftStore
from zagent.evals.assertions import check_case
from zagent.evals.runner import capture_case
from zagent.evals.schema import load_suite
from zagent.privacy import Detector
from zagent.store import Store
from zagent.tools import ClinicalTools


def deployed_cases(root):
    return [
        case
        for case in load_suite(root).cases
        if case.agent.startswith("llm:") and not case.execution and not case.simulator
    ]


async def finished_job(client, session_id, job_id):
    async with asyncio.timeout(180):
        while True:
            response = await client.get(
                f"/sessions/{session_id}/jobs/{job_id}", params={"representation": "model"}
            )
            response.raise_for_status()
            result = response.json()
            if result["finished_at"]:
                assert not Detector().contains(result), "Raw identifiers in job evidence"
                assert [item["seq"] for item in result["logs"]] == list(
                    range(1, result["log_seq"] + 1)
                )
                return result
            await asyncio.sleep(0.25)


async def execution(client, store, *, mrn, app_id, expected):
    clinical = ClinicalStore(store, configured_clock())
    tools, drafts = ClinicalTools(clinical), DraftStore(clinical)
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Cluster execution verification")
    patients = await tools.dispatch(session.id, "find_patients", {"mrn": mrn})
    specimens = await tools.dispatch(
        session.id, "find_specimens", {"patient_handle": patients["handle"]}
    )
    draft = await drafts.update(
        session.id,
        conversation_turn_id=turn.conversation_turn_id,
        app_id=app_id,
        specimen_handle=specimens["handle"],
    )
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)
    response = await client.post(
        f"/sessions/{session.id}/drafts/{draft.draft_id}/confirm",
        json={"content_hash": draft.content_hash},
    )
    response.raise_for_status()
    job_id = response.json()["job_id"]
    result = await finished_job(client, session.id, job_id)
    assert [attempt["status"] for attempt in result["attempts"]] == expected, result["attempts"]
    registered = await store.pool.fetchval(
        "SELECT count(*) FROM privacy.worker_pods WHERE session_id=$1 AND job_id=$2",
        session.id,
        job_id,
    )
    assert registered == len(expected)
    return {
        "session_id": str(session.id),
        "job_id": job_id,
        "status": result["status"],
        "attempts": result["attempts"],
        "log_count": result["log_seq"],
    }


async def trace_evidence(trace_id):
    async with httpx.AsyncClient(base_url="http://tempo.zagent-neutral:3200", timeout=10) as client:
        async with asyncio.timeout(30):
            while True:
                response = await client.get(f"/api/traces/{trace_id}")
                if response.status_code == 404:
                    await asyncio.sleep(0.25)
                    continue
                response.raise_for_status()
                document = response.json()
                services = {}
                for batch in document.get("batches", document.get("resourceSpans", [])):
                    service = next(
                        item["value"]["stringValue"]
                        for item in batch["resource"]["attributes"]
                        if item["key"] == "service.name"
                    )
                    spans = [
                        span
                        for scope in batch.get(
                            "scopeSpans", batch.get("instrumentationLibrarySpans", [])
                        )
                        for span in scope["spans"]
                    ]
                    services.setdefault(service, []).extend(span["name"] for span in spans)
                if not any("job.execute" in spans for spans in services.values()):
                    await asyncio.sleep(0.25)
                    continue
                assert "conversation.turn" in services["zagent-agent-runtime"]
                assert {
                    "zagent-bff",
                    "zagent-llm-gateway",
                    "zagent-tools-gateway",
                    "zagent-dispatcher",
                    "zagent-privacy",
                    "zagent-tokenizer",
                } <= services.keys()
                assert not Detector().contains(document), "Raw identifiers in exported trace"
                return {
                    "trace_id": trace_id,
                    "services": {name: len(spans) for name, spans in services.items()},
                }


async def main():
    started = time.monotonic()
    root = Path("evals")
    store = await Store.open(os.environ["ZAGENT_APPLICATION_DATABASE_URL"])
    try:
        async with httpx.AsyncClient(base_url="http://bff:8000", timeout=90) as client:
            cases = []
            confirmation_session = None
            for case in deployed_cases(root):
                assert case.agent == "llm:default", "Deployed verification needs the default route"
                evidence = await capture_case(client, case, timeout_seconds=90)
                failures = check_case(case, evidence, root)
                assert not failures, failures
                cases.append({"case": case.id, "session_id": str(evidence.projection.session_id)})
                print(f"Deployed {case.id}: passed", flush=True)
                if case.id == "DRAFT-CONFIRM":
                    confirmation_session = evidence.projection.session_id
            assert confirmation_session is not None
            confirmed = await finished_job(client, confirmation_session, "job-0001")
            assert confirmed["status"] == "failed"
            assert confirmed["logs"][-1]["record"]["attributes"]["job.code"] == "low_coverage"
            trace = await trace_evidence(confirmed["logs"][0]["record"]["traceId"])
            executions = await asyncio.gather(
                execution(
                    client, store, mrn="NGC-0041873", app_id="readqc", expected=["completed"]
                ),
                execution(
                    client, store, mrn="NGC-0041872", app_id="somatic-snv", expected=["failed"]
                ),
                execution(
                    client,
                    store,
                    mrn="NGC-0041876",
                    app_id="readqc",
                    expected=["evicted", "completed"],
                ),
            )
            report = {
                "passed": True,
                "seconds": round(time.monotonic() - started, 2),
                "deployed_cases": cases,
                "session_id": str(confirmation_session),
                "trace": trace,
                "executions": executions,
            }
            await asyncio.to_thread(
                Path("/evidence/workflows.json").write_text, json.dumps(report, indent=2) + "\n"
            )
            print(json.dumps(report), flush=True)
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
