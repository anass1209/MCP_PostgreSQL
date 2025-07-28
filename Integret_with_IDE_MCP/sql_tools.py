"""
Intelligent MCP server for SQL queries with automated workflow.
Corrected version: imports prompts from the centralized prompts.py file
"""
import re
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
from db import get_conn
from config import GOOGLE_API_KEY
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI

from prompts import (
    DATABASE_SELECTION_PROMPT, 
    TABLE_SELECTION_PROMPT, 
    SQL_GENERATION_PROMPT, 
    RESPONSE_FORMATTING_PROMPT, 
    ERROR_RECOVERY_PROMPT
)

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s", stream=__import__('sys').stderr)
logger = logging.getLogger(__name__)

# Regex to block dangerous queries
FORBIDDEN = re.compile(r"^\s*(ALTER|CREATE|DELETE|DROP|INSERT|UPDATE|TRUNCATE|GRANT|REVOKE)\b", re.I)

# MCP instance
mcp = FastMCP("Intelligent-SQL-MCP")

llm = None
try:
    
    if GOOGLE_API_KEY:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0,
            google_api_key=GOOGLE_API_KEY,
        )
        logger.info("✅ Gemini model successfully initialized")
except Exception as e:
    logger.warning(f" Gemini not available: {e}")


def execute_safe_query(database: str, query: str, max_rows: int = 100) -> List[Dict]:
    """Executes a SQL query safely."""
    if FORBIDDEN.match(query):
        raise ValueError(" Potentially destructive query blocked.")
    
    try:
        with get_conn(database) as conn, conn.cursor() as cur:
            cur.execute(query)
            if not cur.description:
                return []
            
            cols = [d[0] for d in cur.description]
            results = [dict(zip(cols, row)) for row in cur.fetchmany(max_rows)]
            logger.info(f"Query executed successfully: {len(results)} rows returned")
            return results
    except Exception as e:
        logger.error(f"SQL error: {e}")
        raise

