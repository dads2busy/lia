You are assisting with the `lia` project in `~/git/lia`, which implements a bottom-up, agent-based pipeline to build a structured “Material Evolution / Manufacturing Knowledge” representation (materials, processes, references) using LLM agents plus MCP tools. We are preparing this system and its evaluation for an AAMAS paper, and in particular we are implementing and running a “single generalist agent” baseline vs the existing multi-agent (role-specialized) setup, and building a controlled comparison.

## Repository & key entrypoints
- Repo: `~/git/lia`
- CLI entrypoint: `lia` (Typer)
- Bottom-up pipeline CLI namespace: `lia bottomup ...`
- Main run command: `lia bottomup go ...`
- MCP management: `lia bottomup mcp start|status|stop ...`
- Reference cache management: `lia bottomup reference list|show|refresh ...`
- Pipeline code:
  - `src/lia/research/research_pipeline.py` runs a `pydantic_graph` over task nodes.
  - `src/lia/research/research_tasks.py` defines nodes like `generate_research_material`, `generate_material_processes`, `review_material_processes`, etc.
- State file produced per research folder:
  - `<research_folder>/research_state.json`
  - Reference cache:
  - `<research_folder>/reference_content/*.json`

## What we did today (high-level)
1) Implemented an **agent architecture switch** to support an AAMAS baseline:
   - Default: `"multi"` = role-specialized prompts (current system).
   - Baseline: `"generalist"` = a shared generalist prompt across roles, while keeping the same typed outputs per role.
2) Added CLI flag:
   - `lia bottomup go --agent-architecture [multi|generalist]` (default `multi`).
3) Added a shared generalist prompt module:
   - `src/lia/research/agents/generalist_prompts.py` exports `GENERALIST_SYSTEM_PROMPT`.
4) Updated key agent constructors to use either specialized instructions or the generalist prompt + schema reminders depending on `options.agent_architecture`:
   - `material_classificaton_agent.py`
   - `material_finder_agent.py`
   - `material_manufacturing_agent.py`
   - `reference_reviewer_agent.py`
   - `url_scorer_agent.py`
   - `process_merging_agent.py`
5) Addressed multiple runtime blockers related to MCP tooling and local environment:
   - Fixed HS-code MCP failing due to missing rollup file by adding CLI option:
     - `lia bottomup mcp start --hs-rollup-file PATH`
     - Also supports env var `LIA_HS_ROLLUP_FILE`.
   - Located tool script:
     - `src/lia/tools/mcp-server-hscode-faiss-rollupmd.py`
     - It defaults to `/sfs/.../H6_rollup.md` (Rivanna path), but we now pass a local file.
   - Removed/disabled fragile external stdio MCP tools from default agent MCP lists (e.g., `wikipedia-mcp`, `uvx mcp-google-cse`, `mcp-server-fetch`) because they were causing the pipeline to fail at MCP context entry.
   - Removed secret-leaking prints from agent initialization (e.g. printing full options including API keys).
   - Patched CLI defaults so secrets do not appear in `--help` output:
     - `--llm-api-key`, `--google-api-key`, `--wikimedia-access-token` now default to `None` rather than loading from `~/.lia/config.json`.
6) Fixed a bug in the research semantic search MCP server that caused repeated `list index out of range` errors:
   - Script: `src/lia/tools/mcp-preliminary-research-vector.py`
   - Hardened for empty indexes / top_k clamping / index-data mismatch.
7) Fixed scoring logic in `review_material_processes`:
   - `distinct_domains_required` now respects `options.distinct_domains_required` instead of hardcoding `2`.
   - Domain parsing now uses `urllib.parse.urlparse` instead of brittle regex.
8) Debugged why `process_score` was 0 or missing:
   - Root cause was *empty reference content* due to Playwright browsers not installed.
   - Installed Playwright browsers with `playwright install`.
   - Refreshed cached references; Wikipedia fetched correctly; PubChem still yields near-empty content due to site structure.
