import pytest
from scripts.eval.rank_stability import borda, critsum, rbo_ext, order, compare, degree_table

def test_borda_counts_items_strictly_below_and_sums():
    lists = [{"a": 3, "b": 1, "c": 1}, {"a": 0, "b": 2, "d": 2}]
    assert borda(lists) == {"a": 2, "b": 1, "c": 0, "d": 1}
    assert critsum(lists) == {"a": 3, "b": 3, "c": 1, "d": 2}

def test_rbo_ext_known_values():
    assert rbo_ext(list("abc"), list("abc"), 0.9) == pytest.approx(1.0)
    assert rbo_ext(list("abc"), list("xyz"), 0.9) == pytest.approx(0.0)
    # hand-computed (Webber et al. 2010, eq. 30): X=(1,1,3) -> 0.1/0.9*(0.9+0.405+0.729) + 0.729
    assert rbo_ext(list("abc"), list("acb"), 0.9) == pytest.approx(0.1 / 0.9 * 2.034 + 0.729)
    # uneven lengths (eq. 32): a list that is a prefix of the other extrapolates to 1
    assert rbo_ext(["a"], ["a", "b"], 0.5) == pytest.approx(1.0)
    assert rbo_ext(["a", "b"], ["a"], 0.5) == pytest.approx(1.0)
    # uneven, hand-computed: S=[b], L=[a,b], p=0.5: X1=Xs=0, X2=Xl=1
    # (1-p)/p*[0/1*0.5 + 1/2*0.25 + 0] + [(1-0)/2 + 0/1]*0.25 = 0.125 + 0.125
    assert rbo_ext(["b"], ["a", "b"], 0.5) == pytest.approx(0.25)

def test_order_breaks_ties_randomly_but_reproducibly():
    import random
    s = {"a": 2, "b": 1, "c": 1}
    assert order(s, None) == ["a", "b", "c"]
    o = order(s, random.Random(1)); assert o[0] == "a" and set(o[1:]) == {"b", "c"}

def test_compare_without_ties_is_deterministic_and_with_ties_is_expected_value():
    a = {"x": 3, "y": 2, "z": 1}
    r = compare(a, a, p=0.9, k=2, n_samples=5, seed=0)
    assert r["rbo"] == pytest.approx(1.0) and r["topk_overlap"] == 2 and r["topk_jaccard"] == 1.0
    t = {"x": 1, "y": 1}
    r = compare(t, t, p=0.9, k=1, n_samples=4000, seed=0)
    assert r["rbo"] == pytest.approx((1 + 0.9) / 2, abs=0.01)   # same order: 1, swapped: p
    assert r["topk_overlap"] == pytest.approx(0.5, abs=0.03)

def test_degree_table_mean_sd_with_zero_fill():
    runs = [{"in": [0, 1, 1], "out": [2, 0, 0]}, {"in": [1], "out": [0]}]
    rows = degree_table(runs)
    d = {r["degree"]: r for r in rows}
    assert d[0]["in_mean"] == pytest.approx(0.5) and d[1]["in_mean"] == pytest.approx(1.5)
    assert d[2]["out_mean"] == pytest.approx(0.5) and d[2]["in_mean"] == 0
    assert d[1]["in_sd"] == pytest.approx(0.5 ** 0.5)   # sample sd (ddof=1) of (2, 1)

def test_stats_sample_sd_headline_and_population_sd_labelled():
    from scripts.eval.rank_stability import stats
    s = stats([1.0, 2.0, 3.0])
    assert s["mean"] == pytest.approx(2.0) and s["sd"] == pytest.approx(1.0)       # ddof=1
    assert s["sd_pop"] == pytest.approx((2 / 3) ** 0.5) and s["min"] == 1.0 and s["max"] == 3.0

def test_criticality_list_fails_loudly_when_base_missing():
    from scripts.eval.rank_stability import criticality_list
    state = {"materials": {"100000": {"name": "Ore"}, "300000": {"name": "Int"}},
             "processes": {"p": {"precursors": [{"hs_code": "100000"}], "products": [{"hs_code": "300000"}]}}}
    assert criticality_list(state, "300000")[0] == {"100000": 1}
    with pytest.raises(ValueError, match="280450"):
        criticality_list(state, "280450")
