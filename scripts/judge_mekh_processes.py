#!/usr/bin/env python3
"""
LLM-as-Judge evaluation of MEKH hyperedge (process) factual accuracy.

Reads research_state.json files produced by the lia pipeline and evaluates
each process (hyperedge) for factual plausibility using an independent LLM
judge.  Designed to support the AAMAS paper's quality evaluation.

For each process the judge assesses:
  1. Process plausibility — is this a real industrial/chemical transformation?
  2. Input/output correctness — are precursors and products correctly assigned?
  3. HS code accuracy — do the HS codes match the named materials?

Results are cached in a JSONL file so re-runs are cheap.  The script produces
a Markdown report with per-condition precision-proxy metrics.

Example usage
-------------
    python scripts/judge_mekh_processes.py \
        --state-files /tmp/lia_boron_multi/research_state.json \
                      /tmp/lia_boron_generalist/research_state.json \
        --labels multi generalist \
        --judge-model openai:gpt-4.1 \
        --out-md experiment_snapshots/process_judge_report.md \
        --cache-jsonl experiment_snapshots/process_judge_cache.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional, Sequence

from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel, Field as PydanticField
from pydantic_ai import Agent

# ---------------------------------------------------------------------------
# Judge backend prefixes
# ---------------------------------------------------------------------------
# "claude-cli:<model>"  -> shell out to the `claude` CLI (see run_claude_cli_judge).
# "ollama:<model>"      -> pydantic_ai OpenAIModel pointed at a local ollama server.
CLAUDE_CLI_PREFIX = "claude-cli:"
OLLAMA_PREFIX = "ollama:"

JUDGE_SYSTEM_PROMPT = (
    "You are an independent judge evaluating the factual accuracy of "
    "material transformation processes in a knowledge hypergraph. "
    "Output valid JSON only."
)

# Appended to the prompt for the claude-cli backend, which has no structured
# output support of its own (no tools/MCP are enabled for the judge call).
JUDGE_CLI_JSON_INSTRUCTIONS = """
Respond with ONLY a single JSON object (no markdown fences, no commentary)
with exactly these fields:
  - process_plausible (boolean)
  - inputs_outputs_correct (boolean)
  - hs_codes_correct (boolean)
  - overall_correct (boolean)
  - error_mode (string, or null if overall_correct is true)
  - rationale (string, 2-4 sentences)
