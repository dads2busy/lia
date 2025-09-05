import sys
import json
import hashlib
from pathlib import Path
from typing import List, Set
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel
from fastmcp import FastMCP
import typer
import threading
import time
from transformers import AutoTokenizer
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
DOC_DATA = []
DOC_TEXTS = []
DOC_EMBEDDINGS = None
DOC_INDEX = None
MODEL = SentenceTransformer("all-MiniLM-L6-v2")
TOKENIZER = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)
SEEN_FILES: Set[str] = set()

app = typer.Typer()

class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 5

class SemanticSearchResult(BaseModel):
    url: str
    content: str
    score: float

def chunk_text(text: str, min_tokens: int = 300, max_tokens: int = 500, overlap_pct: float = 0.15) -> List[str]:
    tokens = TOKENIZER.encode(text, truncation=False, max_length=4096, return_tensors=None)[:4096]
    chunks = []
    stride = int(max_tokens * (1 - overlap_pct))
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + max_tokens)
        chunk = tokens[start:end]
        if len(chunk) >= min_tokens:
            chunks.append(TOKENIZER.decode(chunk, skip_special_tokens=True))
        if end == len(tokens):
            break
        start += stride
    return chunks

def hash_folder_path(folder_path: Path) -> str:
    abs_path = str(folder_path.resolve()).encode("utf-8")
    return hashlib.sha256(abs_path).hexdigest()

def load_json_documents(watch_dir: Path, cache_dir: Path):
    global DOC_DATA, DOC_TEXTS, DOC_EMBEDDINGS, DOC_INDEX

    cache_key = hash_folder_path(watch_dir)
    embedding_cache = cache_dir / f"{cache_key}_researchdata_embeddings.npy"
    index_cache = cache_dir / f"{cache_key}_researchdata_index.faiss"
    data_cache = cache_dir / f"{cache_key}_researchdata_data.json"

    if embedding_cache.exists() and index_cache.exists() and data_cache.exists():
        print("✅ Loading from cache...", file=sys.stderr)
        DOC_EMBEDDINGS = np.load(embedding_cache)
        DOC_INDEX = faiss.read_index(str(index_cache))
        with open(data_cache, "r", encoding="utf-8") as f:
            DOC_DATA.extend(json.load(f))
        for doc in DOC_DATA:
            SEEN_FILES.add(doc["url"])
    else:
        print("🔄 Building embeddings and index...", file=sys.stderr)
        for file in sorted(watch_dir.glob("*.json")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not data.get("error") and data.get("content"):
                    chunks = chunk_text(data["content"])
                    for i, chunk in enumerate(chunks):
                        chunk_url = f"{data['url']}#chunk{i}"
                        DOC_DATA.append({"url": chunk_url, "content": chunk})
                        SEEN_FILES.add(chunk_url)
            except Exception as e:
                print(f"⚠️ Failed to load {file}: {e}", file=sys.stderr)

        DOC_TEXTS[:] = [doc["content"] for doc in DOC_DATA]
        if not DOC_TEXTS:
            print("⚠️ No valid documents found to index.", file=sys.stderr)
            DOC_EMBEDDINGS = np.zeros((0, MODEL.get_sentence_embedding_dimension()), dtype=np.float32)
            DOC_INDEX = faiss.IndexFlatL2(MODEL.get_sentence_embedding_dimension())
            return

        DOC_EMBEDDINGS = MODEL.encode(DOC_TEXTS, show_progress_bar=True)
        DOC_EMBEDDINGS = np.array(DOC_EMBEDDINGS)

        dim = DOC_EMBEDDINGS.shape[1]
        DOC_INDEX = faiss.IndexFlatL2(dim)
        DOC_INDEX.add(DOC_EMBEDDINGS)

        np.save(embedding_cache, DOC_EMBEDDINGS)
        faiss.write_index(DOC_INDEX, str(index_cache))
        with open(data_cache, "w", encoding="utf-8") as f:
            json.dump(DOC_DATA, f)
        print("✅ Cache saved", file=sys.stderr)

def watch_directory(watch_dir: Path):
    def watch():
        global DOC_DATA
        while True:
            for file in watch_dir.glob("*.json"):
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    url = data.get("url")
                    content = data.get("content")
                    if (not data.get("error")) and content and url not in SEEN_FILES:
                        chunks = chunk_text(content)
                        for i, chunk in enumerate(chunks):
                            chunk_url = f"{url}#chunk{i}"
                            if chunk_url in SEEN_FILES:
                                continue
                            embedding = MODEL.encode([chunk])[0].astype(np.float32)
                            DOC_INDEX.add(np.array([embedding]))
                            DOC_DATA.append({"url": chunk_url, "content": chunk})
                            SEEN_FILES.add(chunk_url)
                            print(f"🆕 Added new document chunk: {chunk_url}", file=sys.stderr)
                except Exception as e:
                    print(f"⚠️ Failed to process {file}: {e}", file=sys.stderr)
            time.sleep(5)
    threading.Thread(target=watch, daemon=True).start()

@app.command()
def run_server(
    watch_dir: Path = typer.Argument(..., help="Directory with JSON files"),
    cache_dir: Path = typer.Option(CACHE_DIR, help="Directory to store cache files"),
    host: str = typer.Option("127.0.0.1", help="Host to serve on"),
    port: int = typer.Option(8001, help="Port to serve on")
):
    
    
    # Set cache directory
    CACHE_DIR = Path(cache_dir).resolve()
    CACHE_DIR.mkdir(exist_ok=True)
    
    
    if not watch_dir.exists() or not watch_dir.is_dir():
        print(f"❌ Directory not found: {watch_dir}", file=sys.stderr)
        raise typer.Exit(code=1)

    load_json_documents(watch_dir, CACHE_DIR)
    watch_directory(watch_dir)

    mcp = FastMCP("Preliminary Research Search Server", version="0.1")

    @mcp.tool(name="semantic_research_search", description="Semantic search over related research material")
    async def semantic_search(input: SemanticSearchRequest) -> List[SemanticSearchResult]:
        def run_faiss_query():
            print(f"Input.query: '{input.query}'")
            try:
                query_vector = MODEL.encode([input.query])
                D, I = DOC_INDEX.search(np.array(query_vector), input.top_k)
                matches = []
                for idx, dist in zip(I[0], D[0]):
                    entry = DOC_DATA[idx]
                    matches.append(SemanticSearchResult(
                        url=entry["url"],
                        content=entry["content"],
                        score=float(1.0 / (1.0 + dist))
                    ))
                print(f"Matches: {len(matches)}")
                print(f"Matches: {matches}")
                return matches
            except Exception as err:
                print(f"Error running query: {err}", file=sys.stderr)
                return []

        print(f"🔍 Querying: {input.query}", file=sys.stderr)
        
        try:
            return await anyio.to_thread.run_sync(run_faiss_query)
        except Exception as e:
            print(f"Search tool error: {e}")
            return []
        
    try:
        mcp.run(transport="http", host=host, port=port, path="/mcp")
    except Exception as e:
        print(f"⚠️ Unexpected error in receive loop: {e}")

if __name__ == "__main__":
    app()
