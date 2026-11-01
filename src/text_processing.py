"""Processamento textual e extração estruturada para solicitações institucionais."""

from __future__ import annotations

import json
from pathlib import Path
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
    "revisao",
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


NAO_LOCALIZADO = "não localizado"


def detectar_lacunas(texto: str, valores: Dict[str, str]) -> List[str]:
    """Informações pedidas ou necessárias que a entrada não fornece (sem inventá-las)."""
    lacunas = [f"{nome.capitalize()}: {NAO_LOCALIZADO}" for nome, valor in valores.items() if valor == NAO_LOCALIZADO]
    if re.search(r"(?i)quais\s+documentos|documentos\s+(?:ainda\s+)?(?:que\s+)?(?:preciso|necess|exigid)", texto):
        lacunas.append(f"Relação de documentos necessários: {NAO_LOCALIZADO}")
    return lacunas


def build_minuta_institucional(
    *,
    valores: Dict[str, str],
    assunto: str,
    solicitacao: str,
    categoria: str,
    fontes: List[str],
    lacunas: List[str],
) -> str:
    """Minuta determinística: usa só os dados recebidos e marca explicitamente o que falta."""
    corpo_lacunas = "\n".join(f"- {item}" for item in lacunas) if lacunas else "- nenhuma lacuna identificada"
    corpo_fontes = "\n".join(f"- {item}" for item in fontes)
    return (
        "MINUTA INSTITUCIONAL (RASCUNHO)\n"
        "\n"
        f"Protocolo: {valores.get('protocolo', NAO_LOCALIZADO)}\n"
        f"Data: {valores.get('data', NAO_LOCALIZADO)}\n"
        f"Solicitante: {valores.get('solicitante', NAO_LOCALIZADO)}\n"
        f"Assunto: {assunto}\n"
        f"Categoria: {categoria}\n"
        "\n"
        "Solicitação registrada:\n"
        f"{solicitacao}\n"
        "\n"
        "Informações não localizadas na solicitação:\n"
        f"{corpo_lacunas}\n"
        "\n"
        "Esta minuta apenas registra o recebimento da solicitação. "
        "Ela não confirma deferimento, prazos, providências nem documentos exigidos.\n"
        "\n"
        "Fontes utilizadas:\n"
        f"{corpo_fontes}\n"
        "\n"
        "Rascunho elaborado com apoio de ferramentas de inteligência artificial. "
        "Requer conferência e aprovação de servidor responsável antes de qualquer envio. "
        "Nenhum envio automático é realizado.\n"
    )


def render_minuta_html(minuta_texto: str, brasao_path: str | None = None) -> str:
    """Versão visual da minuta aprovada (brasão + texto), derivada do texto sem alterá-lo."""
    import base64
    import html
    from pathlib import Path

    imagem = ""
    if brasao_path and Path(brasao_path).exists():
        dados = base64.b64encode(Path(brasao_path).read_bytes()).decode("ascii")
        imagem = f'<img src="data:image/png;base64,{dados}" alt="Brasão institucional" style="height:90px">'
    corpo = html.escape(minuta_texto).replace("\n", "<br>\n")
    return (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Minuta institucional (rascunho)</title></head>'
        '<body style="font-family:sans-serif;max-width:760px;margin:2rem auto">'
        f'<div style="text-align:center">{imagem}</div>'
        '<p style="border:2px solid #b00;padding:6px;text-align:center"><b>RASCUNHO — requer aprovação humana. Não enviar automaticamente.</b></p>'
        f"<div>{corpo}</div></body></html>\n"
    )


