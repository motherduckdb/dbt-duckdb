def motherduck_pg_endpoint_profile(dbt_profile_target, test_database_name):
    profile = {
        "type": "duckdb",
        "path": f"md:{test_database_name}",
        "motherduck_token": dbt_profile_target.get("motherduck_token"),
        "motherduck_postgres_endpoint": True,
        "disable_transactions": True,
    }
    for key in [
        "motherduck_pg_endpoint_host",
        "motherduck_pg_endpoint_sslmode",
        "motherduck_pg_endpoint_sslrootcert",
    ]:
        if key in dbt_profile_target:
            profile[key] = dbt_profile_target[key]

    return {
        "test": {
            "outputs": {
                "dev": profile,
            },
            "target": "dev",
        }
    }


def test_motherduck_pg_endpoint_profile_preserves_connection_overrides():
    profile = motherduck_pg_endpoint_profile(
        {
            "motherduck_token": "quack",
            "motherduck_pg_endpoint_host": "pg.example.com",
            "motherduck_pg_endpoint_sslmode": "verify-full",
            "motherduck_pg_endpoint_sslrootcert": "/tmp/root.crt",
        },
        "test_database",
    )["test"]["outputs"]["dev"]

    assert profile["motherduck_pg_endpoint_host"] == "pg.example.com"
    assert profile["motherduck_pg_endpoint_sslmode"] == "verify-full"
    assert profile["motherduck_pg_endpoint_sslrootcert"] == "/tmp/root.crt"
