"""Real, disposable PostgreSQL; never connects to a user database."""
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import psycopg
import pytest
from sqlalchemy import text
from silicon.shared.db import make_engine

ROOT = Path(__file__).resolve().parents[3]


def run(*args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if result.returncode:
        pytest.fail(result.stderr or result.stdout, pytrace=False)
    return result


@pytest.fixture(scope="session")
def database():
    pg_bin = Path(os.environ["SILICON_TEST_PG_BIN"])
    version = run(str(pg_bin / "postgres"), "--version").stdout.strip()
    assert re.search(r"PostgreSQL\) 17\.11(?:\s|$)", version), f"Tests require PostgreSQL 17.11, got {version}"
    directory = Path(tempfile.mkdtemp(prefix="silicon-test-", dir="/tmp"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    data = directory / "data"
    run(str(pg_bin / "initdb"), "-D", str(data), "-U", "silicon_bootstrap", "-A", "trust", "--no-locale", "-E", "UTF8")
    def start():
        run(str(pg_bin / "pg_ctl"), "-D", str(data), "-l", str(directory / "postgres.log"),
            "-o", f"-h 127.0.0.1 -p {port} -k {directory}", "-w", "start")
    def stop():
        run(str(pg_bin / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop")
    try:
        start()
        with psycopg.connect(host="127.0.0.1", port=port, dbname="postgres", user="silicon_bootstrap", autocommit=True) as db:
            db.execute("CREATE DATABASE silicon")
        run(str(pg_bin / "psql"), "-h", "127.0.0.1", "-p", str(port), "-U", "silicon_bootstrap", "-d", "silicon",
            "-v", "ON_ERROR_STOP=1", "-v", "migration_password=local_migration_only", "-v", "app_password=local_app_only",
            "-f", str(ROOT / "infra/bootstrap.sql"))
        with psycopg.connect(host="127.0.0.1", port=port, dbname="silicon", user="silicon_migrator", autocommit=True) as db:
            assert db.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0] == 0
        url = f"postgresql+psycopg://silicon_app@127.0.0.1:{port}/silicon"
        migration_url = url.replace('silicon_app@', 'silicon_migrator@')
        env = {**os.environ, "DATABASE_URL": url, "MIGRATION_DATABASE_URL": migration_url, "SILICON_ENV": "test"}
        run(sys.executable, "infra/migrate.py", "upgrade", "head", cwd=ROOT, env=env)
        print(f"Verified empty database migration on {version}")
        yield SimpleNamespace(url=url, migration_url=migration_url, env=env, start=start, stop=stop)
    finally:
        if (data / "postmaster.pid").exists():
            stop()
        shutil.rmtree(directory)


@pytest.fixture
def engine(database):
    owner = make_engine(database.migration_url)
    with owner.begin() as db:
        db.execute(text("TRUNCATE publication_commands,contract_drafts,publication_events,quote_version_states,quote_versions,publication_decisions,publication_candidates,publication_policies,quote_commands, quote_exclusions, quote_selections, quote_drafts, jobs, outbox_events, crm_commands, crm_role_history, crm_responsibilities, crm_sites, crm_project_people, crm_projects, crm_contacts, crm_customers"))
    owner.dispose()
    app = make_engine(database.url)
    yield app
    app.dispose()
