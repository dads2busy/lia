#!/usr/bin/env python3
"""Evidence-support rate: does at least one cited reference mention the process's inputs and outputs?

Usage: python scripts/eval/evidence_support.py --out-dir "$DATA" --folder boron "$STATE_B" [--folder gallium "$STATE_GA" ...]
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from pathlib import Path

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+\- ]", " ", s.lower())).strip()

def _ref_url(ref) -> str:
    return ref if isinstance(ref, str) else (ref.get("url") or "")

def material_terms(m, materials: dict) -> set[str]:
    """Names + aliases for a precursor/product entry; falls back to the inline name or bare string."""
    if isinstance(m, str):
        return {_norm(m)} - {""}
    terms = {_norm(m.get("name", ""))}
    rec = materials.get(str(m.get("hs_code", "")))
    if rec:
        terms.add(_norm(rec.get("name", "")))
        terms.update(_norm(a) for a in rec.get("aliases", []) or [])
    return {t for t in terms if len(t) >= 3}

def _mentions(text: str, terms: set[str]) -> bool:
    return any(t in text for t in terms)

def process_support(texts: list[str], pre_terms: list[set[str]], prod_terms: list[set[str]]) -> tuple[bool, bool]:
    """Returns (any_mention, fully_grounded). fully_grounded: one reference mentions >=1 precursor AND >=1 product."""
    any_m = full = False
    for raw in texts:
        t = _norm(raw or "")
        if not t: continue
        p_hit = any(_mentions(t, s) for s in pre_terms)
        q_hit = any(_mentions(t, s) for s in prod_terms)
        any_m |= (p_hit or q_hit); full |= (p_hit and q_hit)
    return any_m, full

def load_content(folder: Path, url: str) -> str | None:
    fn = folder / "reference_content" / (hashlib.md5(url.split("#", 1)[0].encode("utf-8")).hexdigest() + ".json")
    if not fn.exists(): return None
    try:
        return json.loads(fn.read_text()).get("content") or None
    except json.JSONDecodeError:
        return None

def evaluate_folder(folder: Path) -> tuple[dict, list[dict]]:
    state = json.loads((folder / "research_state.json").read_text())
    materials = state.get("materials", {}); procs = state.get("processes", {})
    rows, n_refs, refs_ok, unresolved = [], 0, 0, 0
    for pid, p in procs.items():
        pre = [material_terms(m, materials) for m in p.get("precursors", [])]
        prod = [material_terms(m, materials) for m in p.get("products", [])]
        unresolved += sum(1 for m in p.get("precursors", []) + p.get("products", [])
                          if isinstance(m, str) or str(m.get("hs_code", "")) not in materials)
        texts = []
        for r in p.get("references", []):
            n_refs += 1; c = load_content(folder, _ref_url(r))
            if c: refs_ok += 1; texts.append(c)
        any_m, full = process_support(texts, pre, prod)
        rows.append({"process_id": p.get("id", pid), "n_refs": len(p.get("references", [])),
                     "refs_with_content": len(texts), "any_mention": any_m, "fully_grounded": full})
    n = len(rows)
    summary = {"n_processes": n, "n_refs": n_refs, "refs_with_content": refs_ok,
               "frac_refs_with_content": refs_ok / n_refs if n_refs else 0.0,
               "proc_any_mention": sum(r["any_mention"] for r in rows),
               "proc_fully_grounded": sum(r["fully_grounded"] for r in rows),
               "frac_any": (sum(r["any_mention"] for r in rows) / n) if n else 0.0,
               "frac_full": (sum(r["fully_grounded"] for r in rows) / n) if n else 0.0,
               "unresolved_materials": unresolved}
    return summary, rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", nargs=2, action="append", metavar=("LABEL", "PATH"), required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()
    keys = ["n_processes", "n_refs", "refs_with_content", "frac_refs_with_content", "proc_any_mention",
            "proc_fully_grounded", "frac_any", "frac_full", "unresolved_materials"]
    with open(a.out_dir / "evidence_support.csv", "w", newline="") as f, \
         open(a.out_dir / "evidence_support_per_process.csv", "w", newline="") as g:
        w = csv.writer(f); w.writerow(["label"] + keys)
        wp = csv.writer(g); wp.writerow(["label", "process_id", "n_refs", "refs_with_content", "any_mention", "fully_grounded"])
        for label, path in a.folder:
            s, rows = evaluate_folder(Path(path)); w.writerow([label] + [s[k] for k in keys])
            for r in rows: wp.writerow([label] + [r[k] for k in ["process_id", "n_refs", "refs_with_content", "any_mention", "fully_grounded"]])
            print(label, s)

if __name__ == "__main__":
    main()
