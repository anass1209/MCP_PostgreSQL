"""Intelligent MCP server for Claude Desktop via batch file.
Optimized for automated workflow: discovery → selection → analysis → generation → execution → NLP response.
"""
import logging
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from config import PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DEFAULT_DB, GOOGLE_API_KEY


# Log configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
    datefmt="%H:%M:%S"
)

logger = logging.getLogger(__name__)

def setup_environment():
    """Configure the environment and checks dependencies."""
    logger.info("🔧 Configuring the environment...")

    
    # Debug: Display all important environment variables
    env_vars = {
        "PG_HOST": PG_HOST,
        "PG_USER": PG_USER, 
        "PG_PASSWORD": PG_PASSWORD,
        "GOOGLE_API_KEY": GOOGLE_API_KEY
    }

    logger.info("🔍 Detected environment variables:")
    for key, value in env_vars.items():
        status = "✅ Defined" if value else "❌ Missing"
        logger.info(f"   • {key}: {status}")
    
    # Check critical environment variables
    required_vars = ["PG_HOST", "PG_USER", "PG_PASSWORD", "GOOGLE_API_KEY"]
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
        if missing_vars:
            log.info(f"missing_vars = {missing_vars}")

    logger.info("✅ Environment variables OK")
    return True

def test_imports():
    """Tests critical imports."""
    logger.info("📦 Checking dependencies...")
    
    try:
        import psycopg2
        logger.info("✅ psycopg2 available")
    except ImportError:
        logger.error("psycopg2 missing - pip install psycopg2-binary")
        return False
    
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        logger.info("✅ langchain-google-genai available")
    except ImportError:
        logger.error("langchain-google-genai missing")
        return False
    
    try:
        from fastmcp import FastMCP
        logger.info("✅ fastmcp available")
    except ImportError:
        logger.error("fastmcp missing")
        return False
    
    return True

def test_db_connection():
    """Tests the PostgreSQL connection."""
    logger.info("🔍 Testing PostgreSQL connection...")
    
    try:
        from db import get_conn
        
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), version();")
                db_name, version = cur.fetchone()
                logger.info(f"✅ Connected to '{db_name}'")
                logger.info(f"📊 PostgreSQL: {version[:50]}...")
        
        return True
        
    except Exception as e:
        logger.error(f" DB connection failed: {e}")
        logger.error(" Check your PostgreSQL parameters in .env")
        return False

def test_gemini_connection():
    """Tests the connection to the Gemini API."""
    logger.info("🤖 Testing Gemini connection...")
    
    try:
        from config import GOOGLE_API_KEY
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your-api-key-here":
            logger.warning("⚠️  Gemini API key not configured - degraded mode")
            return False
        
        # Simple test without real call (saves quotas)
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0,
            google_api_key=GOOGLE_API_KEY,
        )
        
        logger.info("✅ Gemini configured")
        return True
        
    except Exception as e:
        logger.error(f"Gemini configuration error: {e}")
        return False

def main():
    """Main entry point."""
    logger.info("  Starting the intelligent MCP server...")
    
    if not setup_environment():
        logger.error("Configuration failed - server shutdown")
        sys.exit(1)
    
    if not test_imports():
        logger.error("Missing dependencies")
        sys.exit(1)
    
    if not test_db_connection():
        logger.error("PostgreSQL connection failed")
        sys.exit(1)
    
    gemini_ok = test_gemini_connection()
    
    try:
        from sql_tools import mcp
        
        logger.info("🎯 Intelligent MCP server ready")
        if not gemini_ok:
            logger.warning("⚠️ Degraded mode: limited AI")
        
        logger.info(" Server listening on stdio...")
        mcp.run(transport="stdio")
        
    except KeyboardInterrupt:
        logger.info(" Shutdown requested")
    except Exception as e:
        logger.error(f" Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()