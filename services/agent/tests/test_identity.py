import asyncio
import base64
import json
import time
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.server.fastmcp import Context, FastMCP
from zagent.broker import CALLER_META, KnowledgeBroker
from zagent.identity import (
    CALLER_CONTEXT_META,
    CONTEXT_TTL_SECONDS,
    PERSONAS,
    CallerRejected,
    CallerSigner,
    CallerVerifier,
    GrantSigner,
    write_keypair,
)
from zagent.kb_tools import contract_hash
from zagent.privacy import Tokenized
from zagent.store import AgentSession
from zagent.tools import McpToolClient

SIGNER = CallerSigner.configured()
VERIFIER = CallerVerifier.configured()
SESSION, TURN = uuid4(), uuid4()
EMPTY_SEARCH = {"snapshot": "a" * 64, "expanded_terms": [], "matches": [], "counts": {}}


class PassThrough:
    async def tokenize(self, session_id, raw, *, path, schema=None, external=False):
        return Tokenized(value=raw.value)


def mint(persona="analyst", *, session_id=SESSION, turn_id=TURN, signer=SIGNER, now=None):
    return signer.mint(
        session_id=session_id, turn_id=turn_id, site="northgate", persona=persona, now=now
    )


def unsigned(token: str) -> str:
    claims = jwt.decode(token, options={"verify_signature": False})
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{body}."


def widened(token: str) -> str:
    header, body, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    claims["roles"] = ["lab-director"]
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.{signature}"


def test_a_signed_context_carries_the_persona_roles_for_one_turn():
    context = VERIFIER.verify(mint("qa-officer"), session_id=SESSION, turn_id=TURN)
    assert (context.site, context.persona, context.roles) == (
        "northgate",
        "qa-officer",
        ("qa-officer",),
    )
    assert context.exp - context.iat == CONTEXT_TTL_SECONDS


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: None, id="missing"),
        pytest.param(lambda: "not-a-token", id="garbage"),
        pytest.param(lambda: mint(now=time.time() - CONTEXT_TTL_SECONDS - 60), id="expired"),
        pytest.param(
            lambda: mint(signer=CallerSigner(Ed25519PrivateKey.generate())), id="foreign-key"
        ),
        pytest.param(lambda: widened(mint()), id="widened-roles"),
        pytest.param(lambda: unsigned(mint()), id="alg-none"),
        pytest.param(
            lambda: jwt.encode(
                jwt.decode(mint(), options={"verify_signature": False}), "s" * 32, "HS256"
            ),
            id="symmetric",
        ),
        pytest.param(lambda: mint(session_id=uuid4()), id="other-session"),
        pytest.param(lambda: mint(turn_id=uuid4()), id="other-turn"),
    ],
)
def test_unverifiable_or_rebound_contexts_are_rejected(token):
    with pytest.raises(CallerRejected):
        VERIFIER.verify(token(), session_id=SESSION, turn_id=TURN)


def test_keypair_files_are_private_and_the_signing_key_is_kept(tmp_path, monkeypatch):
    signing, verify = tmp_path / "signing/key.pem", tmp_path / "verify/key.pem"
    write_keypair(signing, verify)
    original = signing.read_bytes()
    write_keypair(signing, verify)
    assert signing.read_bytes() == original
    assert signing.stat().st_mode & 0o777 == verify.stat().st_mode & 0o777 == 0o600
    monkeypatch.setenv("ZAGENT_CALLER_SIGNING_KEY_FILE", str(signing))
    monkeypatch.setenv("ZAGENT_CALLER_VERIFY_KEY_FILE", str(verify))
    token = mint(signer=CallerSigner.configured())
    assert CallerVerifier.configured().verify(token, session_id=SESSION, turn_id=TURN)
    with pytest.raises(CallerRejected):
        CallerVerifier.configured().verify(mint(), session_id=SESSION, turn_id=TURN)


def test_personas_use_knowledge_roles_and_never_match_patient_rules():
    from zagent.evals.privacy import fixture_identifiers
    from zagent.privacy import Detector
    from zknowledge.document import ROLES

    detector = Detector(fixture_identifiers())
    for persona in PERSONAS.values():
        assert set(persona.roles) <= set(ROLES)
        for text in (persona.name, persona.title, persona.description):
            assert not detector.matches(text), text


