from pathlib import Path

import chromadb

RUNBOOK_DIR = Path("runbooks")

_client = chromadb.PersistentClient(path=".chroma")
_collection = _client.get_or_create_collection("runbooks")


def index_runbooks() -> int:
    """Load every runbook file into the vector store."""
    files = sorted(RUNBOOK_DIR.glob("*.md"))
    _collection.upsert(
        ids=[f.stem for f in files],
        documents=[f.read_text() for f in files],
        metadatas=[{"name": f.stem} for f in files],
    )
    return len(files)


def search_runbooks(query: str, top_k: int = 2) -> str:
    """Return the most relevant runbooks for a problem description."""
    if _collection.count() == 0:
        index_runbooks()
    result = _collection.query(query_texts=[query], n_results=top_k)
    parts = []
    for name, doc in zip(result["ids"][0], result["documents"][0]):
        parts.append(f"[runbook: {name}]\n{doc}")
    return "\n\n".join(parts)