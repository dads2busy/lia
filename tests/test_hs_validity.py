import csv
import json
from pathlib import Path

from scripts.eval.hs_validity import (
    load_hs6_codes,
    audit_state,
    judge_rate_on_invalid,
    main as hs_validity_main,
)


def _write_jsonl(p: Path, rows):
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_load_hs6_codes_parses_leading_code_lines_only(tmp_path):
    p = tmp_path / "rollup.md"
    p.write_text(
        "010121: Horses; live, pure-bred breeding animals\n"
        "252800: Natural borates and concentrates\n"
        # Continuation line with no leading 6-digit code -- must be skipped,
        # not misparsed as a code (this shape occurs in the real file: a
        # wrapped multi-item entry whose text happens to start with ";").
        "; Pepperoncini, prepared or preserved (provided for in subheading 2001.90.38)\n"
        "\n"
    )
    codes = load_hs6_codes(p)
    assert codes == {"010121", "252800"}


def test_audit_state_counts_material_validity_and_invalid_edges():
    valid_codes = {"252800", "284520"}
    state = {
        "materials": {
            "252800": {"name": "borate ore"},
            "284520": {"name": "refined boron"},
            "999999": {"name": "not in nomenclature"},
        },
        "processes": {
            "p1": {
                "id": "p1",
                "precursors": [{"hs_code": "252800"}],
                "products": [{"hs_code": "284520"}],
            },  # both valid -> not an invalid-code hyperedge
            "p2": {
                "id": "p2",
                "precursors": [{"hs_code": "252800"}],
                "products": [{"hs_code": "123456"}],  # 6-digit, not in nomenclature
            },
            "p3": {
                "id": "p3",
                "precursors": [{"hs_code": "Unknown"}],  # not 6-digit -> ignored, not "invalid"
                "products": [{"hs_code": "284520"}],
            },
        },
    }
    audit = audit_state(state, valid_codes)
    assert audit["n_materials"] == 3
    assert audit["n_materials_valid"] == 2
    assert abs(audit["frac_materials_valid"] - 2 / 3) < 1e-9
    assert audit["n_processes"] == 3
    assert audit["n_invalid_edges"] == 1
    assert audit["invalid_process_ids"] == {"p2"}


def test_judge_rate_on_invalid(tmp_path):
    cache = tmp_path / "judge.jsonl"
    _write_jsonl(cache, [
        {"process_id": "p2", "hs_codes_correct": True},   # invalid-code edge, judge says correct
        {"process_id": "p4", "hs_codes_correct": False},  # not in invalid set -- excluded
        {"process_id": "p5", "hs_codes_correct": False},  # invalid-code edge, judge says incorrect
    ])
    n, n_correct, frac = judge_rate_on_invalid(cache, {"p2", "p5"})
    assert n == 2
    assert n_correct == 1
    assert abs(frac - 0.5) < 1e-9


def test_judge_rate_on_invalid_empty_set_returns_zero(tmp_path):
    cache = tmp_path / "judge.jsonl"
    _write_jsonl(cache, [{"process_id": "p1", "hs_codes_correct": True}])
    assert judge_rate_on_invalid(cache, set()) == (0, 0, 0.0)


def test_main_writes_both_csvs(tmp_path, monkeypatch):
    rollup = tmp_path / "rollup.md"
    rollup.write_text("252800: borate ore\n284520: refined boron\n")

    state_dir = tmp_path / "boron_state"
    state_dir.mkdir()
    (state_dir / "research_state.json").write_text(json.dumps({
        "materials": {"252800": {}, "999999": {}},
        "processes": {
            "p1": {"id": "p1", "precursors": [{"hs_code": "252800"}], "products": [{"hs_code": "284520"}]},
            "p2": {"id": "p2", "precursors": [{"hs_code": "252800"}], "products": [{"hs_code": "123456"}]},
        },
    }))

    cache_a = tmp_path / "judge_boron_claude.jsonl"
    cache_b = tmp_path / "judge_boron_llama.jsonl"
    _write_jsonl(cache_a, [
        {"process_id": "p1", "hs_codes_correct": True},
        {"process_id": "p2", "hs_codes_correct": True},
    ])
    _write_jsonl(cache_b, [
        {"process_id": "p1", "hs_codes_correct": True},
        {"process_id": "p2", "hs_codes_correct": False},
    ])

    monkeypatch.setattr("sys.argv", [
        "hs_validity.py",
        "--nomenclature", str(rollup),
        "--folder", "boron", str(state_dir),
        "--cache", "boron:claude", str(cache_a),
        "--cache", "boron:llama", str(cache_b),
        "--out-dir", str(tmp_path),
    ])
    hs_validity_main()

    with open(tmp_path / "hs_validity.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["label"] == "boron"
    assert rows[0]["n_materials"] == "2"
    assert rows[0]["n_materials_hs6_valid"] == "1"
    assert rows[0]["n_invalid_edges"] == "1"

    with open(tmp_path / "hs_validity_judges.csv") as f:
        jrows = {r["judge"]: r for r in csv.DictReader(f)}
    assert jrows["claude"]["n_invalid_edges"] == "1"
    assert jrows["claude"]["n_marked_hs_correct"] == "1"  # claude marked p2 correct despite invalid code
    assert jrows["llama"]["n_marked_hs_correct"] == "0"   # llama marked p2 incorrect


def test_audit_state_counts_only_six_digit_material_keys():
    # A non-code key such as "UNCLASSIFIED" is not an HS-6 material vertex.
    state = {"materials": {"252800": {}, "999999": {}, "UNCLASSIFIED": {}}, "processes": {}}
    audit = audit_state(state, {"252800"})
    assert audit["n_materials"] == 2
    assert audit["n_materials_valid"] == 1
    assert abs(audit["frac_materials_valid"] - 0.5) < 1e-9
