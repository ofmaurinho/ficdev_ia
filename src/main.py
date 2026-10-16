"""Ponto de entrada principal do protótipo.

Comandos disponíveis:
  processar-texto   — extração local de campos a partir de texto
  prompts           — executa os três experimentos de prompt (A, B, C)
  revisar           — registra a decisão humana sobre um prompt
  logs              — exibe o log de auditoria
  audio             — transcreve arquivo de áudio (STT) e salva campos críticos
  ocr               — extrai texto de PDF ou imagem (OCR híbrido)
  imagem            — gera peça visual institucional
  voz               — sintetiza voz do roteiro aprovado (TTS)
  aprovar-minuta    — registra versão e decisão humana sobre a minuta
  avaliar           — avalia STT, OCR ou extração contra gabarito validado
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone

from dotenv import load_dotenv

from src.audit import AuditLogger, ExecutionAudit
from src.llm_client import APIClientError, DEFAULT_OPENAI_MODEL, OpenAIClient
from src.prompts import PROMPT_RESPONSE_SCHEMA, PROMPT_VERSIONS, SYSTEM_PROMPT, prompt_for
from src.text_processing import (
    ALLOWED_CATEGORIES,
    build_minuta,
    extract_structured_data,
    minimize_text_for_provider,
    safe_json_blob,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEXT_PATH = ROOT / "arquivos" / "entrada_texto.txt"


# ---------------------------------------------------------------------------
# Configuração e utilitários
# ---------------------------------------------------------------------------

def load_config(config_path: Path | str = ROOT / "config.json") -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de configuração ausente: {path}")
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("config.json deve conter um objeto JSON válido.")
    return config


def configured_path(config: dict, key: str, default: str) -> Path:
    path = Path(config.get(key, default))
    return path if path.is_absolute() else ROOT / path


def path_reference(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def default_input_path(config: dict) -> Path:
    return configured_path(config, "input_dir", "arquivos") / config.get(
        "default_input_file", DEFAULT_TEXT_PATH.name
    )


def read_text_input(path: Path | str | None = None) -> str:
    config = load_config()
    candidate = Path(path) if path else default_input_path(config)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    if not candidate.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {candidate}")
    return candidate.read_text(encoding="utf-8")


def ensure_structure(config: dict | None = None) -> None:
    settings = config or load_config()
    results_dir = configured_path(settings, "results_dir", "resultados")
    for path in [
        ROOT / "dados" / "originais",
        configured_path(settings, "gold_dir", "dados/gabaritos"),
        configured_path(settings, "processed_dir", "dados/processados"),
        results_dir / "minutas",
        results_dir / "revisoes",
        results_dir / "logs",
        ROOT / "documentacao",
        ROOT / "prompts",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_client(config: dict) -> OpenAIClient | None:
    """Cria o cliente OpenAI se a chave estiver disponível; caso contrário retorna None."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("OPENAI_MODEL") or config.get("model") or DEFAULT_OPENAI_MODEL
    return OpenAIClient(
        api_key=api_key,
        model=model,
        timeout=float(config.get("timeout_seconds", 30)),
        temperature=float(config.get("temperature", 0)),
    )


# ---------------------------------------------------------------------------
# Experimentos de prompt (legado)
# ---------------------------------------------------------------------------

def validate_prompt_output(text: str, expected: dict | None = None, source_name: str | None = None) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"json_valido": False, "erros": [f"JSON inválido: {exc.msg}"]}

    if not isinstance(payload, dict):
        return {"json_valido": False, "erros": ["A saída JSON não é um objeto."]}

    required = {
        "protocolo",
        "data",
        "solicitante",
        "assunto",
        "solicitacao",
        "categoria",
        "campos_ausentes",
        "confianca",
        "revisao_humana_necessaria",
        "minuta",
        "fontes",
    }
    errors = [f"Campo obrigatório ausente: {key}" for key in sorted(required - payload.keys())]
    if payload.get("categoria") not in ALLOWED_CATEGORIES:
        errors.append("Categoria fora da lista documentada.")
    if not isinstance(payload.get("campos_ausentes"), list):
        errors.append("campos_ausentes deve ser uma lista.")
    if not isinstance(payload.get("confianca"), (int, float)):
        errors.append("confianca deve ser numérica.")
    if payload.get("revisao_humana_necessaria") is not True:
        errors.append("A revisão humana deve permanecer obrigatória.")
    if not isinstance(payload.get("minuta"), str):
        errors.append("minuta deve ser texto.")
    if not isinstance(payload.get("fontes"), list):
        errors.append("fontes deve ser uma lista.")
    elif source_name and source_name not in payload["fontes"]:
        errors.append("A fonte de origem não foi identificada pelo nome do arquivo.")
    if expected:
        expected_fields = expected.get("resultado_esperado", expected)
        for field in ("protocolo", "data", "solicitante", "categoria"):
            if payload.get(field) != expected_fields.get(field):
                errors.append(f"Valor divergente do gabarito: {field}.")
        absent_fields = payload.get("campos_ausentes", [])
        if isinstance(absent_fields, list) and not any("document" in str(item).lower() for item in absent_fields):
            errors.append("A lacuna sobre os documentos necessários não foi sinalizada.")
        if payload.get("revisao_humana_necessaria") is not True:
            errors.append("O gabarito exige revisão humana.")
        minuta = str(payload.get("minuta", "")).lower()
        if "document" not in minuta or "não localizado" not in minuta:
            errors.append("A minuta não sinaliza que a informação de documentos não foi localizada.")
        combined_text = f"{payload.get('solicitacao', '')} {minuta}".lower()
        for detail in expected_fields.get("detalhes_obrigatorios", []):
            if detail.lower() not in combined_text:
                errors.append(f"Detalhe relevante omitido: {detail}.")
    return {"json_valido": True, "conforme_esquema": not errors, "erros": errors}


