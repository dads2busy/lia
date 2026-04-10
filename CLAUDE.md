# LIA (Local Intelligence Assistant) - Development Guide

CLI-based local intelligence assistant for material research and supply chain analysis using multi-agent workflows and MCP servers.

## Quick Start

```bash
# Install
conda create -n lia python=3.11.11
conda activate lia
pip install -e .

# Run chat with context manager (interactive conversation)
lia lia

# Run with specific agent (e.g., supply chain focus)
lia lia -a supply_chain_agent

# Run Automoteam (dynamic multi-agent swarm)
lia ateam

# Run Reasoner (fixed left-brain/right-brain team)
lia reasoner

# Generate material network (bottom-up, requires HS code MCP server running)
lia bottomup generate-materials -h  # See research_cli subcommands
```

## Core Commands

### Chat Modes
- `lia lia` - Context manager agent (default: orchestrates analysis around defined objectives/constraints)
- `lia lia -a <agent>` - Use specific agent (context_manager_agent, supply_chain_agent, etc.)
- `lia ateam` - Automoteam: dynamically generates 2-5 expert agents for objective
- `lia ateam -r` - Automoteam with verbose inter-agent communication
- `lia reasoner` - Reasoner: fixed left-brain (low temp) / right-brain (high temp) discussion
- `lia reasoner -r` - Reasoner with verbose reasoning trace

### Material & Supply Chain
- `lia search <query>` - LLM-assisted web search
- `lia identify_raw_materials <material>` - Find raw materials & HS codes for a component
- `lia bottomup generate-materials` - Bottom-up material network generation (requires MCP server)
- `lia stdn-export` - Supply chain analysis and network export

### Configuration
- Default LLM: `llama3.3` at `http://localhost:11434/v1`
- Override with: `--model <name>`, `--llm-api-url <url>`, `--llm-api-key <key>`
- User config: `~/.lia/config.json` (loaded automatically for defaults)

## Architecture

### Directory Structure
```
src/lia/
├── cli.py                          # Main CLI entry point (typer app)
├── analysis_context.py             # Analysis state (objective, questions, constraints)
├── agent/                          # Chat agents (pydantic-ai based)
│   ├── context_manager_agent/      # Orchestrates analysis context (main agent)
│   ├── supply_chain_agent/         # Supply chain focused
│   ├── network_analysis_agent/     # Network analysis
│   ├── component_analysis_agent/   # Component decomposition
│   ├── classify_components_agent/  # Classification
│   ├── message_routing_agent/      # Message routing
│   ├── python_developer_agent/     # Python execution
│   └── trade_supply_agent/         # Trade data analysis
├── research/                       # Bottom-up material research pipeline
│   ├── config.py                   # Research config (material, products, references)
│   ├── research_pipeline.py        # Orchestrates agent workflow via pydantic-graph
│   ├── research_cli.py             # CLI for research pipeline
│   ├── pipeline_state.py           # Stateful research (materials, processes, state)
│   ├── research_tasks.py           # Pydantic-graph tasks (nodes)
│   ├── agents/                     # Specialized research agents
│   │   ├── researcher_agent.py     # Preliminary research
│   │   ├── material_finder_agent.py
│   │   ├── material_manufacturing_agent.py
│   │   ├── reference_reviewer_agent.py
│   │   ├── url_scorer_agent.py
│   │   └── process_merging_agent.py
│   ├── rare_earth_metals/          # Example research config
│   └── research_config.json        # Materials to research
├── tools/                          # MCP servers & utilities
│   ├── mcp-server-hscode-faiss-rollupmd.py    # HS code vector search (FAISS)
│   ├── mcp-server-hscode-sql.py               # HS code SQL lookup
│   ├── mcp-server-hscode-vector-rollupmd.py   # HS code vector (HNSWLIB)
│   ├── mcp-preliminary-research-vector.py     # Preliminary research vectors
│   ├── mcp-server-score-url.py                # URL quality scoring
│   ├── python_execution_tool.py               # Sandboxed Python execution
│   ├── hscodes.json                           # HS code reference (1.7MB)
│   └── prelim-search.py                       # Preliminary search utility
├── util/
│   ├── mcp_server_manager.py       # AsyncContext manager for MCP servers
│   ├── mcp_supervisord.py          # Supervisor daemon management
│   ├── launch_external_mcp_servers.py
│   ├── fetch_reference_content.py  # Web content fetching
│   └── url_to_markdown.py
├── system_prompts/                 # Agent system prompts
│   ├── preliminary_research_agent_prompt.py
│   ├── network_agent_system_prompt.py
│   ├── reference_reviewer_system_prompt.py
│   ├── reviewer_agent_system_prompt.py
│   └── generalist_prompts.py       # Unified generalist agent prompts
├── stdn_export/                    # Supply chain data export
│   ├── cli.py
│   ├── models.py
│   └── export.py
└── identify_raw_materials.py       # Raw material identification workflow

tests/
├── test_cli.py
└── test_stdn_export.py

data/
├── usgs_commodity_buckets.buckets.json  # USGS mineral buckets
└── test_single_bucket.buckets.json
```

