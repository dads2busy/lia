import sys
import os
import duckdb 
import time,random
from pathlib import Path
from fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP(name="Harmonized Service (HS) Code MCP Server", version="0.1")

if len(sys.argv) > 1:
    data_file_path = Path(sys.argv[1]).resolve()
else:
    data_file_path = Path(Path(__file__).parent,'hscodes.json').resolve()
    
if not data_file_path.exists():
    print(f"Data file not found: {data_file_path}", file=sys.stderr)
    sys.exit(1)

# Initialize DuckDB in-memory database
db = duckdb.connect(database=':memory:')
table_name = "hscode"

# Load data into DuckDB

db.execute(
    f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_json('{data_file_path.as_posix()}')"
)

print(f"# Loaded '{table_name}' from {data_file_path}", file=sys.stderr)

@mcp.tool()
def query_hscodes(sql: str) -> list[dict]:
    """
    Execute a SQL query against the Harmonized Service (HS) hscode database,
    Data exists in the table 'hscode'.
    
    Columns are:
        **id**   - Harmonized Service Code (H6,HS-2022). Digits only. No periods or spaces.
        **text** - Description of the Harmonized Service Code
        **aggrlevel** - Aggregation level (2 for a 2 digit code, 4 for a 4 digit code, 6 for a 6 digit code, etc.)
        **standardUnitAbbr** - Standard Unit of Measure (UOM) Abbreviation or n/a
    """
    try:
        print(f"Execute SQL: {sql}", file=sys.stderr)
        result = db.execute(sql).fetchall()
        print("Query Result Length: ", len(result), file=sys.stderr)
        time.sleep(random.randint(1, 10))
        columns = [desc[0] for desc in db.description]
        return [dict(zip(columns, row)) for row in result]
    except Exception as e:
        print(f"Error executing SQL: {e}", file=sys.stderr)
        return [{"error": str(e)}]

# Run the MCP server using stdio transport
if __name__ == "__main__":
    mcp.run(transport='stdio')


