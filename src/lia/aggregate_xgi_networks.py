#!/usr/bin/env python3
"""
Aggregate metrics from multiple bottom-up supply-chain networks analyzed
with analyze_xgi_full.py.

Given a set of *_metrics.json files, compute mean/std/range across all
numeric metrics and aggregate common distributions (degree, reachability, etc.).
Generates an averaged metrics JSON and comparative plots.
"""

import argparse, json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from statistics import mean, stdev

plt.rcParams.update({
    "font.size": 12,          # base font size
    "axes.titlesize": 16,     # title size
    "axes.labelsize": 14,     # axis labels
    "xtick.labelsize": 12,    # x-tick labels
    "ytick.labelsize": 12,    # y-tick labels
    "legend.fontsize": 12,    # legend text
})

# ---------------------------------------------------------------------
# --- Load and numeric aggregation utilities ---
# ---------------------------------------------------------------------

def load_metrics(paths):
    data = []
    for p in paths:
        try:
            with open(p) as f:
                data.append(json.load(f))
        except Exception as e:
            print(f"⚠️  Skipping {p}: {e}")
    return data


def numeric_keys(data_list):
    """Return all keys across data that have numeric values."""
    keys = set()
    for d in data_list:
        for k, v in d.items():
            if isinstance(v, (int, float)):
                keys.add(k)
    return sorted(keys)


def aggregate_numeric_metrics(data_list):
    """Compute mean, std, min, max across networks for numeric keys."""
    agg = {}
    keys = numeric_keys(data_list)
    for k in keys:
        vals = [d[k] for d in data_list if k in d and isinstance(d[k], (int, float))]
        if vals:
            agg[k] = {
                "mean": float(np.mean(vals)),
                "std": float(np.std(vals)),
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
            }
    return agg

# ---------------------------------------------------------------------
# --- Distribution averaging (robust to different binning) ---
# ---------------------------------------------------------------------

def average_distribution(distributions, num_bins=25):
    """
    Average histogram distributions across networks (robust to different bin sizes).
    Returns averaged normalized counts and standard deviations for error bars.
    """
    valid = []
    for dist in distributions:
        if not dist or "bins" not in dist or "counts" not in dist:
            continue
        bins = np.array(dist["bins"], dtype=float)
        counts = np.array(dist["counts"], dtype=float)
        if len(bins) < 2 or len(counts) == 0:
            continue
        # Normalize to sum=1
        if counts.sum() > 0:
            counts = counts / counts.sum()
        valid.append((bins, counts))

    if not valid:
        return {"bins": [], "mean": [], "std": []}

    # Common bin grid
    min_edge = min(b[0] for b, _ in valid)
    max_edge = max(b[-1] for b, _ in valid)
    common_bins = np.linspace(min_edge, max_edge, num_bins + 1)
    centers = (common_bins[:-1] + common_bins[1:]) / 2

    all_interp = []
    for bins, counts in valid:
        c_old = (bins[:-1] + bins[1:]) / 2
        interp = np.interp(centers, c_old, counts, left=0, right=0)
        all_interp.append(interp)

    arr = np.vstack(all_interp)
    mean_vals = np.mean(arr, axis=0)
    std_vals = np.std(arr, axis=0)

    # Keep absolute scale (do not renormalize)
    return {
        "bins": common_bins.tolist(),
        "mean": mean_vals.tolist(),
        "std": std_vals.tolist(),
    }


def aggregate_distributions(data_list, keys_to_merge):
    """Combine degree/reach distributions across all networks."""
    agg_dists = {}
    for key in keys_to_merge:
        dists = [d.get(key) for d in data_list if d.get(key)]
        agg_dists[key] = average_distribution(dists)
    return agg_dists

