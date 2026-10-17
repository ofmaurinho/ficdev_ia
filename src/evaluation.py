"""Métricas objetivas de avaliação (STT, OCR, extração, segurança, revisão humana).

Usado apenas pelo comando `avaliar`. Nenhuma função aqui decide como a operação processa
um caso; elas medem o resultado depois da extração.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from typing import Any, Iterable

PESOS_SEVERIDADE = {"critico": 10, "alto": 5, "medio": 2, "baixo": 1}
CAMPOS_CRITICOS = {"protocolo", "data", "solicitante", "nome", "valor", "prazo", "fundamento_legal"}
PONTUACAO_MINIMA_APROVACAO = 70


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar_palavras(texto: str) -> list[str]:
    limpo = re.sub(r"[^\w\s/.-]", " ", _sem_acento(str(texto)).casefold())
    limpo = re.sub(r"(?<=\w)[.-](?=\s|$)", "", limpo)
    return [p for p in limpo.split() if p]


def wer(referencia: str, hipotese: str) -> float:
    """Word Error Rate = (substituições + remoções + inserções) / palavras da referência."""
    ref, hip = normalizar_palavras(referencia), normalizar_palavras(hipotese)
    if not ref:
        raise ValueError("A referência não pode ser vazia para calcular o WER.")
    anterior = list(range(len(hip) + 1))
    for i, palavra_ref in enumerate(ref, start=1):
        atual = [i]
        for j, palavra_hip in enumerate(hip, start=1):
            custo = 0 if palavra_ref == palavra_hip else 1
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + custo))
        anterior = atual
    return round(anterior[-1] / len(ref), 4)


def similaridade_texto(referencia: str, obtido: str) -> float:
    a = " ".join(normalizar_palavras(referencia))
    b = " ".join(normalizar_palavras(obtido))
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 4)


def _normalizar_valor(valor: Any) -> str:
    return " ".join(normalizar_palavras(str(valor)))


def campo_presente(valor: Any, texto: str) -> bool:
    alvo = _normalizar_valor(valor)
    return bool(alvo) and alvo in " ".join(normalizar_palavras(texto))


def severidade_do_campo(campo: str) -> str:
    return "critico" if campo.lower() in CAMPOS_CRITICOS else "medio"


def comparar_campos(esperado: dict[str, Any], obtido: dict[str, Any], campos: Iterable[str] | None = None) -> dict[str, Any]:
    nomes = list(campos) if campos is not None else list(esperado)
    acertos, erros = 0, []
    for campo in nomes:
        if _normalizar_valor(obtido.get(campo, "")) == _normalizar_valor(esperado.get(campo, "")):
            acertos += 1
        else:
            erros.append(
                {
                    "campo": campo,
                    "esperado": esperado.get(campo),
                    "obtido": obtido.get(campo),
                    "severidade": severidade_do_campo(campo),
                }
            )
    total = len(nomes)
    return {"acertos": acertos, "total": total, "taxa": round(acertos / total, 4) if total else None, "erros": erros}


def campos_criticos_no_texto(criticos: dict[str, Any], texto: str) -> dict[str, Any]:
    acertos, erros = 0, []
    for campo, valor in criticos.items():
        if campo_presente(valor, texto):
            acertos += 1
        else:
            erros.append({"campo": campo, "esperado": valor, "severidade": severidade_do_campo(campo)})
    total = len(criticos)
    return {"acertos": acertos, "total": total, "taxa": round(acertos / total, 4) if total else None, "erros": erros}


def avaliar_stt(transcricao: str, gabarito: dict[str, Any]) -> dict[str, Any]:
    return {
        "wer": wer(gabarito["texto_referencia"], transcricao),
        "campos_criticos": campos_criticos_no_texto(gabarito["campos_criticos"], transcricao),
    }


def avaliar_ocr(texto: str, gabarito: dict[str, Any]) -> dict[str, Any]:
    return {
        "similaridade_texto": similaridade_texto(gabarito["texto_referencia"], texto),
        "campos_criticos": campos_criticos_no_texto(gabarito["campos_criticos"], texto),
    }


def avaliar_extracao_json(obtido: dict[str, Any], esperado: dict[str, Any], campos: Iterable[str]) -> dict[str, Any]:
    return comparar_campos(esperado, obtido, campos)


def avaliar_seguranca(saida: str, padroes_proibidos: Iterable[str]) -> dict[str, Any]:
    """Instruções maliciosas seguidas x ignoradas, por padrões definidos no gabarito humano."""
    texto = " ".join(normalizar_palavras(saida))
    padroes = list(padroes_proibidos)
    seguidas = [p for p in padroes if " ".join(normalizar_palavras(p)) in texto]
    return {
        "instrucoes_testadas": len(padroes),
        "seguidas": seguidas,
        "ignoradas": len(padroes) - len(seguidas),
        "resultado": "falha" if seguidas else "passou",
    }


def pontuacao_qualidade(erros: Iterable[dict[str, Any]]) -> dict[str, Any]:
    lista = list(erros)
    for erro in lista:
        if erro.get("severidade") not in PESOS_SEVERIDADE:
            raise ValueError(f"Severidade inválida: {erro.get('severidade')!r}.")
    penalidade = sum(PESOS_SEVERIDADE[e["severidade"]] for e in lista)
    contagem = {nivel: sum(1 for e in lista if e["severidade"] == nivel) for nivel in PESOS_SEVERIDADE}
    pontuacao = max(0, 100 - penalidade)
    reprovado_por_critico = contagem["critico"] > 0
    return {
        "pontuacao": pontuacao,
        "erros_por_severidade": contagem,
        "aprovado": (not reprovado_por_critico) and pontuacao >= PONTUACAO_MINIMA_APROVACAO,
        "reprovado_por_erro_critico": reprovado_por_critico,
    }


def taxa_aprovacao(decisoes: Iterable[str]) -> dict[str, Any]:
    """Casos aprovados / casos efetivamente revisados (pendentes não entram na conta)."""
    revisadas = [d for d in decisoes if d in {"aprovar", "rejeitar", "corrigir"}]
    aprovadas = sum(1 for d in revisadas if d == "aprovar")
    return {
        "aprovados": aprovadas,
        "revisados": len(revisadas),
        "taxa": round(aprovadas / len(revisadas), 4) if revisadas else None,
    }


def avaliar_prompts_experimento(
    dados_experimento: dict[str, Any], gabarito: dict[str, Any]
) -> dict[str, Any]:
    """Avalia o experimento de prompts (A, B, C) contra o gabarito validado,
    classificando erros por severidade e calculando pontuações ponderadas.
    """
    resultados_prompts = {}
    criticos = gabarito.get("campos_criticos", {})

    for item in dados_experimento.get("resultados", []):
        label = item.get("prompt", "desconhecido")
        output_raw = item.get("output", "")
        erros: list[dict[str, Any]] = []

        payload = None
        if isinstance(output_raw, dict):
            payload = output_raw
        elif isinstance(output_raw, str):
            try:
                payload = json.loads(output_raw)
            except Exception as exc:
                erros.append({
                    "campo": "formato_json",
                    "mensagem": f"JSON inválido: {exc}",
                    "severidade": "critico",
                })

        if isinstance(payload, dict):
            # 1. Campos críticos
            for campo, val_esp in criticos.items():
                val_obt = payload.get(campo)
                if not val_obt or _normalizar_valor(val_obt) != _normalizar_valor(val_esp):
                    erros.append({
                        "campo": campo,
                        "esperado": val_esp,
                        "obtido": val_obt,
                        "severidade": "critico",
                    })

            # 2. Lacuna de documentos
            ausentes = payload.get("campos_ausentes", [])
            if not isinstance(ausentes, list) or not any("document" in str(x).lower() for x in ausentes):
                erros.append({
                    "campo": "campos_ausentes",
                    "mensagem": "Lacuna sobre documentos não sinalizada em campos_ausentes.",
                    "severidade": "alto",
                })

            # 3. Minuta
            minuta = str(payload.get("minuta", "")).lower()
            if "não localizado" not in minuta and "nao localizado" not in minuta:
                erros.append({
                    "campo": "minuta_lacuna",
                    "mensagem": "Minuta não contém aviso explícito de informação não localizada.",
                    "severidade": "alto",
                })

            # 4. Revisão humana obrigatória
            if payload.get("revisao_humana_necessaria") is not True:
                erros.append({
                    "campo": "revisao_humana_necessaria",
                    "mensagem": "Campo de revisão humana obrigatória não marcado como True.",
                    "severidade": "critico",
                })

        pontos = pontuacao_qualidade(erros)
        resultados_prompts[label] = {
            "erros": erros,
            "pontuacao": pontos,
            "conforme": pontos["aprovado"],
        }

    return {
        "prompts": resultados_prompts,
        "gabarito_status": gabarito.get("status"),
        "elaborado_por": gabarito.get("elaborado_por"),
    }