def run_prompt_experiments(input_path: Path | str | None = None) -> list[dict]:
    load_dotenv(ROOT / ".env", override=False)
    config = load_config()
    source_path = Path(input_path) if input_path else default_input_path(config)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    prompt_input = read_text_input(source_path)
    minimized_input = minimize_text_for_provider(prompt_input)
    model = os.getenv("OPENAI_MODEL") or config.get("model") or DEFAULT_OPENAI_MODEL
    parameters = {
        "temperature": float(config.get("temperature", 0)),
        "max_output_tokens": int(config.get("max_output_tokens", 1500)),
        "timeout_seconds": float(config.get("timeout_seconds", 30)),
    }
    results_dir = configured_path(config, "results_dir", "resultados")
    execution = ExecutionAudit(log_dir=str(results_dir / "logs"))
    execution.start(
        modalidade="texto",
        arquivo_origem=path_reference(source_path),
        provider="openai",
        modelo=model,
        parametros=parameters,
        versoes_prompt=[item["version"] for item in PROMPT_VERSIONS.values()],
    )
    if not os.getenv("OPENAI_API_KEY"):
        results = []
        for label, definition in PROMPT_VERSIONS.items():
            results.append(
                {
                    "prompt": label,
                    "version": definition["version"],
                    "status": "pendente_execucao",
                    "observacao": "Execução real depende da chave da OpenAI no ambiente e da disponibilidade do provedor.",
                }
            )
        execution.revise(status="pendente_execucao", decisao_humana="pendente", motivo="OPENAI_API_KEY ausente")
        return results

    results = []
    client = OpenAIClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model=model,
        timeout=parameters["timeout_seconds"],
        temperature=parameters["temperature"],
    )
    expected_path = configured_path(config, "gold_dir", "dados/gabaritos") / f"{source_path.stem}.json"
    expected_result = None
    if expected_path.exists():
        expected_result = json.loads(expected_path.read_text(encoding="utf-8"))
    try:
        for label, definition in PROMPT_VERSIONS.items():
            metaprompt_response = None
            task_prompt = prompt_for(label)
            if label == "C":
                metaprompt_response = client.generate_text(
                    task_prompt,
                    system_prompt=SYSTEM_PROMPT,
                    max_output_tokens=parameters["max_output_tokens"],
                )
                task_prompt = metaprompt_response["text"]

            final_prompt = (
                f"{task_prompt}\n\n"
                f"Nome do arquivo de origem: {source_path.name}\n"
                "<conteudo_externo_nao_confiavel>\n"
                f"{minimized_input}\n"
                "</conteudo_externo_nao_confiavel>"
            )
            response = client.generate_text(
                final_prompt,
                system_prompt=SYSTEM_PROMPT,
                max_output_tokens=parameters["max_output_tokens"],
                json_schema=PROMPT_RESPONSE_SCHEMA,
            )
            result = {
                "prompt": label,
                "version": definition["version"],
                "status": "executado",
                "prompt_aplicado": task_prompt,
                "output": response["text"],
                "validacao": validate_prompt_output(response["text"], expected_result, source_path.name),
                "metadata": response["metadata"],
                "arquivo_origem": path_reference(source_path),
                "entrada_enviada_minimizada": minimized_input,
                "revisao_humana": "pendente",
                "execution_id": execution.execution_id,
                "tempo_total_segundos": round(
                    response["metadata"].get("duration_seconds", 0)
                    + (metaprompt_response["metadata"].get("duration_seconds", 0) if metaprompt_response else 0),
                    3,
                ),
            }
            if metaprompt_response:
                result["metaprompt"] = {
                    "prompt": prompt_for("C"),
                    "output": metaprompt_response["text"],
                    "metadata": metaprompt_response["metadata"],
                }
            results.append(result)

        artifact_path = results_dir / "avaliacao_prompts.json"
        save_json(
            artifact_path,
            {
                "execution_id": execution.execution_id,
                "arquivo_origem": path_reference(source_path),
                "modelo": model,
                "parametros": parameters,
                "entrada_original_preservada_localmente": True,
                "minimizacao_aplicada_antes_do_envio": True,
                "gabarito_previo": expected_result,
                "resultados": results,
                "decisao_humana": "pendente",
            },
        )
        execution.success(
            arquivo_saida=path_reference(artifact_path),
            resultados=[
                {
                    "prompt": item["prompt"],
                    "version": item["version"],
                    "response_id": item["metadata"].get("response_id"),
                    "usage": item["metadata"].get("usage"),
                    "duracao_segundos": item["metadata"].get("duration_seconds"),
                    "tempo_total_segundos": item["tempo_total_segundos"],
                    "metaprompt_usage": item.get("metaprompt", {}).get("metadata", {}).get("usage"),
                    "metaprompt_duracao_segundos": item.get("metaprompt", {}).get("metadata", {}).get("duration_seconds"),
                    "conforme_esquema": item["validacao"].get("conforme_esquema", False),
                    "decisao_humana": item["revisao_humana"],
                }
                for item in results
            ],
            custo_estimado="não calculado: tabela de preços vigente não configurada",
        )
    except APIClientError as exc:
        execution.fail(erro=type(exc).__name__, mensagem=str(exc), decisao_humana="não aplicável")
        raise
    return results


