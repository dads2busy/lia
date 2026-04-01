# STDN Export: Comtrade Trade Flow Data for STDN Explorer

## Problem

The STDN Explorer's disruption simulator uses USGS production share data to model supply chain risk. This captures where materials are *produced* but not how they *flow* through international trade. The Vullikanti et al. paper ("Supply Chain Disruptions in Microelectronic Inputs") demonstrates that trade flow analysis — import concentration, leverage ratios, lock-in — reveals vulnerabilities that production data alone cannot.

Integrating Comtrade bilateral trade flow data into the Explorer requires:
1. Mapping each material to all its related HS-6 codes (material buckets)
2. Querying Comtrade data for those codes from a US imports perspective
3. Producing a CSV that the Explorer can ingest

## Constraints

- **HS code granularity**: At the 6-digit level, many HS codes lump multiple materials together (e.g., HS 261590 = niobium + tantalum + vanadium). Trade data for shared codes cannot be disaggregated to individual materials.
- **Data availability**: Pre-aggregated Comtrade Arrow files contain USD value only (no quantity). Leverage ratios as defined in the paper (quantity/value asymmetry) cannot be computed exactly. Value-based import concentration is the primary metric.
- **Minimal code changes**: Lia's existing agent architecture and MCP server pattern should be reused, not refactored.

## Design

### Command Interface

```
lia stdn-export \
  --materials materials.csv \
  --comtrade-dir data/UN_Comtrade \
  --years 2017-2025 \
  --perspective US \
  --output stdn_trade_data.csv \
  --cache-dir ~/.lia/stdn-cache \
  --hs-rollup ~/git/lia/H6_rollup.md \
  --no-cache
```

| Flag | Default | Description |
|---|---|---|
| `--materials` | required | Path to a file (one material per line) or comma-separated string. If the value is an existing file path, it is read as a file; otherwise it is parsed as comma-separated material names. |
| `--comtrade-dir` | `data/UN_Comtrade` | Directory containing Arrow files |
| `--years` | `2017-2025` | Year range to query |
| `--perspective` | `US` | Importer country perspective. Only `US` (reporterCode 840) is supported in this version. Other values raise an error. |
| `--output` | `stdn_trade_data.csv` | Output CSV path |
| `--cache-dir` | `~/.lia/stdn-cache` | Directory for cached bucket mappings |
| `--hs-rollup` | `~/git/lia/H6_rollup.md` | Path to HS code descriptions file |
| `--no-cache` | false | Force regeneration of bucket mappings |

All path defaults are overridable via `~/.lia/config.json`:

```json
{
  "comtrade_dir": "data/UN_Comtrade",
  "hs_rollup_file": "~/git/lia/H6_rollup.md",
  "cache_dir": "~/.lia/stdn-cache"
}
```

### Pipeline Stages

```
1. Auto-launch MCP servers (FAISS HS code search)
2. For each material:
   a. Check bucket cache → if cached, skip to stage 3
   b. Run Material Classification Agent → discover all HS-6 codes
   c. Validate each HS code against H6_rollup.md → flag as clean or shared
   d. Cache the bucket mapping as JSON
3. Load Comtrade Arrow files for requested years
4. Filter: reporterCode == 840 (US) AND cmdCode IN bucket HS codes
5. Join partnerAreas.arrow to resolve exporter country codes to names
6. Aggregate: per material-bucket × exporter-country × year, sum value
7. Compute import_share_pct per material-bucket per year
8. Write output CSV + bucket mapping JSON
9. Shut down MCP servers
```

### Material Bucket Generation (Stage 2)

Uses Lia's existing **Material Classification Agent** (`material_classificaton_agent.py`). Given a material name (e.g., "Gallium"), the agent discovers all forms — raw ores, refined products, intermediates, compounds — each with their HS-6 code. The FAISS semantic search MCP server over H6_rollup.md assists the agent in finding candidate codes.

The agent returns a `list[ResearchMaterial]`, where each item is one material form (raw, refined, intermediate) with a single `hs_code`. All returned HS codes are collected into the bucket.

Each discovered HS code is then validated against H6_rollup.md and flagged using this algorithm:

1. Look up the HS code's full description (including sub-level rollups) in H6_rollup.md
2. Check if the description references only this material (or its known aliases): flag as **clean**
3. If the description references multiple distinct materials: flag as **shared**

This classification is performed by the LLM agent as part of the bucket generation step — the agent receives the H6_rollup.md description and determines whether the code is specific to the target material.

- **clean**: HS code maps specifically to this material (e.g., HS 260500 = "Cobalt ores and concentrates"). Trade data is directly attributable.
- **shared**: HS code includes this material plus others (e.g., HS 280429 = "Rare gases other than argon" covers Helium + Neon). Trade data is a superset and cannot be disaggregated.

### Comtrade Data Processing (Stages 3-7)

**Data source**: Pre-aggregated Arrow files at `{comtrade_dir}/aggregate_intercountry_HS_flow_values_{year}.arrow`.

**Arrow file schema**:

| Column | Type | Description |
|---|---|---|
| `partnerCode` | int64 | Exporter country code |
| `reporterCode` | int64 | Importer country code (840 = US) |
| `cmdCode` | string | HS-6 code |
| `refYear` | int64 | Trade year |
| `value` | double | Trade value in USD |

