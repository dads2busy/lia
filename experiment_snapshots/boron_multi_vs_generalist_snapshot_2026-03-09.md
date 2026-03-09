# Boron baseline snapshot — multi vs generalist (2026-03-09)

This snapshot records the key metrics used for the “multi-agent vs single generalist” baseline comparison on the Boron case study.

The metrics were computed from the saved pipeline state files after running a review-only scoring pass (so that reviewed references had numeric `source_quality_score` and `content_quality_score`), and then computing an offline score using the same scoring rule as the pipeline:
- select references by combined score: `content_quality_score * min(source_quality_score * 2, 1.0)`
- require `minimum_process_references = 2`
- require `distinct_domains_required = 2`
- per-process score = average combined score over the selected top references

> Note: the “offline score” and `process_score` are expected to match when computed from the same reviewed references.

## Inputs (state files)

- Multi (specialized prompts): `/tmp/lia_boron_multi/research_state.json`
- Generalist baseline (generalist prompt across roles): `/tmp/lia_boron_generalist/research_state.json`

## Summary table

| Condition   | Materials | Processes | Total refs | Reviewed refs (numeric) | Scored processes (n) | Mean score | Median | Min  | Max  |
|------------|----------:|----------:|-----------:|--------------------------:|---------------------:|-----------:|-------:|-----:|-----:|
| multi      | 8         | 5         | 11         | 11                       | 3                    | 0.4333     | 0.4000 | 0.20 | 0.70 |
| generalist | 4         | 4         | 10         | 10                       | 4                    | 0.7500     | 0.7625 | 0.575| 0.90 |

## Raw snapshot (verbatim)

### multi
- state_file: `/tmp/lia_boron_multi/research_state.json`
- materials: 8
- processes: 5
- total_refs: 11
- reviewed_refs_numeric: 11
- process_score_stats:
  - n: 3
  - mean: 0.43333333333333335
  - median: 0.4
  - min: 0.2
  - max: 0.7
- offline_score_stats:
  - n: 3
  - mean: 0.43333333333333335
  - median: 0.4
  - min: 0.2
  - max: 0.7

### generalist
- state_file: `/tmp/lia_boron_generalist/research_state.json`
- materials: 4
- processes: 4
- total_refs: 10
- reviewed_refs_numeric: 10
- process_score_stats:
  - n: 4
  - mean: 0.75
  - median: 0.7625
  - min: 0.575
  - max: 0.9
- offline_score_stats:
  - n: 4
  - mean: 0.75
  - median: 0.7625
  - min: 0.575
  - max: 0.9

## Notes / caveats

- These results reflect the specific run configuration used on 2026-03-09 (including reference fetching/scoring behavior at that time).
- Some processes may be unscored if they have insufficient references or insufficient distinct domains, or if references lack numeric review scores.
- “Materials” is the count of HS-coded `ResearchMaterial` entries in the state; “Processes” is the count of `MaterialProcess` entries.