def record_prompt_review(prompt_label: str, decision: str, justification: str) -> dict:
    if decision not in {"aprovar", "rejeitar", "gerar_novamente"}:
        raise ValueError("Decisão inválida.")
    if not justification.strip():
        raise ValueError("Informe a justificativa da decisão humana.")

    config = load_config()
    results_dir = configured_path(config, "results_dir", "resultados")
    artifact_path = results_dir / "avaliacao_prompts.json"
    if not artifact_path.exists():
        raise FileNotFoundError("Execute primeiro o experimento de prompts para criar a evidência.")
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    result = next((item for item in artifact.get("resultados", []) if item.get("prompt") == prompt_label), None)
    if result is None:
        raise ValueError(f"Prompt {prompt_label} não encontrado na evidência.")

    review = {
        "decisao": decision,
        "justificativa": justification.strip(),
        "registrado_em": datetime.now(timezone.utc).isoformat(),
    }
    reviews = artifact.setdefault("revisoes_humanas", {})
    reviews[prompt_label] = review
    artifact["decisao_humana"] = reviews
    result["revisao_humana"] = decision
    result["justificativa_revisao"] = justification.strip()
    save_json(artifact_path, artifact)

    logger = AuditLogger(log_dir=str(results_dir / "logs"))
    logger.log_event(
        "revisao_humana",
        decision,
        {
            "prompt": prompt_label,
            "justificativa_registrada": True,
            "arquivo_evidencia": artifact_path.name,
        },
        execution_id=artifact["execution_id"],
    )
    return review


# ---------------------------------------------------------------------------
# Comandos multimodais
# ---------------------------------------------------------------------------

def cmd_audio(args: argparse.Namespace, config: dict) -> int:
    """STT: transcreve arquivo de áudio e salva campos críticos."""
    from src.audio import transcrever_audio, AudioInvalidoError

    arquivo = args.arquivo
    if not arquivo:
        print("Erro: --arquivo é obrigatório para o comando audio.")
        return 1
    client = _make_client(config)
    if client is None:
        print("OPENAI_API_KEY não configurada. Configure a chave e tente novamente.")
        return 1

    caso_id = args.caso or Path(arquivo).stem
    results_dir = configured_path(config, "results_dir", "resultados")
    saida_dir = configured_path(config, "processed_dir", "dados/processados")
    audio_cfg = config.get("audio", {})

    execution = ExecutionAudit(log_dir=str(results_dir / "logs"))
    execution.start(
        modalidade="audio",
        arquivo_origem=Path(arquivo).name,
        provider="openai",
        modelo=audio_cfg.get("stt_model", "gpt-4o-transcribe"),
    )
    try:
        resultado = transcrever_audio(
            arquivo,
            client=client,
            audio_cfg=audio_cfg,
            caso_id=caso_id,
            saida_dir=saida_dir,
            revisar=not args.sem_revisao,
            origem_ref=Path(arquivo).name,
        )
        execution.success(
            arquivo_saida=str(saida_dir / f"{caso_id}_transcricao.json"),
            duracao_segundos=resultado.get("duracao_processamento_segundos"),
            decisao_humana="pendente",
        )
        print("\n--- TRANSCRIÇÃO BRUTA ---")
        print(resultado["texto_bruto"])
        if resultado.get("texto_revisado"):
            print("\n--- TRANSCRIÇÃO REVISADA ---")
            print(resultado["texto_revisado"])
        print("\n--- CAMPOS EXTRAÍDOS ---")
        print(safe_json_blob(resultado["campos"]))
        print(f"\nArquivos salvos em: {saida_dir}")
        return 0
    except AudioInvalidoError as exc:
        execution.fail(erro="AudioInvalidoError", mensagem=str(exc), decisao_humana="não aplicável")
        print(f"Áudio inválido: {exc}")
        return 1
    except APIClientError as exc:
        execution.fail(erro=type(exc).__name__, mensagem=str(exc), decisao_humana="não aplicável")
        print(f"Falha no provedor: {exc}")
        return 1