def get_or_create_event_loop():
    """Gets or creates an asyncio event loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop is closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop

async def call_llm_async(chain, params: dict) -> str:
    """Calls the LLM model asynchronously."""
    try:
        result = await chain.ainvoke(params)
        return result.strip()
    except Exception as e:
        logger.error(f"LLM call error: {e}")
        raise

def select_best_database(user_question: str, databases: List[str]) -> str:
    """Uses AI to select the best database."""
    if not llm or len(databases) == 1:
        return databases[0] if databases else "postgres"
    
    try:
        prompt = ChatPromptTemplate.from_template(DATABASE_SELECTION_PROMPT)
        chain = prompt | llm | StrOutputParser()
        
        loop = get_or_create_event_loop()
        selected = loop.run_until_complete(call_llm_async(chain, {
            "question": user_question, 
            "databases": databases
        }))
        
        if selected in databases:
            return selected
        else:
            logger.warning(f"AI chose invalid '{selected}', using {databases[0]}")
            return databases[0]
    except Exception as e:
        logger.error(f"Database selection error: {e}")
        return databases[0]

def select_best_table(user_question: str, database: str, tables: List[str]) -> str:
    """Uses AI to select the best table."""
    if not llm or len(tables) == 1:
        return tables[0] if tables else "unknown"
    
    try:
        prompt = ChatPromptTemplate.from_template(TABLE_SELECTION_PROMPT)
        chain = prompt | llm | StrOutputParser()
        
        loop = get_or_create_event_loop()
        selected = loop.run_until_complete(call_llm_async(chain, {
            "question": user_question,
            "database": database,
            "tables": tables
        }))
        
        if selected in tables:
            return selected
        else:
            logger.warning(f"AI chose invalid '{selected}', using {tables[0]}")
            return tables[0]
    except Exception as e:
        logger.error(f"Table selection error: {e}")
        return tables[0]

def generate_sql_query(user_question: str, database: str, table: str, 
                      schema: List[Dict], sample_data: List[Dict]) -> str:
    """Generates an intelligent SQL query based on context."""
    if not llm:
        return f'SELECT * FROM "{table}" LIMIT 3;'
    
    try:
        prompt = ChatPromptTemplate.from_template(SQL_GENERATION_PROMPT)
        chain = prompt | llm | StrOutputParser()
        
        loop = get_or_create_event_loop()
        sql = loop.run_until_complete(call_llm_async(chain, {
            "question": user_question,
            "database": database,
            "table": table,
            "schema": json.dumps(schema, indent=2),
            "sample_data": json.dumps(sample_data, indent=2, ensure_ascii=False)
        }))
        
        sql = sql.replace("```sql", "").replace("```", "").strip().rstrip(";")
        logger.info(f"SQL query generated: {sql}")
        return sql
    except Exception as e:
        logger.error(f"SQL generation error: {e}")
        return f'SELECT * FROM "{table}" LIMIT 10;'

def generate_corrected_sql(user_question: str, database: str, table: str, 
                          schema: List[Dict], sample_data: List[Dict],
                          failed_sql: str, error: str) -> str:
    """Generates a corrected SQL query after an error."""
    if not llm:
        return f'SELECT * FROM "{table}" LIMIT 10;'
    
    try:
        prompt = ChatPromptTemplate.from_template(ERROR_RECOVERY_PROMPT)
        chain = prompt | llm | StrOutputParser()
        
        loop = get_or_create_event_loop()
        sql = loop.run_until_complete(call_llm_async(chain, {
            "question": user_question,
            "database": database,
            "table": table,
            "failed_sql": failed_sql,
            "error": str(error),
            "schema": json.dumps(schema, indent=2),
            "sample_data": json.dumps(sample_data, indent=2, ensure_ascii=False)
        }))
        
        sql = sql.replace("```sql", "").replace("```", "").strip().rstrip(";")
        logger.info(f"Corrected SQL query: {sql}")
        return sql
    except Exception as e:
        logger.error(f"SQL correction error: {e}")
        return f'SELECT * FROM "{table}" LIMIT 10;'

def format_natural_response(user_question: str, sql_query: str, 
                           results: List[Dict]) -> str:
    """Formats the response in natural language."""
    if not llm:
        return f"I found {len(results)} result(s) for your question."
    
    try:
        prompt = ChatPromptTemplate.from_template(RESPONSE_FORMATTING_PROMPT)
        chain = prompt | llm | StrOutputParser()
        
        loop = get_or_create_event_loop()
        response = loop.run_until_complete(call_llm_async(chain, {
            "question": user_question,
            "sql": sql_query,
            "count": len(results),
            "results": json.dumps(results, indent=2, ensure_ascii=False, default=str)
        }))
        
        return response
    except Exception as e:
        logger.error(f"Response formatting error: {e}")
        return f"I found {len(results)} result(s) for your question."



def _list_databases() -> List[str]:
    """Internal function to list databases"""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datistemplate = FALSE ORDER BY datname;")
            databases = [row[0] for row in cur.fetchall()]
            logger.info(f"Databases found: {databases}")
            return databases
    except Exception as e:
        logger.error(f"Database listing error: {e}")
        return ["postgres"]

def _list_tables(database: str) -> List[str]:
    """Internal function to list tables"""
    try:
        with get_conn(database) as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE'
                ORDER BY table_name;
            """)
            tables = [row[0] for row in cur.fetchall()]
            logger.info(f"Tables found in {database}: {tables}")
            return tables
    except Exception as e:
        logger.error(f"Table listing error: {e}")
        return []

def _describe_table(database: str, table: str) -> List[Dict[str, Any]]:
    """Internal function to describe a table"""
    try:
        with get_conn(database) as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s
                ORDER BY ordinal_position;
            """, (table,))
            
            schema = [{
                "column_name": row[0],
                "data_type": row[1],
                "is_nullable": row[2] == "YES",
                "column_default": row[3]
            } for row in cur.fetchall()]
            
            logger.info(f"Schema of {table}: {len(schema)} columns")
            return schema
    except Exception as e:
        logger.error(f"Table description error: {e}")
        return []

def _sample_data(database: str, table: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Internal function to sample data"""
    try:
        query = f'SELECT * FROM "{table}" LIMIT {limit};'
        return execute_safe_query(database, query, limit)
    except Exception as e:
        logger.error(f"Sample error for {table}: {e}")
        return []


#---- MCP TOOLS ----

@mcp.tool
def list_databases() -> List[str]:
    """Lists all available databases"""
    return _list_databases()