def render_minuta_pdf(
    minuta_texto: str,
    out_path: str | Path,
    brasao_path: str | Path | None = None,
) -> Path:
    """Gera um PDF institucional formal da minuta contendo o brasão oficial e carimbo de rascunho."""
    from PIL import Image, ImageDraw, ImageFont

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Dimensões A4 em 150 DPI: 1240 x 1754 pixels
    width, height = 1240, 1754
    canvas = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Seleção de fontes TTF do sistema com fallback
    candidatos_bold = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    candidatos_regular = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]

    fonte_bold_path = next((p for p in candidatos_bold if Path(p).exists()), None)
    fonte_reg_path = next((p for p in candidatos_regular if Path(p).exists()), None)

    if fonte_bold_path and fonte_reg_path:
        font_header_bold = ImageFont.truetype(fonte_bold_path, 22)
        font_header_reg = ImageFont.truetype(fonte_reg_path, 18)
        font_title = ImageFont.truetype(fonte_bold_path, 26)
        font_warn = ImageFont.truetype(fonte_bold_path, 17)
        font_label = ImageFont.truetype(fonte_bold_path, 20)
        font_body = ImageFont.truetype(fonte_reg_path, 20)
        font_footer = ImageFont.truetype(fonte_reg_path, 14)
    else:
        font_header_bold = font_header_reg = font_title = font_warn = font_label = font_body = font_footer = ImageFont.load_default()

    margin_left = 100
    margin_right = width - 100
    max_content_width = margin_right - margin_left
    y = 50

    # 1. Brasão Oficial Centralizado
    brasao_p = Path(brasao_path) if brasao_path else None
    if brasao_p and brasao_p.exists():
        try:
            b_img = Image.open(brasao_p).convert("RGBA")
            target_h = 110
            ratio = target_h / b_img.height
            target_w = int(b_img.width * ratio)
            b_resized = b_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            b_x = int((width - target_w) / 2)
            canvas.paste(b_resized, (b_x, y), b_resized)
            y += target_h + 15
        except Exception:
            y += 10
    else:
        y += 20

    # 2. Cabeçalho Institucional
    def draw_centered(text: str, font, fill=(30, 41, 59)):
        nonlocal y
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text(((width - text_w) / 2, y), text, font=font, fill=fill)
        y += (bbox[3] - bbox[1]) + 6

    draw_centered("ESTADO DE MATO GROSSO", font_header_bold, fill=(15, 23, 42))
    draw_centered("SECRETARIA DE ESTADO DE EDUCAÇÃO", font_header_reg, fill=(71, 85, 105))
    draw_centered("CENTRAL INTELIGENTE DE ATENDIMENTO INSTITUCIONAL", font_header_bold, fill=(30, 58, 138))
    y += 10

    # 3. Faixa de Aviso de Rascunho / Não Envio Automático
    box_top = y
    box_h = 44
    draw.rectangle([margin_left, box_top, margin_right, box_top + box_h], fill=(255, 241, 242), outline=(185, 28, 28), width=2)
    warn_text = "RASCUNHO — REQUER APROVAÇÃO HUMANA. NÃO ENVIAR AUTOMATICAMENTE."
    warn_bbox = draw.textbbox((0, 0), warn_text, font=font_warn)
    warn_w = warn_bbox[2] - warn_bbox[0]
    draw.text(((width - warn_w) / 2, box_top + 12), warn_text, font=font_warn, fill=(153, 27, 27))
    y += box_h + 25

    # 4. Título do Documento
    draw_centered("MINUTA DE RESPOSTA INSTITUCIONAL", font_title, fill=(15, 23, 42))
    y += 8
    draw.line([(margin_left, y), (margin_right, y)], fill=(203, 213, 225), width=2)
    y += 20

    # 5. Helper de Quebra de Linha
    def wrap_lines(text: str, font, max_w: int):
        lines = []
        for raw_line in text.split("\n"):
            if not raw_line.strip():
                lines.append("")
                continue
            words = raw_line.split()
            cur = []
            for w in words:
                cand = " ".join(cur + [w])
                bb = draw.textbbox((0, 0), cand, font=font)
                if (bb[2] - bb[0]) <= max_w:
                    cur.append(w)
                else:
                    if cur:
                        lines.append(" ".join(cur))
                        cur = [w]
                    else:
                        lines.append(w)
                        cur = []
            if cur:
                lines.append(" ".join(cur))
        return lines

    # 6. Renderização do Corpo da Minuta
    linhas = wrap_lines(minuta_texto.strip(), font_body, max_content_width)
    for linha in linhas:
        if y > height - 120:
            break
        if not linha:
            y += 12
            continue

        # Destaque para campos chave
        is_campo_header = any(linha.startswith(prefix) for prefix in (
            "Protocolo:", "Data:", "Solicitante:", "Assunto:", "Categoria:",
            "Solicitação:", "Observações:", "Fonte:", "Informações não localizadas"
        ))

        if is_campo_header:
            draw.text((margin_left, y), linha, font=font_label, fill=(15, 23, 42))
            y += 28
        elif linha.startswith("- "):
            draw.text((margin_left + 15, y), "•", font=font_label, fill=(71, 85, 105))
            draw.text((margin_left + 35, y), linha[2:], font=font_body, fill=(51, 65, 85))
            y += 26
        else:
            draw.text((margin_left, y), linha, font=font_body, fill=(51, 65, 85))
            y += 26

    # 7. Rodapé Institucional
    footer_y = height - 85
    draw.line([(margin_left, footer_y), (margin_right, footer_y)], fill=(226, 232, 240), width=1)
    footer_text1 = "Documento preliminar gerado com assistência de inteligência artificial em conformidade com a LGPD."
    footer_text2 = "Decisão final, assinatura e expedição condicionadas à revisão e aprovação exclusiva de servidor responsável."
    bb1 = draw.textbbox((0, 0), footer_text1, font=font_footer)
    bb2 = draw.textbbox((0, 0), footer_text2, font=font_footer)
    draw.text(((width - (bb1[2] - bb1[0])) / 2, footer_y + 12), footer_text1, font=font_footer, fill=(100, 116, 139))
    draw.text(((width - (bb2[2] - bb2[0])) / 2, footer_y + 32), footer_text2, font=font_footer, fill=(148, 163, 184))

    canvas.save(out_p, "PDF", resolution=150.0)
    return out_p
