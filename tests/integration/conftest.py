"""Disposable pgvector Postgres; never reuse the developer database."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine


@pytest.fixture(scope='module')
def postgres_container_engine():
    from testcontainers.postgres import PostgresContainer
    # An explicitly selected integration run fails if Docker is unavailable.
    with PostgresContainer('pgvector/pgvector:pg16', driver='psycopg') as container:
        url = container.get_connection_url()
        environment = dict(os.environ, DATABASE_URL=url)
        subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'],
                       cwd=Path(__file__).parents[2], env=environment, check=True)
        engine = create_engine(url)
        try:
            yield engine
        finally:
            engine.dispose()