### Chat Modes & Agents

**Context Manager Agent** (default `lia lia`)
- Manages an `AnalysisContext` (objective, questions, constraints)
- Tools: get/set/update/delete context elements
- Flow: Retrieves context → answers questions → modifies context
- System prompt emphasizes showing current state before changes

**Automoteam** (`lia ateam`)
- Dynamically generates 2-5 expert personas based on objective
- Leader orchestrates discussion between experts
- Each expert gets its own agent with specialized system prompt
- Uses `create_team` tool to instantiate agents on-the-fly

**Reasoner** (`lia reasoner`)
- Fixed left-brain (analytical, low temp=0.3) / right-brain (creative, high temp=1.5) agents
- Leader mediates discussion
- Designed for exploring problems from multiple angles

**Supply Chain Agent** (`lia lia -a supply_chain_agent`)
- Focused on supply chain analysis, trade data, material flows
- Can be combined with other modes

### How MCP Servers Work

MCP (Model Context Protocol) servers provide tools to agents:

1. **Server Definition**: Each MCP server is a standalone Python script (e.g., `mcp-server-hscode-faiss-rollupmd.py`)
   - Uses `FastMCP` framework to expose tools via stdio
   - Tools defined with Pydantic models for input/output

2. **Server Configuration**: Defined in agent/research code as `MCPServerStdio` or `MCPServerHTTP`:
   ```python
   MCPServerStdio('uvx', args=["duckduckgo-mcp-server"])  # Via uvx
   MCPServerHTTP(url="http://127.0.0.1:8000/mcp/")        # HTTP endpoint
   ```

3. **Agent Integration**: `pydantic_ai.mcp` automatically discovers and registers tools:
   ```python
   async with agent.run_mcp_servers():
       result = await agent.run(...)
   ```

4. **Lifecycle Management**: `MCPServerManager` in `util/mcp_server_manager.py` handles:
   - Async entry/exit of MCP contexts
   - Error handling on startup

**Available MCP Servers**:
- **HS Code Search** (FAISS or HNSW): Vector semantic search over Harmonized System codes
- **HS Code SQL**: Direct database lookup
- **DuckDuckGo**: Web search
- **Wikipedia**: Encyclopedic knowledge
- **ArXiv**: Academic papers (in code but not fully deployed)

### Network Generation (Bottom-Up Research Pipeline)

**Flow**: Material → Preliminary Research → Agent-Driven Discovery → Network Output

1. **Research Config**: `research_config.json` specifies:
   ```json
   {
     "material": "boron",
     "materials": [],
     "references": [],
     "products": []
   }
   ```

