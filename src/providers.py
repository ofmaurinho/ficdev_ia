"""Contratos estruturais para injetar provedores sem acoplar serviços à OpenAI."""

from __future__ import annotations

from typing import Any, Protocol


class StructuredGenerationProvider(Protocol):
    def parse_structured(
        self,
        *,
        prompt: str,
        system_prompt: str,
        text_format: type,
        max_output_tokens: int = 2000,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]: ...


class EmbeddingProvider(Protocol):
    def create_embeddings(
        self,
        texts: list[str],
        *,
        model: str,
        dimensions: int | None = None,
    ) -> dict[str, Any]: ...


class RetrievalGenerationProvider(StructuredGenerationProvider, EmbeddingProvider, Protocol):
    """Provider usado por um fluxo que precisa executar retrieval e geração estruturada."""

    api_calls_made: int

    def begin_run(self, max_calls: int | None = None) -> None: ...