@mcp.tool
def list_tables(database: str) -> List[str]:
    """Lists tables in a database"""
    return _list_tables(database)

@mcp.tool
def describe_table(database: str, table: str) -> List[Dict[str, Any]]:
    """Describes the schema of a table"""
    return _describe_table(database, table)

@mcp.tool
def run_sql(database: str, query: str) -> List[Dict[str, Any]]:
    """Executes a safe SQL SELECT query"""
    logger.info(f"SQL execution on {database}: {query}")
    return execute_safe_query(database, query)

@mcp.tool
def sample_data(database: str, table: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Displays a sample of data from a table"""
    return _sample_data(database, table, limit)

#---- Steps -----

@mcp.tool
def step1_discover_databases() -> Dict[str, Any]:
    """Step 1: Discovers all available databases"""
    try:
        databases = _list_databases()
        return {
            "step": 1,
            "action": "discover_databases",
            "status": "success",
            "databases": databases,
            "count": len(databases),
            "message": f"✅ {len(databases)} database(s) found: {', '.join(databases)}"
        }
    except Exception as e:
        return {
            "step": 1,
            "action": "discover_databases", 
            "status": "error",
            "error": str(e),
            "message": f"❌ Error during database discovery: {str(e)}"
        }

@mcp.tool
def step2_select_database(user_question: str, databases: List[str]) -> Dict[str, Any]:
    """Step 2: Selects the best database for the question"""
    try:
        selected_db = select_best_database(user_question, databases)
        return {
            "step": 2,
            "action": "select_database",
            "status": "success",
            "selected_database": selected_db,
            "available_databases": databases,
            "message": f"✅ Selected database: '{selected_db}' for the question: '{user_question}'"
        }
    except Exception as e:
        return {
            "step": 2,
            "action": "select_database",
            "status": "error", 
            "error": str(e),
            "message": f"❌ Error during database selection: {str(e)}"
        }

@mcp.tool
def step3_discover_tables(database: str) -> Dict[str, Any]:
    """Step 3: Discovers tables in the selected database"""
    try:
        tables = _list_tables(database)
        return {
            "step": 3,
            "action": "discover_tables",
            "status": "success",
            "database": database,
            "tables": tables,
            "count": len(tables),
            "message": f"✅ {len(tables)} table(s) found in '{database}': {', '.join(tables)}"
        }
    except Exception as e:
        return {
            "step": 3,
            "action": "discover_tables",
            "status": "error",
            "database": database,
            "error": str(e),
            "message": f"❌ Error during table discovery: {str(e)}"
        }

@mcp.tool
def step4_select_table(user_question: str, database: str, tables: List[str]) -> Dict[str, Any]:
    """Step 4: Selects the best table for the question"""
    try:
        selected_table = select_best_table(user_question, database, tables)
        return {
            "step": 4,
            "action": "select_table",
            "status": "success",
            "database": database,
            "selected_table": selected_table,
            "available_tables": tables,
            "message": f"✅ Selected table: '{selected_table}' in '{database}'"
        }
    except Exception as e:
        return {
            "step": 4,
            "action": "select_table",
            "status": "error",
            "error": str(e),
            "message": f"❌ Error during table selection: {str(e)}"
        }

@mcp.tool
def step5_analyze_schema(database: str, table: str) -> Dict[str, Any]:
    """Step 5: Analyzes the structure of the selected table"""
    try:
        schema = _describe_table(database, table)
        return {
            "step": 5,
            "action": "analyze_schema",
            "status": "success",
            "database": database,
            "table": table,
            "schema": schema,
            "columns_count": len(schema),
            "message": f"✅ Schema analyzed for '{table}': {len(schema)} columns"
        }
    except Exception as e:
        return {
            "step": 5,
            "action": "analyze_schema",
            "status": "error",
            "error": str(e),
            "message": f"❌ Error during schema analysis: {str(e)}"
        }

@mcp.tool
def step6_get_sample(database: str, table: str) -> Dict[str, Any]:
    """Step 6: Retrieves a data sample to understand the content"""
    try:
        sample = _sample_data(database, table, 3)
        return {
            "step": 6,
            "action": "get_sample",
            "status": "success", 
            "database": database,
            "table": table,
            "sample_data": sample,
            "rows_count": len(sample),
            "message": f"✅ Sample retrieved: {len(sample)} rows from '{table}'"
        }
    except Exception as e:
        return {
            "step": 6,
            "action": "get_sample",
            "status": "error",
            "error": str(e),
            "message": f"❌ Error during sample retrieval: {str(e)}"
        }

@mcp.tool
def step7_generate_sql(user_question: str, database: str, table: str, 
                      schema: List[Dict], sample_data_list: List[Dict]) -> Dict[str, Any]:
    """Step 7: Generates an intelligent SQL query"""
    try:
        sql_query = generate_sql_query(user_question, database, table, schema, sample_data_list)
        return {
            "step": 7,
            "action": "generate_sql",
            "status": "success",
            "user_question": user_question,
            "database": database,
            "table": table,
            "sql_query": sql_query,
            "message": f"✅ SQL query generated: {sql_query[:50]}..."
        }
    except Exception as e:
        return {
            "step": 7,
            "action": "generate_sql",
            "status": "error",
            "error": str(e),
            "message": f"❌ Error during SQL generation: {str(e)}"
        }

@mcp.tool
def step8_execute_query(database: str, sql_query: str, user_question: str = "", 
                       table: str = "", schema: List[Dict] = None, 
                       sample_data_list: List[Dict] = None) -> Dict[str, Any]:
    """Step 8: Executes the SQL query with error handling"""
    try:
        try:
            results = execute_safe_query(database, sql_query)
            return {
                "step": 8,
                "action": "execute_query",
                "status": "success",
                "database": database,
                "sql_query": sql_query,
                "results": results,
                "rows_count": len(results),
                "message": f"✅ Query executed successfully: {len(results)} result(s)"
            }
        except Exception as e:
            if llm and user_question and table and schema and sample_data_list:
                logger.info(f"🔄 Attempting to correct the query after error: {e}")
                corrected_sql = generate_corrected_sql(
                    user_question, database, table, schema, sample_data_list, sql_query, str(e)
                )
                
                try:
                    results = execute_safe_query(database, corrected_sql)
                    return {
                        "step": 8,
                        "action": "execute_query",
                        "status": "success_after_retry",
                        "database": database,
                        "original_sql": sql_query,
                        "corrected_sql": corrected_sql,
                        "results": results,
                        "rows_count": len(results),
                        "message": f"✅ Query corrected and executed: {len(results)} result(s)"
                    }
                except Exception as e2:
                    raise e2
            else:
                raise e
                
    except Exception as e:
        return {
            "step": 8,
            "action": "execute_query",
            "status": "error",
            "database": database,
            "sql_query": sql_query,
            "error": str(e),
            "message": f"❌ Error during execution: {str(e)}"
        }

@mcp.tool
def step9_format_response(user_question: str, sql_query: str, results: List[Dict]) -> Dict[str, Any]:
    """Step 9: Formats the final response in natural language"""
    try:
        natural_response = format_natural_response(user_question, sql_query, results)
        return {
            "step": 9,
            "action": "format_response",
            "status": "success",
            "user_question": user_question,
            "sql_query": sql_query,
            "results_count": len(results),
            "natural_response": natural_response,
            "message": "✅ Response formatted in natural language"
        }
    except Exception as e:
        return {
            "step": 9,
            "action": "format_response",
            "status": "error",
            "error": str(e),
            "message": f"❌ Error during formatting: {str(e)}"
        }


#---- Debug ----
@mcp.tool
def debug_connection() -> Dict[str, Any]:
    """Debug tool to test connection and features"""
    try:
        databases = _list_databases()
        info = {
            "status": "✅ Connection OK",
            "databases_count": len(databases),
            "databases": databases,
            "llm_available": llm is not None,
            "fastmcp_version": "corrected",
            "timestamp": str(__import__('datetime').datetime.now())
        }
        
        if databases:
            tables = _list_tables(databases[0])
            info["sample_database"] = databases[0]
            info["sample_tables_count"] = len(tables)
            info["sample_tables"] = tables[:5]
        
        return info
    except Exception as e:
        return {
            "status": "❌ Connection error",
            "error": str(e),
            "timestamp": str(__import__('datetime').datetime.now())
        }