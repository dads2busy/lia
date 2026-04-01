---
name: reference_data_locations
description: Locations of key data files in the lia repo and their schemas
type: reference
---

**Comtrade Arrow files:** `data/UN_Comtrade/aggregate_intercountry_HS_flow_values_{year}.arrow` (2017-2025, ~2.8GB total)
- Schema: partnerCode (int64, exporter), reporterCode (int64, importer), cmdCode (string, HS-6), refYear (int64), value (double, USD)
- US reporter code = 840
- gitignored (too large for git)

**Country code mappings:** `data/UN_Comtrade/partnerAreas.arrow`
- Note case mismatch: trade files use `partnerCode`, this file uses `PartnerCode` (capital P/C)
- Country names: `PartnerDesc`, ISO-3: `PartnerCodeIsoAlpha3`
- Filter out `isGroup=True` entries

**HS code descriptions:** `H6_rollup.md` (repo root, 5,771 HS-6 codes)
- Format: `HSCODE: description; sub-descriptor; sub-descriptor...`
- Includes rolled-up 8-digit and 10-digit sub-level descriptions

**Comtrade bulk data (raw):** On Rivanna at `/sfs/gpfs/tardis/project/bi_dpi/data/UN_Comtrade/bulk/` (2.5TB)
- Has quantity columns (qty, altQty, netWgt, grossWgt) that the aggregated files lack
- SSH alias: `rivanna` (login.hpc.virginia.edu)

**FAISS MCP server:** `src/lia/tools/mcp-server-hscode-faiss-rollupmd.py` (port 8000)
- Uses all-MiniLM-L6-v2 embeddings over H6_rollup.md
- Default path needs updating from Rivanna to repo-local
