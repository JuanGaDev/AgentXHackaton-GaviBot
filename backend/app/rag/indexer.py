"""
Solidus codebase indexer.
Clones the Solidus repo and indexes Ruby source files into ChromaDB
using Gemini embeddings for RAG-based triage context.
"""
import os
import re
import asyncio
from pathlib import Path
from typing import Optional
import chromadb
from app.observability.logging_config import get_logger
from app.integrations.gemini_client import embed_text

logger = get_logger(__name__)

SOLIDUS_REPO_URL = os.getenv("SOLIDUS_REPO_URL", "https://github.com/solidusio/solidus")
SOLIDUS_REPO_PATH = os.getenv("SOLIDUS_REPO_PATH", "/app/solidus_repo")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
COLLECTION_NAME = "solidus_codebase"

_chroma_client: Optional[chromadb.AsyncHttpClient] = None
_collection = None


def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
        )
    return _chroma_client


def get_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _chunk_file(content: str, file_path: str, chunk_size: int = 800) -> list[dict]:
    """Split file content into overlapping chunks."""
    lines = content.split("\n")
    chunks = []
    chunk_lines = []
    current_size = 0

    for i, line in enumerate(lines):
        chunk_lines.append(line)
        current_size += len(line) + 1

        if current_size >= chunk_size:
            chunk_text = "\n".join(chunk_lines)
            chunks.append({
                "text": chunk_text,
                "file": file_path,
                "line_start": max(0, i - len(chunk_lines) + 1),
                "line_end": i,
            })
            # 20-line overlap
            chunk_lines = chunk_lines[-20:]
            current_size = sum(len(l) + 1 for l in chunk_lines)

    if chunk_lines and current_size > 50:
        chunks.append({
            "text": "\n".join(chunk_lines),
            "file": file_path,
            "line_start": max(0, len(lines) - len(chunk_lines)),
            "line_end": len(lines),
        })

    return chunks


def _is_indexable(path: Path) -> bool:
    """Only index Ruby source files that are relevant to SRE triage."""
    if path.suffix not in {".rb", ".rake", ".gemspec"}:
        return False
    skip_dirs = {"spec", "test", ".git", "node_modules", "vendor", "tmp", "log"}
    for part in path.parts:
        if part in skip_dirs:
            return False
    return True


async def clone_or_update_repo() -> bool:
    """Clone Solidus repo if not present, otherwise pull latest."""
    repo_path = Path(SOLIDUS_REPO_PATH)

    if (repo_path / ".git").exists():
        logger.info("Solidus repo already cloned - skipping clone")
        return True

    logger.info(f"Cloning Solidus from {SOLIDUS_REPO_URL}...")
    try:
        import git
        git.Repo.clone_from(
            SOLIDUS_REPO_URL,
            str(repo_path),
            depth=1,
            single_branch=True,
            branch="main",
        )
        logger.info("Solidus clone complete")
        return True
    except Exception as e:
        logger.error(f"Clone failed: {e}")
        return False


async def index_solidus() -> int:
    """Index the Solidus codebase into ChromaDB. Returns number of chunks indexed."""
    repo_path = Path(SOLIDUS_REPO_PATH)

    if not repo_path.exists():
        success = await clone_or_update_repo()
        if not success:
            logger.error("Cannot index - repo not available")
            return 0

    collection = get_collection()

    # Check if already indexed
    try:
        count = collection.count()
        if count > 100:
            logger.info(f"Solidus already indexed with {count} chunks - skipping")
            return count
    except Exception:
        pass

    logger.info("Starting Solidus codebase indexing...")
    ruby_files = list(repo_path.rglob("*.rb"))
    indexable = [f for f in ruby_files if _is_indexable(f)]
    logger.info(f"Found {len(indexable)} indexable Ruby files")

    all_chunks = []
    for file_path in indexable[:500]:  # Limit for demo
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if len(content) < 50:
                continue
            rel_path = str(file_path.relative_to(repo_path))
            chunks = _chunk_file(content, rel_path)
            all_chunks.extend(chunks)
        except Exception as e:
            logger.debug(f"Skip {file_path}: {e}")

    logger.info(f"Embedding {len(all_chunks)} chunks...")
    batch_size = 50
    total_indexed = 0

    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        texts = [c["text"] for c in batch]
        ids = [f"solidus_{i + j}" for j in range(len(batch))]
        metadatas = [{"file": c["file"], "line_start": c["line_start"]} for c in batch]

        embeddings = []
        for text in texts:
            emb = embed_text(text)
            embeddings.append(emb if emb else [0.0] * 768)

        try:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            total_indexed += len(batch)
        except Exception as e:
            logger.error(f"Batch indexing failed at {i}: {e}")

        if (i // batch_size) % 5 == 0:
            logger.info(f"Indexed {total_indexed}/{len(all_chunks)} chunks")

    logger.info(f"Indexing complete: {total_indexed} chunks stored")
    return total_indexed
