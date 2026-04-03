import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic_ai.mcp import MCPServerStreamableHTTP

from lia.research import ResearchMaterial, ResearchPipelineOptions
from lia.research.agents.material_classificaton_agent import (
    MaterialClassificatonAgentDeps,
    get_material_classification_agent,
)
from lia.stdn_export import HSCodeEntry, MaterialBucket


def load_h6_rollup(path: str) -> dict[str, str]:
    """Load H6_rollup.md into a dict of hs_code -> description."""
    rollup = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            code, desc = line.split(":", 1)
            rollup[code.strip()] = desc.strip()
    return rollup


def load_cached_bucket(cache_dir: Path, material: str) -> Optional[MaterialBucket]:
    """Load a cached bucket mapping if it exists."""
    cache_file = cache_dir / f"{material.lower().replace(' ', '_')}.json"
    if cache_file.exists():
        with cache_file.open() as f:
            return MaterialBucket.model_validate_json(f.read())
    return None


def save_cached_bucket(cache_dir: Path, material: str, bucket: MaterialBucket):
    """Save a bucket mapping to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{material.lower().replace(' ', '_')}.json"
    cache_file.write_text(bucket.model_dump_json(indent=2))


async def generate_bucket(
    material: str,
    options: ResearchPipelineOptions,
    h6_rollup: dict[str, str],
    cache_dir: Path,
    use_cache: bool = True,
    mcp_server: MCPServerStreamableHTTP | None = None,
) -> MaterialBucket:
    """Generate an HS code bucket for a material.

    1. Check cache
    2. Run Material Classification Agent to discover all HS-6 codes
    3. Classify each code as clean/shared using H6_rollup descriptions
    4. Cache and return

    If mcp_server is provided, it must already be entered as an async context
    manager by the caller (session stays open across multiple calls).
    """
    if use_cache:
        cached = load_cached_bucket(cache_dir, material)
        if cached is not None:
            print(f"  Using cached bucket for {material} ({len(cached.hs_codes)} HS codes)")
            return cached

    print(f"  Generating bucket for {material} via Material Classification Agent...")
    if mcp_server is None:
        mcp_server = MCPServerStreamableHTTP(url="http://127.0.0.1:8000/mcp")
    agent = await get_material_classification_agent(options, mcp_servers=[mcp_server])

    deps = MaterialClassificatonAgentDeps(materials=None)
    result = await asyncio.wait_for(
        agent.run(
            f"Identify all HS-6 codes for the material: {material}. "
            f"Include raw/mined forms, refined forms, intermediates, and compounds. "
            f"For each HS code, also determine if the code is specific to {material} "
            f"(quality: 'clean') or if it covers multiple distinct materials "
            f"(quality: 'shared'). Use the HS code search tool to find candidates.",
            deps=deps,
        ),
        timeout=120,
    )

    # Parse agent result into HSCodeEntry list
    # The agent returns list[ResearchMaterial], each with one hs_code
    # pydantic_ai RunResult exposes structured output via .output (not .data)
    entries = []
    if hasattr(result, "output") and isinstance(result.output, list):
        for mat in result.output:
            if isinstance(mat, ResearchMaterial) and mat.hs_code:
                desc = h6_rollup.get(mat.hs_code, mat.hs_description or "")
                # Determine quality: check if H6 description mentions other materials
                quality = classify_hs_quality(material, mat, desc)
                entries.append(HSCodeEntry(
                    code=mat.hs_code,
                    description=desc[:200] if desc else "",
                    quality=quality,
                    relevance=f"{mat.name} ({'mined' if mat.mined else 'refined/intermediate'})",
                ))

    bucket = MaterialBucket(
        hs_codes=entries,
        generated_at=datetime.now().isoformat(),
        model=options.model_name,
    )

    if entries:
        save_cached_bucket(cache_dir, material, bucket)
    else:
        print(f"  Warning: No HS codes found for {material} — bucket not cached (will retry next run)")
    print(f"  Bucket for {material}: {len(entries)} HS codes ({sum(1 for e in entries if e.quality == 'clean')} clean, {sum(1 for e in entries if e.quality == 'shared')} shared)")
    return bucket


def classify_hs_quality(material: str, mat: ResearchMaterial, h6_desc: str) -> str:
    """Determine if an HS code is 'clean' (specific to this material) or 'shared'.

    Heuristic: if the description references distinct material names beyond
    the target material and its aliases, it's 'shared'. Common HS description
    patterns like "ores and concentrates" or "articles thereof" are NOT
    treated as multi-material indicators.
    """
    if not h6_desc:
        return "shared"  # Can't verify, assume shared

    # Normalize for comparison
    material_lower = material.lower()
    desc_lower = h6_desc.lower()
    aliases = [a.lower() for a in (mat.aliases or [])]
    all_names = [material_lower] + aliases + [mat.name.lower()]

    # Strong indicators of multi-material codes
    strong_multi_indicators = [
        ";", "other than", "n.e.c.", "not elsewhere",
    ]

    material_mentioned = any(name in desc_lower for name in all_names)
    has_strong_indicator = any(ind in desc_lower for ind in strong_multi_indicators)

    if material_mentioned and not has_strong_indicator:
        return "clean"

    return "shared"
