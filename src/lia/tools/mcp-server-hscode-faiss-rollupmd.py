import sys
import hashlib
from pathlib import Path
from typing import List
import json
import argparse
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel
from fastmcp import FastMCP
import anyio

# Globals
HS_DATA = []
HS_TEXTS = []
HS_EMBEDDINGS = None
HS_INDEX = None
HS_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
CACHE_DIR = Path(".cache")  # Default cache directory

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
    global HS_DATA, HS_TEXTS, HS_EMBEDDINGS, HS_INDEX

    cache_key = hash_file_path(text_path)
    embedding_cache = cache_dir / f"{cache_key}_hscode_embeddings.npy"
    index_cache = cache_dir / f"{cache_key}_hscode_index.faiss"

    if embedding_cache.exists() and index_cache.exists():
        print("✅ Loading from cache...", file=sys.stderr)
        HS_EMBEDDINGS = np.load(embedding_cache)
        HS_INDEX = faiss.read_index(str(index_cache))

        with open(text_path, "r", encoding="utf-8") as f:
            for line in f:
                if ":" not in line:
                    continue
                code, desc = line.strip().split(":", 1)
                code = code.strip()
                desc = desc.strip()
                HS_DATA.append({"id": code, "text": desc})

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
        HS_EMBEDDINGS = HS_MODEL.encode(HS_TEXTS, show_progress_bar=True)
        HS_EMBEDDINGS = np.array(HS_EMBEDDINGS)

        dim = HS_EMBEDDINGS.shape[1]
        HS_INDEX = faiss.IndexFlatL2(dim)
        HS_INDEX.add(HS_EMBEDDINGS)

        np.save(embedding_cache, HS_EMBEDDINGS)
        faiss.write_index(HS_INDEX, str(index_cache))
        print("✅ Cache saved", file=sys.stderr)

# --- MCP Server Definition ---
mcp = FastMCP("HSCode Text Semantic Server (FAISS)", version="0.2")

@mcp.tool(name="semantic_hs_query", description="Query Harmonized Service Codes using semantic search")
async def semantic_hs_query(input: HSQueryInput) -> HSQueryOutput:
    def run_faiss_query():
        query_vector = HS_MODEL.encode([input.query])
        D, I = HS_INDEX.search(np.array(query_vector), input.top_k)
        matches = []
        for idx, dist in zip(I[0], D[0]):
            entry = HS_DATA[idx]
            matches.append(HSMatch(
                id=entry["id"],
                text=entry["text"],
                score=float(1.0 / (1.0 + dist))  # Convert L2 distance to similarity
            ))
            print(f"Matches: {matches}", file=sys.stderr)
        return HSQueryOutput(matches=matches)

    print(f"🔍 Querying HS Codes: {input.query}", file=sys.stderr)
    return await anyio.to_thread.run_sync(run_faiss_query)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, help="Path to HSCode file", default="/sfs/gpfs/tardis/project/bi_dpi/data/UN_Comtrade/H6_rollup.md")
    parser.add_argument("--cache-dir", type=str, help="Path to cache directory", default=".cache")
    args = parser.parse_args()

    # Set cache directory
    CACHE_DIR = Path(args.cache_dir).resolve()
    CACHE_DIR.mkdir(exist_ok=True)

    # Load Data
    text_path = Path(args.file).resolve()
    if not text_path.exists():
        print(f"File not found: {text_path}", file=sys.stderr)
        sys.exit(1)

    load_hs_text_data(text_path, CACHE_DIR)

    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000, path="/mcp")
