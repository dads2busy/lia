# STDN Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `lia stdn-export` CLI command that generates HS code material buckets and queries Comtrade trade flow data to produce a CSV for the STDN Explorer.

**Architecture:** New CLI command registered in `cli.py`, backed by three modules: bucket generation (wraps existing Material Classification Agent), Comtrade querying (adapts existing `map_exports_to_material.py` patterns), and MCP auto-launch (wraps existing `mcp_supervisord.py`). All modules live under `src/lia/stdn_export/`.

**Tech Stack:** Python 3.11, typer (CLI), pydantic_ai (agents), pyarrow (Arrow files), existing FAISS MCP server

**Spec:** `docs/superpowers/specs/2026-03-27-stdn-export-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/lia/stdn_export/__init__.py` | Package init, Pydantic models for bucket mapping and CSV output |
| `src/lia/stdn_export/cli.py` | Typer CLI command definition for `stdn-export` |
| `src/lia/stdn_export/bucket_generator.py` | Material → HS code bucket mapping using Material Classification Agent |
| `src/lia/stdn_export/comtrade_query.py` | Arrow file loading, filtering, aggregation, CSV output |
| `src/lia/stdn_export/mcp_launcher.py` | Auto-launch/shutdown MCP servers as subprocesses |
| `src/lia/cli.py` | Modify: register stdn-export subcommand |
| `src/lia/tools/mcp-server-hscode-faiss-rollupmd.py` | Modify: update default H6_rollup.md path |
| `tests/test_stdn_export.py` | Unit tests for comtrade_query and bucket cache logic |

---

### Task 1: Data Models and Package Setup

**Files:**
- Create: `src/lia/stdn_export/__init__.py`

- [ ] **Step 1: Create the package with Pydantic models**

```python
# src/lia/stdn_export/__init__.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class HSCodeEntry(BaseModel):
    """A single HS-6 code in a material bucket."""
    code: str
    description: str
    quality: str = Field(description="'clean' or 'shared'")
    relevance: str = Field(description="Why this HS code relates to the material")


class MaterialBucket(BaseModel):
    """All HS codes related to a single material."""
    hs_codes: List[HSCodeEntry]
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    model: str = "llama3.3"


class TradeFlowRow(BaseModel):
    """One row of the output CSV."""
    material: str
    hs_bucket: str
    hs_bucket_quality: str
    year: int
    exporter: str
    exporter_iso3: str
    import_value_usd: float
    import_share_pct: float
    exporter_rank: int
```

- [ ] **Step 2: Verify import works**

Run: `cd ~/git/lia && .venv/bin/python -c "from lia.stdn_export import HSCodeEntry, MaterialBucket, TradeFlowRow; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/lia/stdn_export/__init__.py
git commit -m "feat(stdn-export): add data models for bucket mapping and trade flow output"
```

---

### Task 2: MCP Auto-Launcher

**Files:**
- Create: `src/lia/stdn_export/mcp_launcher.py`

- [ ] **Step 1: Write MCP launcher module**

This module starts the FAISS MCP server as a subprocess if it's not already running, and provides a context manager for cleanup.

```python
# src/lia/stdn_export/mcp_launcher.py
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def find_mcp_server_script() -> Path:
    """Locate the FAISS MCP server script relative to this package."""
    pkg_dir = Path(__file__).resolve().parent.parent
    script = pkg_dir / "tools" / "mcp-server-hscode-faiss-rollupmd.py"
    if not script.exists():
        raise FileNotFoundError(f"MCP server script not found at {script}")
    return script


@contextmanager
def mcp_server_context(
    hs_rollup_file: str,
    port: int = 8000,
    python: Optional[str] = None,
):
    """Context manager that ensures the FAISS MCP server is running.

    If already running on the port, reuses it (launched_here=False).
    Otherwise, starts it as a subprocess and kills on exit.
    """
    if is_port_open(port):
        print(f"MCP server already running on port {port}, reusing.")
        yield
        return

    script = find_mcp_server_script()
    python = python or sys.executable
    cmd = [python, str(script), "--file", hs_rollup_file, "--port", str(port)]

    print(f"Starting MCP server: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for server to be ready (up to 30 seconds)
    for i in range(60):
        if is_port_open(port):
            print(f"MCP server ready on port {port}")
            break
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"MCP server exited with code {proc.returncode}: {stderr}")
        time.sleep(0.5)
    else:
        proc.terminate()
        raise TimeoutError(f"MCP server did not start within 30 seconds on port {port}")

    try:
        yield
    finally:
        print(f"Shutting down MCP server (pid {proc.pid})")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
```

