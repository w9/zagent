from datetime import timedelta

import pytest
from zagent.cohort import FROZEN_NOW, HANDLE_TTL, SITES, ClinicalStore, HandleError, generate_cohort
from zagent.store import NotFound


def test_fixture_generation_is_seeded_relative_and_contains_all_four_conditions():
    cohort = generate_cohort(FROZEN_NOW)
    assert cohort == generate_cohort(FROZEN_NOW)
    assert cohort != generate_cohort(FROZEN_NOW, seed=7)
    for site in SITES:
        patients = [row for row in cohort["patients"] if row["site_id"] == site]
        specimens = [row for row in cohort["specimens"] if row["site_id"] == site]
        libraries = [row for row in cohort["libraries"] if row["site_id"] == site]
        assert len(patients) == 10
        assert len(specimens) == 29
        assert len([row for row in specimens if row["kind"] != row["assayed_kind"]]) == 2
        assert any(row["kind"] == "tumor" and row["purity"] < 0.2 for row in specimens)
        assert any(row["coverage"] < 20 and row["qc_status"] == "review" for row in libraries)
        assert not any(
            row["patient_id"] == f"PAT-{site}-004" and row["kind"] == "normal" for row in specimens
        )
        assert {row["received_at"].date() for row in specimens} == {
            FROZEN_NOW.date(),
            (FROZEN_NOW - timedelta(days=1)).date(),
        }
    tomorrow = generate_cohort(FROZEN_NOW + timedelta(days=1))
    assert tomorrow["specimens"][0]["received_at"] == (
        cohort["specimens"][0]["received_at"] + timedelta(days=1)
    )


@pytest.mark.integration
async def test_rls_filters_cross_site_queries_under_actual_database_roles(store):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    for site in SITES:
        async with clinical.site_connection(site) as connection:
            assert await connection.fetchval("SELECT current_user") == f"zagent_site_{site}"
            assert await connection.fetchval("SELECT count(*) FROM patients") == 10
            assert (
                await connection.fetchval("SELECT count(*) FROM patients WHERE site_id <> $1", site)
                == 0
            )
            for table in ("specimens", "libraries"):
                assert await connection.fetchval(f"SELECT count(*) FROM {table}") == 29
                assert (
                    await connection.fetchval(
                        f"SELECT count(*) FROM {table} WHERE site_id <> $1", site
                    )
                    == 0
                )
            with pytest.raises(Exception, match="permission denied"):
                await connection.execute("DELETE FROM patients")


@pytest.mark.integration
async def test_handles_are_session_scoped_persistent_and_expire_visibly(store):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    session = await store.create_session()
    columns = [{"key": "id", "label": "Patient", "type": "string"}]
    async with clinical.site_connection(session.site_id) as connection:
        patients = [
            dict(row) for row in await connection.fetch("SELECT * FROM patients ORDER BY id")
        ]
    result = await clinical.save_handle(session.id, "patients", columns, patients)
    assert result == {"handle": "query-0001", "count": 10, "schema": columns}
    assert (await clinical.resolve(session.id, result["handle"]))["row_count"] == 10
    other = await store.create_session()
    with pytest.raises(NotFound):
        await clinical.resolve(other.id, result["handle"])
    with pytest.raises(HandleError, match="Expected a specimens handle"):
        await clinical.resolve(session.id, result["handle"], "specimens")
    expired = ClinicalStore(store, lambda: FROZEN_NOW + HANDLE_TTL)
    with pytest.raises(HandleError, match="expired.*run the query again"):
        await expired.resolve(session.id, result["handle"])
    async with clinical.site_connection("lakeside") as connection:
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM query_handles WHERE session_id = $1", session.id
            )
            == 0
        )