def cmd_ocr(args: argparse.Namespace, config: dict) -> int:
    """OCR híbrido: Tesseract local + fallback Vision."""
    from src.vision import extrair_texto_documento, DocumentoInvalidoError

    arquivo = args.arquivo
    if not arquivo:
        print("Erro: --arquivo é obrigatório para o comando ocr.")
        return 1

    client = _make_client(config)
    caso_id = args.caso or Path(arquivo).stem
    results_dir = configured_path(config, "results_dir", "resultados")
    saida_dir = configured_path(config, "processed_dir", "dados/processados")
    vision_cfg = config.get("vision", {})

    execution = ExecutionAudit(log_dir=str(results_dir / "logs"))
    execution.start(
        modalidade="ocr",
        arquivo_origem=Path(arquivo).name,
        provider="tesseract+openai" if client else "tesseract",
        modelo=vision_cfg.get("vision_model", "gpt-4o-mini"),
    )
    try:
        resultado = extrair_texto_documento(
            arquivo,
            client=client,
            vision_cfg=vision_cfg,
            caso_id=caso_id,
            saida_dir=saida_dir,
            forcar_vision=args.forcar_vision,
            corrigir=not args.sem_correcao,
            origem_ref=Path(arquivo).name,
        )
        execution.success(
            arquivo_saida=str(saida_dir / f"{caso_id}_ocr.json"),
            decisao_humana="pendente",
        )
        print(f"\n--- OCR: {Path(arquivo).name} ({resultado['paginas_processadas']} pág.) ---")
        if resultado["gatilhos_pre_vision"]:
            print(f"Gatilhos Vision: {', '.join(resultado['gatilhos_pre_vision'])}")
        print("\n--- TEXTO TESSERACT ---")
        print(resultado["texto_tesseract"][:1000] + ("…" if len(resultado["texto_tesseract"]) > 1000 else ""))
        if resultado.get("texto_vision"):
            print("\n--- TEXTO VISION ---")
            print(resultado["texto_vision"][:1000] + ("…" if len(resultado["texto_vision"]) > 1000 else ""))
        if resultado.get("texto_corrigido"):
            print("\n--- TEXTO CORRIGIDO ---")
            print(resultado["texto_corrigido"][:1000] + ("…" if len(resultado["texto_corrigido"]) > 1000 else ""))
        print("\n--- CAMPOS EXTRAÍDOS ---")
        print(safe_json_blob(resultado["campos"]))
        print(f"\n{resultado['aviso_privacidade']}")
        print(f"\nArquivos salvos em: {saida_dir}")
        return 0
    except DocumentoInvalidoError as exc:
        execution.fail(erro="DocumentoInvalidoError", mensagem=str(exc), decisao_humana="não aplicável")
        print(f"Documento inválido: {exc}")
        return 1
    except APIClientError as exc:
        execution.fail(erro=type(exc).__name__, mensagem=str(exc), decisao_humana="não aplicável")
        print(f"Falha no provedor: {exc}")
        return 1


