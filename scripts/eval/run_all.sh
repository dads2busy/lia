#!/usr/bin/env bash
# Regenerate every evaluation output the paper cites (CSVs, eval_numbers.tex,
# eval_tables.tex) from the MEKH state folders, the judge caches, and the
# curated/reference inputs, with the exact arguments used for the paper.
#
# Does NOT call any LLM: the judge caches ($DATA/judge_<mekh>_<judge>.jsonl,
# written by scripts/judge_mekh_processes.py) are inputs here.
#
# Usage:
#   scripts/eval/run_all.sh PATH/TO/state_paths.env [OUT_DIR]
#   STATE_PATHS_ENV=PATH/TO/state_paths.env scripts/eval/run_all.sh
#
# state_paths.env defines STATE_B, STATE_CO, STATE_GA, STATE_GE (MEKH state
# folders, each holding research_state.json) and STATE_B_RUNS (the seven boron
# generations, space-separated). OUT_DIR (default: the folder holding
# state_paths.env, i.e. the paper's data/eval) must already contain the
# inputs: judge_*.jsonl, known_routes.csv, usgs_mcs_hs_codes.csv.
#
# Other env vars (optional):
#   PYTHON     Python interpreter with the eval deps (default: python3)
#   H6         HS-6 nomenclature (default: <repo root>/H6_rollup.md)
#   TRADE      UN Comtrade 2024 flows
#              (default: <repo root>/data/UN_Comtrade/aggregate_intercountry_HS_flow_values_2024.arrow)
#   PARTNERS   UN Comtrade partner table (default: <repo root>/data/UN_Comtrade/partnerAreas.arrow)
#   RANK_PY    interpreter command for rank_stability.py (default: `uv run --no-project
#              --with matplotlib --with numpy python` when uv is installed, else $PYTHON).
#              The committed RQ3 CSVs were produced that way; another Python
#              version can differ in the last floating-point digit of the RBO
#              statistics (never in the rounded macros).
#   FIGURE     if set, also redraw the RQ3 degree figure to this PNG path
#              (needs matplotlib, i.e. the uv default above)
set -euo pipefail

ENV_FILE="${1:-${STATE_PATHS_ENV:-}}"
if [ -z "$ENV_FILE" ] || [ ! -f "$ENV_FILE" ]; then
  echo "usage: $0 PATH/TO/state_paths.env [OUT_DIR]  (or set STATE_PATHS_ENV)" >&2
  exit 2
fi
# shellcheck disable=SC1090
source "$ENV_FILE"
DATA="${2:-$(cd "$(dirname "$ENV_FILE")" && pwd)}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
H6="${H6:-$ROOT/H6_rollup.md}"
TRADE="${TRADE:-$ROOT/data/UN_Comtrade/aggregate_intercountry_HS_flow_values_2024.arrow}"
PARTNERS="${PARTNERS:-$ROOT/data/UN_Comtrade/partnerAreas.arrow}"

for v in STATE_B STATE_CO STATE_GA STATE_GE STATE_B_RUNS; do
  [ -n "${!v:-}" ] || { echo "ERROR: $v not set by $ENV_FILE" >&2; exit 2; }
done

# The --folder orders below are fixed: they are the orders the committed
# outputs were produced with (row order in the CSVs follows them).
# RQ1-RQ2 scripts (evidence, recall, coverage): germanium, gallium, cobalt, boron.
F_RQ=(--folder germanium "$STATE_GE" --folder gallium "$STATE_GA" --folder cobalt "$STATE_CO" --folder boron "$STATE_B")
# Section 6 scripts and the HS audit: alphabetical.
F_ABC=(--folder boron "$STATE_B" --folder cobalt "$STATE_CO" --folder gallium "$STATE_GA" --folder germanium "$STATE_GE")
# make_latex (row order of mekh_sizes.csv): boron, gallium, germanium, cobalt.
F_TEX=(--folder boron "$STATE_B" --folder gallium "$STATE_GA" --folder germanium "$STATE_GE" --folder cobalt "$STATE_CO")

