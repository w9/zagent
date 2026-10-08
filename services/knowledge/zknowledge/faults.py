"""Test-only enforcement mutations for the knowledge team's services; inert in any other setup."""

import os

MUTATIONS = ("site_acl_off", "site_trust_unsigned_grant", "site_unpinned")


def configured() -> str | None:
    mutation = os.environ.get("ZKNOWLEDGE_MUTATION")
    if not mutation:
        return None
    if mutation not in MUTATIONS or os.environ.get("ZKNOWLEDGE_TEST_MODE") != "mutation":
        raise RuntimeError("Mutation flags require an explicit mutation test configuration")
    return mutation


def enabled(name: str) -> bool:
    return configured() == name