# ---------------------------------------------------------------------
# --- Plotting functions ---
# ---------------------------------------------------------------------
def plot_aggregate_reachability_distributions(agg_data, out_prefix):
    """
    Create a combined bar chart comparing in- and out-reachability distributions
    (mean ± std error bars) across aggregated networks.
    """
    in_reach = agg_data.get("in_reach_distribution")
    out_reach = agg_data.get("out_reach_distribution")
    if not in_reach or not out_reach:
        print("⚠️  Reachability distributions missing; skipping combined plot.")
        return

    # Extract arrays (match aggregator schema)
    in_bins = np.array(in_reach.get("bins", []), dtype=float)
    out_bins = np.array(out_reach.get("bins", []), dtype=float)
    mean_in = np.array(in_reach.get("mean", []), dtype=float)
    std_in  = np.array(in_reach.get("std", []), dtype=float)
    mean_out = np.array(out_reach.get("mean", []), dtype=float)
    std_out  = np.array(out_reach.get("std", []), dtype=float)

    if len(in_bins) > 1:
        centers = (in_bins[:-1] + in_bins[1:]) / 2
    elif len(out_bins) > 1:
        centers = (out_bins[:-1] + out_bins[1:]) / 2
    else:
        print("⚠️  Skipping combined reachability plot: insufficient data.")
        return

    # Align lengths
    n = min(len(mean_in), len(mean_out), len(centers))
    mean_in, mean_out = mean_in[:n], mean_out[:n]
    std_in, std_out = std_in[:n], std_out[:n]
    centers = centers[:n]

    # Plot
    x = np.arange(len(centers))
    width = 0.4

    plt.figure(figsize=(9,6))
    plt.bar(
        x - width/2,
        mean_in,
        width=width,
        color="orange",
        alpha=0.7,
        yerr=std_in,
        ecolor="black",
        capsize=3,
        label="In-Reach ±1 SD"
    )
    plt.bar(
        x + width/2,
        mean_out,
        width=width,
        color="teal",
        alpha=0.7,
        yerr=std_out,
        ecolor="black",
        capsize=3,
        label="Out-Reach ±1 SD"
    )

    plt.xlabel("Reachability value")
    plt.ylabel("Normalized frequency")
    plt.title("Aggregated In-Reach vs Out-Reach Distribution (Mean ± SD)")
    plt.xticks(x, [str(int(c)) for c in centers])
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    out_path = f"{out_prefix}_reachability_comparison_avgdist.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")

def plot_aggregated_distribution(dist, title, xlabel, ylabel, out_path, color="steelblue"):
    """
    Plot aggregated (mean ± std) distribution with clearly visible error bars and shaded region.
    Works even when normalized counts are small.
    """
    bins = np.array(dist.get("bins", []), dtype=float)
    mean_vals = np.array(dist.get("mean", []), dtype=float)
    std_vals = np.array(dist.get("std", []), dtype=float)

    if len(bins) < 2 or len(mean_vals) == 0:
        print(f"⚠️  Skipping empty distribution plot: {title}")
        return

    centers = (bins[:-1] + bins[1:]) / 2
    plt.figure(figsize=(8, 5))

    plt.bar(
        centers,
        mean_vals,
        width=np.diff(bins),
        color=color,
        alpha=0.7,
        yerr=std_vals,
        ecolor="black",
        capsize=3,
        align="center",
    )
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")


def plot_multi_network_bar(agg_metrics, out_path):
    """Plot summary of mean ± std for selected core metrics."""
    selected = [
        "avg_in_degree", "avg_out_degree", "avg_total_degree",
        "avg_downstream_reach", "avg_upstream_reach",
        "avg_edge_betweenness", "avg_flow_centrality"
    ]
    selected = [m for m in selected if m in agg_metrics]
    if not selected:
        print("⚠️  No common numeric metrics to plot.")
        return

    means = [agg_metrics[m]["mean"] for m in selected]
    stds  = [agg_metrics[m]["std"] for m in selected]
    x = np.arange(len(selected))
    plt.figure(figsize=(10,6))
    plt.bar(x, means, yerr=stds, capsize=6, color="slateblue", alpha=0.75, ecolor="black")
    plt.xticks(x, selected, rotation=30, ha="right")
    plt.ylabel("Mean ± SD")
    plt.title("Average Network Metrics Across Datasets")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")

def _collapse_hist_to_integers(bins, mean_vals, std_vals):
    """
    Integrate (with overlap weighting) continuous histogram bins into integer
    buckets [k, k+1). Returns degrees, mean_per_degree, std_per_degree.
    """
    bins = np.asarray(bins, dtype=float)
    mean_vals = np.asarray(mean_vals, dtype=float)
    std_vals = np.asarray(std_vals, dtype=float)

    lo = int(np.floor(bins[0]))
    hi = int(np.ceil(bins[-1]))
    degrees = np.arange(lo, hi)  # integer degree values

    int_mean = []
    int_std = []
    for k in degrees:
        # bins that overlap [k, k+1)
        left = bins[:-1]
        right = bins[1:]
        mask = (left < k + 1) & (right > k)
        if not np.any(mask):
            int_mean.append(0.0)
            int_std.append(0.0)
            continue

        # overlap-weighted contribution from each overlapping bin
        ovl = np.maximum(0.0, np.minimum(right[mask], k + 1.0) - np.maximum(left[mask], float(k)))
        widths = (right[mask] - left[mask])
        w = ovl / widths  # fraction of each bin allocated to [k, k+1)
        m = mean_vals[mask] * w
        s2 = (std_vals[mask] * w) ** 2  # combine stds in quadrature as an approximation

        int_mean.append(np.sum(m))
        int_std.append(np.sqrt(np.sum(s2)))

    return degrees, np.array(int_mean), np.array(int_std)


