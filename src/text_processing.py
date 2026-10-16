"""Processamento textual e extração estruturada para solicitações institucionais."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

ALLOWED_CATEGORIES = {
    "informacao",
    "solicitacao_servico",
    "reclamacao",
    "sugestao",
    "elogio",
    "outros",
    "nao_classificado",
}


def normalize_text(text: str) -> str:
    if text is None:
        raise ValueError("O texto de entrada não pode ser nulo.")
    value = str(text).strip()
    if not value:
        raise ValueError("O texto de entrada está vazio.")
    sanitized = re.sub(r"(?i)(api[_ -]?key|jwt|senha|token|secret)", "[redacted]", value)
    return re.sub(r"\s+", " ", sanitized)


def minimize_text_for_provider(text: str) -> str:
    """Remove identificadores pessoais não necessários antes de uma chamada externa."""
    value = str(text)
    value = re.sub(
        r"(?is)Meus demais dados são:.*?(?=\s*(?:Declaro|Peço|Atenciosamente|$))",
        "",
        value,
    )
    value = re.sub(
        r"(?i)(?:nasci|nascido|nascida)\s+em\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4},?\s*em\s+[^,]+,?",
        "",
        value,
    )
    value = re.sub(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "[CPF OMITIDO]", value)
    value = re.sub(r"\b\d{7}-?\d{1,2}\b", "[RG OMITIDO]", value)
    return re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[E-MAIL OMITIDO]", value)


def classify_request(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("reclama", "queixa", "problema", "insatisfação")):
        return "reclamacao"
    if any(term in lowered for term in ("elogio", "agradeço", "agradecimento", "parabéns")):
        return "elogio"
    if any(term in lowered for term in ("sugestão", "sugestao", "melhoria", "proposta")):
        return "sugestao"
    if any(term in lowered for term in ("matrícula", "matricula", "curso", "documentos", "vagas", "inscrição", "inscricao")):
        return "solicitacao_servico"
    if any(term in lowered for term in ("informação", "informacao", "esclarecimento", "dúvida", "duvida")):
        return "informacao"
    return "nao_classificado"


def _find_protocol(text: str) -> str | None:
    match = re.search(r"\bprotocolo\s*[:\-]\s*([A-Za-z0-9./-]+)", text, flags=re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"\bn\.?o\.?\s*\d+\s*[:\-]\s*([A-Za-z0-9./-]+)", text, flags=re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"\b\d{4}-\d{6}\b", text)
    if match:
        return match.group(0)
    return None


def _find_date(text: str) -> str | None:
    match = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
    if match:
        return match.group(0)
    return None


def _find_solicitante(text: str) -> str | None:
    patterns = [
        r"(?:meu nome\s+[ée]\s+|nome\s*[:\-]?\s*)([A-ZÁÉÍÓÚÃÕÂÊÔÇ][A-Za-záéíóúãõâêôçü\s]+)",
        r"(?:sou\s+)([A-ZÁÉÍÓÚÃÕÂÊÔÇ][A-Za-záéíóúãõâêôçü\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            value = match.group(1).strip()
            if value and len(value) > 2:
                return value
    return None


def _find_subject(text: str) -> str:
    if "matrícula" in text.lower() or "matricula" in text.lower():
        return "Solicitação de matrícula"
    if "documentos" in text.lower():
        return "Solicitação de documentos"
    return "Solicitação institucional"


def _find_request(text: str) -> str:
    text_without_redaction = re.sub(r"(?i)(api[_ -]?key|jwt|senha|token|secret)", "[redacted]", text)
    patterns = [
        r"solicito(?:\s+que)?\s+(.*?)(?:\.|$)",
        r"peço(?:\s+que)?\s+(.*?)(?:\.|$)",
        r"desejo(?:\s+que)?\s+(.*?)(?:\.|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text_without_redaction, flags=re.I)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return candidate
    return text_without_redaction[:200].strip()


def validate_extracted_data(data: Dict[str, Any]) -> Dict[str, Any]:
    required_fields = [
        "protocolo",
        "data",
        "solicitante",
        "assunto",
        "solicitacao",
        "categoria",
        "campos_ausentes",
        "confianca",
        "revisao_humana_necessaria",
        "texto_original",
    ]
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise ValueError(f"Campos obrigatórios ausentes: {missing}")
    if data["categoria"] not in ALLOWED_CATEGORIES:
        raise ValueError(f"Categoria inválida: {data['categoria']}")
    if not isinstance(data["campos_ausentes"], list):
        raise ValueError("campos_ausentes deve ser uma lista.")
    if not isinstance(data["revisao_humana_necessaria"], bool):
        raise ValueError("revisao_humana_necessaria deve ser booleano.")
    if data["texto_original"] is None:
        raise ValueError("texto_original não pode ser nulo.")
    return data


def extract_structured_data(text: str) -> Dict[str, Any]:
    clean = normalize_text(text)
    protocol = _find_protocol(clean)
    data_value = _find_date(clean)
    solicitante = _find_solicitante(clean)
    assunto = _find_subject(clean)
    solicitacao = _find_request(clean)
    categoria = classify_request(clean)
    fields_missing: List[str] = []
    if protocol is None:
        fields_missing.append("protocolo")
    if data_value is None:
        fields_missing.append("data")
    if solicitante is None:
        fields_missing.append("solicitante")
    if not assunto:
        fields_missing.append("assunto")
    if not solicitacao:
        fields_missing.append("solicitacao")
    if categoria == "nao_classificado":
        fields_missing.append("categoria")
    if any(token in clean.lower() for token in ("revele", "ignore", "senha", "secreto", "api_key", "chave")):
        fields_missing.append("validacao_segurança")

    payload = {
        "protocolo": protocol,
        "data": data_value,
        "solicitante": solicitante,
        "assunto": assunto,
        "solicitacao": solicitacao,
        "categoria": categoria,
        "campos_ausentes": fields_missing,
        "confianca": 0.6 if not fields_missing else 0.4,
        "revisao_humana_necessaria": True,
        "texto_original": text,
    }
    if any(token in clean.lower() for token in ("releia", "ignore", "senha", "secreto")):
        payload["revisao_humana_necessaria"] = True
    validate_extracted_data(payload)
    return payload


def build_minuta(data: Dict[str, Any]) -> str:
    validated = validate_extracted_data(data)
    solicitante = validated.get("solicitante") or "Não informado"
    assunto = validated.get("assunto") or "Assunto não identificado"
    solicitacao = validated.get("solicitacao") or "Solicitação não detalhada"
    protocolo = validated.get("protocolo") or "Não informado"
    data_informada = validated.get("data") or "Não informado"
    campos_ausentes = ", ".join(validated.get("campos_ausentes") or ["nenhum campo obrigatório identificado"]) if (validated.get("campos_ausentes")) else "nenhum campo obrigatório identificado"

    text = f"""MINUTA INSTITUCIONAL (RASCUNHO)

Protocolo: {protocolo}
Data: {data_informada}
Solicitante: {solicitante}
Assunto: {assunto}

Solicitação:
{solicitacao}

Observações:
- Este é um rascunho institucional e deve ser validado por pessoa responsável antes do envio final.
- Os dados foram extraídos somente do conteúdo fornecido e não foram inventados.
- Campos ausentes ou pendentes: {campos_ausentes}.
- Qualquer informação adicional ou correção deve ser confirmada antes de encaminhamento.
"""
    return text.strip()


def safe_json_blob(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
