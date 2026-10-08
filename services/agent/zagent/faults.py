import os
import re
from urllib.parse import unquote, urlsplit

MUTATIONS = (
    "tokenizer_off",
    "tripwire_off",
    "submit_tool_on",
    "guard_off",
    "resume_off",
    "drop_events",
    "zones_off",
    "rls_off",
    "validator_off",
    "acl_off",
    "trust_unsigned_context",
    "broker_tokenize_off",
    "ignore_snapshot_pin",
    "skip_contract_pin",
    "kb_direct_route",
    "site_acl_off",
    "site_trust_unsigned_grant",
    "site_unpinned",
    "site_direct_route",
)


def configured(database_url: str | None = None) -> str | None:
    mutation = os.environ.get("ZAGENT_MUTATION")
    if not mutation:
        return None
    target = os.environ.get("ZAGENT_TEST_DATABASE_URL", "")
    database = unquote(urlsplit(target).path).removeprefix("/")
    if (
        mutation not in MUTATIONS
        or os.environ.get("ZAGENT_TEST_MODE") != "mutation"
        or os.environ.get("ZAGENT_LLM_MODE") != "replay"
        or not re.fullmatch(r"zagent_mutation_[a-f0-9]{32}", database)
        or os.environ.get("DATABASE_URL") != target
        or (database_url is not None and database_url != target)
    ):
        raise RuntimeError(
            "Mutation flags require explicit replay-only mutation test configuration "
            "and its dedicated disposable database"
        )
    return mutation


def enabled(name: str) -> bool:
    return configured() == name