def plot_combined_degree_distribution(in_dist, out_dist, out_prefix):
    """
    Plot aggregated in-degree vs out-degree as side-by-side bars over INTEGER degrees,
    with ±1 SD error bars. This avoids duplicated tick labels.
    """
    bins_in = np.array(in_dist.get("bins", []), dtype=float)
    mean_in = np.array(in_dist.get("mean", []), dtype=float)
    std_in  = np.array(in_dist.get("std", []), dtype=float)

    bins_out = np.array(out_dist.get("bins", []), dtype=float)
    mean_out = np.array(out_dist.get("mean", []), dtype=float)
    std_out  = np.array(out_dist.get("std", []), dtype=float)

    if len(bins_in) < 2 and len(bins_out) < 2:
        print("⚠️  Skipping combined degree plot: insufficient data.")
        return

    # Collapse each histogram onto integer degree buckets
    deg_in, mean_in_i, std_in_i   = _collapse_hist_to_integers(bins_in,  mean_in,  std_in)   if len(bins_in)  > 1 else (np.array([]), np.array([]), np.array([]))
    deg_out, mean_out_i, std_out_i = _collapse_hist_to_integers(bins_out, mean_out, std_out) if len(bins_out) > 1 else (np.array([]), np.array([]), np.array([]))

    # Align to common integer degree axis
    all_degrees = np.unique(np.concatenate([deg_in, deg_out]))
    if all_degrees.size == 0:
        print("⚠️  Skipping combined degree plot: no integer buckets.")
        return

    def align(deg_src, vals):
        aligned = np.zeros_like(all_degrees, dtype=float)
        if deg_src.size:
            idx = np.searchsorted(all_degrees, deg_src)
            aligned[idx] = vals
        return aligned

    mean_in_a  = align(deg_in,  mean_in_i)
    std_in_a   = align(deg_in,  std_in_i)
    mean_out_a = align(deg_out, mean_out_i)
    std_out_a  = align(deg_out, std_out_i)

    x = np.arange(all_degrees.size)
    width = 0.4

    plt.figure(figsize=(9,6))
    plt.bar(x - width/2, mean_in_a,  width=width, color="orange", alpha=0.7,
            yerr=std_in_a,  ecolor="black", capsize=3, label="In-degree ±1 SD")
    plt.bar(x + width/2, mean_out_a, width=width, color="teal",   alpha=0.7,
            yerr=std_out_a, ecolor="black", capsize=3, label="Out-degree ±1 SD")

    plt.xlabel("Degree value")
    plt.ylabel("Normalized frequency")
    plt.title("Aggregated In-Degree vs Out-Degree Distribution (Mean ± SD)")
    plt.xticks(x, [str(int(k)) for k in all_degrees])
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    out_path = f"{out_prefix}_degree_comparison_avgdist.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")

# ---------------------------------------------------------------------
# --- Main aggregation workflow ---
# ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="List of *_metrics.json files to aggregate")
    ap.add_argument("--out-prefix", required=True, help="Output prefix for JSON and plots")
    args = ap.parse_args()

    data_list = load_metrics(args.inputs)
    if not data_list:
        print("No valid metrics files provided.")
        return

    print(f"Aggregating {len(data_list)} network metrics...")

    # --- Numeric metrics ---
    agg_metrics = aggregate_numeric_metrics(data_list)

    # --- Common distributions to merge ---
    keys_to_merge = [
        "in_degree_distribution", "out_degree_distribution", "total_degree_distribution",
        "in_reach_distribution", "out_reach_distribution",
        "edge_betweenness_distribution", "flow_centrality_distribution"
    ]
    agg_dists = aggregate_distributions(data_list, keys_to_merge)

    # --- Ensure output directory exists ---
    out_dir = Path(args.out_prefix).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Save combined JSON ---
    combined = {
        "num_networks": len(data_list),
        "aggregated_metrics": agg_metrics,
        "aggregated_distributions": agg_dists
    }

    out_json = f"{args.out_prefix}_aggregate_metrics.json"
    with open(out_json, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"Saved aggregate JSON: {out_json}")

    # --- Plots ---
    plot_multi_network_bar(agg_metrics, f"{args.out_prefix}_avg_metrics_bar.png")

    # Combined in/out degree
    if "in_degree_distribution" in agg_dists and "out_degree_distribution" in agg_dists:
        plot_combined_degree_distribution(
            agg_dists["in_degree_distribution"],
            agg_dists["out_degree_distribution"],
            args.out_prefix
        )

    # Other distributions
    for key, dist in agg_dists.items():
        if key in ["in_degree_distribution", "out_degree_distribution"]:
            continue  # already combined
        name = key.replace("_distribution", "")
        plot_aggregated_distribution(
            dist,
            title=f"Average {name.replace('_',' ').title()} Distribution (Mean ± SD)",
            xlabel=name.replace("_"," "),
            ylabel="Normalized frequency",
            out_path=f"{args.out_prefix}_{name}_avgdist.png"
        )

    plot_aggregate_reachability_distributions(agg_dists, args.out_prefix)
# ---------------------------------------------------------------------

if __name__ == "__main__":
    main()

