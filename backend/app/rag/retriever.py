"""
Retrieve relevant code context from ChromaDB for a given incident description.
"""
from typing import Optional
from app.rag.indexer import get_collection
from app.integrations.gemini_client import embed_query
from app.observability.logging_config import get_logger

logger = get_logger(__name__)


def retrieve_context(query: str, n_results: int = 5) -> str:
    """
    Query ChromaDB for code chunks relevant to the incident.
    Returns a formatted string of code snippets with file paths.
    """
    try:
        collection = get_collection()
        count = collection.count()
        if count == 0:
            logger.warning("ChromaDB collection is empty - no code context available")
            return ""

        query_embedding = embed_query(query)
        if not query_embedding:
            return ""

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not documents:
            return ""

        context_parts = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            if dist > 1.2:  # Skip low relevance
                continue
            file_path = meta.get("file", "unknown")
            context_parts.append(f"# {file_path}\n{doc}")

        return "\n\n---\n\n".join(context_parts[:3])

    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        return ""