"""


# ---------------------------------------------------------------------------
# Judge verdict model
# ---------------------------------------------------------------------------

class ProcessVerdict(BaseModel):
    """Structured output from the LLM judge for a single MEKH process."""

    process_plausible: bool = PydanticField(
        description=(
            "True if the described transformation is a real, documented "
            "industrial or chemical process."
        )
    )
    inputs_outputs_correct: bool = PydanticField(
        description=(
            "True if the precursors and products listed are correct for "
            "the described process."
        )
    )
    hs_codes_correct: bool = PydanticField(
        description=(
            "True if every HS code assigned to a precursor or product "
            "plausibly matches the named material."
        )
    )
    overall_correct: bool = PydanticField(
        description=(
            "True if the process is fully correct: plausible process with "
            "correct inputs/outputs and correct HS codes."
        )
    )
    error_mode: Optional[str] = PydanticField(
        None,
        description=(
            "If overall_correct is false, a SHORT label for the error type. "
            "Examples: 'hallucinated_process', 'wrong_precursor', "
            "'wrong_product', 'wrong_hs_code', 'wrong_scale', "
            "'partially_correct'. None when overall_correct is true."
        ),
    )
    rationale: str = PydanticField(
        description="Concise justification (2-4 sentences)."
    )


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CacheKey:
    """Deduplication key: process description + sorted precursor/product HS codes."""
    description_hash: str  # first 120 chars of description, normalized
    precursor_codes: tuple[str, ...]
    product_codes: tuple[str, ...]

    def as_str(self) -> str:
        return (
            f"{self.description_hash}|||"
            f"{','.join(self.precursor_codes)}|||"
            f"{','.join(self.product_codes)}"
        )


@dataclass
class JudgedRecord:
    process_id: str
    description: str
    precursors: list[dict]
    products: list[dict]
    process_plausible: bool
    inputs_outputs_correct: bool
    hs_codes_correct: bool
    overall_correct: bool
    error_mode: Optional[str]
    rationale: str
    judged_at_utc: str
    judge_model: str


@dataclass
class ConditionMetrics:
    label: str
    n_processes: int
    n_judged: int
    n_overall_correct: int
    n_process_plausible: int
    n_io_correct: int
    n_hs_correct: int
    error_modes: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Extract processes from state file
# ---------------------------------------------------------------------------

def load_processes(state_path: Path) -> list[dict]:
    """Load processes from a research_state.json, returning list of dicts."""
    with state_path.open("r", encoding="utf-8") as f:
        state = json.load(f)

    materials_lookup = state.get("materials", {})
    processes_raw = state.get("processes", {})

    out: list[dict] = []
    for pid, proc in processes_raw.items():
        precursors = []
        for p in proc.get("precursors", []):
            if isinstance(p, dict):
                precursors.append(p)
            elif isinstance(p, str):
                precursors.append({"name": p, "hs_code": None})

        products = []
        for p in proc.get("products", []):
            if isinstance(p, dict):
                products.append(p)
            elif isinstance(p, str):
                products.append({"name": p, "hs_code": None})

        refs = proc.get("references", [])
        ref_summaries = []
        for r in refs:
            if isinstance(r, dict):
                ref_summaries.append({
                    "url": r.get("url", ""),
                    "source_quality_score": r.get("source_quality_score"),
                    "content_quality_score": r.get("content_quality_score"),
                })
            elif isinstance(r, str):
                ref_summaries.append({"url": r})

        out.append({
            "id": proc.get("id", pid),
            "description": proc.get("description", ""),
            "scale": proc.get("scale"),
            "precursors": precursors,
            "products": products,
            "references": ref_summaries,
            "process_score": proc.get("process_score"),
        })
    return out


def make_cache_key(proc: dict) -> CacheKey:
    desc = " ".join(proc["description"][:120].lower().split())
    pre_codes = tuple(sorted(
        p.get("hs_code", "") or "" for p in proc["precursors"]
    ))
    prod_codes = tuple(sorted(
        p.get("hs_code", "") or "" for p in proc["products"]
    ))
    return CacheKey(
        description_hash=desc,
        precursor_codes=pre_codes,
        product_codes=prod_codes,
    )


# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------

def build_judge_prompt(proc: dict) -> str:
    precursor_lines = "\n".join(
        f"  - {p.get('name', '?')} [HS {p.get('hs_code', '?')}]"
        for p in proc["precursors"]
    )
    product_lines = "\n".join(
        f"  - {p.get('name', '?')} [HS {p.get('hs_code', '?')}]"
        for p in proc["products"]
    )
    scale = proc.get("scale", "unknown")

    return f"""You are an expert in industrial chemistry, materials science, and the Harmonized System (HS) trade classification.

Your task is to evaluate whether the following material transformation process is factually accurate.

## Process description
{proc['description']}

## Scale
{scale}

## Precursors (inputs)
{precursor_lines}

## Products (outputs)
{product_lines}

## Evaluation criteria

1. **Process plausibility**: Is this a real, documented industrial or chemical transformation? Would a materials scientist or chemical engineer recognize it?

2. **Input/output correctness**: Are the listed precursors actually needed for this process? Are the listed products actually produced by this process? Are any key inputs or outputs missing that would make this implausible?

3. **HS code accuracy**: For each precursor and product, does the 6-digit HS code plausibly match the named material? HS codes are from the Harmonized System for international trade classification. A mismatch means the code refers to a different commodity than the name suggests.

4. **Overall correctness**: True ONLY if all three above are true. If any aspect is wrong, mark overall_correct as false and provide an error_mode label.