- [ ] **Step 2: Verify module imports**

Run: `cd ~/git/lia && .venv/bin/python -c "from lia.stdn_export.mcp_launcher import mcp_server_context, is_port_open; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/lia/stdn_export/mcp_launcher.py
git commit -m "feat(stdn-export): add MCP server auto-launcher with context manager"
```

---

### Task 3: Bucket Generator

**Files:**
- Create: `src/lia/stdn_export/bucket_generator.py`

- [ ] **Step 1: Write bucket generator module**

This module wraps the Material Classification Agent to produce HS code buckets with quality flags, and handles caching.

```python
# src/lia/stdn_export/bucket_generator.py
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from lia.research import ResearchMaterial, ResearchPipelineOptions
from lia.research.agents.material_classificaton_agent import (
    get_material_classification_agent,
)
from lia.stdn_export import HSCodeEntry, MaterialBucket


def load_h6_rollup(path: str) -> dict[str, str]:
    """Load H6_rollup.md into a dict of hs_code -> description."""
    rollup = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            code, desc = line.split(":", 1)
            rollup[code.strip()] = desc.strip()
    return rollup


def load_cached_bucket(cache_dir: Path, material: str) -> Optional[MaterialBucket]:
    """Load a cached bucket mapping if it exists."""
    cache_file = cache_dir / f"{material.lower().replace(' ', '_')}.json"
    if cache_file.exists():
        with cache_file.open() as f:
            return MaterialBucket.model_validate_json(f.read())
    return None


def save_cached_bucket(cache_dir: Path, material: str, bucket: MaterialBucket):
    """Save a bucket mapping to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{material.lower().replace(' ', '_')}.json"
    cache_file.write_text(bucket.model_dump_json(indent=2))


async def generate_bucket(
    material: str,
    options: ResearchPipelineOptions,
    h6_rollup: dict[str, str],
    cache_dir: Path,
    use_cache: bool = True,
) -> MaterialBucket:
    """Generate an HS code bucket for a material.

    1. Check cache
    2. Run Material Classification Agent to discover all HS-6 codes
    3. Classify each code as clean/shared using H6_rollup descriptions
    4. Cache and return
    """
    if use_cache:
        cached = load_cached_bucket(cache_dir, material)
        if cached is not None:
            print(f"  Using cached bucket for {material} ({len(cached.hs_codes)} HS codes)")
            return cached

    print(f"  Generating bucket for {material} via Material Classification Agent...")
    agent = await get_material_classification_agent(options)

    # No async context manager needed — MCPServerStreamableHTTP connects per call,
    # and the MCP server subprocess is managed by mcp_server_context externally.
    result = await agent.run(
        f"Identify all HS-6 codes for the material: {material}. "
        f"Include raw/mined forms, refined forms, intermediates, and compounds. "
        f"For each HS code, also determine if the code is specific to {material} "
        f"(quality: 'clean') or if it covers multiple distinct materials "
        f"(quality: 'shared'). Use the HS code search tool to find candidates.",
    )

    # Parse agent result into HSCodeEntry list
    # The agent returns list[ResearchMaterial], each with one hs_code
    # pydantic_ai RunResult exposes structured output via .output (not .data)
    entries = []
    if hasattr(result, "output") and isinstance(result.output, list):
        for mat in result.output:
            if isinstance(mat, ResearchMaterial) and mat.hs_code:
                desc = h6_rollup.get(mat.hs_code, mat.hs_description or "")
                # Determine quality: check if H6 description mentions other materials
                quality = classify_hs_quality(material, mat, desc)
                entries.append(HSCodeEntry(
                    code=mat.hs_code,
                    description=desc[:200] if desc else "",
                    quality=quality,
                    relevance=f"{mat.name} ({'mined' if mat.mined else 'refined/intermediate'})",
                ))

    bucket = MaterialBucket(
        hs_codes=entries,
        generated_at=datetime.now().isoformat(),
        model=options.model_name,
    )

    save_cached_bucket(cache_dir, material, bucket)
    print(f"  Bucket for {material}: {len(entries)} HS codes ({sum(1 for e in entries if e.quality == 'clean')} clean, {sum(1 for e in entries if e.quality == 'shared')} shared)")
    return bucket


def classify_hs_quality(material: str, mat: ResearchMaterial, h6_desc: str) -> str:
    """Determine if an HS code is 'clean' (specific to this material) or 'shared'.

    Heuristic: check if the H6 description contains semicolons separating
    multiple distinct material names. If the description only references
    the target material (or its aliases), it's clean.
    """
    if not h6_desc:
        return "shared"  # Can't verify, assume shared

    # Normalize for comparison
    material_lower = material.lower()
    desc_lower = h6_desc.lower()
    aliases = [a.lower() for a in (mat.aliases or [])]
    all_names = [material_lower] + aliases + [mat.name.lower()]

    # If description is short and clearly about this material, it's clean
    # Check for common "multi-material" patterns
    multi_material_indicators = [
        " and ", " or ", ";", "other than", "n.e.c.", "not elsewhere",
        "whether or not", "including"
    ]

    # If material name appears and no multi-material indicators, likely clean
    material_mentioned = any(name in desc_lower for name in all_names)
    has_multi_indicator = any(ind in desc_lower for ind in multi_material_indicators)

    if material_mentioned and not has_multi_indicator:
        return "clean"

    return "shared"
```