def test_the_intranet_directory_and_grants_agree_with_the_workbench(tmp_path, monkeypatch):
    from zagent.cohort import SITES
    from zknowledge.site import identity as intranet

    assert {
        persona.id: (persona.name, persona.title, persona.roles) for persona in PERSONAS.values()
    } == intranet.STAFF
    assert set(intranet.SITES) == set(SITES)
    signing, verify = tmp_path / "signing/key.pem", tmp_path / "verify/key.pem"
    write_keypair(signing, verify)
    monkeypatch.setenv("ZAGENT_SITE_SIGNING_KEY_FILE", str(signing))
    monkeypatch.setenv("ZKNOWLEDGE_GRANT_VERIFY_KEY_FILE", str(verify))
    token = GrantSigner.configured().mint(
        site="lakeside", persona="lab-director", document="wiki-40205", lines="3-4"
    )
    grant = intranet.GrantVerifier.configured().redeem(token)
    assert (grant.persona, grant.site, grant.roles, grant.document, grant.lines) == (
        "lab-director",
        "lakeside",
        ("lab-director",),
        "wiki-40205",
        "3-4",
    )
    with pytest.raises(intranet.GrantRejected):
        intranet.GrantVerifier.configured().redeem(
            GrantSigner(Ed25519PrivateKey.generate()).mint(
                site="northgate", persona="analyst", document="wiki-40205"
            )
        )
    with pytest.raises(intranet.GrantRejected):
        intranet.GrantVerifier.configured().redeem(mint("qa-officer"))


def recording_upstream(seen: list[dict]) -> FastMCP:
    server = FastMCP("recording-knowledge")

    @server.tool(name="search_knowledge")
    def search_knowledge(
        query: str, ctx: Context, include_inactive: bool = False, limit: int = 5
    ) -> dict[str, Any]:
        meta = ctx.request_context.meta
        seen.append((meta.model_extra or {}) if meta else {})
        return EMPTY_SEARCH

    return server


async def test_the_broker_forwards_only_the_verified_caller_never_model_input():
    seen: list[dict] = []
    upstream = McpToolClient(server=recording_upstream(seen))
    broker = KnowledgeBroker(
        upstream, PassThrough(), contract=contract_hash(await upstream.tool_schemas())
    )
    result = await broker.dispatch(
        SESSION, TURN, "search_knowledge", {"query": "coverage"}, mint("qa-officer")
    )
    assert result == EMPTY_SEARCH
    assert seen == [{CALLER_META: {"site": "northgate", "roles": ["qa-officer"]}}]
    widening = await broker.dispatch(
        SESSION,
        TURN,
        "search_knowledge",
        {"query": "coverage", "site": "lakeside", "roles": ["lab-director"]},
        mint(),
    )
    assert widening["error"]["code"] == "invalid_arguments"
    for rejected in (None, mint(now=time.time() - CONTEXT_TTL_SECONDS - 60)):
        result = await broker.dispatch(
            SESSION, TURN, "search_knowledge", {"query": "coverage"}, rejected
        )
        assert result["error"]["code"] == "unavailable"
    assert len(seen) == 1


async def test_the_runtime_sends_the_context_only_with_knowledge_calls():
    seen: dict[str, dict] = {}
    server = FastMCP("recording-tools")

    def register(name: str) -> None:
        async def invoke(
            session_id: str,
            conversation_turn_id: str,
            arguments: dict[str, Any],
            ctx: Context,
            operation_id: str | None = None,
        ) -> dict[str, Any]:
            meta = ctx.request_context.meta
            seen[name] = (meta.model_extra or {}) if meta else {}
            return {"ok": True}

        server.add_tool(invoke, name=name)

    for name in ("find_patients", "search_knowledge"):
        register(name)
    session = AgentSession(
        id=SESSION, conversation_turn_id=TURN, message="Hello", caller_context=mint()
    )
    client = McpToolClient(server=server, knowledge=McpToolClient(server=server))
    await client.call(session, "find_patients", {"mrn": "NGC-0041872"})
    await client.call(session, "search_knowledge", {"query": "coverage"})
    assert CALLER_CONTEXT_META not in seen["find_patients"]
    assert seen["search_knowledge"] == {CALLER_CONTEXT_META: session.caller_context}
    assert "caller_context" not in repr(session)