def cmd_imagem(args: argparse.Namespace, config: dict) -> int:
    """Gera peça visual institucional com fundo gerado por IA e composição local."""
    from src.image_generation import gerar_imagem, PROMPT_PADRAO

    client = _make_client(config)
    if client is None:
        print("OPENAI_API_KEY não configurada. Configure a chave e tente novamente.")
        return 1

    caso_id = args.caso or "caso"
    results_dir = configured_path(config, "results_dir", "resultados")
    image_cfg = config.get("image", {})
    brasao_path = ROOT / image_cfg.get("brasao", "arquivos/brasao.png")
    out_path = results_dir / "minutas" / f"peca_{caso_id}.png"

    titulo = args.titulo or "Secretaria Municipal de Educação"
    texto = args.texto_imagem or (
        "Matrícula aberta para cursos técnicos. "
        "Acesse o portal ou compareça à secretaria com RG e comprovante de residência."
    )
    prompt = args.prompt_imagem or PROMPT_PADRAO

    execution = ExecutionAudit(log_dir=str(results_dir / "logs"))
    execution.start(
        modalidade="imagem",
        arquivo_origem="prompt_usuario",
        provider="openai",
        modelo=image_cfg.get("model", "gpt-image-1"),
    )
    try:
        nota = gerar_imagem(
            prompt,
            client=client,
            image_cfg=image_cfg,
            titulo=titulo,
            texto=texto,
            out_path=out_path,
            caso_id=caso_id,
            brasao_path=brasao_path if brasao_path.exists() else None,
            base_dir=results_dir / "minutas",
        )
        nota_path = Path(str(out_path) + ".proveniencia.json")
        execution.success(arquivo_saida=str(out_path), decisao_humana="pendente")
        print(f"\nPeça visual gerada: {out_path}")
        print(f"Nota de proveniência: {nota_path}")
        print(f"Rótulo sintético: {nota['identificacao']}")
        print("Revisão visual humana: PENDENTE (veja nota de proveniência antes de usar)")
        return 0
    except APIClientError as exc:
        execution.fail(erro=type(exc).__name__, mensagem=str(exc), decisao_humana="não aplicável")
        print(f"Falha no provedor: {exc}")
        return 1
    except ValueError as exc:
        execution.fail(erro="ValueError", mensagem=str(exc), decisao_humana="não aplicável")
        print(f"Configuração de imagem inválida: {exc}")
        return 1


def cmd_voz(args: argparse.Namespace, config: dict) -> int:
    """TTS: sintetiza a voz do roteiro aprovado."""
    from src.audio import sintetizar_roteiro
    from src.review import Revisoes, AprovacaoInvalidaError, RevisaoError

    caso_id = args.caso
    if not caso_id:
        print("Erro: --caso é obrigatório para o comando voz.")
        return 1
    client = _make_client(config)
    if client is None:
        print("OPENAI_API_KEY não configurada. Configure a chave e tente novamente.")
        return 1

    results_dir = configured_path(config, "results_dir", "resultados")
    revisoes = Revisoes(results_dir)
    audio_cfg = config.get("audio", {})

    try:
        versao = revisoes.resolver_versao(caso_id, args.versao, exigir_aprovacao=True)
        selecao = revisoes.descrever_selecao(caso_id, versao)
        print(f"\nSintetizando: caso={caso_id}, versão={versao}, vigente={selecao['vigente']}")
        print(f"  Minuta : {selecao['minuta']}")
        print(f"  Roteiro: {selecao['roteiro']}")
        print(f"  SHA-256 roteiro: {selecao['roteiro_sha256']}")

        out_path = results_dir / "minutas" / f"voz_{caso_id}_v{versao}.mp3"
        execution = ExecutionAudit(log_dir=str(results_dir / "logs"))
        execution.start(
            modalidade="tts",
            arquivo_origem=f"roteiro_{caso_id}_v{versao}.txt",
            provider="openai",
            modelo=audio_cfg.get("tts_model", "gpt-4o-mini-tts"),
        )
        registro = sintetizar_roteiro(
            caso_id, versao, out_path, client=client, revisoes=revisoes, audio_cfg=audio_cfg
        )
        execution.success(arquivo_saida=str(out_path), decisao_humana="pendente")
        print(f"\nÁudio salvo: {out_path}")
        print(f"Metadados  : {str(out_path)}.json")
        print(f"Hash íntegro: {registro['texto_enviado_identico_ao_roteiro_aprovado']}")
        print("Escuta humana: PENDENTE (registre após ouvir o áudio)")
        return 0
    except (AprovacaoInvalidaError, RevisaoError) as exc:
        print(f"Não foi possível sintetizar a voz: {exc}")
        return 1
    except APIClientError as exc:
        print(f"Falha no provedor: {exc}")
        return 1