Note: The `classify_hs_quality` function uses a heuristic as a starting point. The agent prompt also asks the LLM to classify quality during bucket generation. The heuristic serves as a fallback — if the agent provides quality classification directly, use that instead. The implementer should adapt the agent result parsing based on the actual response format from `get_material_classification_agent`.

- [ ] **Step 2: Verify module imports**

Run: `cd ~/git/lia && .venv/bin/python -c "from lia.stdn_export.bucket_generator import load_h6_rollup, load_cached_bucket; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Test H6 rollup loading**

Run: `cd ~/git/lia && .venv/bin/python -c "
from lia.stdn_export.bucket_generator import load_h6_rollup
rollup = load_h6_rollup('H6_rollup.md')
print(f'Loaded {len(rollup)} HS codes')
print(f'260500: {rollup.get(\"260500\", \"NOT FOUND\")}')
print(f'280429: {rollup.get(\"280429\", \"NOT FOUND\")}')
"`
Expected: ~5771 HS codes loaded, with descriptions for cobalt and rare gases

- [ ] **Step 4: Commit**

```bash
git add src/lia/stdn_export/bucket_generator.py
git commit -m "feat(stdn-export): add bucket generator with Material Classification Agent and caching"
```

---

### Task 4: Comtrade Query Module

**Files:**
- Create: `src/lia/stdn_export/comtrade_query.py`
- Test: `tests/test_stdn_export.py`

- [ ] **Step 1: Write the test for country code loading**

