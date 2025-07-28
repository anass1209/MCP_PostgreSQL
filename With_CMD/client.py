# client.py (STDIO Version)

import asyncio
import sys
import json
import logging
from typing import List, Dict, Any
import subprocess
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI

from fastmcp import Client
from fastmcp.exceptions import ToolError
from config import GOOGLE_API_KEY

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

class SmartMCPClient:
    
    def __init__(self):
        self.model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0,
            google_api_key=GOOGLE_API_KEY,
        )
        # Change: using STDIO transport instead of HTTP
        self.server_process = None
        self.session = None

    async def __aenter__(self):
        # For FastMCP, we need to use a local HTTP transport
        # but starting the server automatically
        logger.info("  Starting MCP server...")
        
        # Launch server.py as a subprocess
        self.server_process = subprocess.Popen(
            [sys.executable, "server.py"],
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a bit for the server to start
        await asyncio.sleep(2)
        
        # Connect to the server via local HTTP
        self.session = Client("http://127.0.0.1:8080/mcp/")
        
        await self.session.__aenter__()
        await self.session.ping()
        logger.info("📡 Connected to MCP server")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.__aexit__(exc_type, exc_val, exc_tb)
        
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()
            logger.info("🔌 MCP server closed")

    async def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Executes an MCP tool and returns the result properly."""
        try:
            logger.info(f"🔧 Executing tool: {tool_name} with args: {kwargs}")
            result_obj = await self.session.call_tool(tool_name, kwargs)
            data = result_obj.data

            # Case 1: The data is simple (or empty), we return it directly.
            if not data or isinstance(data, (str, int, float, bool, dict)):
                return data
            
            # Case 2: It's a list. We need to clean its content.
            if isinstance(data, list):
                if not data:
                    return [] # Return an empty list if it's empty
                
                # The problem is that `fastmcp` returns a list of objects that are not real dicts.
                # Conversion via JSON is the safest workaround.
                logger.info("Converting complex list data via JSON...")
                try:
                    # We transform the object into its JSON representation, then reload it as a pure Python object.
                    # This is the most reliable method to normalize the structure.
                    return json.loads(json.dumps(data, default=str))
                except TypeError as e:
                    logger.error(f"Failed JSON conversion for {tool_name}: {e}")
                    # As a last resort, we return a list of textual representations.
                    # This avoids a crash and gives the LLM readable information.
                    return [repr(item) for item in data]

            # Case 3: It's another type of complex object (like the 'Root' object).
            # We try the same JSON conversion.
            logger.info(f"Converting a complex object ({type(data).__name__}) via JSON...")
            try:
                return json.loads(json.dumps(data, default=str))
            except TypeError as e:
                logger.error(f"Failed JSON conversion for object {type(data).__name__}: {e}")
                # If everything fails, we return its textual representation.
                return repr(data)

        except ToolError as e:
            logger.error(f"❌ Error executing {tool_name}: {e}")
            raise RuntimeError(f"MCP Error {tool_name}: {e}")

    async def step1_discover_databases(self) -> List[str]:
        """Step 1: Discover all available databases."""
        logger.info("🔍 STEP 1: Discovering databases...")
        databases = await self.execute_tool("list_databases")
        logger.info(f"✅ Databases found: {databases}")
        return databases

    async def step2_select_database(self, user_question: str, databases: List[str]) -> str:
        """Step 2: Select the appropriate database based on the user's question."""
        logger.info("🎯 STEP 2: Selecting the appropriate database...")
        template = """You are an expert in database selection. 
        User question: "{user_question}"
        Available databases: {databases}
        Analyze the question and choose the most appropriate database.
        Answer ONLY with the exact name of the chosen database.
        If no database seems appropriate, choose the first one in the list."""
        
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | self.model | StrOutputParser()
        selected_db = await chain.ainvoke({"user_question": user_question, "databases": databases})
        selected_db = selected_db.strip()
        
        if selected_db not in databases:
            logger.warning(f"The AI chose a non-existent database ('{selected_db}'). Using the first one in the list.")
            selected_db = databases[0] if databases else "postgres"
        logger.info(f"✅ Selected database: {selected_db}")
        return selected_db

    async def step3_discover_tables(self, database: str) -> List[str]:
        """Step 3: Discover all tables in the selected database."""
        logger.info(f"🔍 STEP 3: Discovering tables in '{database}'...")
        tables = await self.execute_tool("list_tables", database=database)
        logger.info(f"✅ Tables found: {tables}")
        return tables

    async def step4_select_table(self, user_question: str, database: str, tables: List[str]) -> str:
        """Step 4: Select the appropriate table based on the user's question."""
        logger.info("🎯 STEP 4: Selecting the appropriate table...")
        template = """You are an expert in table selection.
        Question: "{user_question}"
        Database: {database}
        Available tables: {tables}
        Choose the most appropriate table. Answer ONLY with the exact name of the table.
        If no table seems appropriate, choose the first one."""
        
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | self.model | StrOutputParser()
        selected_table = await chain.ainvoke({"user_question": user_question, "database": database, "tables": tables})
        selected_table = selected_table.strip()
        
        if selected_table not in tables:
            logger.warning(f"The AI chose a non-existent table ('{selected_table}'). Using the first one in the list.")
            selected_table = tables[0] if tables else "candidates"
        logger.info(f"✅ Selected table: {selected_table}")
        return selected_table

    async def step5_analyze_table_structure(self, database: str, table: str) -> Dict[str, Any]:
        """Step 5: Analyze the table structure and view a sample."""
        logger.info(f"🔍 STEP 5: Analyzing the structure of '{table}'...")
        schema = await self.execute_tool("describe_table", database=database, table=table)
        logger.info(f"📋 Schema: {len(schema)} columns found.")
        sample_query = f'SELECT * FROM "{table}" LIMIT 3'
        sample_data = await self.execute_tool("run_sql", database=database, query=sample_query)
        logger.info(f"📊 Data sample: {len(sample_data)} rows.")
        return {"schema": schema, "sample_data": sample_data, "table_name": table, "database": database}
    
    async def step6_generate_sql_query(self, user_question: str, table_info: Dict[str, Any]) -> str:
        """Step 6: Generate the appropriate SQL query based on the user's question."""
        logger.info("🧠 STEP 6: Generating SQL query...")
        
        sql_generation_prompt_template = """
        You are an expert and precise PostgreSQL SQL query generator.
    
        CONTEXT:
        - User question: "{user_question}"
        - Database: {database}
        - Table: {table_name}
        - Table schema (columns and types): {schema}
        - Data sample: {sample_data}
    
        INSTRUCTIONS:
        1.  Analyze the user question, schema, and sample to understand the data structure.
        2.  Generate a precise and optimized SQL SELECT query to answer the question.
        3.  **Adapt your query strategy based on the data type (`data_type`) of each column.**
    
        **RULES FOR HANDLING COMPLEX COLUMNS (VERY IMPORTANT):**
    
        - **CASE 1: The column is of type `jsonb`** (ex: `educations`, `skills`, `work_experiences`).
        - You MUST use JSONB-specific operators. NEVER USE `LIKE` on a `jsonb` column.
        - To check if a `jsonb` array contains an object with a certain key/value, use the `@>` operator. This is the most reliable method.
        - **Example to find 'University of Strasbourg' in `educations` (jsonb):**
            `WHERE educations @> '[{{"institute": "University of Strasbourg"}}]'::jsonb`
        - **Example to find the skill 'python' in `skills` (jsonb):**
            `WHERE skills @> '[{{"skill": "python"}}]'::jsonb`
        - Note the syntax: `CAST` the string to `jsonb` with `::jsonb`.
    
        - **CASE 2: The column is of type `text` but contains JSON.**
        - If and only if the `data_type` is `text` or `varchar`, you can use `LIKE`.
        - **Example (only if the column was text):**
            `WHERE educations LIKE '%"institute":"University of Strasbourg"%'`
    
        4.  Use `LIMIT 100` by default, except for counting queries (`COUNT`).
        5.  Generate NOTHING other than the raw SQL query, without backticks, comments, or explanation.
    
        SQL QUERY:
        """
        
        parser = StrOutputParser()
        prompt = ChatPromptTemplate.from_template(sql_generation_prompt_template)
        chain = prompt | self.model | parser
        
        # The schema is crucial, we ensure it is well formatted
        schema_str = json.dumps(table_info.get('schema', '[]'), indent=2)
        sample_data_str = json.dumps(table_info.get('sample_data', '[]'), indent=2, ensure_ascii=False)
    
        raw_sql = await chain.ainvoke({
            "user_question": user_question,
            "database": table_info['database'],
            "table_name": table_info['table_name'],
            "schema": schema_str,
            "sample_data": sample_data_str
        })
        
        sql = raw_sql.replace("```sql", "").replace("```", "").strip().rstrip(";")
        
        logger.info(f"✅ SQL query generated:\n{sql}")
        return sql
    

    async def step7_execute_query(self, database: str, query: str) -> List[Any]:
        """Step 7: Execute the SQL query."""
        logger.info("  STEP 7: Executing final query...")
        results = await self.execute_tool("run_sql", database=database, query=query)
        logger.info(f"✅ {len(results) if isinstance(results, list) else 'N/A'} result row(s).")
        return results

    async def step8_format_natural_language_response(self, user_question: str, query: str, results: List[Any]) -> str:
        """Step 8: Format the response in natural language."""
        logger.info("📝 STEP 8: Formatting the response...")
        template = """You are a communication expert who transforms SQL results into clear answers.

        CONTEXT:
        - Question: "{user_question}"
        - SQL Query: {sql_query}
        - Results: {results}

        INSTRUCTIONS:
        1. Analyze the results.
        2. Answer the question clearly and naturally in English.
        3. Include relevant data in your response.
        4. Be concise but informative.

        NATURAL RESPONSE:"""

        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | self.model | StrOutputParser()
        
        results_str = json.dumps(results, indent=2, ensure_ascii=False)
        
        natural_response = await chain.ainvoke({
            "user_question": user_question,
            "sql_query": query,
            "results": results_str
        })
        logger.info("✅ Natural language response generated.")
        return natural_response.strip()

    async def process_user_question(self, user_question: str) -> str:
        """Complete pipeline for processing a user question."""
        try:
            logger.info(f"🎬 BEGINNING PROCESSING: '{user_question}'")
            databases = await self.step1_discover_databases()
            selected_db = await self.step2_select_database(user_question, databases)
            tables = await self.step3_discover_tables(selected_db)
            selected_table = await self.step4_select_table(user_question, selected_db, tables)
            table_info = await self.step5_analyze_table_structure(selected_db, selected_table)
            sql_query = await self.step6_generate_sql_query(user_question, table_info)
            results = await self.step7_execute_query(selected_db, sql_query)
            final_response = await self.step8_format_natural_language_response(user_question, sql_query, results)
            logger.info("🎉 PROCESSING COMPLETED SUCCESSFULLY")
            return final_response
        except Exception as e:
            logger.error(f"❌ Error during processing: {e}", exc_info=True)
            return f"Sorry, a critical error occurred: {e}"

async def main():
    user_question = " ".join(sys.argv[1:])
    if not user_question:
        user_question = input("❓ Ask your question: ")
    
    async with SmartMCPClient() as client:
        response = await client.process_user_question(user_question)
        print(f"\n🎉 FINAL ANSWER:\n{response}")

if __name__ == "__main__":
    asyncio.run(main())