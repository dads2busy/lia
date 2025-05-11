import sys
import os
import duckdb 

from pathlib import Path
from fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP(name="DuckDB MCP Server", version="0.1")

# Retrieve the data file path from command-line arguments
if len(sys.argv) < 2:
    print("Usage: python mcp_duckdb_server.py <data_file.[csv|arrow|json]>", file=sys.stderr)
    sys.exit(1)

data_file_path = Path(sys.argv[1]).resolve()
if not data_file_path.exists():
    print(f"Data file not found: {data_file_path}", file=sys.stderr)
    sys.exit(1)

# Initialize DuckDB in-memory database
db = duckdb.connect(database=':memory:')
table_name = "data"

# Load data into DuckDB
ext = data_file_path.suffix.lower()
if ext == ".csv":
    db.execute(
        f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto('{data_file_path.as_posix()}')"
    )

elif ext == ".arrow":
    db.execute("INSTALL 'nanoarrow' from community")
    db.execute("LOAD 'nanoarrow'")
    # print(f"Nanoarrow version: {db.execute('SELECT nanoarrow_version()').fetchone()[0]}")
    db.execute(
        f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_arrow('{data_file_path.as_posix()}')"
    )
elif ext == ".json":
    db.execute(
        f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_json('{data_file_path.as_posix()}')"
    )
else:
    print(f"Unsupported file extension: {ext}", file=sys.stderr)
    sys.exit(1)


print(f"# Loaded '{table_name}' from {data_file_path}", file=sys.stderr)
# result = db.execute(f"SELECT id,text FROM {table_name} WHERE id = '281000' LIMIT 5").fetchall()
# columns = [desc[0] for desc in db.description]
# print(f"{[dict(zip(columns, row)) for row in result]}")

# Define the 'query' tool
@mcp.tool()
def query(sql: str) -> list[dict]:
    """
    Execute a SQL query against the loaded data.
    """
    try:
        print(f"Execute SQL: {sql}", file=sys.stderr)
        result = db.execute(sql).fetchall()
        columns = [desc[0] for desc in db.description]
        return [dict(zip(columns, row)) for row in result]
    except Exception as e:
        return [{"error": str(e)}]

# Run the MCP server using stdio transport
if __name__ == "__main__":
    mcp.run(transport='stdio')


