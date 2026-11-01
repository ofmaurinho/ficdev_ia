"""Contratos versionados das saídas do Desafio Prático 2."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, ValidationError


CategoriaSolicitacao = Literal[
    "informacao", "solicitacao_servico", "reclamacao", "sugestao", "elogio",
    "outros", "nao_classificado", "revisao",
]
TipoEntidade = Literal[
    "pessoa", "orgao", "local", "data", "protocolo", "curso",
    "turno", "carga_horaria", "atividade", "outro",
]
PolaridadeSentimento = Literal["positiva", "negativa", "neutra", "indeterminada"]
DecisaoGuardrail = Literal["permitir", "revisar", "bloquear"]


class ContratoEstrito(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EntidadeLiteral(ContratoEstrito):
    tipo: TipoEntidade = Field(description="Tipo fechado da entidade identificada literalmente.")
    texto_literal: StrictStr = Field(description="Trecho copiado literalmente da solicitação.")
    observacao: StrictStr | None = Field(description="Normalização explicativa opcional, nunca um novo fato.")


class FichaSolicitacao(ContratoEstrito):
    """Schema v1.0. Campos anuláveis continuam obrigatórios no JSON estruturado."""

    versao_esquema: Literal["solicitacao.v2"] = Field(description="Versão fixa deste contrato.")
    protocolo: StrictStr | None = Field(description="Protocolo literal ou null quando ausente.")
    data: StrictStr | None = Field(description="Data literal da solicitação ou null.")
    solicitante: StrictStr | None = Field(description="Nome fictício literal ou null.")
    assunto: StrictStr | None = Field(description="Assunto explícito ou null quando não identificável.")
    pedido: StrictStr | None = Field(description="Pedido explícito, sem completar lacunas.")
    categoria: CategoriaSolicitacao = Field(description="Categoria pertencente ao conjunto fechado.")
    resumo: StrictStr = Field(description="Resumo fiel de no máximo 100 palavras.")
    entidades: list[EntidadeLiteral] = Field(description="Entidades copiadas literalmente do texto.")
    campos_ausentes: list[StrictStr] = Field(description="Campos que não aparecem ou não podem ser confirmados.")
    inferencias: list[StrictStr] = Field(description="Inferências explicitamente rotuladas, sem tratá-las como fatos.")
    revisao_humana_necessaria: StrictBool = Field(description="Se um operador precisa conferir o caso.")
    motivo_revisao: StrictStr | None = Field(description="Motivo da revisão ou null quando não houver alerta.")


class CitacaoRAG(ContratoEstrito):
    chunk_id: StrictStr = Field(description="ID de trecho recuperado nesta consulta.")
    afirmacao: StrictStr = Field(description="Afirmação sustentada pelo trecho citado.")


class RespostaRAG(ContratoEstrito):
    respondida_pelas_fontes: StrictBool = Field(description="False se as fontes não contêm a resposta.")
    conflito_na_evidencia: StrictBool = Field(description="True se as fontes recuperadas divergem sem precedência clara.")
    resposta: StrictStr = Field(description="Resposta institucional concisa; vazia quando não há suporte.")
    citacoes: list[CitacaoRAG] = Field(description="IDs de chunks que sustentam afirmações da resposta.")
    motivo_revisao: StrictStr | None = Field(description="Motivo de abstenção/revisão ou null.")


class AnaliseSentimento(ContratoEstrito):
    id: StrictStr = Field(description="Identificador da avaliação.")
    polaridade: PolaridadeSentimento = Field(description="positiva, negativa, neutra ou indeterminada.")
    justificativa: StrictStr = Field(description="Justificativa curta baseada apenas no texto.")
    confianca_modelo: float = Field(ge=0.0, le=1.0, description="Estimativa não calibrada reportada pelo modelo.")
    revisao_necessaria: StrictBool = Field(description="True quando houver ironia, mensagem mista ou falta de contexto.")
    motivo_revisao: StrictStr | None = Field(description="Motivo de revisão quando aplicável.")


class ResultadoGuardrail(ContratoEstrito):
    decisao: DecisaoGuardrail
    camada: Literal["entrada", "recuperacao", "saida"]
    motivos: list[StrictStr]
    moderacao_acionada: StrictBool
    acao_recomendada: StrictStr


class ErroRegraNegocio(ValueError):
    """Saída bem formada que não passou pela validação factual ou de domínio."""


def validar_resumo(resumo: str) -> None:
    if len(resumo.split()) > 100:
        raise ErroRegraNegocio("O resumo excede o limite de 100 palavras.")


def validar_classificacao(categoria: str) -> None:
    permitidas = {"informacao", "solicitacao_servico", "reclamacao", "sugestao", "elogio", "outros", "nao_classificado", "revisao"}
    if categoria not in permitidas:
        raise ErroRegraNegocio("A categoria não pertence ao conjunto fechado.")


def validar_entidades_literais(entidades: list[EntidadeLiteral], texto_original: str) -> None:
    fonte = _normalizar(texto_original)
    for entidade in entidades:
        if not entidade.texto_literal or _normalizar(entidade.texto_literal) not in fonte:
            raise ErroRegraNegocio("Uma entidade marcada como literal não aparece na solicitação original.")


def _normalizar(texto: str) -> str:
    sem_acentos = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sem_acentos.casefold().split())


def _datas_no_texto(texto: str) -> set[date]:
    meses = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
             "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
    resultado: set[date] = set()
    for match in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", texto):
        try:
            resultado.add(date(int(match.group(3)), int(match.group(2)), int(match.group(1))))
        except ValueError:
            continue
    folded = _normalizar(texto)
    for match in re.finditer(r"\b(\d{1,2})\s+de\s+(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b", folded):
        try:
            resultado.add(date(int(match.group(3)), meses[match.group(2)], int(match.group(1))))
        except ValueError:
            continue
    for match in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", texto):
        try:
            resultado.add(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            continue
    return resultado


def validar_ficha(ficha: FichaSolicitacao, texto_original: str) -> list[str]:
    """Valida regras de negócio que um JSON Schema/Pydantic não consegue provar."""
    fonte = _normalizar(texto_original)
    ausentes = set(ficha.campos_ausentes)
    alertas: list[str] = []

    # O schema valida o formato da data, mas não que ela exista no calendário.
    if ficha.data:
        try:
            parsed = datetime.strptime(ficha.data, "%d/%m/%Y").date()
        except ValueError:
            try:
                parsed = date.fromisoformat(ficha.data)
            except ValueError:
                parsed_dates = _datas_no_texto(ficha.data)
                if len(parsed_dates) != 1:
                    raise ErroRegraNegocio("A data extraída não é uma data válida ou usa formato não aceito.")
                parsed = next(iter(parsed_dates))
        # Aceita equivalência entre data escrita por extenso e forma numérica, mas não uma data inventada.
        if parsed not in _datas_no_texto(texto_original):
            raise ErroRegraNegocio("A data estruturada não é sustentada pelo texto de origem.")

    validar_classificacao(ficha.categoria)
    validar_resumo(ficha.resumo)
    validar_entidades_literais(ficha.entidades, texto_original)

    # O schema aceita qualquer string; este controle impede protocolar/personalizar casos por invenção.
    for nome, valor in (("protocolo", ficha.protocolo), ("solicitante", ficha.solicitante)):
        if valor and _normalizar(valor) not in fonte:
            raise ErroRegraNegocio(f"O campo {nome} não foi localizado literalmente na solicitação.")

    # O tipo anulável do schema não obriga o modelo a manter a lista de lacunas coerente.
    for nome in ("protocolo", "data", "solicitante", "assunto", "pedido"):
        if getattr(ficha, nome) is None and nome not in ausentes:
            raise ErroRegraNegocio(f"O campo {nome} está nulo, mas não consta em campos_ausentes.")
        if getattr(ficha, nome) is not None and nome in ausentes:
            raise ErroRegraNegocio(f"O campo {nome} foi marcado ausente apesar de ter valor.")

    if ficha.categoria == "revisao" and not ficha.revisao_humana_necessaria:
        raise ErroRegraNegocio("A categoria revisao exige encaminhamento humano.")
    if any(getattr(ficha, nome) is None for nome in ("protocolo", "data", "solicitante", "assunto", "pedido")):
        if not ficha.revisao_humana_necessaria:
            raise ErroRegraNegocio("Campos críticos ausentes exigem revisão humana.")
        alertas.append("Há campo(s) crítico(s) ausente(s); não produzir minuta automática.")
    return alertas


def demonstrar_json_vs_schema() -> dict:
    """Demonstra JSON sintático válido que falha separadamente no contrato estrito."""
    import json

    base = {
        "versao_esquema": "solicitacao.v2", "protocolo": "FIC-001", "data": "01/01/2026",
        "solicitante": "Pessoa Fictícia", "assunto": "Informação", "pedido": "Pedir orientação",
        "categoria": "informacao", "resumo": "Solicita orientação.", "entidades": [],
        "campos_ausentes": [], "inferencias": [], "revisao_humana_necessaria": True,
        "motivo_revisao": "Conferência humana obrigatória.",
    }
    extras = dict(base, campo_extra=True)
    wrong_type = dict(base, protocolo=142)
    missing = dict(base)
    missing.pop("assunto")
    casos = {
        "campo_extra": json.dumps(extras),
        "tipo_incorreto": json.dumps(wrong_type),
        "campo_obrigatorio_ausente": json.dumps(missing),
    }
    resultado = {}
    for nome, bruto in casos.items():
        try:
            json.loads(bruto)
            sintatico = True
        except json.JSONDecodeError:
            sintatico = False
        try:
            FichaSolicitacao.model_validate_json(bruto)
            erro = None
        except ValidationError as exc:
            erro = exc.errors(include_url=False)
        resultado[nome] = {
            "json_sintatico": sintatico,
            "schema_valido": erro is None,
            "erros": [{"campo": ".".join(str(part) for part in item["loc"]), "tipo": item["type"]} for item in erro] if erro else [],
        }
    return resultado