Return structured JSON with: process_plausible, inputs_outputs_correct, hs_codes_correct, overall_correct, error_mode (null if correct), rationale.
"""


def make_judge_agent(judge_model: str, retries: int = 3) -> Optional[Agent]:
    """Build a pydantic_ai Agent for the judge, or None for the claude-cli backend.

    The claude-cli backend (judge_model starts with "claude-cli:") does not go
    through pydantic_ai at all -- it shells out to the `claude` CLI. See
    run_claude_cli_judge() below.
    """
    if judge_model.startswith(CLAUDE_CLI_PREFIX):
        return None

    if judge_model.startswith(OLLAMA_PREFIX):
        # pydantic_ai 0.3.4: OpenAI-compatible model with a custom base_url,
        # pointed at a local ollama server (OpenAI-compatible /v1 API).
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider

        model_name = judge_model[len(OLLAMA_PREFIX):]
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        model = OpenAIModel(
            model_name,
            provider=OpenAIProvider(base_url=base_url, api_key="ollama"),
        )
        # Ask the (hybrid reasoning) model to skip its "thinking" pass. Note:
        # for qwen3.6:27b this measurably helps on short/trivial prompts but
        # does NOT reliably bound latency on the full judge prompt -- see
        # task-1-report.md for measured timings and the decision this led to.
        return Agent(
            model=model,
            output_type=ProcessVerdict,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            model_settings={"extra_body": {"think": False}},
            retries=retries,
            output_retries=retries,
        )

    return Agent(
        model=judge_model,
        output_type=ProcessVerdict,
        system_prompt=JUDGE_SYSTEM_PROMPT,
        retries=retries,
        output_retries=retries,
    )


# ---------------------------------------------------------------------------
# claude-cli judge backend
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    m = _CODE_FENCE_RE.match(text)
    if m:
        return m.group(1).strip()
    return text


def parse_claude_cli_stdout(stdout: str) -> tuple[ProcessVerdict, Optional[str]]:
    """Parse the JSON stdout of `claude -p --output-format json` into a verdict.

    Returns (verdict, actual_model_id). actual_model_id is the first key of
    the CLI's `modelUsage` map (the real model id, e.g. "claude-sonnet-5"), or
    None if that field is missing.

    Raises ValueError / json.JSONDecodeError / pydantic.ValidationError on
    malformed input -- the caller is responsible for retrying.
    """
    outer = json.loads(stdout)
    result_text = outer.get("result")
    if not isinstance(result_text, str) or not result_text.strip():
        raise ValueError("claude CLI response missing non-empty 'result' text")
    inner_text = _strip_code_fence(result_text)
    payload = json.loads(inner_text)
    verdict = ProcessVerdict.model_validate(payload)
    model_usage = outer.get("modelUsage") or {}
    actual_model = next(iter(model_usage), None)
    return verdict, actual_model


def run_claude_cli_judge(
    prompt: str,
    model: str,
    retries: int = 3,
    timeout_s: int = 180,
) -> tuple[ProcessVerdict, str]:
    """Run a single judge query through the `claude` CLI as a subprocess.

    Isolation: runs from a neutral temporary cwd, with all built-in tools
    disabled (--tools ""), no MCP servers (--strict-mcp-config with no
    --mcp-config), no user/project/local settings loaded
    (--setting-sources ""), and no session persistence.
    """
    full_prompt = prompt + "\n" + JUDGE_CLI_JSON_INSTRUCTIONS
    last_err: Optional[BaseException] = None

    for attempt in range(1, retries + 1):
        with tempfile.TemporaryDirectory(prefix="claude_judge_") as tmp_cwd:
            cmd = [
                "claude",
                "-p",
                "--model", model,
                "--output-format", "json",
                "--tools", "",
                "--strict-mcp-config",
                "--setting-sources", "",
                "--no-session-persistence",
                "--system-prompt", JUDGE_SYSTEM_PROMPT,
                full_prompt,
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=tmp_cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )
            except subprocess.TimeoutExpired as e:
                last_err = e
                continue

            if proc.returncode != 0:
                last_err = RuntimeError(
                    f"claude CLI exit {proc.returncode}: {proc.stderr[:500]}"
                )
                continue

            try:
                verdict, actual_model = parse_claude_cli_stdout(proc.stdout)
                return verdict, actual_model or f"{CLAUDE_CLI_PREFIX}{model}"
            except Exception as e:  # malformed reply -- retry
                last_err = e
                continue

    raise RuntimeError(
        f"claude-cli judge failed after {retries} attempts: {last_err}"
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def load_cache(cache_path: Path) -> Dict[str, JudgedRecord]:
    cache: Dict[str, JudgedRecord] = {}
    if not cache_path.exists():
        return cache
    with cache_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            cache[obj["key"]] = JudgedRecord(
                process_id=obj.get("process_id", ""),
                description=obj.get("description", ""),
                precursors=obj.get("precursors", []),
                products=obj.get("products", []),
                process_plausible=obj["process_plausible"],
                inputs_outputs_correct=obj["inputs_outputs_correct"],
                hs_codes_correct=obj["hs_codes_correct"],
                overall_correct=obj["overall_correct"],
                error_mode=obj.get("error_mode"),
                rationale=obj.get("rationale", ""),
                judged_at_utc=obj.get("judged_at_utc", ""),
                judge_model=obj.get("judge_model", ""),
            )
    return cache


def append_cache(cache_path: Path, key: str, rec: JudgedRecord) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "key": key,
        "process_id": rec.process_id,
        "description": rec.description,
        "precursors": rec.precursors,
        "products": rec.products,
        "process_plausible": rec.process_plausible,
        "inputs_outputs_correct": rec.inputs_outputs_correct,
        "hs_codes_correct": rec.hs_codes_correct,
        "overall_correct": rec.overall_correct,
        "error_mode": rec.error_mode,
        "rationale": rec.rationale,
        "judged_at_utc": rec.judged_at_utc,
        "judge_model": rec.judge_model,
    }
    with cache_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main evaluation logic
# ---------------------------------------------------------------------------

async def judge_processes(
    processes: list[dict],
    agent: Optional[Agent],
    judge_model: str,
    cache: Dict[str, JudgedRecord],
    cache_path: Path,
    max_items: Optional[int] = None,
) -> list[JudgedRecord]:
    """Judge each process, using cache when available."""
    import random

    to_judge = list(processes)
    if max_items and len(to_judge) > max_items:
        random.shuffle(to_judge)
        to_judge = to_judge[:max_items]

    results: list[JudgedRecord] = []
    for i, proc in enumerate(to_judge, 1):
        key = make_cache_key(proc).as_str()

        if key in cache:
            print(f"  [{i}/{len(to_judge)}] cache hit: {proc['description'][:60]}...")
            results.append(cache[key])
            continue

        print(f"  [{i}/{len(to_judge)}] judging: {proc['description'][:60]}...")
        prompt = build_judge_prompt(proc)
        judge_model_used = judge_model
        try:
            if judge_model.startswith(CLAUDE_CLI_PREFIX):
                cli_model = judge_model[len(CLAUDE_CLI_PREFIX):]
                verdict, judge_model_used = await asyncio.to_thread(
                    run_claude_cli_judge, prompt, cli_model
                )
            else:
                result = await agent.run(prompt)
                verdict = result.output
        except Exception as e:
            # Do NOT cache this as a permanent "judge_error" verdict: a
            # transient outage or rate limit (observed in practice with the
            # claude-cli backend) would otherwise be baked into the cache
            # forever, defeating "rerun to resume/retry". Skip the item; a
            # later run of this same command will retry it since it is
            # still absent from the cache.
            print(f"    ERROR (will retry on next run): {e}", file=sys.stderr)
            continue

        rec = JudgedRecord(
            process_id=proc["id"],
            description=proc["description"],
            precursors=proc["precursors"],
            products=proc["products"],
            process_plausible=verdict.process_plausible,
            inputs_outputs_correct=verdict.inputs_outputs_correct,
            hs_codes_correct=verdict.hs_codes_correct,
            overall_correct=verdict.overall_correct,
            error_mode=verdict.error_mode,
            rationale=verdict.rationale,
            judged_at_utc=datetime.now(timezone.utc).isoformat(),
            judge_model=judge_model_used,
        )
        cache[key] = rec
        append_cache(cache_path, key, rec)
        results.append(rec)

    return results


def compute_metrics(label: str, records: list[JudgedRecord]) -> ConditionMetrics:
    n = len(records)
    error_modes: Dict[str, int] = {}
    for r in records:
        if r.error_mode:
            error_modes[r.error_mode] = error_modes.get(r.error_mode, 0) + 1

    return ConditionMetrics(
        label=label,
        n_processes=n,
        n_judged=n,
        n_overall_correct=sum(1 for r in records if r.overall_correct),
        n_process_plausible=sum(1 for r in records if r.process_plausible),
        n_io_correct=sum(1 for r in records if r.inputs_outputs_correct),
        n_hs_correct=sum(1 for r in records if r.hs_codes_correct),
        error_modes=error_modes,
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def pct(n: int, total: int) -> str:
    if total == 0:
        return "N/A"
    return f"{100 * n / total:.1f}%"


def generate_report(
    conditions: list[tuple[str, ConditionMetrics, list[JudgedRecord]]],
    judge_model: str,
) -> str:
    lines: list[str] = []
    lines.append("# MEKH Process Factual Accuracy — LLM-as-Judge Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Judge model: `{judge_model}`")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Condition | Processes | Overall correct | "
        "Process plausible | I/O correct | HS codes correct |"
    )
    lines.append(
        "|-----------|----------:|----------------:|"
        "------------------:|------------:|-----------------:|"
    )
    for label, m, _ in conditions:
        lines.append(
            f"| {label} | {m.n_processes} | "
            f"{m.n_overall_correct}/{m.n_processes} ({pct(m.n_overall_correct, m.n_processes)}) | "
            f"{m.n_process_plausible}/{m.n_processes} ({pct(m.n_process_plausible, m.n_processes)}) | "
            f"{m.n_io_correct}/{m.n_processes} ({pct(m.n_io_correct, m.n_processes)}) | "
            f"{m.n_hs_correct}/{m.n_processes} ({pct(m.n_hs_correct, m.n_processes)}) |"
        )
    lines.append("")

    # Precision proxy
    lines.append("## Precision proxy")
    lines.append("")
    lines.append("Precision proxy = (overall correct) / (total judged)")
    lines.append("")
    for label, m, _ in conditions:
        pp = m.n_overall_correct / m.n_processes if m.n_processes else 0
        lines.append(f"- **{label}**: {pp:.3f}")
    lines.append("")

    # Error modes
    lines.append("## Error modes")
    lines.append("")
    for label, m, _ in conditions:
        if m.error_modes:
            lines.append(f"### {label}")
            for mode, count in sorted(m.error_modes.items(), key=lambda x: -x[1]):
                lines.append(f"- `{mode}`: {count}")
            lines.append("")

    # Per-process details
    lines.append("## Per-process details")
    lines.append("")
    for label, m, records in conditions:
        lines.append(f"### {label}")
        lines.append("")
        for r in records:
            status = "CORRECT" if r.overall_correct else f"INCORRECT ({r.error_mode})"
            lines.append(f"**[{status}]** {r.description[:100]}")
            lines.append(f"  - Precursors: {', '.join(p.get('name', '?') for p in r.precursors)}")
            lines.append(f"  - Products: {', '.join(p.get('name', '?') for p in r.products)}")
            lines.append(f"  - Rationale: {r.rationale}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="LLM-as-judge evaluation of MEKH process factual accuracy.",
    )
    p.add_argument(
        "--state-files",
        nargs="+",
        required=True,
        type=Path,
        help="One or more research_state.json paths to evaluate.",
    )
    p.add_argument(
        "--labels",
        nargs="+",
        required=True,
        help="Labels for each state file (same order), e.g. 'multi' 'generalist'.",
    )
    p.add_argument(
        "--judge-model",
        default="openai:gpt-4.1",
        help=(
            "Judge model. Either a pydantic_ai model string (e.g. "
            "'openai:gpt-4.1'), 'ollama:<model>' for a local ollama server "
            "at $OLLAMA_BASE_URL (default http://localhost:11434/v1), or "
            "'claude-cli:<model>' to shell out to the `claude` CLI "
            "(default: openai:gpt-4.1)."
        ),
    )
    p.add_argument(
        "--out-md",
        type=Path,
        default=None,
        help="Path for Markdown report output.",
    )
    p.add_argument(
        "--cache-jsonl",
        type=Path,
        default=Path("experiment_snapshots/process_judge_cache.jsonl"),
        help="JSONL cache file path.",
    )
    p.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Max processes to judge per condition (for cost control).",
    )
    p.add_argument(
        "--llm-api-key",
        default=None,
        help="API key for the judge model. Also reads OPENAI_API_KEY env var.",
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    if len(args.state_files) != len(args.labels):
        print("ERROR: --state-files and --labels must have the same length.", file=sys.stderr)
        sys.exit(1)

    # Set API key from flag if provided (before agent creation)
    if args.llm_api_key:
        import os
        os.environ["OPENAI_API_KEY"] = args.llm_api_key

    print(f"Judge model: {args.judge_model}")
    print(f"Cache: {args.cache_jsonl}")
    print()

    cache = load_cache(args.cache_jsonl)
    print(f"Loaded {len(cache)} cached judgments.")

    agent = make_judge_agent(args.judge_model)

    conditions: list[tuple[str, ConditionMetrics, list[JudgedRecord]]] = []

    for state_file, label in zip(args.state_files, args.labels):
        print(f"\n=== Condition: {label} ({state_file}) ===")
        processes = load_processes(state_file)
        print(f"  Found {len(processes)} processes.")

        records = await judge_processes(
            processes,
            agent,
            args.judge_model,
            cache,
            args.cache_jsonl,
            max_items=args.max_items,
        )

        metrics = compute_metrics(label, records)
        conditions.append((label, metrics, records))

        pp = metrics.n_overall_correct / metrics.n_processes if metrics.n_processes else 0
        print(f"  Precision proxy: {pp:.3f} ({metrics.n_overall_correct}/{metrics.n_processes})")

    # Generate report
    report = generate_report(conditions, args.judge_model)
    print("\n" + report)

    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(report, encoding="utf-8")
        print(f"\nReport written to {args.out_md}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