9) Built a controlled baseline comparison for Boron:
   - Multi condition: `/tmp/lia_boron_multi`
   - Generalist condition: `/tmp/lia_boron_generalist`
   - We ran the pipeline and then ran a **review-only scoring pass** (start at `review_material_processes`) to populate numeric reference scores and `process_score`.
   - We computed offline scoring metrics from the saved state JSONs and saved the snapshot files in-repo:
     - `lia/experiment_snapshots/boron_multi_vs_generalist_snapshot_2026-03-09.json`
     - `lia/experiment_snapshots/boron_multi_vs_generalist_snapshot_2026-03-09.md`

## How to run the system (canonical commands)
### Initialize research folders
- Multi:
  - `lia bottomup init /tmp/lia_boron_multi boron`
- Generalist:
  - `lia bottomup init /tmp/lia_boron_generalist boron`

### Start MCP servers (per folder)
- Use local HS rollup file `~/git/lia/H6_rollup.md`:
  - `lia bottomup mcp start --research-folder /tmp/lia_boron_multi --hs-rollup-file /Users/ads7fg/git/lia/H6_rollup.md`
  - `lia bottomup mcp start --research-folder /tmp/lia_boron_generalist --hs-rollup-file /Users/ads7fg/git/lia/H6_rollup.md`
- Check status:
  - `lia bottomup mcp status --research-folder /tmp/lia_boron_multi`
  - `lia bottomup mcp status --research-folder /tmp/lia_boron_generalist`

### Run multi vs generalist
- Multi (specialized prompts):
  - `lia bottomup go --research-folder /tmp/lia_boron_multi --agent-architecture multi --no-purge-processes --model gpt-4.1-mini --llm-api-key "$OAIKEY"`
- Generalist baseline:
  - `lia bottomup go --research-folder /tmp/lia_boron_generalist --agent-architecture generalist --no-purge-processes --model gpt-4.1-mini --llm-api-key "$OAIKEY"`

### Review-only scoring pass (do NOT start over)
Use this after each run to ensure references get numeric review scores and `process_score` is computed, without looping back into process generation:
- `lia bottomup go --research-folder <FOLDER> --start review_material_processes --solo --no-generate-processess --no-purge-processes --purge-dry-run --maximum-reference-reviews 1 --force-reference-review --model gpt-4.1-mini --llm-api-key "$OAIKEY"`

## Environment notes / pitfalls discovered today
- Playwright fetcher is required by `fetch_url_as_markdown`; if browsers are not installed, reference fetching fails and cached content is empty. Fix: `playwright install`.
- PubChem pages may still yield near-empty content even with Playwright; Wikipedia pages fetch well. Consider filtering out ultra-short content or preferring other sources.
- MCP servers must be reachable:
  - HS tool: `http://127.0.0.1:8000/mcp/` (streamable HTTP; expects `Accept: text/event-stream`)
  - Research semantic search: `http://127.0.0.1:8001/mcp/`
- External stdio MCP tools were unstable and were disabled/removed from default agent MCP lists to keep runs reliable.
- Avoid printing secrets: removed prints and removed secret defaults from CLI help.

## What you should help with next
We’re preparing an AAMAS-quality comparison. Next tasks:
1) Make the evaluation reproducible and fair across multi vs generalist:
   - same model, same budgets, same rounds.
   - ideally add request/token budgeting and log usage.
2) Produce a paper-ready comparison table and plots:
   - materials count, processes count, refs/process, scored fraction, mean/median scores.
3) Investigate why generalist baseline scored higher than multi in the first snapshot:
   - could be differences in reference selection or process specificity.
   - run 2–3 repeats per condition and report variance.
4) (Optional) Improve the multi-agent system so specialization helps:
   - tighten manufacturing agent rules, reduce irrelevant processes (e.g., sulfuric acid contact process drift),
   - add ablation experiments (e.g., disable reference reviewer agent).
5) Fix quality issues:
   - validate/clamp `scale` to [0,1] (multi run had scale > 1),
   - ensure references are retained (avoid reference purge wiping evidence during scoring runs).

When responding:
- Do not leak secrets; never echo API keys/tokens.
- Prefer minimal, robust changes; avoid reintroducing fragile MCP stdio tools.
- When asked for “review-only”, use `--start review_material_processes --solo --no-generate-processess --purge-dry-run` to keep it fast and safe.

Review experiment_snapshots/boron_multi_vs_generalist_snapshot_2026-03-09.json for most recent experimental results.
