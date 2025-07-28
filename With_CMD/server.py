"""Exposes tools via MCP (STDIO)."""
from sql_tools import mcp
import logging
import sys
import db

def test_db_connection():
    """Attempts to connect to the database and perform a simple query."""
    logging.info("--- BEGINNING OF POSTGRESQL CONNECTION TEST ---")
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                result = cur.fetchone()
                if result and result[0] == 1:
                    logging.info("✅ Database connection test successful!")
                else:
                    logging.error("❌ Connection test failed: the query did not return the expected result.")
                    sys.exit(1)
    except Exception as e:
        logging.error("🔥🔥🔥 CRITICAL DATABASE CONNECTION FAILURE 🔥🔥🔥")
        logging.error(f"Exact error: {e}")
        logging.error("👉 CHECK YOUR ENVIRONMENT VARIABLES IN .env (PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DEFAULT_DB)")
        sys.exit(1)
    finally:
        logging.info("--- END OF CONNECTION TEST ---")

def main():
    """Main entry point."""
    # Configure logs to stderr to avoid conflicts
    logging.basicConfig(
        level=logging.INFO, 
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr
    )
    
    # Connection test
    test_db_connection()
    
    try:
        # Start in HTTP mode on localhost for FastMCP
        logging.info("  Starting MCP server in local HTTP mode")
        mcp.run(
            transport="http",
            host="127.0.0.1",
            port=8080,
        )
    except Exception as e:
        logging.exception(f"Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()