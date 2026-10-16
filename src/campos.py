"""Proveniência por campo crítico (protocolo, solicitante, data).

Cada campo guarda valor, origem, hash da origem, página (ou trecho de tempo), método e status.
A minuta cita os campos DAQUI, não do texto corrigido por IA. O texto corrigido nunca
substitui o original.

Status:
- ausente: não localizado em nenhuma rota; NÃO bloqueia a minuta (vira "não localizado");
- extraido: valor encontrado; se veio de STT/OCR, aguarda conferência humana;
- incerto / divergente: valor duvidoso ou discordante entre rotas; bloqueia até confirmação;
- confirmado_humano: conferido por um operador.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.text_processing import _find_date, _find_protocol, _find_solicitante

NAO_LOCALIZADO = "não localizado"
CAMPOS_CRITICOS_PADRAO = ("protocolo", "data", "solicitante")
METODOS = {"tesseract", "vision", "stt", "texto_original", "correcao_humana"}
STATUS = {"ausente", "extraido", "incerto", "divergente", "confirmado_humano"}


class CampoError(Exception):
    """Campo desconhecido ou operação inválida sobre um campo."""


def _data_valida(valor: str) -> bool:
    partes = valor.replace("-", "/").split("/")
    if len(partes) != 3:
        return False
    try:
        dia, mes, ano = (int(p) for p in partes)
        ano = ano + 2000 if ano < 100 else ano
        datetime(ano, mes, dia)
    except ValueError:
        return False
    return True


def extrair_campos(
    texto: str,
    *,
    origem: str,
    origem_sha256: str | None,
    metodo: str,
    pagina: int | None = None,
    trecho_tempo: dict[str, float] | None = None,
    incertos: Iterable[str] = (),
) -> dict[str, dict[str, Any]]:
    """Extrai os campos críticos do texto BRUTO e registra sua origem."""
    if metodo not in METODOS:
        raise CampoError(f"Método desconhecido: {metodo}.")
    suspeitos = set(incertos)
    encontrados = {
        "protocolo": _find_protocol(texto),
        "data": _find_date(texto),
        "solicitante": _find_solicitante(texto),
    }
    campos: dict[str, dict[str, Any]] = {}
    for nome in CAMPOS_CRITICOS_PADRAO:
        valor = encontrados[nome]
        if not valor:
            campos[nome] = {"valor": NAO_LOCALIZADO, "status": "ausente"}
            continue
        status = "extraido"
        if nome in suspeitos or (nome == "data" and not _data_valida(valor)):
            status = "incerto"
        item: dict[str, Any] = {
            "valor": valor,
            "origem": origem,
            "origem_sha256": origem_sha256,
            "metodo": metodo,
            "status": status,
        }
        if pagina is not None:
            item["pagina"] = pagina
        if trecho_tempo:
            item["trecho_tempo"] = trecho_tempo
        campos[nome] = item
    return campos


def comparar_rotas(
    principal: dict[str, dict[str, Any]], alternativa: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Depois do Vision: marca como divergente qualquer campo que as duas rotas não confirmem."""
    resultado = {nome: dict(item) for nome, item in principal.items()}
    for nome, item in resultado.items():
        outro = alternativa.get(nome, {})
        if item["status"] == "ausente" and outro.get("status") == "ausente":
            continue
        if item["status"] == "ausente" or outro.get("status") == "ausente" or item["valor"] != outro.get("valor"):
            item["status"] = "divergente"
            item["valor_alternativo"] = outro.get("valor", NAO_LOCALIZADO)
            item["metodo_alternativo"] = outro.get("metodo")
            if item["status"] == "divergente" and "origem" not in item:
                item.update({k: outro[k] for k in ("origem", "origem_sha256", "metodo") if k in outro})
    return resultado


def precisa_confirmacao(item: dict[str, Any]) -> bool:
    if item["status"] in {"incerto", "divergente"}:
        return True
    # Valor extraído por STT/OCR deve ser conferido por humano (RF06/RF08).
    return item["status"] == "extraido" and item.get("metodo") != "texto_original"


def campos_pendentes(campos: dict[str, dict[str, Any]]) -> list[str]:
    return [nome for nome, item in campos.items() if precisa_confirmacao(item)]


def confirmar_campo(
    campos: dict[str, dict[str, Any]], nome: str, operador: str, valor_corrigido: str | None = None
) -> dict[str, Any]:
    if nome not in campos:
        raise CampoError(f"Campo desconhecido: {nome}.")
    if not (operador or "").strip():
        raise CampoError("Informe o operador que confirma o campo.")
    item = campos[nome]
    if item["status"] == "ausente" and not valor_corrigido:
        raise CampoError(f"O campo {nome} está ausente; informe o valor correto para confirmá-lo.")
    if valor_corrigido is not None and valor_corrigido.strip() != item["valor"]:
        item["valor_extraido_original"] = item["valor"]
        item["valor"] = valor_corrigido.strip()
        item["metodo"] = "correcao_humana"
    item["status"] = "confirmado_humano"
    item["confirmado_por"] = operador.strip()
    item["confirmado_em"] = datetime.now(timezone.utc).isoformat()
    item.pop("valor_alternativo", None)
    return item


def salvar_campos(path: Path | str, campos: dict[str, dict[str, Any]]) -> Path:
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps(campos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, destino)
    return destino


def carregar_campos(path: Path | str) -> dict[str, dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
