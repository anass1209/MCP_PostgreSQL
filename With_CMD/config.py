"""Centralizes configuration.
Automatically loads environment variables from a .env file
(remember to `pip install python-dotenv`)."""
from pathlib import Path
from dotenv import load_dotenv
import os

# Loads .env at the root of the repo if present
env = Path(__file__).resolve().with_name('.env')
if env.exists():
    load_dotenv(env)

# PostgreSQL parameters
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", 5432))
PG_USER = os.getenv("PG_USER", "anass")
PG_PASSWORD = os.getenv("PG_PASSWORD", "Dna_enginnering_Data@$")
PG_DEFAULT_DB = os.getenv("PG_DEFAULT_DB", "postgres")

# API key for Gemini → exported for the SDK
GOOGLE_API_KEY = "AIzaSyCVqBnd8Z5xBz-6DMBIvu64VT9GdLz5tek"
os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY