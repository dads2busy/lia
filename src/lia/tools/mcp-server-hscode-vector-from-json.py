import sys
import json
import hashlib
from pathlib import Path
from typing import List

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

from fastmcp import FastMCP

# Globals
HS_DATA = []
HS_TEXTS = []
HS_EMBEDDINGS = None
HS_INDEX = None
HS_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)


class HSQueryInput(BaseModel):
    query: str
    top_k: int = 6


class HSMatch(BaseModel):
    text: str
    id: str
    score: float


class HSQueryOutput(BaseModel):
    matches: List[HSMatch]


def hash_file_path(file_path: Path) -> str:
    abs_path = str(file_path.resolve()).encode("utf-8")
    return hashlib.sha256(abs_path).hexdigest()


def load_hs_data(json_path: Path):
    global HS_DATA, HS_TEXTS, HS_EMBEDDINGS, HS_INDEX

    cache_key = hash_file_path(json_path)
    embedding_cache = CACHE_DIR / f"{cache_key}_embeddings.npy"
    index_cache = CACHE_DIR / f"{cache_key}_index.faiss"

    with open(json_path, "r", encoding="utf-8") as f:
        HS_DATA = json.load(f)

    HS_TEXTS = [f"{item['id']} {item['text']}" for item in HS_DATA]

    if embedding_cache.exists() and index_cache.exists():
        print("✅ Loading from cache...", file=sys.stderr)
        HS_EMBEDDINGS = np.load(embedding_cache)
        HS_INDEX = faiss.read_index(str(index_cache))
    else:
        print("🔄 Building embeddings and index...", file=sys.stderr)
        HS_EMBEDDINGS = HS_MODEL.encode(HS_TEXTS, show_progress_bar=True)
        HS_EMBEDDINGS = np.array(HS_EMBEDDINGS)

        dim = HS_EMBEDDINGS.shape[1]
        HS_INDEX = faiss.IndexFlatL2(dim)
        HS_INDEX.add(HS_EMBEDDINGS)

        np.save(embedding_cache, HS_EMBEDDINGS)
        faiss.write_index(HS_INDEX, str(index_cache))
        print("✅ Cache saved", file=sys.stderr)


def main():

    if len(sys.argv) > 1:
        data_file_path = Path(sys.argv[1]).resolve()
    else:
        data_file_path = Path(Path(__file__).parent,'hscodes.json').resolve()
        
    json_path = Path(data_file_path)
    if not json_path.exists():
        print(f"File not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    load_hs_data(json_path)

    mcp = FastMCP("HSCode Semantic MCP Server", transport="stdio")

    @mcp.tool(name="semantic_hs_query", description="Query Harmonized Service Codes using semantic search")
    def semantic_hs_query(input: HSQueryInput) -> HSQueryOutput:
        print("🔍 Querying HS Codes:", input.query, file=sys.stderr)
        query_vector = HS_MODEL.encode([input.query])
        D, I = HS_INDEX.search(np.array(query_vector), input.top_k)

        matches = []
        for idx, dist in zip(I[0], D[0]):
            entry = HS_DATA[idx]
            matches.append(HSMatch(
                id=entry["id"],
                text=entry["text"],
                score=float(dist)
            ))

        print(f"Found {len(matches)} semantic matches", file=sys.stderr)
        print("Matches:", matches, file=sys.stderr)
        return HSQueryOutput(matches=matches)

    mcp.run()


if __name__ == "__main__":
    main()