```python
# tests/test_stdn_export.py
import pytest
import pyarrow as pa
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "UN_Comtrade"


def test_load_partner_areas():
    """partnerAreas.arrow loads and contains US (code 840)."""
    from lia.stdn_export.comtrade_query import load_partner_map
    partner_map = load_partner_map(DATA_DIR / "partnerAreas.arrow")
    assert 840 in partner_map
    assert partner_map[840]["name"] == "United States of America"
    assert partner_map[840]["iso3"] == "USA"
    assert len(partner_map) > 200
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/git/lia && .venv/bin/python -m pytest tests/test_stdn_export.py::test_load_partner_areas -v`
Expected: FAIL — `ImportError: cannot import name 'load_partner_map'`

- [ ] **Step 3: Write the comtrade_query module**

```python
# src/lia/stdn_export/comtrade_query.py
import csv
from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.compute as pc

from lia.stdn_export import MaterialBucket, TradeFlowRow


# --- Country code resolution ---

def load_partner_map(partner_file: Path) -> dict[int, dict]:
    """Load partnerAreas.arrow into a dict of code -> {name, iso3}.

    Note: partnerAreas uses PartnerCode (capital P/C), not partnerCode.
    Excludes group entries (isGroup=True).
    """
    with pa.memory_map(str(partner_file), "r") as source:
        reader = pa.ipc.RecordBatchFileReader(source)
        table = reader.read_all()

    result = {}
    for row in table.to_pylist():
        if row.get("isGroup", False):
            continue
        code = row["PartnerCode"]
        result[code] = {
            "name": row["PartnerDesc"],
            "iso3": row.get("PartnerCodeIsoAlpha3", ""),
        }
    return result


# --- Arrow file loading and filtering ---

def load_arrow_table(path: Path) -> pa.Table:
    """Load an Arrow IPC file into memory."""
    with pa.memory_map(str(path), "r") as source:
        reader = pa.ipc.RecordBatchFileReader(source)
        return reader.read_all()


def query_us_imports(
    comtrade_dir: Path,
    years: list[int],
    hs_codes: set[str],
    reporter_code: int = 840,
) -> list[dict]:
    """Query Arrow files for US imports of specific HS codes.

    Returns list of dicts with keys: partnerCode, cmdCode, refYear, value
    """
    all_rows = []
    for year in years:
        arrow_file = comtrade_dir / f"aggregate_intercountry_HS_flow_values_{year}.arrow"
        if not arrow_file.exists():
            print(f"  Warning: No data file for year {year}, skipping.")
            continue

        table = load_arrow_table(arrow_file)

        # Filter: reporter == US AND cmdCode in our HS codes
        reporter_mask = pc.equal(table["reporterCode"], reporter_code)
        filtered = table.filter(reporter_mask)

        # Filter by HS codes (cmdCode is string)
        hs_mask = pc.is_in(filtered["cmdCode"], pa.array(list(hs_codes), type=pa.string()))
        filtered = filtered.filter(hs_mask)

        if filtered.num_rows > 0:
            all_rows.extend(filtered.to_pylist())
            print(f"  Year {year}: {filtered.num_rows} matching trade records")
        else:
            print(f"  Year {year}: no matching records")

    return all_rows


# --- Aggregation ---

def aggregate_trade_data(
    raw_rows: list[dict],
    buckets: dict[str, MaterialBucket],
    partner_map: dict[int, dict],
) -> list[TradeFlowRow]:
    """Aggregate raw trade rows into per-material, per-country, per-year summaries.

    For each material bucket, sum USD values across all HS codes in the bucket,
    grouped by exporter country and year. Compute import share and rank.
    """
    # Build reverse map: hs_code -> list of material names
    # Note: shared HS codes may map to multiple materials. Trade value is
    # attributed to ALL materials that claim the code (duplicated, not split),
    # since we cannot disaggregate shared codes.
    hs_to_materials: dict[str, list[str]] = {}
    for material, bucket in buckets.items():
        for entry in bucket.hs_codes:
            hs_to_materials.setdefault(entry.code, []).append(material)

    # Group: (material, partnerCode, year) -> total_value
    groups: dict[tuple, float] = {}
    for row in raw_rows:
        materials = hs_to_materials.get(row["cmdCode"], [])
        for material in materials:
            key = (material, row["partnerCode"], row["refYear"])
            groups[key] = groups.get(key, 0.0) + (row["value"] or 0.0)

    # Compute totals per (material, year) for share calculation
    material_year_totals: dict[tuple, float] = {}
    for (material, _, year), value in groups.items():
        k = (material, year)
        material_year_totals[k] = material_year_totals.get(k, 0.0) + value

    # Build output rows
    output = []
    for (material, partner_code, year), value in groups.items():
        total = material_year_totals.get((material, year), 1.0)
        share = (value / total * 100) if total > 0 else 0.0

        partner = partner_map.get(partner_code, {"name": f"Unknown ({partner_code})", "iso3": ""})
        bucket = buckets[material]
        hs_bucket_str = "|".join(e.code for e in bucket.hs_codes)
        worst_quality = "shared" if any(e.quality == "shared" for e in bucket.hs_codes) else "clean"

        output.append(TradeFlowRow(
            material=material,
            hs_bucket=hs_bucket_str,
            hs_bucket_quality=worst_quality,
            year=year,
            exporter=partner["name"],
            exporter_iso3=partner["iso3"],
            import_value_usd=round(value, 2),
            import_share_pct=round(share, 2),
            exporter_rank=0,  # Filled in next step
        ))

    # Compute ranks within each (material, year) group
    from itertools import groupby
    output.sort(key=lambda r: (r.material, r.year, -r.import_share_pct))
    ranked = []
    for _, group in groupby(output, key=lambda r: (r.material, r.year)):
        for rank, row in enumerate(group, 1):
            row.exporter_rank = rank
            ranked.append(row)

    return ranked


# --- CSV output ---

def write_csv(rows: list[TradeFlowRow], output_path: Path):
    """Write trade flow rows to CSV."""
    if not rows:
        print("  Warning: No trade data to write.")
        return

    fieldnames = [
        "material", "hs_bucket", "hs_bucket_quality", "year",
        "exporter", "exporter_iso3", "import_value_usd",
        "import_share_pct", "exporter_rank",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump())

    print(f"  Wrote {len(rows)} rows to {output_path}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/git/lia && .venv/bin/python -m pytest tests/test_stdn_export.py::test_load_partner_areas -v`
