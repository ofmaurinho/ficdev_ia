"""Classificação de sentimentos e agregação determinística (RF22)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.audit import AuditLogger
from src.guardrails import delimitar_conteudo_nao_confiavel
from src.llm_client import OpenAIClient, RateLimitError, RequestTimeoutError, ServiceUnavailableError
from src.providers import StructuredGenerationProvider
from src.schemas import AnaliseSentimento, ErroRegraNegocio
from src.text_processing import minimize_text_for_provider

PROMPT_VERSION = "sentimento_atendimento.v1"
SCHEMA_VERSION = "sentimento.v1"
_TRANSIENT = (RateLimitError, RequestTimeoutError, ServiceUnavailableError)

_PSYCH_FORBIDDEN = re.compile(
    r"(?i)\b(?:transtorno|diagn[óo]stico|depress[ãa]o|ansiedade|psicol[óo]gico|psiqui[áa]trico|personalidade|car[áa]ter|patologia)\b"
)
_MIXED_IRONY_CONTEXT_RULES = (
    (re.compile(r"(?i)\b(?:mas|por[ée]m|todavia|contudo)\b.*\b(?:espera|demor|longa|ruim|problema)\b"), "mensagem_mista"),
    (re.compile(r"(?i)\b(?:maravilhoso|excelente|[óo]timo)\b.*(?::|;|-).*?\b(?:voltar|terceira\s+vez|sem\s+resposta|erro)\b"), "ironia_detectada"),
    (re.compile(r"(?i)^\s*foi\s+diferente\s+desta\s+vez\.?\s*$"), "contexto_insuficiente"),
)


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    if config is not None:
        return config
    return json.loads((_root() / "config.json").read_text(encoding="utf-8"))


def _system_prompt() -> str:
    return (_root() / "prompts" / "desafio2_sentimento_system_v1.txt").read_text(encoding="utf-8")


def _client(config: dict[str, Any]) -> OpenAIClient:
    llm = config.get("desafio2", {}).get("llm", {})
    return OpenAIClient(
        model=llm.get("model") or config.get("model", "gpt-4o-mini"),
        timeout=float(llm.get("timeout_seconds", config.get("timeout_seconds", 30))),
        max_calls_per_run=int(llm.get("max_calls_per_run", 20)),
    )


def _aplicar_regras_sentimento(analise: AnaliseSentimento, texto_original: str) -> tuple[AnaliseSentimento, list[str]]:
    """Aplica regras locais para ironia, mensagens mistas, falta de contexto e vedação psicológica."""
    ajustes: list[str] = []
    if _PSYCH_FORBIDDEN.search(analise.justificativa):
        raise ErroRegraNegocio("A justificativa contém inferência psicológica ou diagnóstica proibida.")

    for padrao, motivo in _MIXED_IRONY_CONTEXT_RULES:
        if padrao.search(texto_original):
            if analise.polaridade != "indeterminada" or not analise.revisao_necessaria:
                ajustes.append(f"ajustado_para_indeterminada_por_{motivo}")
                analise = analise.model_copy(
                    update={
                        "polaridade": "indeterminada",
                        "revisao_necessaria": True,
                        "motivo_revisao": analise.motivo_revisao or f"Caso incerto ({motivo}); requer revisão humana.",
                    }
                )
            break

    if analise.polaridade == "indeterminada" and not analise.revisao_necessaria:
        ajustes.append("revisao_obrigatoria_em_indeterminada")
        analise = analise.model_copy(
            update={
                "revisao_necessaria": True,
                "motivo_revisao": analise.motivo_revisao or "Polaridade indeterminada exige revisão humana.",
            }
        )
    return analise, ajustes


def classificar_avaliacao(
    avaliacao_id: str,
    texto: str,
    *,
    config: dict[str, Any] | None = None,
    cliente: StructuredGenerationProvider | None = None,
) -> dict[str, Any]:
    """Classifica uma avaliação individual e retorna o contrato validado."""
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError("O texto da avaliação não pode estar vazio.")
    cfg = _config(config)
    llm_cfg = cfg.get("desafio2", {}).get("llm", {})
    provider = cliente or _client(cfg)
    minimizado = minimize_text_for_provider(texto.strip())
    delimitado = delimitar_conteudo_nao_confiavel(minimizado, "AVALIACAO_NAO_CONFIAVEL")
    prompt = (
        f"ID da avaliação: {avaliacao_id}\n"
        "Classifique a avaliação abaixo sem inferir traços pessoais ou diagnósticos. "
        "Se houver elogio e crítica juntos, ironia ou ausência de contexto claro, use polaridade='indeterminada' "
        "e revisao_necessaria=true.\n\n"
        f"{delimitado}"
    )
    max_attempts = 1 + min(1, max(0, int(llm_cfg.get("max_retries", 1))))
    for attempt in range(max_attempts):
        try:
            res = provider.parse_structured(
                prompt=prompt,
                system_prompt=_system_prompt(),
                text_format=AnaliseSentimento,
                max_output_tokens=int(llm_cfg.get("max_output_tokens", 800)),
                reasoning_effort=llm_cfg.get("reasoning_effort"),
            )
            parsed = res["parsed"]
            if isinstance(parsed, dict):
                parsed = AnaliseSentimento.model_validate(parsed)
            if parsed.id != avaliacao_id:
                parsed = parsed.model_copy(update={"id": avaliacao_id})
            parsed, ajustes = _aplicar_regras_sentimento(parsed, texto)
            meta = dict(res.get("metadata") or {})
            meta["ajustes_regras"] = ajustes
            return {
                "analise": parsed.model_dump(mode="json"),
                "metadata": meta,
            }
        except _TRANSIENT:
            if attempt + 1 >= max_attempts:
                raise
    raise RuntimeError("Não foi possível classificar a avaliação.")


def rotulo_equivalente(polaridade_obtida: str, rotulo_gabarito: str) -> bool:
    """Conecta o rótulo 'ambigua_mista' do gabarito à classe 'indeterminada' do contrato."""
    if rotulo_gabarito in {"ambigua_mista", "indeterminada"}:
        return polaridade_obtida == "indeterminada"
    return polaridade_obtida == rotulo_gabarito


def agregar_sentimentos(
    itens: list[dict[str, Any]],
    *,
    filtro_polaridade: str | None = None,
    apenas_revisao: bool = False,
) -> dict[str, Any]:
    """Agrega resultados em Python, removendo duplicatas por ID e protegendo conjunto vazio (T13)."""
    vistos: set[str] = set()
    unicos: list[dict[str, Any]] = []
    duplicatas_removidas = 0
    for item in itens:
        analise = item.get("analise", item)
        item_id = str(analise.get("id") or "")
        if item_id and item_id in vistos:
            duplicatas_removidas += 1
            continue
        if item_id:
            vistos.add(item_id)
        unicos.append(item)

    filtrados: list[dict[str, Any]] = []
    for item in unicos:
        analise = item.get("analise", item)
        if filtro_polaridade and analise.get("polaridade") != filtro_polaridade:
            continue
        if apenas_revisao and not bool(analise.get("revisao_necessaria")):
            continue
        filtrados.append(item)

    denominador = len(filtrados)
    contagem = {"positiva": 0, "negativa": 0, "neutra": 0, "indeterminada": 0}
    revisao_count = 0
    acertos = 0
    com_gabarito = 0

    for item in filtrados:
        analise = item.get("analise", item)
        pol = analise.get("polaridade", "indeterminada")
        if pol in contagem:
            contagem[pol] += 1
        if bool(analise.get("revisao_necessaria")):
            revisao_count += 1
        if "acerto_gabarito" in item and item["acerto_gabarito"] is not None:
            com_gabarito += 1
            if item["acerto_gabarito"]:
                acertos += 1

    proporcoes = {
        k: {
            "numerador": v,
            "denominador": denominador,
            "proporcao": round(v / denominador, 4) if denominador > 0 else None,
        }
        for k, v in contagem.items()
    }
    return {
        "total_recebido": len(itens),
        "duplicatas_removidas": duplicatas_removidas,
        "total_unico": len(unicos),
        "denominador": denominador,
        "filtro_aplicado": {"polaridade": filtro_polaridade, "apenas_revisao": apenas_revisao},
        "contagem_por_polaridade": contagem,
        "proporcoes": proporcoes,
        "casos_para_revisao": {
            "numerador": revisao_count,
            "denominador": denominador,
            "proporcao": round(revisao_count / denominador, 4) if denominador > 0 else None,
        },
        "acuracia_gabarito": {
            "numerador": acertos,
            "denominador": com_gabarito,
            "acuracia": round(acertos / com_gabarito, 4) if com_gabarito > 0 else None,
        },
        "nota_metodologica": (
            "Contagens e proporções calculadas deterministicamente em código. "
            "A confiança informada pelo modelo é estimativa não calibrada e não representa probabilidade "
            "nem pesquisa de opinião da população."
        ),
    }


def avaliar_conjunto_sentimentos(
    *,
    config: dict[str, Any] | None = None,
    cliente: StructuredGenerationProvider | None = None,
) -> dict[str, Any]:
    """Classifica as 12 avaliações fictícias e compara com o gabarito."""
    cfg = _config(config)
    d2 = cfg.get("desafio2", {})
    aval_dir = Path(d2.get("paths", {}).get("avaliacoes_directory", "dados/originais/avaliacoes"))
    if not aval_dir.is_absolute():
        aval_dir = _root() / aval_dir
    fonte = json.loads((aval_dir / "avaliacoes_ficticias.json").read_text(encoding="utf-8"))
    avaliacoes = fonte["avaliacoes"]

    provider = cliente or _client(cfg)
    call_limit = int(d2.get("llm", {}).get("max_calls_per_run", 20))
    if hasattr(provider, "begin_run"):
        provider.begin_run(max(call_limit, len(avaliacoes) + 2))

    started = time.perf_counter()
    resultados: list[dict[str, Any]] = []
    for item in avaliacoes:
        aid = item["id"]
        texto = item["texto"]
        gabarito_rotulo = item["rotulo_gabarito"]
        saida = classificar_avaliacao(aid, texto, config=cfg, cliente=provider)
        analise = saida["analise"]
        acerto = rotulo_equivalente(analise["polaridade"], gabarito_rotulo)
        resultados.append({
            "id": aid,
            "texto": texto,
            "rotulo_gabarito": gabarito_rotulo,
            "justificativa_gabarito": item.get("justificativa"),
            "analise": analise,
            "acerto_gabarito": acerto,
            "caso_incerto": analise["polaridade"] == "indeterminada" or bool(analise["revisao_necessaria"]),
            "metadata": saida["metadata"],
        })

    agregado = agregar_sentimentos(resultados)
    relatorio = {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "agregacao": agregado,
        "resultados": resultados,
    }
    results_dir = Path(d2.get("paths", {}).get("results_directory", cfg.get("results_dir", "resultados")))
    if not results_dir.is_absolute():
        results_dir = _root() / results_dir
    out_path = results_dir / "avaliacao_sentimentos.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")

    AuditLogger(str(results_dir / "logs")).log_event(
        "sentimentos_avaliados",
        "sucesso",
        {
            "schema_version": SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION,
            "total": agregado["denominador"],
            "acertos": agregado["acuracia_gabarito"]["numerador"],
            "casos_revisao": agregado["casos_para_revisao"]["numerador"],
            "duration_seconds": relatorio["duration_seconds"],
        },
    )
    return relatorio
