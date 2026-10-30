"""Adaptador explícito de embeddings OpenAI e Chroma persistente (sem função oculta)."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from src.llm_client import OpenAIClient
from src.ingestion import Fragment, chunk_corpus
from src.providers import EmbeddingProvider


class IndexErrorRAG(RuntimeError):
    """Índice ausente, incompatível ou sem metadados rastreáveis."""


INDEX_VERSION = "rag-index.v1"


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _settings(config: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = config or json.loads((_root() / "config.json").read_text(encoding="utf-8"))
    settings = cfg.get("desafio2", {})
    return cfg, settings


def _client(config: dict[str, Any] | None = None) -> OpenAIClient:
    cfg, settings = _settings(config)
    llm = settings.get("llm", {})
    embedding = settings.get("embeddings", {})
    if embedding.get("provider", "openai") != "openai":
        raise ValueError("O adaptador de embeddings desta etapa aceita somente provider=openai.")
    return OpenAIClient(
        model=llm.get("model") or cfg.get("model"),
        timeout=float(llm.get("timeout_seconds", cfg.get("timeout_seconds", 30))),
        max_calls_per_run=int(llm.get("max_calls_per_run", 20)),
    )


def _chroma(config: dict[str, Any] | None = None):
    _, settings = _settings(config)
    store = settings.get("vector_store", {})
    if store.get("provider", "chroma") != "chroma":
        raise ValueError("O armazenamento vetorial desta etapa usa ChromaDB.")
    path = Path(store.get("persist_directory", "dados/indice/chroma"))
    if not path.is_absolute():
        path = _root() / path
    try:
        import chromadb
    except ImportError as exc:
        raise IndexErrorRAG("ChromaDB não está instalado; instale as dependências do Desafio 2.") from exc
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path)), store


def _embedding_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    _, settings = _settings(config)
    return settings.get("embeddings", {})


def _collection_name(strategy: str, config: dict[str, Any] | None = None, explicit: str | None = None) -> str:
    _, settings = _settings(config)
    store = settings.get("vector_store", {})
    base = explicit or store.get("collection_name", "acervo_institucional")
    safe_strategy = re.sub(r"[^a-zA-Z0-9_-]", "_", strategy)
    return f"{base}_{safe_strategy}"


def open_collection(
    strategy: str,
    *,
    config: dict[str, Any] | None = None,
    collection_name: str | None = None,
):
    _, settings = _settings(config)
    client, store = _chroma(config)
    embedding = _embedding_config(config)
    strategy_cfg = settings.get("chunking", {}).get("strategies", {}).get(strategy)
    if strategy_cfg is None:
        raise IndexErrorRAG(f"Estratégia de chunking não configurada: {strategy}.")
    metric = store.get("distance_metric", "cosine")
    if metric != "cosine":
        raise IndexErrorRAG("Esta versão requer distância cosine para converter similaridade como 1 - distância.")
    expected = {
        "hnsw:space": "cosine",
        "index_schema": INDEX_VERSION,
        "embedding_model": embedding.get("model", "text-embedding-3-small"),
        "embedding_dimensions": int(embedding.get("dimensions", 1536)),
        "chunking_strategy": strategy,
        "chunking_version": "chunking.v1",
        "chunking_unit": strategy_cfg.get("unit", "section_paragraph"),
        "chunking_size": int(strategy_cfg.get("size", 0)),
        "chunking_overlap": int(strategy_cfg.get("overlap", 0)),
    }
    name = _collection_name(strategy, config, collection_name)
    collection = client.get_or_create_collection(name=name, metadata=expected)
    actual = collection.metadata or {}
    mismatches = {key: {"expected": value, "actual": actual.get(key)} for key, value in expected.items() if actual.get(key) != value}
    if mismatches:
        raise IndexErrorRAG(f"Índice incompatível com embedding/estratégia; reindexação obrigatória: {mismatches}")
    return collection


def _embed(texts: list[str], config: dict[str, Any] | None = None, client: EmbeddingProvider | None = None) -> tuple[list[list[float]], dict[str, Any]]:
    embedding = _embedding_config(config)
    model = embedding.get("model", "text-embedding-3-small")
    dimensions = int(embedding.get("dimensions", 1536))
    result = (client or _client(config)).create_embeddings(texts, model=model, dimensions=dimensions)
    return result["vectors"], result["metadata"]


def indexar_acervo(
    *,
    strategy: str | None = None,
    config: dict[str, Any] | None = None,
    client: EmbeddingProvider | None = None,
    collection_name: str | None = None,
) -> dict[str, Any]:
    """Indexa somente os documentos explicitamente enumerados no manifesto."""
    _, settings = _settings(config)
    chunk_cfg = settings.get("chunking", {})
    selected = strategy or chunk_cfg.get("strategy_selected", "structural")
    strategy_cfg = chunk_cfg.get("strategies", {}).get(selected, {})
    acervo_directory = settings.get("paths", {}).get("acervo_directory", "dados/originais/acervo")
    chunks = chunk_corpus(
        strategy=selected,
        size=int(strategy_cfg.get("size", 400)),
        overlap=int(strategy_cfg.get("overlap", 80)),
        acervo_directory=acervo_directory,
    )
    collection = open_collection(selected, config=config, collection_name=collection_name)
    embedding_cfg = _embedding_config(config)
    batch_size = max(1, min(64, int(embedding_cfg.get("batch_size", 16))))
    required_calls = math.ceil(len(chunks) / batch_size)
    call_limit = int(settings.get("llm", {}).get("max_calls_per_run", 20))
    if required_calls > call_limit:
        raise IndexErrorRAG(f"Indexação requer {required_calls} lotes, acima do limite configurado ({call_limit}).")
    embedding_client = client or _client(config)
    if hasattr(embedding_client, "begin_run") and getattr(embedding_client, "max_calls_per_run", None) is None:
        embedding_client.begin_run(call_limit)
    all_vectors: list[list[float]] = []
    embedding_usage: list[dict[str, Any]] = []
    # Lotes podem atravessar documentos; os IDs/metadados continuam associados por posição.
    for offset in range(0, len(chunks), batch_size):
        batch = chunks[offset:offset + batch_size]
        vectors, metadata = _embed([item.text for item in batch], config, embedding_client)
        all_vectors.extend(vectors)
        embedding_usage.append(metadata.get("usage", {}))
    vector_by_id = {chunk.chunk_id: vector for chunk, vector in zip(chunks, all_vectors, strict=True)}
    indexed_docs: dict[str, dict[str, Any]] = {}
    total_vectors = 0
    for doc_id in sorted({chunk.document_id for chunk in chunks}):
        document_chunks = [chunk for chunk in chunks if chunk.document_id == doc_id]
        vectors = [vector_by_id[item.chunk_id] for item in document_chunks]
        # Os embeddings de todo o acervo foram calculados antes de substituir qualquer documento.
        previous = collection.get(where={"document_id": doc_id}, include=["metadatas"])
        old_ids = previous.get("ids", [])
        if old_ids:
            collection.delete(ids=old_ids)
        collection.upsert(
            ids=[item.chunk_id for item in document_chunks],
            documents=[item.text for item in document_chunks],
            embeddings=vectors,
            metadatas=[item.metadata() for item in document_chunks],
        )
        indexed_docs[doc_id] = {
            "file_sha256": document_chunks[0].file_sha256,
            "chunks": len(document_chunks),
            "substituted_old_chunks": len(old_ids),
        }
        total_vectors += len(document_chunks)
    return {
        "collection": collection.name,
        "index_version": INDEX_VERSION,
        "strategy": selected,
        "chunking_unit": strategy_cfg.get("unit", "section_paragraph"),
        "chunking_size": int(strategy_cfg.get("size", 0)),
        "chunking_overlap": int(strategy_cfg.get("overlap", 0)),
        "embedding_model": embedding_cfg.get("model", "text-embedding-3-small"),
        "embedding_dimensions": int(embedding_cfg.get("dimensions", 1536)),
        "metric": "cosine_distance; similarity = 1 - distance",
        "documents": indexed_docs,
        "embedding_usage": embedding_usage,
        "total_chunks": total_vectors,
        "persistent": True,
    }


def search_chunks(
    query: str,
    *,
    top_k: int | None = None,
    strategy: str | None = None,
    config: dict[str, Any] | None = None,
    client: EmbeddingProvider | None = None,
    collection_name: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("A consulta de recuperação não pode estar vazia.")
    _, settings = _settings(config)
    chosen = strategy or settings.get("chunking", {}).get("strategy_selected", "structural")
    collection = open_collection(chosen, config=config, collection_name=collection_name)
    if collection.count() == 0:
        raise IndexErrorRAG("O índice persistente está vazio; indexe o acervo antes de consultar.")
    call_limit = int(settings.get("llm", {}).get("max_calls_per_run", 20))
    if call_limit < 1:
        raise IndexErrorRAG("Limite de chamadas configurado não permite embedding da consulta.")
    embedding_client = client or _client(config)
    if hasattr(embedding_client, "begin_run") and getattr(embedding_client, "max_calls_per_run", None) is None:
        embedding_client.begin_run(call_limit)
    vector, _ = _embed([query], config, embedding_client)
    amount = max(1, min(20, int(top_k or settings.get("retrieval", {}).get("top_k", 3))))
    result = collection.query(query_embeddings=vector, n_results=min(amount, collection.count()), include=["documents", "metadatas", "distances"])
    items: list[dict[str, Any]] = []
    for index, chunk_id in enumerate(result["ids"][0]):
        distance = float(result["distances"][0][index])
        items.append({
            "chunk_id": chunk_id,
            "text": result["documents"][0][index],
            "metadata": result["metadatas"][0][index],
            "distance": distance,
            "similarity": 1.0 - distance,
        })
    return items


def listar_documentos_indexados(
    *, strategy: str | None = None,
    config: dict[str, Any] | None = None,
    collection_name: str | None = None,
) -> list[dict[str, Any]]:
    _, settings = _settings(config)
    chosen = strategy or settings.get("chunking", {}).get("strategy_selected", "structural")
    collection = open_collection(chosen, config=config, collection_name=collection_name)
    found = collection.get(include=["metadatas"])
    docs: dict[str, dict[str, Any]] = {}
    for meta in found.get("metadatas") or []:
        doc_id = meta["document_id"]
        info = docs.setdefault(doc_id, {key: meta.get(key) for key in ("document_id", "title", "version", "file_name", "file_sha256")})
        info["chunks"] = info.get("chunks", 0) + 1
    return list(docs.values())