async def test_restricted_knowledge_follows_the_verified_persona():
    from zagent.evals.local_knowledge import local_broker

    broker = local_broker(PassThrough())

    async def get_document(persona: str, document: str) -> dict:
        return await broker.dispatch(
            SESSION, TURN, "get_document", {"document": document}, mint(persona)
        )

    hidden = await get_document("analyst", "sop-qc-001-v4")
    assert hidden == await get_document("analyst", "sop-qc-099-v1")
    assert hidden["error"]["code"] == "not_found"
    assert (await get_document("lab-technologist", "sop-qc-001-v4"))["error"]["code"] == (
        "not_found"
    )
    for persona in ("qa-officer", "lab-director"):
        assert (await get_document(persona, "sop-qc-001-v4"))["status"] == "draft"
    assert (await get_document("qa-officer", "wiki-40205"))["error"]["code"] == "not_found"
    assert (await get_document("lab-director", "wiki-40205"))["source"] == "wiki"


async def test_the_intranet_opens_exactly_the_citations_the_broker_would_serve():
    """REQ-ACL-03 parity: the same persona and site see the same restricted documents."""
    import httpx
    from zagent.cohort import SITES
    from zagent.evals.local_knowledge import local_broker, published_snapshots
    from zknowledge.index import IndexStore
    from zknowledge.site.app import create_site
    from zknowledge.site.identity import GrantVerifier

    broker = local_broker(PassThrough())
    key = Ed25519PrivateKey.generate()
    intranet = create_site(
        IndexStore(published_snapshots()), verifier=GrantVerifier(key.public_key())
    )
    documents = (
        "sop-qc-001-v3",
        "sop-qc-001-v4",
        "sop-acc-001a-v1",
        "chg-0024",
        "inc-0142",
        "inc-0151",
        "wiki-40100",
        "wiki-40204",
        "wiki-40205",
        "wiki-40223",
        "wiki-40232",
    )
    seen = set()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=intranet), base_url="http://intranet"
    ) as web:
        for site in SITES:
            for persona in PERSONAS:
                context = SIGNER.mint(session_id=SESSION, turn_id=TURN, site=site, persona=persona)
                for document in documents:
                    served = "error" not in await broker.dispatch(
                        SESSION, TURN, "get_document", {"document": document}, context
                    )
                    token = GrantSigner(key).mint(site=site, persona=persona, document=document)
                    page = await web.get(
                        "/signin/grant", params={"token": token}, follow_redirects=True
                    )
                    assert page.status_code == (200 if served else 404), (site, persona, document)
                    seen.add(served)
    assert seen == {True, False}


@pytest.mark.integration
async def test_sessions_record_a_persona_and_turns_carry_a_signed_context(api):
    client, store = api.client, api.app.state.store
    personas = (await client.get("/personas")).json()
    assert personas["default"] == "analyst"
    assert [persona["id"] for persona in personas["personas"]] == list(PERSONAS)
    assert (await client.post("/sessions")).json()["persona"] == "analyst"
    for body in ({"persona": "administrator"}, {"persona": "analyst", "roles": ["lab-director"]}):
        assert (await client.post("/sessions", json=body)).status_code == 422
    created = await client.post("/sessions", json={"persona": "qa-officer"})
    assert created.status_code == 201 and created.json()["persona"] == "qa-officer"
    session_id = UUID(created.json()["id"])
    listed = next(
        item for item in (await client.get("/sessions")).json() if item["id"] == str(session_id)
    )
    assert listed["persona"] == "qa-officer"
    accepted = await client.post(f"/sessions/{session_id}/messages", json={"text": "Hello"})
    turn_id = UUID(accepted.json()["conversation_turn_id"])
    token = await store.pool.fetchval(
        "SELECT caller_context FROM conversation_turns WHERE id=$1", turn_id
    )
    context = VERIFIER.verify(token, session_id=session_id, turn_id=turn_id)
    assert (context.persona, context.roles, context.site) == (
        "qa-officer",
        ("qa-officer",),
        "northgate",
    )
    events = await store.snapshot_events(session_id)
    assert token not in json.dumps([event.model_dump(mode="json") for event in events])
    await finished(store, session_id)


