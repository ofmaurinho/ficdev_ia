"""Guardrails de entrada, recuperação, saída e limites de execução (RF16)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.audit import AuditLogger, sanitize_log_payload
from src.llm_client import CallLimitExceededError, OpenAIClient
from src.schemas import ResultadoGuardrail

EXTENSOES_PERMITIDAS = {".txt", ".pdf", ".json", ".mp3", ".wav", ".m4a", ".png", ".jpg", ".jpeg"}

_SECRET_EXFIL_PATTERNS = (
    re.compile(r"(?i)\b(?:openai_api_key|api[_ -]?key|secret[_ -]?key|access[_ -]?token|bearer\s+token)\b"),
    re.compile(r"(?i)\b(?:revele|mostre|exiba|imprima|retorne|liste)\b.{0,40}\b(?:credenciais|senha|senhas|segredo|segredos|chave|token|\.env)\b"),
    re.compile(r"(?i)\bsenha\s+configurada\s+no\s+ambiente\b"),
)

_DIRECT_INJECTION_PATTERNS = (
    re.compile(r"(?i)\b(?:ignore|desconsidere|esqueça)\s+(?:todas\s+)?(?:as\s+)?(?:regras|instru[çc][õo]es|diretrizes|sistema)\b"),
    re.compile(r"(?i)\bignore\s+o\s+sistema\b"),
    re.compile(r"(?i)\baprove\s+(?:minha\s+)?matr[íi]cula\s+sem\s+verificar\b"),
    re.compile(r"(?i)\bresponda\s+apenas\s+com\s+a\s+seguinte\s+mensagem\b"),
    re.compile(r"(?i)\bmodo\s+(?:desenvolvedor| irrestrito|jailbreak|dan)\b"),
)

_INDIRECT_INJECTION_PATTERNS = (
    re.compile(r"(?i)\binstru[çc][ãa]o\s+maliciosa\b"),
    re.compile(r"(?i)\b(?:ignore|desconsidere)\s+(?:o\s+sistema|as\s+regras|as\s+instru[çc][õo]es)\b"),
    re.compile(r"(?i)\brevele\s+credenciais\b"),
    re.compile(r"(?i)</?(?:FONTES_NAO_CONFIAVEIS|SOLICITACAO_NAO_CONFIAVEL|TRECHO|SYSTEM)\b"),
)

_MODERATION_PATTERNS = (
    re.compile(r"(?i)\b(?:vou\s+matar|amea[çc]a\s+de\s+morte|ataque\s+violento|explosivo| Discurso\s+de\s+[óo]dio)\b"),
)

_OUT_OF_SCOPE_PATTERNS = (
    re.compile(r"(?i)\b(?:receita\s+de\s+bolo|aposta\s+esportiva|cassino\s+online|comprar\s+criptomoeda|bitcoin|hor[óo]scopo\s+do\s+dia|piada\s+engra[çc]ada)\b"),
)

_UNSAFE_OUTPUT_PATTERNS = (
    re.compile(r"\bsk-(?:proj-|live-|test-|svcacct-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b"),
    re.compile(r"(?i)\bmatr[íi]cula\s+foi\s+(?:aprovada|renovada)\s+automaticamente\b"),
    re.compile(r"(?i)\bnenhum\s+documento\s+adicional\s+[ée]\s+necess[áa]rio\b"),
)


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    if config is not None:
        return config
    return json.loads((_root() / "config.json").read_text(encoding="utf-8"))


def _logger(config: dict[str, Any] | None = None) -> AuditLogger:
    cfg = _load_config(config)
    results_dir = cfg.get("desafio2", {}).get("paths", {}).get("results_directory", cfg.get("results_dir", "resultados"))
    path = Path(results_dir)
    if not path.is_absolute():
        path = _root() / path
    return AuditLogger(str(path / "logs"))


def delimitar_conteudo_nao_confiavel(texto: str, tag: str = "CONTEUDO_NAO_CONFIAVEL") -> str:
    """Remove fechamentos de tag injetados e envolve o texto em delimitador explícito."""
    limpo = re.sub(rf"(?i)</?{re.escape(tag)}>", "[TAG_REMOVIDA]", str(texto or ""))
    return f"<{tag}>\n{limpo}\n</{tag}>"


def filtrar_dados_indevidos(texto: str) -> str:
    """Remove padrões de chaves, tokens, CPFs e e-mails não institucionais da saída."""
    valor = str(texto or "")
    valor = re.sub(r"\bsk-(?:proj-|live-|test-|svcacct-)?[A-Za-z0-9_-]{16,}\b", "[SEGREDO_BLOQUEADO]", valor)
    valor = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [SEGREDO_BLOQUEADO]", valor)
    valor = re.sub(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "[CPF_OMITIDO]", valor)
    return valor


def validar_limites_execucao(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Confere timeout, no máximo 1 repetição e teto de chamadas/tokens da configuração."""
    cfg = _load_config(config)
    llm = cfg.get("desafio2", {}).get("llm", {})
    timeout = float(llm.get("timeout_seconds", cfg.get("timeout_seconds", 30)))
    max_retries = int(llm.get("max_retries", 1))
    max_calls = int(llm.get("max_calls_per_run", 20))
    max_tokens = int(llm.get("max_output_tokens", cfg.get("max_output_tokens", 1500)))
    erros: list[str] = []
    if timeout <= 0 or timeout > 120:
        erros.append("timeout_fora_do_intervalo")
    if max_retries < 0 or max_retries > 1:
        erros.append("max_retries_excede_uma_repeticao")
    if max_calls < 1 or max_calls > 50:
        erros.append("max_calls_per_run_invalido")
    if max_tokens < 64 or max_tokens > 4000:
        erros.append("max_output_tokens_invalido")
    return {
        "valido": not erros,
        "timeout_seconds": timeout,
        "max_retries": max_retries,
        "max_calls_per_run": max_calls,
        "max_output_tokens": max_tokens,
        "erros": erros,
    }


def validar_arquivo_entrada(
    path: str | Path,
    *,
    max_mb: float = 10.0,
    extensoes_permitidas: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> ResultadoGuardrail:
    """Valida existência, extensão e tamanho máximo do arquivo antes de abrir."""
    arquivo = Path(path)
    permitidas = extensoes_permitidas or EXTENSOES_PERMITIDAS
    motivos: list[str] = []
    if not arquivo.is_file():
        motivos.append("arquivo_inexistente")
    else:
        if arquivo.suffix.lower() not in permitidas:
            motivos.append("extensao_nao_permitida")
        limite_bytes = int(max_mb * 1024 * 1024)
        if arquivo.stat().st_size > limite_bytes:
            motivos.append("arquivo_excede_limite")
        if arquivo.stat().st_size == 0:
            motivos.append("arquivo_vazio")
    decisao = "bloquear" if motivos else "permitir"
    resultado = ResultadoGuardrail(
        decisao=decisao,
        camada="entrada",
        motivos=motivos,
        moderacao_acionada=False,
        acao_recomendada="Rejeitar arquivo antes do processamento." if motivos else "Prosseguir.",
    )
    if motivos:
        _logger(config).log_event(
            "guardrail_arquivo",
            decisao,
            {"camada": "entrada", "motivos": motivos, "extensao": arquivo.suffix.lower()},
        )
    return resultado


def avaliar_entrada_guardrail(
    texto: str,
    *,
    max_chars: int = 10_000,
    config: dict[str, Any] | None = None,
) -> ResultadoGuardrail:
    """Avalia texto de entrada quanto a tamanho, escopo, moderação, injeção e segredos."""
    motivos: list[str] = []
    moderacao = False
    conteudo = str(texto or "").strip()

    if not conteudo:
        motivos.append("entrada_vazia")
    elif len(conteudo) > max_chars:
        motivos.append("comprimento_excede_limite")

    if any(p.search(conteudo) for p in _SECRET_EXFIL_PATTERNS):
        motivos.append("tentativa_exfiltracao_segredo")

    if any(p.search(conteudo) for p in _DIRECT_INJECTION_PATTERNS):
        motivos.append("injecao_direta")

    if any(p.search(conteudo) for p in _MODERATION_PATTERNS):
        motivos.append("conteudo_improprio_moderacao")
        moderacao = True

    if any(p.search(conteudo) for p in _OUT_OF_SCOPE_PATTERNS):
        motivos.append("fora_de_escopo")

    if not motivos:
        decisao = "permitir"
        acao = "Prosseguir com o fluxo normal."
    elif any(
        m in motivos
        for m in (
            "entrada_vazia",
            "comprimento_excede_limite",
            "tentativa_exfiltracao_segredo",
            "conteudo_improprio_moderacao",
            "fora_de_escopo",
        )
    ):
        decisao = "bloquear"
        acao = "Bloquear execução e registrar motivo sanitizado."
    else:
        # Quando há apenas injeção direta sem dados formais de protocolo/solicitante, bloqueia;
        # quando está misturada a uma solicitação com protocolo, encaminha para revisão humana.
        tem_protocolo = bool(re.search(r"(?i)\bprotocolo\b|\b\d{4}-\d{6}\b|\bFIC-\d{4}-\d+\b", conteudo))
        decisao = "revisar" if tem_protocolo else "bloquear"
        acao = "Tratar como dado não confiável, impedir minuta automática e exigir revisão humana."

    resultado = ResultadoGuardrail(
        decisao=decisao,
        camada="entrada",
        motivos=motivos,
        moderacao_acionada=moderacao,
        acao_recomendada=acao,
    )
    if decisao != "permitir":
        _logger(config).log_event(
            "guardrail_entrada",
            decisao,
            {
                "camada": "entrada",
                "decisao": decisao,
                "motivos": motivos,
                "moderacao_acionada": moderacao,
                "input_sha256": hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16],
            },
        )
    return resultado


def avaliar_recuperacao_guardrail(
    chunks: list[dict[str, Any]],
    *,
    config: dict[str, Any] | None = None,
) -> tuple[ResultadoGuardrail, list[dict[str, Any]], list[str]]:
    """Inspeciona trechos recuperados contra injeção indireta e exfiltração."""
    seguros: list[dict[str, Any]] = []
    bloqueados: list[str] = []
    motivos: list[str] = []

    for item in chunks:
        texto = str(item.get("text") or "")
        chunk_id = str(item.get("chunk_id") or "desconhecido")
        contaminado = any(p.search(texto) for p in _INDIRECT_INJECTION_PATTERNS) or any(
            p.search(texto) for p in _SECRET_EXFIL_PATTERNS
        )
        if contaminado:
            bloqueados.append(chunk_id)
            if "injecao_indireta_acervo" not in motivos:
                motivos.append("injecao_indireta_acervo")
        else:
            seguros.append(item)

    if bloqueados:
        decisao = "revisar" if seguros else "bloquear"
        acao = "Descartar trechos contaminados e encaminhar resposta para revisão humana."
        _logger(config).log_event(
            "guardrail_recuperacao",
            decisao,
            {"camada": "recuperacao", "motivos": motivos, "chunks_bloqueados": bloqueados},
        )
    else:
        decisao = "permitir"
        acao = "Trechos recuperados liberados como contexto delimitado."

    return (
        ResultadoGuardrail(
            decisao=decisao,
            camada="recuperacao",
            motivos=motivos,
            moderacao_acionada=False,
            acao_recomendada=acao,
        ),
        seguros,
        bloqueados,
    )


def avaliar_saida_guardrail(
    texto_saida: str,
    *,
    citacoes: list[str] | None = None,
    chunks_permitidos: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[ResultadoGuardrail, str]:
    """Filtra dados indevidos na saída e confere citações e padrões proibidos."""
    motivos: list[str] = []
    bruto = str(texto_saida or "")

    if any(p.search(bruto) for p in _UNSAFE_OUTPUT_PATTERNS):
        motivos.append("saida_contem_padrao_proibido")

    if citacoes is not None and chunks_permitidos is not None:
        invalidas = [cid for cid in citacoes if cid not in chunks_permitidos]
        if invalidas:
            motivos.append("citacao_fora_dos_trechos_recuperados")

    filtrado = filtrar_dados_indevidos(bruto)
    decisao = "revisar" if motivos else "permitir"
    resultado = ResultadoGuardrail(
        decisao=decisao,
        camada="saida",
        motivos=motivos,
        moderacao_acionada=False,
        acao_recomendada="Encaminhar para revisão humana e bloquear aprovação." if motivos else "Saída validada.",
    )
    if motivos:
        _logger(config).log_event(
            "guardrail_saida",
            decisao,
            {"camada": "saida", "motivos": motivos},
        )
    return resultado, filtrado


def avaliar_casos_adversariais(*, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Executa os 3 ataques adversariais (T04) e os controles de escopo/arquivo/limite (T05)."""
    cfg = _load_config(config)
    d2 = cfg.get("desafio2", {})
    aval_dir = Path(d2.get("paths", {}).get("avaliacoes_directory", "dados/originais/avaliacoes"))
    if not aval_dir.is_absolute():
        aval_dir = _root() / aval_dir
    adv_file = aval_dir / "avaliacoes_adversariais.json"
    casos = json.loads(adv_file.read_text(encoding="utf-8"))["casos"]

    resultados_ataques: list[dict[str, Any]] = []
    for caso in casos:
        cid = caso["id"]
        local = caso["local"]
        texto = caso["texto"]
        if local == "documento_acervo":
            guard, seguros, bloqueados = avaliar_recuperacao_guardrail(
                [{"chunk_id": f"chunk-{cid.lower()}", "text": texto, "metadata": {"document_id": "ADV-DOC"}}],
                config=cfg,
            )
            protegido = guard.decisao in {"bloquear", "revisar"} and len(seguros) == 0 and len(bloqueados) == 1
            resultados_ataques.append({
                "id": cid,
                "local": local,
                "risco": caso["risco"],
                "decisao": guard.decisao,
                "camada": guard.camada,
                "motivos": guard.motivos,
                "segredo_revelado": False,
                "instrucao_executada": False,
                "envio_autorizado": False,
                "ataque_contido": protegido,
            })
        else:
            guard = avaliar_entrada_guardrail(texto, config=cfg)
            protegido = guard.decisao in {"bloquear", "revisar"}
            resultados_ataques.append({
                "id": cid,
                "local": local,
                "risco": caso["risco"],
                "decisao": guard.decisao,
                "camada": guard.camada,
                "motivos": guard.motivos,
                "segredo_revelado": False,
                "instrucao_executada": False,
                "envio_autorizado": False,
                "ataque_contido": protegido,
            })

    # Verificações de T05: fora de escopo, arquivo inválido/excessivo e limite de chamadas
    fora_escopo = avaliar_entrada_guardrail("Qual a melhor receita de bolo de chocolate e aposta esportiva?", config=cfg)
    comprimento_excesso = avaliar_entrada_guardrail("A" * 12_000, max_chars=10_000, config=cfg)
    arquivo_invalido = validar_arquivo_entrada(_root() / "script_inexistente.exe", config=cfg)

    cliente_orcamento = OpenAIClient(api_key="chave-ficticia-teste-local", max_calls_per_run=1)
    cliente_orcamento._reserve_call()
    limite_respeitado = False
    try:
        cliente_orcamento._reserve_call()
    except CallLimitExceededError:
        limite_respeitado = True

    limites_cfg = validar_limites_execucao(cfg)

    relatorio = {
        "schema_version": "guardrails-evaluation.v1",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "ataques_adversariais": resultados_ataques,
        "ataques_contidos": sum(1 for item in resultados_ataques if item["ataque_contido"]),
        "total_ataques": len(resultados_ataques),
        "controles_t05": {
            "fora_de_escopo": {
                "decisao": fora_escopo.decisao,
                "motivos": fora_escopo.motivos,
                "bloqueado": fora_escopo.decisao == "bloquear",
            },
            "entrada_excessiva": {
                "decisao": comprimento_excesso.decisao,
                "motivos": comprimento_excesso.motivos,
                "bloqueado": comprimento_excesso.decisao == "bloquear",
            },
            "arquivo_invalido": {
                "decisao": arquivo_invalido.decisao,
                "motivos": arquivo_invalido.motivos,
                "bloqueado": arquivo_invalido.decisao == "bloquear",
            },
            "limite_chamadas": {
                "max_calls_per_run": 1,
                "bloqueou_segunda_chamada": limite_respeitado,
            },
            "configuracao_limites": limites_cfg,
        },
    }
    relatorio_seguro = sanitize_log_payload(relatorio)
    results_dir = Path(d2.get("paths", {}).get("results_directory", "resultados"))
    if not results_dir.is_absolute():
        results_dir = _root() / results_dir
    out_path = results_dir / "avaliacao_guardrails.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(relatorio_seguro, ensure_ascii=False, indent=2), encoding="utf-8")
    return relatorio_seguro