Expected: PASS

- [ ] **Step 5: Write test for US imports query**

Add to `tests/test_stdn_export.py`:

```python
def test_query_us_imports_with_known_hs_code():
    """Querying a common HS code returns non-empty results for US imports."""
    from lia.stdn_export.comtrade_query import query_us_imports
    # HS 260500 = Cobalt ores, should have US import records
    rows = query_us_imports(DATA_DIR, [2023], {"260500"})
    assert len(rows) > 0
    assert all(r["reporterCode"] == 840 for r in rows)
    assert all(r["cmdCode"] == "260500" for r in rows)
```

- [ ] **Step 6: Run the test**

Run: `cd ~/git/lia && .venv/bin/python -m pytest tests/test_stdn_export.py::test_query_us_imports_with_known_hs_code -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/lia/stdn_export/comtrade_query.py tests/test_stdn_export.py
git commit -m "feat(stdn-export): add Comtrade query module with Arrow loading, filtering, and aggregation"
```

---

### Task 5: CLI Command

**Files:**
- Create: `src/lia/stdn_export/cli.py`
- Modify: `src/lia/cli.py`

- [ ] **Step 1: Write the CLI command module**

```python
# src/lia/stdn_export/cli.py
import asyncio
import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from lia.stdn_export import MaterialBucket

app = typer.Typer(help="Export STDN trade flow data from Comtrade for the STDN Explorer")

# Repo root for resolving relative defaults
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Load user config for defaults (same pattern as cli.py)
DEFAULT_LIA_CONFIG = Path.home() / ".lia" / "config.json"
def _load_user_config() -> dict:
    if DEFAULT_LIA_CONFIG.exists():
        with DEFAULT_LIA_CONFIG.open() as f:
            return json.load(f)
    return {}
UserConfig = _load_user_config()


def parse_materials(materials_arg: str) -> list[str]:
    """Parse materials from file path or comma-separated string."""
    path = Path(materials_arg)
    if path.exists() and path.is_file():
        return [line.strip() for line in path.read_text().splitlines() if line.strip()]
    return [m.strip() for m in materials_arg.split(",") if m.strip()]


def parse_years(years_str: str) -> list[int]:
    """Parse year range string like '2017-2025' into list of ints."""
    if "-" in years_str:
        start, end = years_str.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(y.strip()) for y in years_str.split(",")]


@app.command()
def export(
    materials: Annotated[str, typer.Option("--materials", "-m", help="File path (one per line) or comma-separated material names")] = ...,
    comtrade_dir: Annotated[str, typer.Option("--comtrade-dir", help="Directory containing Arrow files")] = UserConfig.get("comtrade_dir", str(REPO_ROOT / "data" / "UN_Comtrade")),
    years: Annotated[str, typer.Option("--years", help="Year range (e.g., 2017-2025)")] = "2017-2025",
    perspective: Annotated[str, typer.Option("--perspective", help="Importer country (only 'US' supported)")] = "US",
    output: Annotated[str, typer.Option("--output", "-o", help="Output CSV path")] = "stdn_trade_data.csv",
    cache_dir: Annotated[str, typer.Option("--cache-dir", help="Bucket mapping cache directory")] = UserConfig.get("cache_dir", "~/.lia/stdn-cache"),
    hs_rollup: Annotated[str, typer.Option("--hs-rollup", help="Path to H6_rollup.md")] = UserConfig.get("hs_rollup_file", str(REPO_ROOT / "H6_rollup.md")),
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Force regeneration of bucket mappings")] = False,
    no_mcp_auto: Annotated[bool, typer.Option("--no-mcp-auto", help="Don't auto-launch MCP servers")] = False,
    model: Annotated[str, typer.Option("--model", help="LLM model name")] = "llama3.3",
    llm_api_url: Annotated[Optional[str], typer.Option("--llm-api-url", help="LLM API URL")] = "http://localhost:11434/v1",
    llm_api_key: Annotated[Optional[str], typer.Option("--llm-api-key", help="LLM API key")] = None,
):
    """Export STDN trade flow data from Comtrade for the STDN Explorer."""
    if perspective.upper() != "US":
        typer.echo(f"Error: Only 'US' perspective is supported. Got: '{perspective}'", err=True)
        raise typer.Exit(1)

    asyncio.run(_run_export(
        materials_arg=materials,
        comtrade_dir=Path(comtrade_dir),
        years=parse_years(years),
        output_path=Path(output),
        cache_dir=Path(cache_dir).expanduser(),
        hs_rollup_path=hs_rollup,
        use_cache=not no_cache,
        auto_mcp=not no_mcp_auto,
        model=model,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key or "",
    ))


async def _run_export(
    materials_arg: str,
    comtrade_dir: Path,
    years: list[int],
    output_path: Path,
    cache_dir: Path,
    hs_rollup_path: str,
    use_cache: bool,
    auto_mcp: bool,
    model: str,
    llm_api_url: str,
    llm_api_key: str,
):
    from lia.research import ResearchPipelineOptions
    from lia.stdn_export.bucket_generator import generate_bucket, load_h6_rollup
    from lia.stdn_export.comtrade_query import (
        aggregate_trade_data,
        load_partner_map,
        query_us_imports,
        write_csv,
    )
    from lia.stdn_export.mcp_launcher import mcp_server_context

    material_list = parse_materials(materials_arg)
    print(f"Materials: {material_list}")
    print(f"Years: {years[0]}-{years[-1]}")
    print(f"Output: {output_path}")

    options = ResearchPipelineOptions(
        model_name=model,
        llm_api_url=llm_api_url,
        llm_api_key=llm_api_key,
    )

    # Load H6 rollup for quality classification
    h6_rollup = load_h6_rollup(hs_rollup_path)
    print(f"Loaded {len(h6_rollup)} HS code descriptions from {hs_rollup_path}")

    # Stage 1-2: Generate buckets (with optional MCP auto-launch)
    buckets: dict[str, MaterialBucket] = {}

    # mcp_server_context is a sync context manager (subprocess management).
    # Use plain `with` — works fine inside async functions.
    if auto_mcp:
        ctx = mcp_server_context(hs_rollup_file=hs_rollup_path)
    else:
        from contextlib import nullcontext
        ctx = nullcontext()

    with ctx:
        for material in material_list:
            print(f"\n[{material}]")
            bucket = await generate_bucket(
                material=material,
                options=options,
                h6_rollup=h6_rollup,
                cache_dir=cache_dir,
                use_cache=use_cache,
            )
            buckets[material] = bucket

    # Collect all HS codes across all buckets
    all_hs_codes = set()
    for bucket in buckets.values():
        for entry in bucket.hs_codes:
            all_hs_codes.add(entry.code)
    print(f"\nTotal unique HS codes across all buckets: {len(all_hs_codes)}")

    # Stage 3-5: Query Comtrade
    print("\nQuerying Comtrade data...")
    partner_map = load_partner_map(comtrade_dir / "partnerAreas.arrow")
    raw_rows = query_us_imports(comtrade_dir, years, all_hs_codes)
    print(f"Total raw trade records: {len(raw_rows)}")

    # Stage 6-7: Aggregate and rank
    print("\nAggregating trade data...")
    trade_rows = aggregate_trade_data(raw_rows, buckets, partner_map)

    # Stage 8: Write outputs
    write_csv(trade_rows, output_path)

    # Also write the consolidated bucket mapping
    bucket_json_path = output_path.with_suffix(".buckets.json")
    bucket_dict = {name: bucket.model_dump() for name, bucket in buckets.items()}
    bucket_json_path.write_text(json.dumps(bucket_dict, indent=2))
    print(f"Bucket mapping written to {bucket_json_path}")

    print(f"\nDone! {len(trade_rows)} trade flow rows for {len(buckets)} materials.")
```