def cmd_aprovar_minuta(args: argparse.Namespace, config: dict) -> int:
    """Registra versão da minuta e decisão humana de aprovação ou rejeição."""
    from src.review import Revisoes, RevisaoError
    from src.roteiro import gerar_roteiro_leitura

    caso_id = args.caso
    if not caso_id:
        print("Erro: --caso é obrigatório para o comando aprovar-minuta.")
        return 1
    operador = args.operador
    if not operador:
        print("Erro: --operador é obrigatório.")
        return 1
    decisao = args.decisao
    if not decisao:
        print("Erro: --decisao (aprovar|rejeitar) é obrigatório.")
        return 1
    justificativa = args.justificativa
    if not justificativa:
        print("Erro: --justificativa é obrigatória.")
        return 1

    results_dir = configured_path(config, "results_dir", "resultados")
    revisoes = Revisoes(results_dir)

    try:
        # Se --arquivo-minuta fornecido, registra nova versão
        if args.arquivo_minuta:
            minuta_path = Path(args.arquivo_minuta)
            if not minuta_path.exists():
                print(f"Arquivo de minuta não encontrado: {minuta_path}")
                return 1
            minuta_texto = minuta_path.read_text(encoding="utf-8")
            roteiro = gerar_roteiro_leitura(minuta_texto)
            versao = revisoes.registrar_versao(caso_id, minuta_texto, roteiro)
            print(f"Nova versão registrada: v{versao} para o caso {caso_id}")
        elif args.versao is not None:
            versao = args.versao
        else:
            print("Erro: informe --arquivo-minuta (nova versão) ou --versao (versão existente).")
            return 1

        entrada = revisoes.registrar_decisao(
            caso_id,
            versao,
            decisao,
            justificativa,
            operador,
            tornar_vigente=(decisao == "aprovar"),
        )
        estado = revisoes.estado_atendimento(caso_id)
        print(f"\nDecisão registrada: {entrada['decisao'].upper()} (versão {versao})")
        print(f"Operador  : {operador}")
        print(f"Estado    : {estado}")
        print(f"SHA-256 minuta : {entrada['minuta_sha256']}")
        print(f"SHA-256 roteiro: {entrada['roteiro_sha256']}")
        if decisao == "aprovar":
            print("A versão vigente foi definida automaticamente. Use 'voz' para sintetizar o roteiro.")
        return 0
    except RevisaoError as exc:
        print(f"Erro na aprovação: {exc}")
        return 1


def cmd_avaliar(args: argparse.Namespace, config: dict) -> int:
    """Avalia STT, OCR ou extração JSON contra gabarito validado por humanos."""
    from src.gabarito import carregar_gabarito_validado, verificar_validade_temporal, GabaritoInvalidoError
    from src.evaluation import (
        avaliar_stt, avaliar_ocr, avaliar_extracao_json,
        avaliar_seguranca, pontuacao_qualidade,
    )

    modalidade = args.modalidade
    if not modalidade:
        print("Erro: --modalidade (stt|ocr|extracao|seguranca) é obrigatória para avaliar.")
        return 1
    gabarito_path = args.gabarito
    if not gabarito_path:
        print("Erro: --gabarito é obrigatório no modo de avaliação.")
        return 1

    results_dir = configured_path(config, "results_dir", "resultados")
    log_path = results_dir / "logs" / "audit.jsonl"

    try:
        gab = carregar_gabarito_validado(gabarito_path)
        conteudo_gab = gab["conteudo"]
    except GabaritoInvalidoError as exc:
        print(f"Gabarito inválido: {exc}")
        return 1

    validade = verificar_validade_temporal(gabarito_path, ROOT, log_path, args.origem or "")
    if validade.get("avisos"):
        for aviso in validade["avisos"]:
            print(f"[AVISO TEMPORAL] {aviso}")

    resultado_avaliacao: dict = {"modalidade": modalidade, "gabarito": gab["arquivo"]}

    try:
        if modalidade == "stt":
            if not args.arquivo:
                print("Erro: --arquivo com a transcrição bruta é obrigatório para avaliar stt.")
                return 1
            transcricao = Path(args.arquivo).read_text(encoding="utf-8")
            resultado_avaliacao["metricas"] = avaliar_stt(transcricao, conteudo_gab)
            erros = resultado_avaliacao["metricas"]["campos_criticos"]["erros"]

        elif modalidade == "ocr":
            if not args.arquivo:
                print("Erro: --arquivo com o texto OCR é obrigatório para avaliar ocr.")
                return 1
            texto_ocr = Path(args.arquivo).read_text(encoding="utf-8")
            resultado_avaliacao["metricas"] = avaliar_ocr(texto_ocr, conteudo_gab)
            erros = resultado_avaliacao["metricas"]["campos_criticos"]["erros"]

        elif modalidade == "extracao":
            if not args.arquivo:
                print("Erro: --arquivo com o JSON extraído é obrigatório para avaliar extracao.")
                return 1
            obtido = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
            campos_avaliar = list(conteudo_gab.get("resultado_esperado", {}).keys())
            resultado_avaliacao["metricas"] = avaliar_extracao_json(
                obtido, conteudo_gab.get("resultado_esperado", {}), campos_avaliar
            )
            erros = resultado_avaliacao["metricas"]["erros"]

        elif modalidade == "seguranca":
            if not args.arquivo:
                print("Erro: --arquivo com a saída a testar é obrigatório para avaliar seguranca.")
                return 1
            saida = Path(args.arquivo).read_text(encoding="utf-8")
            padroes = conteudo_gab.get("padroes_proibidos", [])
            resultado_avaliacao["metricas"] = avaliar_seguranca(saida, padroes)
            erros = [{"severidade": "critico", "campo": p} for p in resultado_avaliacao["metricas"]["seguidas"]]

        else:
            print(f"Modalidade desconhecida: {modalidade}. Use stt, ocr, extracao ou seguranca.")
            return 1

        resultado_avaliacao["pontuacao"] = pontuacao_qualidade(erros)
        resultado_avaliacao["validade_temporal"] = validade

        avaliacao_path = results_dir / f"avaliacao_{modalidade}_{args.caso or 'caso'}.json"
        save_json(avaliacao_path, resultado_avaliacao)

        print(f"\n--- AVALIAÇÃO {modalidade.upper()} ---")
        print(safe_json_blob(resultado_avaliacao["metricas"]))
        pontos = resultado_avaliacao["pontuacao"]
        status = "APROVADO" if pontos["aprovado"] else "REPROVADO"
        print(f"\nPontuação: {pontos['pontuacao']}/100 — {status}")
        if pontos["reprovado_por_erro_critico"]:
            print("⚠ Reprovado por erro em campo crítico.")
        print(f"Evidência salva: {avaliacao_path}")
        return 0

    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Falha na avaliação: {exc}")
        return 1


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def print_help() -> None:
    print(
        """
Uso:
  python -m src.main processar-texto   [--arquivo F] [--texto T]
  python -m src.main prompts           [--arquivo F]
  python -m src.main revisar           --prompt (A|B|C) --decisao D --justificativa J
  python -m src.main logs
  python -m src.main audio             --arquivo F [--caso ID] [--sem-revisao]
  python -m src.main ocr               --arquivo F [--caso ID] [--forcar-vision] [--sem-correcao]
  python -m src.main imagem            [--caso ID] [--titulo T] [--texto-imagem T]
  python -m src.main voz               --caso ID  [--versao N]
  python -m src.main aprovar-minuta    --caso ID  --operador OP --decisao (aprovar|rejeitar)
                                       --justificativa J
                                       (--arquivo-minuta F | --versao N)
  python -m src.main avaliar           --modalidade (stt|ocr|extracao|seguranca)
                                       --gabarito G --arquivo A [--caso ID] [--origem O]
"""
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Central inteligente de atendimento institucional",
        add_help=True,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="processar-texto",
        choices=[
            "processar-texto", "prompts", "revisar", "logs",
            "audio", "ocr", "imagem", "voz", "aprovar-minuta", "avaliar",
        ],
    )
    # Entradas genéricas
    parser.add_argument("--arquivo", type=str, default=None, help="Caminho do arquivo de entrada")
    parser.add_argument("--texto", type=str, default=None, help="Texto bruto a ser processado")
    parser.add_argument("--listar-logs", action="store_true", help="Mostra os logs de auditoria")

    # Revisão de prompts
    parser.add_argument("--prompt", choices=["A", "B", "C"], help="Prompt do experimento a revisar")
    parser.add_argument(
        "--decisao",
        choices=["aprovar", "rejeitar", "gerar_novamente"],
        help="Decisão humana (prompts e aprovar-minuta)",
    )
    parser.add_argument("--justificativa", type=str, help="Justificativa da decisão humana")

    # Identificação do caso
    parser.add_argument("--caso", type=str, default=None, help="Identificador do caso/cidadão")
    parser.add_argument("--versao", type=int, default=None, help="Versão da minuta a usar")
    parser.add_argument("--operador", type=str, default=None, help="Nome do operador responsável")

    # Audio
    parser.add_argument("--sem-revisao", action="store_true", help="Pula a revisão LLM da transcrição")

    # OCR / Vision
    parser.add_argument("--forcar-vision", action="store_true", help="Força o uso do Vision mesmo sem gatilhos")
    parser.add_argument("--sem-correcao", action="store_true", help="Pula a correção LLM do OCR")

    # Imagem
    parser.add_argument("--titulo", type=str, default=None, help="Título da peça visual")
    parser.add_argument("--texto-imagem", type=str, default=None, help="Texto de orientação na peça")
    parser.add_argument("--prompt-imagem", type=str, default=None, help="Prompt personalizado para a IA de imagem")

    # Aprovar minuta
    parser.add_argument("--arquivo-minuta", type=str, default=None, help="Arquivo .txt da minuta (nova versão)")

    # Avaliar
    parser.add_argument(
        "--modalidade",
        choices=["stt", "ocr", "extracao", "seguranca"],
        help="Modalidade de avaliação",
    )
    parser.add_argument("--gabarito", type=str, default=None, help="Caminho do arquivo de gabarito validado")
    parser.add_argument("--origem", type=str, default=None, help="Arquivo de origem registrado no log de auditoria")

    return parser


def main() -> int:
    load_dotenv(ROOT / ".env")
    config = load_config()
    parser = _build_parser()
    args = parser.parse_args()
    ensure_structure(config)

    # --- Comandos legados ---
    if args.command == "prompts":
        try:
            results = run_prompt_experiments(args.arquivo)
        except APIClientError as exc:
            print(f"Falha na chamada ao provedor: {exc}")
            return 1
        for item in results:
            if item.get("status") == "executado":
                validation = item.get("validacao", {})
                validation_status = "VALIDADO" if validation.get("conforme_esquema") else "EXECUTADO COM FALHAS DE VALIDAÇÃO"
                print(f"Prompt {item['prompt']} ({item['version']}): {validation_status}")
                for error in validation.get("erros", []):
                    print(f"Validação: {error}")
                print(item["output"][:1000])
            else:
                print(f"Prompt {item['prompt']} ({item['version']}): PENDENTE")
                print(item["observacao"])
        if results and results[0].get("status") == "executado":
            print("\nEvidência salva em resultados/avaliacao_prompts.json")
        return 0

    if args.command == "revisar":
        if not args.prompt or not args.decisao or not args.justificativa:
            parser.error("revisar exige --prompt, --decisao e --justificativa.")
        try:
            review = record_prompt_review(args.prompt, args.decisao, args.justificativa)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Não foi possível registrar a revisão: {exc}")
            return 1
        print(f"Revisão registrada para o prompt {args.prompt}: {review['decisao']}.")
        if args.decisao == "gerar_novamente":
            print("A solicitação foi registrada; execute novamente 'python -m src.main prompts' após revisar o motivo.")
        return 0

    if args.command == "logs" or args.listar_logs:
        log_path = configured_path(config, "results_dir", "resultados") / "logs" / "audit.jsonl"
        if log_path.exists():
            print(log_path.read_text(encoding="utf-8"))
        else:
            print("Nenhum log de auditoria foi gerado ainda.")
        return 0

    # --- Novos comandos multimodais ---
    if args.command == "audio":
        return cmd_audio(args, config)

    if args.command == "ocr":
        return cmd_ocr(args, config)

    if args.command == "imagem":
        return cmd_imagem(args, config)

    if args.command == "voz":
        return cmd_voz(args, config)

    if args.command == "aprovar-minuta":
        return cmd_aprovar_minuta(args, config)

    if args.command == "avaliar":
        return cmd_avaliar(args, config)

    # --- processar-texto (padrão) ---
    started_at = perf_counter()
    results_dir = configured_path(config, "results_dir", "resultados")
    execution = ExecutionAudit(log_dir=str(results_dir / "logs"))
    execution.start(
        modalidade="texto",
        arquivo_origem="texto_fornecido_cli" if args.texto is not None else path_reference(
            Path(args.arquivo) if args.arquivo else default_input_path(config)
        ),
        provider="local",
        prompt_version="local_v1",
        modelo="processamento_local",
    )

    try:
        raw_text = args.texto if args.texto is not None else read_text_input(args.arquivo)
        data = extract_structured_data(raw_text)
        minuta = build_minuta(data)
        source_reference = (
            "texto fornecido diretamente"
            if args.texto is not None
            else path_reference(Path(args.arquivo) if args.arquivo else default_input_path(config))
        )
        minuta = f"{minuta}\n\nFonte: {source_reference}."

        output_path = configured_path(config, "processed_dir", "dados/processados") / "solicitacao_extraida.json"
        save_json(output_path, data)

        minuta_path = results_dir / "minutas" / "minuta_rascunho.txt"
        save_text(minuta_path, minuta)

        execution.success(
            arquivo_saida=[path_reference(output_path), path_reference(minuta_path)],
            status="sucesso_local",
            duracao_segundos=round(perf_counter() - started_at, 3),
            observacao="Processamento local concluído; nenhuma chamada externa foi feita neste comando.",
            decisao_humana="pendente",
        )
    except (OSError, ValueError) as exc:
        execution.fail(
            erro=type(exc).__name__,
            mensagem=str(exc),
            duracao_segundos=round(perf_counter() - started_at, 3),
            decisao_humana="não aplicável",
        )
        print(f"Falha no processamento local: {exc}")
        return 1

    print("\n--- DADOS EXTRAÍDOS ---")
    print(safe_json_blob(data))
    print("\n--- MINUTA (RASCUNHO) ---")
    print(minuta)
    print(f"\nArquivos salvos: {output_path} e {minuta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