CACHES=()
for m in boron cobalt gallium germanium; do
  for j in claude llama; do
    CACHES+=(--cache "$m:$j" "$DATA/judge_${m}_${j}.jsonl")
  done
done

run() { echo "+ $*" >&2; "$@"; }
# A step whose external input is absent (e.g. when run from the supplementary
# ZIP, which omits the HS nomenclature, the Comtrade extract and the fetched
# reference-content cache) is skipped and its existing outputs are kept, rather
# than overwritten with numbers computed from missing data.
skip() { echo "SKIPPED ($1): existing outputs in $DATA kept" >&2; }
have_refcache() { local p; for p in "$STATE_GE" "$STATE_GA" "$STATE_CO" "$STATE_B"; do [ -d "$p/reference_content" ] || return 1; done; }

# RQ1: judge summaries, agreement, error modes (from the cached verdicts).
run "$PY" scripts/eval/judge_summary.py --out-dir "$DATA" "${CACHES[@]}"
run "$PY" scripts/eval/judge_error_modes.py --out-dir "$DATA" "${CACHES[@]}"
# RQ1: LLM-free HS-6 validity audit.
if [ -f "$H6" ]; then run "$PY" scripts/eval/hs_validity.py --out-dir "$DATA" --nomenclature "$H6" "${F_ABC[@]}" "${CACHES[@]}"
else skip "hs_validity: no HS-6 nomenclature at $H6"; fi
# RQ1: evidence grounding and curated-route recall.
if have_refcache; then run "$PY" scripts/eval/evidence_support.py --out-dir "$DATA" "${F_RQ[@]}"
else skip "evidence_support: a state folder has no reference_content/ cache"; fi
run "$PY" scripts/eval/known_route_recall.py --routes "$DATA/known_routes.csv" --out-dir "$DATA" "${F_RQ[@]}"
# RQ2: top-down (USGS MCS) coverage.
run "$PY" scripts/eval/topdown_coverage.py --usgs "$DATA/usgs_mcs_hs_codes.csv" --out-dir "$DATA" "${F_RQ[@]}"
# Section 6: criticality (literal rule, then the drop-sourceless sensitivity variant).
run "$PY" scripts/eval/criticality.py --out-dir "$DATA" "${F_ABC[@]}"
run "$PY" scripts/eval/criticality.py --out-dir "$DATA" "${F_ABC[@]}" --drop-sourceless --summary-name criticality_summary_nosourceless.csv
# Section 6: disruption (registered vertices, then the include-unregistered sensitivity variant).
if [ -f "$TRADE" ] && [ -f "$PARTNERS" ]; then
  run "$PY" scripts/eval/disruption.py --out-dir "$DATA" --trade "$TRADE" --partners "$PARTNERS" "${F_ABC[@]}"
  run "$PY" scripts/eval/disruption.py --out-dir "$DATA" --trade "$TRADE" --partners "$PARTNERS" "${F_ABC[@]}" --include-unregistered
else skip "disruption: no Comtrade flows at $TRADE or partners at $PARTNERS"; fi
# RQ3: rank stability over the seven boron generations (labels boron, boron2, ..., boron7).
F_RUNS=(); i=1
for p in $STATE_B_RUNS; do
  if [ "$i" -eq 1 ]; then F_RUNS+=(--folder boron "$p"); else F_RUNS+=(--folder "boron$i" "$p"); fi
  i=$((i + 1))
done
if [ -n "${RANK_PY:-}" ]; then read -r -a RPY <<< "$RANK_PY"
elif command -v uv >/dev/null 2>&1; then RPY=(uv run --no-project --with matplotlib --with numpy python)
else RPY=("$PY"); fi
FIG=(); [ -n "${FIGURE:-}" ] && FIG=(--figure "$FIGURE")
run "${RPY[@]}" scripts/eval/rank_stability.py --out-dir "$DATA" --base 280450 "${F_RUNS[@]}" ${FIG[@]+"${FIG[@]}"}
# LaTeX macros and tables.
run "$PY" scripts/eval/make_latex.py --data-dir "$DATA" --primary-judge claude "${F_TEX[@]}"
echo "run_all.sh: outputs written to $DATA" >&2
