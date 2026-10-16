"""Cliente para integração com a API oficial da OpenAI.

O módulo mantém os parâmetros configuráveis e trata falhas locais de autenticação,
timeout, indisponibilidade, resposta vazia e entradas inválidas sem expor segredos.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()


class APIClientError(Exception):
    """Erro genérico do cliente da API."""


class MissingAPIKeyError(APIClientError):
    """Chave da API ausente."""


class AuthenticationError(APIClientError):
    """Falha de autenticação na API."""


class RateLimitError(APIClientError):
    """Limite de requisição atingido."""


class ServiceUnavailableError(APIClientError):
    """Serviço indisponível no provedor."""


class RequestTimeoutError(APIClientError):
    """Tempo limite excedido."""


class EmptyResponseError(APIClientError):
    """Resposta vazia do provedor."""


class InvalidModelError(APIClientError):
    """Modelo ou parâmetros inválidos."""


class StructuredOutputError(APIClientError):
    """Falha ao interpretar a saída estruturada."""


def _sanitize_exception_message(message: str) -> str:
    lowered = (message or "").lower()
    if "incorrect api key" in lowered or "authentication" in lowered or "unauthorized" in lowered:
        return "autenticacao"
    if "rate limit" in lowered or "quota" in lowered or "too many requests" in lowered:
        return "limite"
    if "timeout" in lowered or "timed out" in lowered or "deadline" in lowered:
        return "timeout"
    if "connection" in lowered or "network" in lowered or "unavailable" in lowered:
        return "indisponibilidade"
    if "model" in lowered and "invalid" in lowered:
        return "modelo"
    return "api"


DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class OpenAIClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        temperature: float = 0,
    ):
        if api_key is None:
            resolved_api_key = os.getenv("OPENAI_API_KEY")
        else:
            resolved_api_key = api_key

        self.api_key = resolved_api_key.strip() if isinstance(resolved_api_key, str) else resolved_api_key
        self.model = model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self.timeout = timeout
        self.temperature = temperature
        if not self.api_key:
            raise MissingAPIKeyError(
                "A chave da API da OpenAI não foi configurada. Adicione OPENAI_API_KEY ao arquivo .env antes de usar o provedor."
            )

        try:
            from openai import OpenAI

            self.client = OpenAI(api_key=self.api_key, timeout=self.timeout)
        except Exception as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("Não foi possível importar ou inicializar o SDK oficial da OpenAI.") from exc

    def _raise_for_error(self, exc: Exception) -> None:
        if isinstance(exc, TimeoutError):
            raise RequestTimeoutError("A requisição excedeu o tempo limite do provedor.") from exc
        label = _sanitize_exception_message(f"{type(exc).__name__}: {exc}")
        if label == "autenticacao":
            raise AuthenticationError("Falha de autenticação no provedor. Verifique a chave configurada.") from exc
        if label == "limite":
            raise RateLimitError("O provedor respondeu que o limite de requisições foi excedido.") from exc
        if label == "timeout":
            raise RequestTimeoutError("A requisição excedeu o tempo limite do provedor.") from exc
        if label == "indisponibilidade":
            raise ServiceUnavailableError("O serviço da OpenAI não está disponível no momento.") from exc
        if label == "modelo":
            raise InvalidModelError("Modelo ou parâmetro inválido para o provedor atual.") from exc
        raise APIClientError("Falha na integração com a API da OpenAI.") from exc

    def _coerce_response_text(self, response: Any) -> str:
        if response is None:
            raise EmptyResponseError("A API retornou resposta vazia.")

        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output = getattr(response, "output", None)
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                content = getattr(item, "content", None)
                if isinstance(content, list):
                    for part in content:
                        text = getattr(part, "text", None)
                        if isinstance(text, str) and text.strip():
                            chunks.append(text.strip())
                elif hasattr(item, "text") and isinstance(item.text, str):
                    chunks.append(item.text.strip())
            combined = "\n".join(filter(None, chunks))
            if combined:
                return combined

        raise EmptyResponseError("A API retornou conteúdo sem texto útil para processamento.")

    def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        max_output_tokens: int = 1500,
        json_mode: bool = False,
        json_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not prompt or not prompt.strip():
            raise ValueError("O prompt para geração de texto não pode estar vazio.")

        started_at = time.perf_counter()
        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            request = {
                "model": self.model,
                "input": messages,
                "max_output_tokens": max_output_tokens,
                "temperature": self.temperature,
            }
            if json_schema is not None:
                request["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": "institutional_request",
                        "strict": True,
                        "schema": json_schema,
                    }
                }
            elif json_mode:
                request["text"] = {"format": {"type": "json_object"}}
            response = self.client.responses.create(**request)
            text = self._coerce_response_text(response)
            usage = getattr(response, "usage", None)
            duration = time.perf_counter() - started_at
            metadata = {
                "provider": "openai",
                "model": self.model,
                "duration_seconds": round(duration, 3),
                "response_id": getattr(response, "id", None),
                "usage": dict(getattr(usage, "model_dump", lambda: {})()) if hasattr(usage, "model_dump") else getattr(usage, "__dict__", {}),
                "custo_estimado": None,
            }
            return {"text": text, "metadata": metadata}
        except Exception as exc:
            if isinstance(exc, (APIClientError, MissingAPIKeyError, AuthenticationError, RateLimitError, ServiceUnavailableError, RequestTimeoutError, EmptyResponseError, InvalidModelError, StructuredOutputError)):
                raise
            self._raise_for_error(exc)
            raise AssertionError("Erro de integração não tratado.")