2. **Pipeline State**: `ResearchPipelineState` tracks:
   - `materials`: Dict[HS_code] → `ResearchMaterial` (name, aliases, uses, processes)
   - `processes`: Dict[process_id] → `MaterialProcess` (description, precursors, products, references, scale)
   - `options`: `ResearchPipelineOptions` (model, urls, thresholds, feature flags)

3. **Pydantic-Graph Workflow** (`research_tasks.py` nodes):
   - `generate_research_material` - Preliminary web search → material info
   - `generate_material_processes` - Find manufacturing/mining processes
   - `review_material_processes` - Score references & processes
   - `expand_process_materials` - Recursively find precursor materials
   - `expand_product_family_materials` - Find related products
   - `purge_processes` - Remove low-quality processes (scale < threshold)
   - `merge_duplicate_processes` - Consolidate duplicates
   - `review_materials` - Final material validation

4. **Agent Roles** (specialized or generalist):
   - **Researcher Agent**: Conducts preliminary web searches
   - **Material Finder Agent**: Identifies raw materials in processes
   - **Material Manufacturing Agent**: Describes production methods
   - **Reference Reviewer Agent**: Scores reference quality
   - **URL Scorer Agent**: Assesses source credibility
   - **Process Merging Agent**: Deduplicates processes
   - **Material Classification Agent**: Categorizes material types

5. **Output**: JSON network file with materials, processes, relationships

**Starting the Pipeline**:
```bash
cd src/lia
# Start HS code MCP server (expects H6_rollup.md file)
python tools/mcp-server-hscode-faiss-rollupmd.py --file /path/to/H6_rollup.md

# In another terminal, run pipeline
lia bottomup generate-materials -m gpt-4o-mini --llm-api-key $OAIKEY "boron"
```

## Configuration

### Files
- `pyproject.toml`: Dependencies (pydantic-ai 0.3.4, mcp 1.9.4+, fastmcp 2.9.2+)
- `src/lia/research/config.py`: `ResearchConfig` model for material research
- `~/.lia/config.json`: User defaults (model, api_url, api_key, goog custom search settings)

