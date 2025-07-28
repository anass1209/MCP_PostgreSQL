"""Secure PostgreSQL connection (read-only by default)."""

import psycopg2
from contextlib import contextmanager
from config import PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DEFAULT_DB

@contextmanager
def get_conn(dbname: str = PG_DEFAULT_DB, *, read_only: bool = True):
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=dbname,
        options="-c search_path=public",
    )
    try:
        if read_only:
            conn.set_session(readonly=True, autocommit=True)
        yield conn
    finally:
        conn.close()