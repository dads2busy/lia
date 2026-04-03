import csv
from pathlib import Path
from typing import Optional
from itertools import groupby

import pyarrow as pa
import pyarrow.compute as pc

from lia.stdn_export import MaterialBucket, TradeFlowRow


# --- Country code resolution ---

def load_partner_map(partner_file: Path) -> dict[int, dict]:
    """Load partnerAreas.arrow into a dict of code -> {name, iso3}.

    Note: partnerAreas uses PartnerCode (capital P/C), not partnerCode.
    Excludes group entries (isGroup=True).
    """
    with pa.memory_map(str(partner_file), "r") as source:
        reader = pa.ipc.RecordBatchFileReader(source)
        table = reader.read_all()

    result = {}
    for row in table.to_pylist():
        if row.get("isGroup", False):
            continue
        code = row["PartnerCode"]
        result[code] = {
            "name": row["PartnerDesc"],
            "iso3": row.get("PartnerCodeIsoAlpha3", ""),
        }
    return result


# --- Arrow file loading and filtering ---

def load_arrow_table(path: Path) -> pa.Table:
    """Load an Arrow IPC file into memory."""
    with pa.memory_map(str(path), "r") as source:
        reader = pa.ipc.RecordBatchFileReader(source)
        return reader.read_all()


def query_us_imports(
    comtrade_dir: Path,
    years: list[int],
    hs_codes: set[str],
    reporter_code: int = 842,
) -> list[dict]:
    """Query Arrow files for US imports of specific HS codes.

    Returns list of dicts with keys: partnerCode, cmdCode, refYear, value
    """
    all_rows = []
    for year in years:
        arrow_file = comtrade_dir / f"aggregate_intercountry_HS_flow_values_{year}.arrow"
        if not arrow_file.exists():
            print(f"  Warning: No data file for year {year}, skipping.")
            continue

        table = load_arrow_table(arrow_file)

        # Filter: reporter == US AND cmdCode in our HS codes
        reporter_mask = pc.equal(table["reporterCode"], reporter_code)
        filtered = table.filter(reporter_mask)

        # Filter by HS codes (cmdCode is string)
        hs_mask = pc.is_in(filtered["cmdCode"], pa.array(list(hs_codes), type=pa.string()))
        filtered = filtered.filter(hs_mask)

        if filtered.num_rows > 0:
            all_rows.extend(filtered.to_pylist())
            print(f"  Year {year}: {filtered.num_rows} matching trade records")
        else:
            print(f"  Year {year}: no matching records")

    return all_rows


# --- Aggregation ---

def aggregate_trade_data(
    raw_rows: list[dict],
    buckets: dict[str, MaterialBucket],
    partner_map: dict[int, dict],
) -> list[TradeFlowRow]:
    """Aggregate raw trade rows into per-material, per-country, per-year summaries.

    For each material bucket, sum USD values across all HS codes in the bucket,
    grouped by exporter country and year. Compute import share and rank.
    """
    # Build reverse map: hs_code -> list of (material_name, quality)
    # Note: shared HS codes may map to multiple materials. Trade value is
    # attributed to ALL materials that claim the code (duplicated, not split),
    # since we cannot disaggregate shared codes.
    hs_to_materials: dict[str, list[tuple[str, str]]] = {}
    for material, bucket in buckets.items():
        for entry in bucket.hs_codes:
            hs_to_materials.setdefault(entry.code, []).append(
                (material, entry.quality)
            )

    # Group: (material, hs_code, partnerCode, year) -> total_value
    # One row per HS code (multiplex layer) per the paper's definition,
    # so g(S) = max_i g_i(S) can be computed downstream.
    groups: dict[tuple, float] = {}
    hs_quality: dict[tuple[str, str], str] = {}  # (material, hs_code) -> quality
    for row in raw_rows:
        mat_entries = hs_to_materials.get(row["cmdCode"], [])
        for material, quality in mat_entries:
            key = (material, row["cmdCode"], row["partnerCode"], row["refYear"])
            groups[key] = groups.get(key, 0.0) + (row["value"] or 0.0)
            hs_quality[(material, row["cmdCode"])] = quality

    # Compute totals per (material, hs_code, year) for share calculation
    hs_year_totals: dict[tuple, float] = {}
    for (material, hs_code, _, year), value in groups.items():
        k = (material, hs_code, year)
        hs_year_totals[k] = hs_year_totals.get(k, 0.0) + value

    # Build output rows — one per (material, hs_code, exporter, year)
    output = []
    for (material, hs_code, partner_code, year), value in groups.items():
        total = hs_year_totals.get((material, hs_code, year), 1.0)
        share = (value / total * 100) if total > 0 else 0.0

        partner = partner_map.get(partner_code, {"name": f"Unknown ({partner_code})", "iso3": ""})
        quality = hs_quality.get((material, hs_code), "shared")

        output.append(TradeFlowRow(
            material=material,
            hs_bucket=hs_code,
            hs_bucket_quality=quality,
            year=year,
            exporter=partner["name"],
            exporter_iso3=partner["iso3"],
            import_value_usd=round(value, 2),
            import_share_pct=round(share, 2),
            exporter_rank=0,  # Filled in next step
        ))

    # Compute ranks within each (material, hs_code, year) group
    output.sort(key=lambda r: (r.material, r.hs_bucket, r.year, -r.import_share_pct))
    ranked = []
    for _, group in groupby(output, key=lambda r: (r.material, r.hs_bucket, r.year)):
        for rank, row in enumerate(group, 1):
            row.exporter_rank = rank
            ranked.append(row)

    return ranked


# --- CSV output ---

def write_csv(rows: list[TradeFlowRow], output_path: Path):
    """Write trade flow rows to CSV."""
    if not rows:
        print("  Warning: No trade data to write.")
        return

    fieldnames = [
        "material", "hs_bucket", "hs_bucket_quality", "year",
        "exporter", "exporter_iso3", "import_value_usd",
        "import_share_pct", "exporter_rank",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump())

    print(f"  Wrote {len(rows)} rows to {output_path}")
