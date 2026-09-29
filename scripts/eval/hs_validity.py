#!/usr/bin/env python3
"""Objective, LLM-free HS-6 validity audit for MEKH hyperedges.

Background: the two LLM judges disagree mainly on HS-code correctness
(agreement ~53% on that criterion vs. ~85-99% on plausibility/I-O -- see
judge_agreement_criteria.csv). This script sidesteps the judges entirely
and checks each hyperedge's HS codes against the actual HS-6 nomenclature,
to see which judge's "hs_codes_correct" calls line up with an objective
ground truth.

Nomenclature source: H6_rollup.md (repo root of the `lia` checkout). Its
format is one line per code, "CODE: description...". Inspected before
writing this script (`grep -c -E '^[0-9]{6}: ' H6_rollup.md` -> 5768 unique
6-digit codes; a handful of other lines are wrapped continuation text from
a multi-item entry with no leading code and are skipped). The file carries
no explicit HS-revision/vintage header, but it is a roll-up of the US
Harmonized Tariff Schedule (HTS) to the international 6-digit HS level, and
contains at least one HTS compiler's note for a subheading that "expired at
the close of Dec. 31, 2022" (code 990319) -- consistent with, though not
conclusive proof of, HS 2022 vintage.

Usage:
  python scripts/eval/hs_validity.py --out-dir "$DATA" \
      --nomenclature "$LIA/H6_rollup.md" \
      --folder boron "$STATE_B" --folder gallium "$STATE_GA" \
      --folder germanium "$STATE_GE" --folder cobalt "$STATE_CO" \
      --cache boron:claude "$DATA/judge_boron_claude.jsonl" \
      --cache boron:llama "$DATA/judge_boron_llama.jsonl" ...

Writes:
  - hs_validity.csv (judge-independent, one row per label): fraction of
    registered material codes (state["materials"] keys) that exist in the
    nomenclature, and the count/fraction of hyperedges ("invalid-code
    hyperedges") with >=1 precursor/product hs_code that is syntactically
    6 digits but does not exist in the nomenclature.
  - hs_validity_judges.csv (one row per label,judge): among that label's
    invalid-code hyperedges (joined to the judge cache by process_id, which
    both the state-derived process list and judge_mekh_processes.py's cache
    records carry), the count/fraction the judge nonetheless marked
    hs_codes_correct=true. Lower is more reliable on HS correctness.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from pathlib import Path

HS6_LINE = re.compile(r"^(\d{6}):")
SIX_DIGIT = re.compile(r"^\d{6}$")


def load_hs6_codes(path: Path) -> set[str]:
    """Parse H6_rollup.md, returning the set of valid 6-digit HS codes."""
    codes: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = HS6_LINE.match(line)
            if m:
                codes.add(m.group(1))
    return codes


def load_state(folder: Path) -> dict:
    with open(folder / "research_state.json", encoding="utf-8") as f:
        return json.load(f)


def _process_hs_codes(proc: dict) -> list[str]:
    codes: list[str] = []
    for p in proc.get("precursors", []) or []:
        if isinstance(p, dict) and p.get("hs_code"):
            codes.append(str(p["hs_code"]))
    for p in proc.get("products", []) or []:
        if isinstance(p, dict) and p.get("hs_code"):
            codes.append(str(p["hs_code"]))
    return codes


def audit_state(state: dict, valid_codes: set[str]) -> dict:
    """Judge-independent structural HS-validity stats for one MEKH state."""
    materials = state.get("materials", {})
    n_materials = len(materials)
    n_materials_valid = sum(1 for code in materials if code in valid_codes)

    processes = state.get("processes", {})
    invalid_process_ids: set[str] = set()
    for pid, proc in processes.items():
        process_id = proc.get("id", pid)
        for code in _process_hs_codes(proc):
            if SIX_DIGIT.match(code) and code not in valid_codes:
                invalid_process_ids.add(process_id)
                break

    return {
        "n_materials": n_materials,
        "n_materials_valid": n_materials_valid,
        "frac_materials_valid": (n_materials_valid / n_materials) if n_materials else 0.0,
        "n_processes": len(processes),
        "n_invalid_edges": len(invalid_process_ids),
        "frac_invalid_edges": (len(invalid_process_ids) / len(processes)) if processes else 0.0,
        "invalid_process_ids": invalid_process_ids,
    }


def _cache_rows_by_process_id(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                out[r.get("process_id")] = r
    return out


def judge_rate_on_invalid(cache_path: Path, invalid_process_ids: set[str]) -> tuple[int, int, float]:
    """Among invalid_process_ids that also appear in this judge cache (by
    process_id), returns (n_matched, n_marked_hs_correct, fraction)."""
    if not invalid_process_ids:
        return (0, 0, 0.0)
    rows = _cache_rows_by_process_id(cache_path)
    matched = [rows[pid] for pid in invalid_process_ids if pid in rows]
    n = len(matched)
    n_correct = sum(1 for r in matched if r.get("hs_codes_correct"))
    return (n, n_correct, (n_correct / n) if n else 0.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nomenclature", type=Path, required=True)
    ap.add_argument("--folder", nargs=2, action="append", metavar=("LABEL", "PATH"), required=True)
    ap.add_argument("--cache", nargs=2, action="append", metavar=("LABEL:JUDGE", "PATH"), default=[])
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()

    valid_codes = load_hs6_codes(a.nomenclature)
    folders = {label: Path(p) for label, p in a.folder}
    caches = {tuple(lj.split(":", 1)): Path(p) for lj, p in a.cache}

    audits: dict[str, dict] = {}
    with open(a.out_dir / "hs_validity.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "n_materials", "n_materials_hs6_valid", "frac_materials_hs6_valid",
                    "n_processes", "n_invalid_edges", "frac_invalid_edges"])
        for label in sorted(folders):
            audit = audit_state(load_state(folders[label]), valid_codes)
            audits[label] = audit
            w.writerow([label, audit["n_materials"], audit["n_materials_valid"],
                        f"{audit['frac_materials_valid']:.4f}", audit["n_processes"],
                        audit["n_invalid_edges"], f"{audit['frac_invalid_edges']:.4f}"])

    with open(a.out_dir / "hs_validity_judges.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "judge", "n_invalid_edges", "n_marked_hs_correct", "frac_marked_hs_correct"])
        for (label, judge), p in sorted(caches.items()):
            if label not in audits:
                continue
            n, n_correct, frac = judge_rate_on_invalid(p, audits[label]["invalid_process_ids"])
            w.writerow([label, judge, n, n_correct, f"{frac:.4f}"])


if __name__ == "__main__":
    main()