**Country code resolution**: `partnerAreas.arrow` maps country codes to names. Note the column name case mismatch: trade data files use lowercase `partnerCode`, while `partnerAreas.arrow` uses `PartnerCode` (capital P, capital C). The join must account for this. Country names come from the `PartnerDesc` column and ISO-3 codes from `PartnerCodeIsoAlpha3`.

**Processing**: For each year's Arrow file, load with `pa.ipc.open_file().read_all()` (Arrow IPC format does not support predicate pushdown, so the full file is read into memory — ~330MB per recent year, acceptable). Filter with `pyarrow.compute` to `reporterCode == 840` and `cmdCode` in the union of all bucket HS codes. Group by material bucket, exporter country, and year. Sum USD values. Compute each country's share of total US imports for that material-bucket-year. Rank exporters by `import_share_pct` descending within each material-bucket-year group to produce `exporter_rank`.

### Output Format

#### Primary: `stdn_trade_data.csv`

One row per material-bucket × exporter-country × year:

| Column | Type | Description | Example |
|---|---|---|---|
| `material` | string | Canonical material name | Gallium |
| `hs_bucket` | string | Pipe-delimited HS codes | 260600\|281219\|282590 |
| `hs_bucket_quality` | string | Worst quality flag across bucket codes | shared |
| `year` | int | Trade year | 2023 |
| `exporter` | string | Country name | China |
| `exporter_iso3` | string | ISO alpha-3 code | CHN |
| `import_value_usd` | float | Total USD value of US imports from this country for this bucket | 45200000 |
| `import_share_pct` | float | Country's share of total US imports for this bucket-year | 62.3 |
| `exporter_rank` | int | Rank by import share for this material-year | 1 |

The schema accommodates optional quantity columns (`import_quantity`, `quantity_unit`) for future use if quantity-inclusive aggregated files become available.

#### Secondary: `stdn_bucket_mapping.json`

Cached bucket definitions, reusable across runs:

```json
{
  "Gallium": {
    "hs_codes": [
      {
        "code": "260600",
        "description": "Aluminium ores and concentrates (bauxite, gallium-bearing)",
        "quality": "shared",
        "relevance": "gallium is a byproduct of bauxite processing"
      },
      {
        "code": "281219",
        "description": "Gallium trichloride and other chlorides",
        "quality": "clean",
        "relevance": "direct gallium compound"
      }
    ],
    "generated_at": "2026-03-27T14:30:00",
    "model": "llama3.3"
  }
}
```

### Caching

- **Bucket mapping cache**: One JSON file per material at `{cache_dir}/{material_name}.json`. Persists across runs. Skip LLM calls for cached materials. Override with `--no-cache` flag.
- **MCP server reuse**: On startup, check if FAISS MCP server is already running on the expected port. If so, reuse it. If not, launch as subprocess.

### MCP Server Auto-Launch

Any Lia command that requires MCP servers will auto-launch them as subprocesses:

1. On command start: check if required MCP servers are running (port probe)
2. If not running: start as background subprocess, wait for health check
3. On command exit (normal or error): terminate subprocesses via signal handler
4. CLI flag `--mcp-auto` (default: true) controls this behavior; `--no-mcp-auto` disables for manual management

This applies to the new `stdn-export` command. Retrofitting existing commands (e.g., `lia research go`) to use auto-launch is a stretch goal — the current `check_all_running()` pattern in `research_cli.py` will remain unchanged unless time permits.

### Configurable Data Paths

`~/.lia/config.json` already exists and is loaded by `cli.py` and `research_cli.py` via `load_user_config()`. The new `stdn-export` command adds keys (`comtrade_dir`, `hs_rollup_file`, `cache_dir`) to this existing config file — no new config infrastructure is needed.

Priority order: CLI flag > `~/.lia/config.json` > hardcoded default.

Note: The FAISS MCP server (`mcp-server-hscode-faiss-rollupmd.py`) currently hardcodes a Rivanna path as its default. This should be updated to default to the repo-local `H6_rollup.md`.

## Integration with STDN Explorer

The output CSV is designed for direct ingestion by the Explorer as a supplementary data source alongside the existing STDN production data. The Explorer would:

1. Load `stdn_trade_data.csv` alongside the existing STDN CSV
2. Join on material name
3. Display trade concentration as a new analytical dimension
4. Show `hs_bucket_quality` warnings on materials with "shared" buckets
5. Use `import_share_pct` for trade-based disruption analysis

The specific Explorer UI changes are out of scope for this spec.

## Data Dependencies

| Dependency | Location | Size | Notes |
|---|---|---|---|
| Comtrade Arrow files (2017-2025) | `data/UN_Comtrade/` | ~2.8 GB | Pre-aggregated, value only |
| Country code mappings | `data/UN_Comtrade/partnerAreas.arrow` | 30 KB | Maps codes to country names |
| H6_rollup.md | `~/git/lia/H6_rollup.md` | 1.8 MB | HS-6 code descriptions |
| Lia Material Classification Agent | `src/lia/research/agents/` | existing | Requires Ollama/LLM endpoint |
| FAISS MCP server | `src/lia/tools/` | existing | Requires sentence-transformers |

## Not In Scope

- Leverage ratio computation (requires quantity data not in current aggregated files)
- Multi-country simultaneous disruption modeling (k=2,3) — this uses production data, not trade data
- Explorer UI changes for trade data visualization
- Re-aggregation of bulk Comtrade data to include quantity columns
- DuckDB intermediate storage (may be added later if performance requires it)
