import sys
from types import SimpleNamespace

import pytest
from dbt_common.exceptions import DbtRuntimeError

from dbt.adapters.duckdb.credentials import DuckDBCredentials
from dbt.adapters.duckdb.environments.motherduck_pg_endpoint import (
    MotherDuckPgEndpointCursorWrapper,
    MotherDuckPgEndpointEnvironment,
)

PG_ENDPOINT_HOST = "pg.example.com"


class FakeCursor:
    def __init__(self, fail=False):
        self.fail = fail
        self.sql = []

    def execute(self, sql, bindings=None):
        if self.fail:
            raise RuntimeError("query failed")
        self.sql.append((sql, bindings))

    def close(self):
        self.sql.append(("close", None))


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def install_fake_psycopg(monkeypatch):
    calls = []

    def connect(**kwargs):
        conn = FakeConnection()
        calls.append((kwargs, conn))
        return conn

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    return calls


def test_handle_connects_to_motherduck_pg_endpoint(monkeypatch):
    calls = install_fake_psycopg(monkeypatch)
    creds = DuckDBCredentials.from_dict(
        {
            "path": "md:jaffle_shop",
            "motherduck_token": "quack",
            "motherduck_postgres_endpoint": True,
            "motherduck_pg_endpoint_host": PG_ENDPOINT_HOST,
        }
    )

    handle = MotherDuckPgEndpointEnvironment(creds).handle()

    kwargs, conn = calls[0]
    assert kwargs == {
        "host": PG_ENDPOINT_HOST,
        "port": 5432,
        "dbname": "jaffle_shop",
        "user": "postgres",
        "password": "quack",
        "sslmode": "require",
        "autocommit": True,
    }
    assert handle.cursor()._cursor is conn.cursor_obj
    assert conn.cursor_obj.sql == [("close", None)]


def test_handle_can_use_verify_full_ssl_settings(monkeypatch):
    calls = install_fake_psycopg(monkeypatch)
    creds = DuckDBCredentials.from_dict(
        {
            "path": "md:jaffle_shop",
            "motherduck_token": "quack",
            "motherduck_postgres_endpoint": True,
            "motherduck_pg_endpoint_host": PG_ENDPOINT_HOST,
            "motherduck_pg_endpoint_sslmode": "verify-full",
            "motherduck_pg_endpoint_sslrootcert": "system",
        }
    )

    MotherDuckPgEndpointEnvironment(creds).handle()

    kwargs, _ = calls[0]
    assert kwargs["sslmode"] == "verify-full"
    assert kwargs["sslrootcert"] == "system"


def test_dbname_uses_md_colon_for_empty_motherduck_path(monkeypatch):
    install_fake_psycopg(monkeypatch)
    creds = DuckDBCredentials.from_dict(
        {
            "path": "md:",
            "motherduck_token": "quack",
            "motherduck_postgres_endpoint": True,
            "motherduck_pg_endpoint_host": PG_ENDPOINT_HOST,
        }
    )

    env = MotherDuckPgEndpointEnvironment(creds)

    assert env._dbname() == "md:"


def test_token_can_come_from_path(monkeypatch):
    install_fake_psycopg(monkeypatch)
    creds = DuckDBCredentials.from_dict(
        {
            "path": "md:jaffle_shop?motherduck_token=quack",
            "motherduck_postgres_endpoint": True,
            "motherduck_pg_endpoint_host": PG_ENDPOINT_HOST,
        }
    )

    env = MotherDuckPgEndpointEnvironment(creds)

    assert env._token() == "quack"


def test_token_path_alias_is_not_supported(monkeypatch):
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    monkeypatch.delenv("motherduck_token", raising=False)
    creds = DuckDBCredentials.from_dict(
        {
            "path": "md:jaffle_shop?token=quack",
            "motherduck_postgres_endpoint": True,
            "motherduck_pg_endpoint_host": PG_ENDPOINT_HOST,
        }
    )

    assert MotherDuckPgEndpointEnvironment(creds)._token() is None


def test_missing_token_raises_before_connect(monkeypatch):
    calls = install_fake_psycopg(monkeypatch)
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    monkeypatch.delenv("motherduck_token", raising=False)
    creds = DuckDBCredentials.from_dict(
        {
            "path": "md:jaffle_shop",
            "motherduck_postgres_endpoint": True,
            "motherduck_pg_endpoint_host": PG_ENDPOINT_HOST,
        }
    )

    with pytest.raises(DbtRuntimeError) as exc:
        MotherDuckPgEndpointEnvironment(creds).handle()

    assert "access token is required" in str(exc.value)
    assert calls == []


def test_initialize_connection_runs_endpoint_side_setup(monkeypatch):
    calls = install_fake_psycopg(monkeypatch)
    creds = DuckDBCredentials.from_dict(
        {
            "path": "md:jaffle_shop",
            "motherduck_token": "quack",
            "motherduck_postgres_endpoint": True,
            "motherduck_pg_endpoint_host": PG_ENDPOINT_HOST,
            "settings": {"threads": 4},
            "extensions": ["json"],
            "secrets": [{"type": "huggingface", "token": "hf"}],
            "attach": [{"path": "md:other_db"}],
        }
    )

    MotherDuckPgEndpointEnvironment(creds).handle()

    _, conn = calls[0]
    executed_sql = [sql for sql, _ in conn.cursor_obj.sql]
    assert "SET threads = '4'" in executed_sql
    assert "INSTALL json" in executed_sql
    assert "LOAD json" in executed_sql
    assert "ATTACH IF NOT EXISTS 'md:other_db'" in executed_sql
    assert any("type huggingface" in sql for sql in executed_sql)


def test_cursor_wrapper_wraps_execute_errors():
    cursor = MotherDuckPgEndpointCursorWrapper(FakeCursor(fail=True))

    with pytest.raises(DbtRuntimeError) as exc:
        cursor.execute("select 1")

    assert "query failed" in str(exc.value)


def test_python_models_are_not_supported():
    creds = DuckDBCredentials.from_dict(
        {
            "path": "md:jaffle_shop",
            "motherduck_token": "quack",
            "motherduck_postgres_endpoint": True,
            "motherduck_pg_endpoint_host": PG_ENDPOINT_HOST,
        }
    )
    env = MotherDuckPgEndpointEnvironment(creds)

    with pytest.raises(DbtRuntimeError) as exc:
        env.submit_python_job(None, {}, "")

    assert "Python models are not supported" in str(exc.value)
