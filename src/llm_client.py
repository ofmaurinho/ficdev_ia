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


class CallLimitExceededError(APIClientError):
    """Limite de chamadas reais configurado para a execução foi atingido."""


def _sanitize_exception_message(message: str) -> str:
    lowered = (message or "").lower()
    if "incorrect api key" in lowered or "authentication" in lowered or "unauthorized" in lowered:
        return "autenticacao"
    if "rate limit" in lowered or "ratelimit" in lowered or "quota" in lowered or "too many requests" in lowered or "429" in lowered:
        return "limite"
    if "timeout" in lowered or "timed out" in lowered or "deadline" in lowered:
        return "timeout"
    if (
        "connection" in lowered
        or "network" in lowered
        or "unavailable" in lowered
        or "internalservererror" in lowered
        or "overloaded" in lowered
        or "503" in lowered
    ):
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
        max_calls_per_run: int | None = None,
    ):
        if api_key is None:
            resolved_api_key = os.getenv("OPENAI_API_KEY")
        else:
            resolved_api_key = api_key

        self.api_key = resolved_api_key.strip() if isinstance(resolved_api_key, str) else resolved_api_key
        self.model = model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self.timeout = timeout
        self.temperature = temperature
        if max_calls_per_run is not None and max_calls_per_run < 1:
            raise ValueError("max_calls_per_run deve ser pelo menos 1.")
        self.max_calls_per_run = max_calls_per_run
        self.api_calls_made = 0
        if not self.api_key:
            raise MissingAPIKeyError(
                "A chave da API da OpenAI não foi configurada. Adicione OPENAI_API_KEY ao arquivo .env antes de usar o provedor."
            )

        try:
            from openai import OpenAI

            sdk_options = {"api_key": self.api_key, "timeout": self.timeout}
            # Desativa repetições internas para que cada tentativa seja contabilizada pelo projeto.
            if self.max_calls_per_run is not None:
                sdk_options["max_retries"] = 0
            self.client = OpenAI(**sdk_options)
        except Exception as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("Não foi possível importar ou inicializar o SDK oficial da OpenAI.") from exc

    def begin_run(self, max_calls: int | None = None) -> None:
        """Inicia um orçamento explícito; as tentativas feitas pelos serviços são contabilizadas."""
        if max_calls is not None and max_calls < 1:
            raise ValueError("max_calls_per_run deve ser pelo menos 1.")
        self.max_calls_per_run = max_calls
        self.api_calls_made = 0

    def _reserve_call(self) -> None:
        if self.max_calls_per_run is not None and self.api_calls_made >= self.max_calls_per_run:
            raise CallLimitExceededError("Limite de chamadas da execução atingido.")
        self.api_calls_made += 1

    def _raise_for_error(self, exc: Exception) -> None:
        if isinstance(exc, TimeoutError):
            raise RequestTimeoutError("A requisição excedeu o tempo limite do provedor.") from exc
        if getattr(exc, "param", None) == "model" or getattr(exc, "code", None) in {"model_not_found", "invalid_model"}:
            raise InvalidModelError("O modelo configurado não é aceito ou não está disponível no provedor.") from exc
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
            self._reserve_call()
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

    def parse_structured(
        self,
        *,
        prompt: str,
        system_prompt: str,
        text_format: type,
        max_output_tokens: int = 2000,
        reasoning_effort: str | None = None,
    ) -> Dict[str, Any]:
        """Executa Responses.parse e rejeita recusa, saída incompleta ou sem objeto tipado."""
        if not prompt.strip():
            raise ValueError("O prompt para saída estruturada não pode estar vazio.")
        started_at = time.perf_counter()
        request: dict[str, Any] = {
            "model": self.model,
            "instructions": system_prompt,
            "input": prompt,
            "text_format": text_format,
            "max_output_tokens": int(max_output_tokens),
        }
        if reasoning_effort:
            request["reasoning"] = {"effort": reasoning_effort}
        try:
            self._reserve_call()
            response = self.client.responses.parse(**request)
            status = getattr(response, "status", None)
            if status == "incomplete" or getattr(response, "incomplete_details", None):
                raise StructuredOutputError("A resposta estruturada foi interrompida antes de concluir.")
            for item in getattr(response, "output", []) or []:
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "type", None) == "refusal":
                        raise StructuredOutputError("O provedor recusou a solicitação.")
            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                raise EmptyResponseError("A API não retornou objeto estruturado utilizável.")
            return {
                "parsed": parsed,
                "metadata": self._metadata(response, started_at, self.model, status=status),
            }
        except APIClientError:
            raise
        except Exception as exc:
            self._raise_for_error(exc)
            raise AssertionError("Erro de integração não tratado.")

    def create_embeddings(
        self,
        texts: list[str],
        *,
        model: str,
        dimensions: int | None = None,
    ) -> Dict[str, Any]:
        """Calcula vetores explicitamente; não há embedding implícito no ChromaDB."""
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("O lote de embeddings deve conter textos não vazios.")
        started_at = time.perf_counter()
        request: dict[str, Any] = {"model": model, "input": texts}
        if dimensions is not None:
            request["dimensions"] = int(dimensions)
        try:
            self._reserve_call()
            response = self.client.embeddings.create(**request)
            vectors = [list(item.embedding) for item in response.data]
            if len(vectors) != len(texts) or (dimensions is not None and any(len(vector) != dimensions for vector in vectors)):
                raise StructuredOutputError("Quantidade ou dimensão dos embeddings diverge da configuração.")
            return {
                "vectors": vectors,
                "metadata": self._metadata(response, started_at, model),
            }
        except APIClientError:
            raise
        except Exception as exc:
            self._raise_for_error(exc)
            raise AssertionError("Erro de integração não tratado.")

    # ------------------------------------------------------------------ multimodal
    def _executar(self, chamada):
        """Executa uma chamada ao SDK traduzindo falhas para as exceções do projeto."""
        try:
            self._reserve_call()
            return chamada()
        except APIClientError:
            raise
        except Exception as exc:
            self._raise_for_error(exc)
            raise AssertionError("Erro de integração não tratado.")

    @staticmethod
    def _usage_dict(response: Any) -> dict:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        if hasattr(usage, "model_dump"):
            return dict(usage.model_dump())
        return dict(getattr(usage, "__dict__", {}))

    def _metadata(self, response: Any, started_at: float, model: str, **extra: Any) -> Dict[str, Any]:
        metadata = {
            "provider": "openai",
            "model": model,
            "duration_seconds": round(time.perf_counter() - started_at, 3),
            "response_id": getattr(response, "id", None),
            "usage": self._usage_dict(response),
            "api_calls_made": self.api_calls_made,
            "custo_estimado": None,
        }
        metadata.update(extra)
        return metadata

    def transcribe(
        self,
        path: str,
        *,
        model: str = "gpt-4o-transcribe",
        language: Optional[str] = "pt",
        prompt: Optional[str] = None,
        response_format: str = "json",
    ) -> Dict[str, Any]:
        """Speech-to-text. Devolve a transcrição bruta, sem nenhuma revisão."""
        started_at = time.perf_counter()

        def chamada():
            with open(path, "rb") as handle:
                kwargs: Dict[str, Any] = {"model": model, "file": handle, "response_format": response_format}
                if language:
                    kwargs["language"] = language
                if prompt:
                    kwargs["prompt"] = prompt
                return self.client.audio.transcriptions.create(**kwargs)

        response = self._executar(chamada)
        text = response if isinstance(response, str) else getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise EmptyResponseError("A transcrição retornou vazia.")
        return {"text": text.strip(), "metadata": self._metadata(response, started_at, model, language=language)}

    def speak(
        self,
        text: str,
        out_path: str,
        *,
        model: str = "gpt-4o-mini-tts",
        voice: str = "alloy",
        instructions: Optional[str] = None,
        response_format: str = "mp3",
    ) -> Dict[str, Any]:
        """Text-to-speech. O texto é enviado exatamente como recebido (sem reescrita)."""
        if not text or not text.strip():
            raise ValueError("O texto para síntese de voz não pode estar vazio.")
        started_at = time.perf_counter()
        kwargs: Dict[str, Any] = {"model": model, "voice": voice, "input": text, "response_format": response_format}
        if instructions:
            kwargs["instructions"] = instructions
        response = self._executar(lambda: self.client.audio.speech.create(**kwargs))
        content = getattr(response, "content", None)
        if content is None and hasattr(response, "read"):
            content = response.read()
        if not content:
            raise EmptyResponseError("A síntese de voz retornou áudio vazio.")
        import pathlib

        destino = pathlib.Path(out_path)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(content)
        return {
            "path": str(destino),
            "metadata": self._metadata(
                response,
                started_at,
                model,
                voice=voice,
                instructions=instructions,
                formato=response_format,
                caracteres_enviados=len(text),
                bytes_audio=len(content),
            ),
        }

    def describe_image(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        system_prompt: str = "",
        mime: str = "image/png",
        max_output_tokens: int = 1500,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Visão multimodal: devolve o texto produzido pelo modelo para a imagem."""
        if not image_bytes:
            raise ValueError("A imagem enviada está vazia.")
        if not prompt or not prompt.strip():
            raise ValueError("O prompt de visão não pode estar vazio.")
        import base64

        modelo = model or self.model
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        mensagens = []
        if system_prompt.strip():
            mensagens.append({"role": "system", "content": system_prompt})
        mensagens.append(
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        )
        started_at = time.perf_counter()
        response = self._executar(
            lambda: self.client.responses.create(
                model=modelo,
                input=mensagens,
                max_output_tokens=max_output_tokens,
                temperature=self.temperature,
            )
        )
        return {
            "text": self._coerce_response_text(response),
            "metadata": self._metadata(response, started_at, modelo, bytes_imagem=len(image_bytes)),
        }

    def generate_image(
        self,
        prompt: str,
        *,
        model: str,
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> Dict[str, Any]:
        """Gera uma imagem nova. Devolve os bytes PNG decodificados."""
        if not prompt or not prompt.strip():
            raise ValueError("O prompt de imagem não pode estar vazio.")
        import base64

        started_at = time.perf_counter()
        response = self._executar(
            lambda: self.client.images.generate(model=model, prompt=prompt, size=size, quality=quality, n=1)
        )
        dados = getattr(response, "data", None)
        b64 = getattr(dados[0], "b64_json", None) if dados else None
        if not b64:
            raise EmptyResponseError("A geração de imagem retornou sem conteúdo.")
        return {
            "image_bytes": base64.b64decode(b64),
            "metadata": self._metadata(
                response,
                started_at,
                model,
                size=size,
                quality=quality,
                revised_prompt=getattr(dados[0], "revised_prompt", None),
            ),
        }
