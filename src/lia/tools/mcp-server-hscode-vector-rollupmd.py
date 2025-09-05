import sys
import hashlib
from pathlib import Path
from typing import List
import json
import hnswlib
from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download

from pydantic import BaseModel
from fastmcp import FastMCP
import anyio
import types
import asyncio


## TEMP Patch for MCP not handling client closing connection
from mcp.shared import session as session_shared

def patch_session_class():
    orig_method = session_shared.BaseSession._receive_loop

    async def patched_receive_loop(self):
        try:
            await orig_method(self)
        except (anyio.ClosedResourceError, asyncio.CancelledError):
            print("🔌 Client disconnected cleanly (suppressed)")
        except Exception as e:
            print(f"⚠️ Unexpected error in receive loop: {e}")

    session_shared.BaseSession._receive_loop = patched_receive_loop

# Call this early, after FastMCP is initialized
patch_session_class()

# Globals
HS_DATA = []
HS_TEXTS = []
HS_INDEX = None
model_path = snapshot_download("sentence-transformers/all-MiniLM-L6-v2")
HSMODEL = SentenceTransformer(model_path)

CACHE_DIR = None  # Cache directory will be set dynamically

class HSQueryInput(BaseModel):
    query: str
    top_k: int = 5

class HSMatch(BaseModel):
    id: str
    text: str
    score: float

class HSQueryOutput(BaseModel):
    matches: List[HSMatch]

def hash_file_path(file_path: Path) -> str:
    abs_path = str(file_path.resolve()).encode("utf-8")
    return hashlib.sha256(abs_path).hexdigest()

def load_hs_text_data(text_path: Path, cache_dir: Path):
    global HS_DATA, HS_TEXTS, HS_INDEX

    cache_key = hash_file_path(text_path)
    index_cache = cache_dir / f"{cache_key}_hnsw_index.bin"
    data_cache = cache_dir / f"{cache_key}_data.json"

    if index_cache.exists() and data_cache.exists():
        print("✅ Loading from cache...", file=sys.stderr)
        with open(data_cache, "r", encoding="utf-8") as f:
            HS_DATA.extend(json.load(f))
        HS_TEXTS[:] = [f"{item['id']} {item['text']}" for item in HS_DATA]

        dim = HS_MODEL.get_sentence_embedding_dimension()
        HS_INDEX = hnswlib.Index(space='cosine', dim=dim)
        HS_INDEX.load_index(str(index_cache))
    else:
        print("🔄 Building embeddings and index...", file=sys.stderr)
        with open(text_path, "r", encoding="utf-8") as f:
            for line in f:
                if ":" not in line:
                    continue
                code, desc = line.strip().split(":", 1)
                code = code.strip()
                desc = desc.strip()
                HS_DATA.append({"id": code, "text": desc})

        HS_TEXTS[:] = [f"{item['id']} {item['text']}" for item in HS_DATA]
        embeddings = HSMODEL.encode(HS_TEXTS, show_progress_bar=True)

        dim = embeddings.shape[1]
        HS_INDEX = hnswlib.Index(space='cosine', dim=dim)
        HS_INDEX.init_index(max_elements=len(embeddings), ef_construction=200, M=16)
        HS_INDEX.add_items(embeddings)
        HS_INDEX.set_ef(50)

        HS_INDEX.save_index(str(index_cache))
        with open(data_cache, "w", encoding="utf-8") as f:
            json.dump(HS_DATA, f)
        print("✅ Cache saved", file=sys.stderr)

# --- MCP Server Definition ---
mcp = FastMCP()

# --- Tool Definition ---
@mcp.tool(name="semantic_hs_query", description="""
          Query Harmonized Service Codes using semantic search.
          Input a query string and get the top-k matching HS codes with descriptions.
          Do not include strings like "hs code" or "hs number" in the query.        
    """)
async def semantic_hs_query(input: HSQueryInput) -> HSQueryOutput:
    def run_hnsw_query():
        query_vector = HSMODEL.encode([input.query])
        labels, distances = HS_INDEX.knn_query(query_vector, k=input.top_k)
        matches = []
        for idx, score in zip(labels[0], distances[0]):
            entry = HS_DATA[idx]
            matches.append(HSMatch(
                id=entry["id"],
                text=entry["text"],
                score=float(1 - score)
            ))
        print(f"🔍 Found {len(matches)} matches for query: '{input.query}'", file=sys.stderr)
        if matches:
            print("Matches:", file=sys.stderr)
        return HSQueryOutput(matches=matches)

    print(f"🔍 Querying HS Codes: {input.query}", file=sys.stderr)
    # return await anyio.to_thread.run_sync(run_hnsw_query)
    return run_hnsw_query()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, help="Path to HSCode file", default="/sfs/gpfs/tardis/project/bi_dpi/data/UN_Comtrade/H6_rollup.md")
    parser.add_argument("--cache-dir", type=str, help="Path to cache directory", default=".cache")
    args = parser.parse_args()

    # Set Cache Directory
    CACHE_DIR = Path(args.cache_dir).resolve()
    CACHE_DIR.mkdir(exist_ok=True)

    # Load Data
    text_path = Path(args.file).resolve()
    if not text_path.exists():
        print(f"File not found: {text_path}", file=sys.stderr)
        sys.exit(1)

    load_hs_text_data(text_path, CACHE_DIR)

    # Just run FastMCP directly with HTTP
    mcp.run(transport="http", host="127.0.0.1", port=8000, path="/mcp")