@pytest.mark.integration
async def test_a_citation_opens_the_intranet_as_the_session_persona(api):
    from urllib.parse import parse_qs, urlsplit

    client = api.client
    session_id = (await client.post("/sessions", json={"persona": "qa-officer"})).json()["id"]
    path = f"/sessions/{session_id}/citations/open"
    citation = {
        "document": "sop-qc-001-v4",
        "snapshot": "a" * 64,
        "lines": "10-12",
        "q": "Tumor libraries\n  would require",
    }
    response = await client.post(path, data=citation)
    assert response.status_code == 303
    assert response.headers["cache-control"] == "no-store"
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        "http://localhost:5180/signin/grant"
    )
    claims = jwt.decode(parse_qs(location.query)["token"][0], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 60 and claims["aud"] == "zknowledge-site"
    assert (claims["persona"], claims["roles"], claims["site"]) == (
        "qa-officer",
        ["qa-officer"],
        "northgate",
    )
    assert (claims["document"], claims["lines"], claims["q"]) == (
        "sop-qc-001-v4",
        "10-12",
        "Tumor libraries would require",
    )
    for body in (
        {**citation, "persona": "lab-director"},
        {**citation, "document": "../etc"},
        {**citation, "lines": "1;2"},
        {"lines": "1-2"},
    ):
        assert (await client.post(path, data=body)).status_code == 422, body
    missing = await client.post(f"/sessions/{uuid4()}/citations/open", data=citation)
    assert missing.status_code == 404


async def finished(store, session_id: UUID) -> None:
    for _ in range(200):
        if (await store.snapshot(session_id)).conversation_turn.status != "running":
            return
        await asyncio.sleep(0.05)
    raise AssertionError("The conversation turn did not finish")


@pytest.mark.integration
async def test_the_runtime_keeps_the_forwarded_turn_and_context(database_url):
    import httpx
    from zagent.agent import ScriptedAgent
    from zagent.app import Settings, create_app

    app = create_app(
        Settings(database_url=database_url, display_mode=False), ScriptedAgent(delay_scale=0)
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://runtime"
        ) as client:
            session_id = UUID((await client.post("/sessions")).json()["id"])
            turn_id = uuid4()
            token = mint(session_id=session_id, turn_id=turn_id)
            accepted = await client.post(
                f"/sessions/{session_id}/messages",
                json={
                    "text": {"value": "Hello"},
                    "conversation_turn_id": str(turn_id),
                    "caller_context": token,
                },
            )
            assert accepted.json()["conversation_turn_id"] == str(turn_id)
            assert token == await app.state.store.pool.fetchval(
                "SELECT caller_context FROM conversation_turns WHERE id=$1", turn_id
            )
            await finished(app.state.store, session_id)


@pytest.mark.integration
async def test_a_resumed_turn_with_an_expired_context_fails_closed(store):
    from zagent.evals.local_knowledge import local_broker
    from zagent.runtime import Runtime

    session = await store.create_session(persona="qa-officer")
    turn_id = uuid4()
    expired = mint(
        "qa-officer",
        session_id=session.id,
        turn_id=turn_id,
        now=time.time() - CONTEXT_TTL_SECONDS - 60,
    )
    await store.begin_conversation_turn(
        session.id,
        "What changed in the draft?",
        conversation_turn_id=turn_id,
        caller_context=expired,
    )
    resumed: list[AgentSession] = []

    class Capture:
        resumable = True

        async def run_turn(self, session, emit):
            resumed.append(session)

    runtime = Runtime(store, Capture())
    await runtime.recover()
    await asyncio.gather(*list(runtime.tasks.values()))
    turn = next(item for item in resumed if item.conversation_turn_id == turn_id)
    assert turn.caller_context == expired
    result = await local_broker(store.privacy).dispatch(
        session.id, turn_id, "search_knowledge", {"query": "coverage"}, turn.caller_context
    )
    assert result["error"]["code"] == "unavailable"


@pytest.mark.integration
async def test_the_database_accepts_only_registered_personas(store):
    import asyncpg

    for persona in PERSONAS:
        assert (await store.create_session(persona=persona)).persona == persona
    with pytest.raises(asyncpg.CheckViolationError):
        await store.create_session(persona="administrator")
