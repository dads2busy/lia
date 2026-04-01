---
name: project_stdn_export
description: STDN Export feature — generates HS code material buckets and queries Comtrade trade flow data for STDN Explorer (2026-03-27)
type: project
---

New `lia stdn-export` CLI command that:
1. Takes material names as input
2. Uses existing Material Classification Agent to discover all HS-6 codes per material (buckets)
3. Classifies each HS code as "clean" (specific to material) or "shared" (covers multiple materials)
4. Queries pre-aggregated UN Comtrade Arrow files for US imports (reporterCode=840)
5. Aggregates trade values by material bucket × exporter country × year
6. Outputs CSV ready for STDN Explorer ingestion

**Spec:** `docs/superpowers/specs/2026-03-27-stdn-export-design.md`
**Plan:** `docs/superpowers/plans/2026-03-27-stdn-export.md`

**Key architecture decisions:**
- Comtrade is a post-pipeline analytical layer, NOT a replacement for USGS production data
- HS-6 codes often lump multiple materials — quality flags distinguish clean vs shared
- Arrow files have value (USD) only, no quantity — leverage ratios deferred
- US imports perspective only (reporterCode=840)
- MCP servers auto-launched as subprocesses via context manager
- Shared HS codes duplicate trade rows across all claiming materials
- Config priority: CLI flag > ~/.lia/config.json > hardcoded default

**Implementation status:** Plan written and reviewed, NOT started. 8 tasks covering models, MCP launcher, bucket generator, Comtrade query, CLI, path fixes, and tests.

**Why:** The Vullikanti et al. paper shows trade flow analysis reveals supply chain vulnerabilities that production data alone cannot capture.
