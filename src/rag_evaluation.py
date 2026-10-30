"""Medição reproduzível de recuperação para as cinco perguntas respondíveis (RF18)."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.vector_store import _client as create_embedding_client, indexar_acervo, search_chunks
from src.ingestion import chunk_corpus


def avaliar_chunking(
    *,
    config: dict[str, Any] | None = None,
    client=None,
    gabarito_path: str | Path | None = None,
    strategies: tuple[str, ...] = ("structural", "fixed_400_overlap_80"),
) -> dict[str, Any]:
    """Indexa duas coleções persistentes e compara as mesmas perguntas/top-k.

    Só grava métricas depois da execução solicitada; nunca preenche resultados simulados.
    """
    root = Path(__file__).resolve().parent.parent
    cfg = config or json.loads((root / "config.json").read_text(encoding="utf-8"))
    d2 = cfg.get("desafio2", {})
    gold = Path(gabarito_path) if gabarito_path else root / d2.get("paths", {}).get("gabaritos_directory", "dados/gabaritos") / "desafio2_rag.json"
    if not gold.is_absolute():
        gold = root / gold
    questions = [q for q in json.loads(gold.read_text(encoding="utf-8"))["perguntas_avaliacao"] if q["classe"] == "respondível"]
    if len(questions) != 5:
        raise ValueError("RF18 exige exatamente as cinco perguntas respondíveis do gabarito.")
    retrieval = d2.get("retrieval", {})
    top_k = int(retrieval.get("top_k", 3))
    embed_cfg = d2.get("embeddings", {})
    batch_size = max(1, int(embed_cfg.get("batch_size", 16)))
    acervo_directory = d2.get("paths", {}).get("acervo_directory", "dados/originais/acervo")
    required_calls = 0
    for strategy in strategies:
        chunk_cfg = d2.get("chunking", {}).get("strategies", {}).get(strategy)
        if chunk_cfg is None:
            raise ValueError(f"Estratégia sem configuração: {strategy}")
        chunks = chunk_corpus(strategy=strategy, size=int(chunk_cfg.get("size", 400)),
                              overlap=int(chunk_cfg.get("overlap", 80)), acervo_directory=acervo_directory)
        required_calls += math.ceil(len(chunks) / batch_size) + len(questions)
    maximum = int(d2.get("llm", {}).get("max_calls_per_run", 20))
    if required_calls > maximum:
        raise ValueError(f"Avaliação requer {required_calls} chamadas de embedding; limite configurado: {maximum}.")
    shared_client = client or create_embedding_client(cfg)
    if hasattr(shared_client, "begin_run"):
        shared_client.begin_run(maximum)
    per_strategy = []
    for strategy in strategies:
        chunk_cfg = d2.get("chunking", {}).get("strategies", {}).get(strategy)
        if chunk_cfg is None:
            raise ValueError(f"Estratégia sem configuração: {strategy}")
        # Coleções separadas permitem comparar chunking sem misturar vetores.
        collection_prefix = f"avaliacao_{strategy}"
        index_info = indexar_acervo(strategy=strategy, config=cfg, client=shared_client, collection_name=collection_prefix)
        rows = []
        hits = 0
        for question in questions:
            found = search_chunks(question["pergunta"], top_k=top_k, strategy=strategy, config=cfg,
                                  client=shared_client, collection_name=collection_prefix)
            expected = question.get("expected_chunk_ids", {}).get(strategy, [])
            returned = [item["chunk_id"] for item in found]
            hit = bool(set(expected).intersection(returned))
            hits += int(hit)
            rows.append({
                "question_id": question["id"], "question": question["pergunta"],
                "expected_chunk_ids": expected, "returned_chunk_ids": returned,
                "hit": hit,
                "retrieved": [{"chunk_id": item["chunk_id"], "distance": item["distance"],
                               "similarity": item["similarity"], "document_id": item["metadata"]["document_id"],
                               "page": item["metadata"].get("page"), "section": item["metadata"].get("section")}
                              for item in found],
            })
        per_strategy.append({
            "strategy": strategy, "unit": chunk_cfg.get("unit"), "size": chunk_cfg.get("size"),
            "overlap": chunk_cfg.get("overlap", 0), "embedding_model": embed_cfg.get("model"),
            "embedding_dimensions": embed_cfg.get("dimensions"), "top_k": top_k,
            "collection": index_info["collection"], "total_chunks": index_info["total_chunks"],
            "hits": hits, "denominator": 5, "accuracy": hits / 5, "results": rows,
        })
    report = {
        "schema_version": "retrieval-evaluation.v1",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "embedding_provider": embed_cfg.get("provider"), "embedding_model": embed_cfg.get("model"),
        "top_k": top_k,
        "metric_definition": "Acerto = pergunta com pelo menos um chunk de referência entre top-k; distância cosine; similaridade = 1 - distância.",
        "strategies": per_strategy,
        "preferred_strategy": None,
        "preference_decision": "pendente de revisão dos resultados e preservação de contexto; sem vencedor por intuição.",
    }
    output = Path(d2.get("paths", {}).get("retrieval_evaluation", "resultados/avaliacoes_recuperacao.json"))
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