- [ ] **Step 2: Register the command in the main CLI**

In `src/lia/cli.py`, add the import and registration after the existing `research_app` registration (around line 22):

```python
from lia.stdn_export.cli import app as stdn_export_app
```

And add after `app.add_typer(research_app, name="bottomup")`:

```python
app.add_typer(stdn_export_app, name="stdn-export")
```

- [ ] **Step 3: Verify CLI help shows the new command**

Run: `cd ~/git/lia && .venv/bin/python -m lia --help`
Expected: `stdn-export` appears in the list of commands

- [ ] **Step 4: Commit**

```bash
git add src/lia/stdn_export/cli.py src/lia/cli.py
git commit -m "feat(stdn-export): add CLI command with full pipeline orchestration"
```

---

### Task 6: Fix FAISS MCP Server Default Path

**Files:**
- Modify: `src/lia/tools/mcp-server-hscode-faiss-rollupmd.py`
- Modify: `src/lia/research/research_cli.py`

- [ ] **Step 1: Update the FAISS MCP server default path**

In `src/lia/tools/mcp-server-hscode-faiss-rollupmd.py`, find the hardcoded Rivanna path default and change it to the repo-local `H6_rollup.md`. Look for the `--file` argument default and update it.

The exact line will be in the argparse/typer setup — change the default from `/sfs/gpfs/tardis/project/bi_dpi/data/UN_Comtrade/H6_rollup.md` to `H6_rollup.md` (repo-relative).

