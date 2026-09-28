import json, hashlib
from pathlib import Path
from scripts.eval.evidence_support import material_terms, process_support, evaluate_folder

def test_material_terms_uses_aliases():
    mats = {"281000": {"name": "Boric acid", "hs_code": "281000", "aliases": ["orthoboric acid", "H3BO3"]}}
    assert material_terms({"hs_code": "281000", "name": "boric acid"}, mats) == {"boric acid", "orthoboric acid", "h3bo3"}

def test_material_terms_falls_back_to_inline_name():
    assert material_terms({"hs_code": "999999", "name": "Mystery salt"}, {}) == {"mystery salt"}
    assert material_terms("Bare string material", {}) == {"bare string material"}

def test_process_support_full_and_any():
    texts = ["Borax is treated with sulfuric acid to give boric acid.", ""]
    pre = [{"boric acid"}, {"sulfuric acid"}]; prod = [{"borax"}]
    assert process_support(texts, pre, prod) == (True, True)
    assert process_support(["nothing relevant"], pre, prod) == (False, False)

def test_process_support_word_boundaries():
    """atb should not match 'ask the chatbot'"""
    texts = ["ask the chatbot for help"]
    pre = [{"atb"}]  # This should NOT match
    prod = [{"output"}]
    assert process_support(texts, pre, prod) == (False, False)

def test_material_terms_filters_generic():
    """Generic single-word terms like 'salt' should be filtered out"""
    mats = {}
    # "salt" is generic, should be dropped
    result = material_terms({"hs_code": "999999", "name": "salt"}, mats)
    assert "salt" not in result
    # "table salt" is multi-word with len >= 3, should be kept
    result = material_terms({"hs_code": "999999", "name": "table salt"}, mats)
    assert "table salt" in result

def test_process_support_generic_terms_not_grounded():
    """Process with only generic 'salt' product should not be grounded by 'table salt' mention"""
    texts = ["table salt is used here"]
    pre = []
    prod = [set()]  # Empty set because "salt" was filtered out by material_terms
    assert process_support(texts, pre, prod) == (False, False)

def test_process_support_multiword_terms():
    """Multi-word terms like 'boric acid' should still match correctly"""
    texts = ["The process produces boric acid as output."]
    pre = []
    prod = [{"boric acid"}]
    assert process_support(texts, pre, prod) == (True, False)

def test_evaluate_folder(tmp_path: Path):
    url = "https://example.org/borax#top"
    (tmp_path / "reference_content").mkdir()
    fn = hashlib.md5("https://example.org/borax".encode()).hexdigest() + ".json"
    (tmp_path / "reference_content" / fn).write_text(json.dumps({"url": url, "content": "Borax plus sulfuric acid gives boric acid.", "error": None}))
    state = {"materials": {"252800": {"name": "Borax", "hs_code": "252800", "aliases": []},
                           "281000": {"name": "Boric acid", "hs_code": "281000", "aliases": []}},
             "processes": {"p1": {"id": "p1", "description": "x", "scale": 1.0,
                                  "precursors": [{"name": "Borax", "hs_code": "252800"}],
                                  "products": [{"name": "Boric acid", "hs_code": "281000"}],
                                  "references": [url, {"url": "https://example.org/missing"}]}}}
    (tmp_path / "research_state.json").write_text(json.dumps(state))
    s, rows = evaluate_folder(tmp_path)
    assert s["n_processes"] == 1 and s["n_refs"] == 2 and s["refs_with_content"] == 1
    assert s["proc_fully_grounded"] == 1 and s["proc_any_mention"] == 1
    assert rows[0]["fully_grounded"] is True
