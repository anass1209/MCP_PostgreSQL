"""
Centralized and secure configuration.
Automatically loads environment variables from .env
"""
from pathlib import Path
from dotenv import load_dotenv
import os
import sys

# Load the .env file if it exists
env_file = Path(__file__).resolve().parent / '.env'
if env_file.exists():
    load_dotenv(env_file)

# PostgreSQL parameters with default values
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", 5432))
PG_USER = os.getenv("PG_USER", "")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
PG_DEFAULT_DB = os.getenv("PG_DEFAULT_DB", "")

# Gemini API Key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Export for Google SDK
if GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY

# Debug configuration
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"

# Write debug messages to stderr only (not stdout for MCP)
if DEBUG_MODE:
    print(f"📊 Configuration loaded:", file=sys.stderr)
    print(f"   • PostgreSQL: {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DEFAULT_DB}", file=sys.stderr)
    print(f"   • Google API: {'✅ Configured' if GOOGLE_API_KEY else ' Missing'}", file=sys.stderr)