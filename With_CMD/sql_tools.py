"""FastMCP tools exposed to the LLM (read-only)."""
import re
import logging  # Import the logging module
from fastmcp import FastMCP
from db import get_conn

FORBIDDEN = re.compile(r"^\s*(ALTER|CREATE|DELETE|DROP|INSERT|UPDATE|TRUNCATE)\b", re.I)

mcp = FastMCP("Postgres‑MCP")

# ... (the functions list_databases, list_tables, describe_table don't change) ...
@mcp.tool(description="Lists non-template databases on the server.")
def list_databases() -> list[str]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT datname FROM pg_database WHERE datistemplate = FALSE;")
        return [row[0] for row in cur.fetchall()]

@mcp.tool(description="Lists tables in a database.")
def list_tables(database: str) -> list[str]:
    with get_conn(database) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE';
        """)
        return [row[0] for row in cur.fetchall()]

@mcp.tool(description="Describes the schema of a table.")
def describe_table(database: str, table: str) -> list[dict]:
    with get_conn(database) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s;
        """, (table,))
        return [
            {"column": c, "type": t, "nullable": n == "YES"}
            for c, t, n in cur.fetchall()
        ]

# --- IMPROVED VERSION OF run_sql WITH LOGGING ---
@mcp.tool(description="Executes SELECT/CTE/EXPLAIN up to 100 rows.")
def run_sql(database: str, query: str) -> list:
    import logging
    logging.info(f"Attempting to execute query on database '{database}':\n--- SQL ---\n{query}\n-----------")
    if FORBIDDEN.match(query):
        logging.warning("Potentially destructive query blocked.")
        raise ValueError("🔥 Potentially destructive query blocked.")

    try:
        with get_conn(database) as conn, conn.cursor() as cur:
            cur.execute(query)
            if not cur.description:
                logging.info("The query did not return any columns.")
            return []

            cols = [d[0] for d in cur.description]
            # === Universal COUNT(*) correction ===
            if len(cols) == 1 and cols[0] in ("?column?", "count"):
                # If it's an aggregate (ex: SELECT COUNT(*) ...)
                results = [row[0] for row in cur.fetchmany(100)]
                logging.info(f"Results (COUNT or aggregate): {results}")
                return results
            else:
                # Classic SELECT, classic dict return
                results = [dict(zip(cols, row)) for row in cur.fetchmany(100)]
                logging.info(f"Results (SELECT): {results}")
                return results
    except Exception as e:
        logging.error(f"Error executing SQL query: {e}", exc_info=True)
        raise
