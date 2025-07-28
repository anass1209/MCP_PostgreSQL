@echo off
REM === Silent launch of the NLP-to-SQL server with Poetry ===

REM Move to the project directory
cd /d "%~dp0"

REM Check that Poetry is installed
poetry --version >nul 2>&1
if errorlevel 1 (
    echo Poetry is not installed. Please install it from https://python-poetry.org/ >>&2
    exit /b 1
)

REM Check that the .env file is present
if not exist ".env" (
    echo Missing .env file. Create it with your PostgreSQL parameters >>&2
    exit /b 1
)

REM Activate the Poetry environment and launch the MCP server
echo   Launching intelligent_server.py with Poetry...
poetry run python intelligent_server.py