- [ ] **Step 2: Update research_cli.py default**

In `src/lia/research/research_cli.py`, line 44, change:

```python
DEFAULT_HS_ROLLUP_FILE = "/sfs/gpfs/tardis/project/bi_dpi/data/UN_Comtrade/H6_rollup.md"
```

to:

```python
DEFAULT_HS_ROLLUP_FILE = str(Path(__file__).resolve().parent.parent.parent.parent / "H6_rollup.md")
```

This resolves to the repo root's `H6_rollup.md` regardless of working directory.

- [ ] **Step 3: Commit**

```bash
git add src/lia/tools/mcp-server-hscode-faiss-rollupmd.py src/lia/research/research_cli.py
git commit -m "fix: update H6_rollup.md default paths from Rivanna to repo-local"
```

---

### Task 7: End-to-End Smoke Test

**Files:**
- Test: `tests/test_stdn_export.py` (add to existing)

- [ ] **Step 1: Write smoke test for the full pipeline (comtrade query only, no LLM)**

Add to `tests/test_stdn_export.py`:

```python
def test_full_aggregation_pipeline():
    """Test the aggregation pipeline with a manually constructed bucket."""
    from lia.stdn_export import HSCodeEntry, MaterialBucket, TradeFlowRow
    from lia.stdn_export.comtrade_query import (
        aggregate_trade_data,
        load_partner_map,
        query_us_imports,
    )

    # Create a test bucket for Cobalt (HS 260500 = cobalt ores)
    bucket = MaterialBucket(
        hs_codes=[HSCodeEntry(
            code="260500",
            description="Cobalt ores and concentrates",
            quality="clean",
            relevance="cobalt raw ore",
        )],
        model="test",
    )
    buckets = {"Cobalt": bucket}

    partner_map = load_partner_map(DATA_DIR / "partnerAreas.arrow")
    raw_rows = query_us_imports(DATA_DIR, [2023], {"260500"})

    if not raw_rows:
        pytest.skip("No Comtrade Arrow data files available")

    trade_rows = aggregate_trade_data(raw_rows, buckets, partner_map)

    assert len(trade_rows) > 0
    assert all(isinstance(r, TradeFlowRow) for r in trade_rows)
    assert all(r.material == "Cobalt" for r in trade_rows)
    assert all(r.year == 2023 for r in trade_rows)

    # Shares should sum to ~100%
    total_share = sum(r.import_share_pct for r in trade_rows)
    assert 99.0 <= total_share <= 101.0

    # Ranks should be sequential
    ranks = [r.exporter_rank for r in trade_rows]
    assert ranks == list(range(1, len(ranks) + 1))

    # Quality should be clean (single clean HS code)
    assert all(r.hs_bucket_quality == "clean" for r in trade_rows)
```