### Environment Variables
- `LIA_RESEARCH_FOLDER`: Override default research folder
- Model/API selection (CLI flags override these):
  - `--model`: Model name (default: llama3.3)
  - `--llm-api-url`: LLM endpoint (default: http://localhost:11434/v1)
  - `--llm-api-key`: API key if needed
  - `--google-api-key`: Google Custom Search API key
  - `--google-cse-id`: Custom search engine ID

### ResearchPipelineOptions (research_cli.py)
Key toggles and thresholds:
- `generate_materials`, `regenerate_materials`: Control material discovery
- `generate_processess`: Enable process research
- `process_score_threshold`: Min reference quality score (default 0.5)
- `minimum_process_references`: Min references per process (default 2)
- `maximum_reference_reviews`: Passes over references (default 2)
- `purge_scale_threshold`: Min process scale before removal (default 0.4)
- `agent_architecture`: "multi" (specialized) or "generalist" (single prompt)
- `save_state`: Persist state after each pipeline step
- `start`: Jump to specific task in pipeline

## Data Flow

### Input Data
- **Materials**: User-provided via CLI or research_config.json
- **Web Content**: Fetched via MCP servers (DuckDuckGo, Wikipedia, web fetch)
- **HS Codes**: Semantic search over markdown/JSON reference (H6_rollup.md or hscodes.json)
- **References**: URLs scored and cached in `reference_cache_folder`

### Output Data
- **Network JSON**: Material graph with processes, precursors, products
  ```json
  {
    "materials": {
      "HS_CODE": {
        "name": "...",
        "mined": true/false,
        "aliases": [],
        "primary_uses": [],
        "hs_description": "..."
      }
    },
    "processes": {
      "PROCESS_ID": {
        "description": "...",
        "scale": 0.0-1.0,
        "precursors": ["HS_CODE" or "material string"],
        "products": ["HS_CODE" or "material string"],
        "references": ["URL" or {...score, quality...}]
      }
    }
  }
  ```
- **State Files**: Saved to research folder after each step
  - `pipeline_state.json`: Current materials, processes, pass counts
  - Backups: `pipeline_state_backup_*.json`

### Embeddings & Vector Stores
- **Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- **HS Code Index**: FAISS or HNSW over HS code descriptions
- **Cache**: `.cache/` folder (embeddings.npy, faiss index)

## Key Patterns

### Starting a Chat Session
```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
model = OpenAIModel("gpt-4o-mini", base_url="...", api_key="...")
agent = Agent(model, system_prompt="...", tools=[...])
result = await agent.run("user message", deps=deps)
```

### Generating a Material Network
1. Create `research_config.json` in target folder with material list
2. Start HS code MCP server: `python tools/mcp-server-hscode-faiss-rollupmd.py`
3. Run: `lia bottomup generate-materials --research-folder /path/to/research-dir --start generate_materials`
4. Monitor `pipeline_state.json` for progress
5. Output: `{material}_network.json`

### Discovering MCP Tools
Agents declare MCP servers in their initialization. At agent startup:
- `pydantic_ai.mcp.run_mcp_servers()` spawns servers
- Tools are auto-discovered from server definitions
- Agent can call tools as if they were local functions

Example tool use in agent code:
```python
result = await agent.run(
    "Find HS code for copper ore",
    deps=deps,
    # MCP servers auto-attached via context manager
)
```

### Sandbox Python Execution
`python_execution_tool.py` executes arbitrary Python in a restricted environment:
- Takes script as string
- Runs in subprocess or restricted context
- Captures stdout/stderr
- Returns results to agent

Used by Python Developer Agent for exploratory analysis.

### Important Gotchas
1. **HS Code MCP Server**: Must be running externally before material network generation
   - Expects file path to `H6_rollup.md` or uses `hscodes.json` fallback
   - Takes 2-3 minutes to load on first run (building FAISS index)

2. **Research State Persistence**: Pipeline saves state to disk after each node
   - Restart from checkpoint with `--start <task_name>`
   - Stale state can cause issues; manually edit or delete `pipeline_state.json` to reset

3. **Agent Architecture**: Two modes affect all specialized agents:
   - `"multi"`: Each agent role gets unique system prompt (more capable but more tokens)
   - `"generalist"`: All roles use same prompt (cheaper, less specialized)

4. **Reference Review Cycles**: `maximum_reference_reviews` limits URL fetching
   - Lower for speed, higher for quality
   - References are cached; repeated reviews use cache

5. **Temperature & Left/Right Brain**: Reasoner uses 0.3 vs 1.5 temperatures
   - Left-brain (analytical) vs right-brain (creative)
   - Useful for exploring solutions from multiple perspectives

## Testing

### Test Framework
- `pytest` (installed via pyproject.toml)
- Located in `tests/` directory

### Test Files
- `tests/test_cli.py`: CLI command tests (incomplete; loads context from JSON)
- `tests/test_stdn_export.py`: Supply chain export functionality

### Running Tests
```bash
pytest tests/ -v
pytest tests/test_cli.py::test_load_context_valid
```

### Test Structure
Tests use temporary files and JSON fixtures. Example pattern:
```python
def test_load_context_valid():
    data = {"name": "TestUser", "verbose": True}
    with tempfile.NamedTemporaryFile("w+", delete=False) as tmp:
        json.dump(data, tmp)
    context = load_context(tmp.name)
    assert isinstance(context, ContextData)
```

## Supply Chain Knowledge Base

For broader context on supply chain intelligence, materials, technologies, countries, and policies:
- See wiki: `~/git/personal-ai-wiki/index.md`
- Read relevant wiki pages based on current task
- Wiki maintained following schema in `~/git/personal-ai-wiki/CLAUDE.md`