- [ ] **Step 2: Run all tests**

Run: `cd ~/git/lia && .venv/bin/python -m pytest tests/test_stdn_export.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_stdn_export.py
git commit -m "test(stdn-export): add end-to-end smoke test for aggregation pipeline"
```

---

### Task 8: Manual End-to-End Test with LLM

This task requires Ollama running locally with llama3.3.

- [ ] **Step 1: Create a test materials file**

```bash
echo "Cobalt" > /tmp/test_materials.txt
```

- [ ] **Step 2: Run the full command**

```bash
cd ~/git/lia && .venv/bin/python -m lia stdn-export export \
  --materials /tmp/test_materials.txt \
  --comtrade-dir data/UN_Comtrade \
  --years 2023-2023 \
  --output /tmp/stdn_test_output.csv
```

Expected: Command completes, produces `/tmp/stdn_test_output.csv` and `/tmp/stdn_test_output.buckets.json`

- [ ] **Step 3: Verify output**

```bash
head -5 /tmp/stdn_test_output.csv
cat /tmp/stdn_test_output.buckets.json | python3 -m json.tool | head -20
```

Expected: CSV has header row and data rows with Cobalt material. Bucket JSON shows discovered HS codes with quality flags.

- [ ] **Step 4: Final commit**

```bash
git commit -m "feat(stdn-export): complete STDN export pipeline — bucket generation and Comtrade trade flow query"
```
