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

from src.audit import ArtifactRegistry, AuditLogger, ExecutionAudit, sha256_file
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
        criticos = expected.get("campos_criticos", {})
        expected_fields = expected.get("resultado_esperado", {})
        for field in ("protocolo", "data", "solicitante"):
            target_val = expected_fields.get(field) or criticos.get(field)
            if target_val and payload.get(field) != target_val:
                errors.append(f"Valor divergente do gabarito: {field}.")
        if "categoria" in expected_fields and payload.get("categoria") != expected_fields.get("categoria"):
            errors.append("Valor divergente do gabarito: categoria.")
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
    from src.image_generation import gerar_imagem, registrar_revisao_visual, PROMPT_PADRAO

    caso_id = args.caso or "caso"
    results_dir = configured_path(config, "results_dir", "resultados")
    out_path = results_dir / "minutas" / f"peca_{caso_id}.png"

    # Revisão visual sob demanda
    if getattr(args, "revisar_visual", False):
        nota_path = Path(str(out_path) + ".proveniencia.json")
        if not nota_path.exists():
            print(f"Erro: Nota de proveniência não encontrada para revisão: {nota_path}")
            return 1
        operador = args.operador or os.getenv("USER") or "operador"
        itens = {"texto": True, "simbolos": True, "maos": True, "objetos": True, "coerencia_visual": True}
        nota = registrar_revisao_visual(nota_path, operador, itens, observacao=args.justificativa or "Revisão visual humana aprovada.")
        print(f"\nRevisão visual humana aprovada para {out_path.name}")
        print(f"Operador: {operador}")
        print(f"Status da peça: UTILIZÁVEL ({nota.get('identificacao')})")
        return 0

    client = _make_client(config)
    if client is None:
        print("OPENAI_API_KEY não configurada. Configure a chave e tente novamente.")
        return 1

    image_cfg = config.get("image", {})
    brasao_path = ROOT / image_cfg.get("brasao", "arquivos/brasao.png")

    titulo = args.titulo or "Secretaria Municipal de Educação"
    texto = args.texto_imagem

    # Se --usar-minuta, resolve a versão aprovada e utiliza seu texto
    if getattr(args, "usar_minuta", False):
        from src.review import Revisoes, AprovacaoInvalidaError, RevisaoError
        revisoes = Revisoes(results_dir)
        try:
            versao = revisoes.resolver_versao(caso_id, args.versao, exigir_aprovacao=True)
            minuta_path = revisoes._arquivos(caso_id, versao)[0]
            minuta_texto = minuta_path.read_text(encoding="utf-8")
            if not texto:
                texto = minuta_texto[:240].strip() + ("..." if len(minuta_texto) > 240 else "")
            print(f"Usando texto da minuta aprovada v{versao} do caso {caso_id}.")
        except (AprovacaoInvalidaError, RevisaoError) as exc:
            print(f"Não foi possível utilizar a minuta: {exc}")
            return 1

    if not texto:
        texto = (
            "Matrícula aberta para cursos técnicos. "
            "Acesse o portal ou compareça à secretaria com RG e comprovante de residência."
        )
    prompt = args.prompt_imagem or PROMPT_PADRAO

    registry = ArtifactRegistry(results_dir, caso_id, base_dir=ROOT)
    registry.iniciar("imagem", versao=1)

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
        registry.concluir("imagem", versao=1, arquivo=out_path)
        execution.success(arquivo_saida=str(out_path), decisao_humana="pendente")
        print(f"\nPeça visual gerada: {out_path}")
        print(f"Nota de proveniência: {nota_path}")
        print(f"Rótulo sintético: {nota['identificacao']}")
        print("Revisão visual humana: PENDENTE (use --revisar-visual para aprovar após inspeção)")
        return 0
    except APIClientError as exc:
        registry.falhar("imagem", versao=1, erro=str(exc))
        execution.fail(erro=type(exc).__name__, mensagem=str(exc), decisao_humana="não aplicável")
        print(f"Falha no provedor: {exc}")
        return 1
    except ValueError as exc:
        registry.falhar("imagem", versao=1, erro=str(exc))
        execution.fail(erro="ValueError", mensagem=str(exc), decisao_humana="não aplicável")
        print(f"Configuração de imagem inválida: {exc}")
        return 1


def cmd_voz(args: argparse.Namespace, config: dict) -> int:
    """TTS: sintetiza a voz do roteiro aprovado."""
    from src.audio import sintetizar_roteiro
    from src.evaluation import wer
    from src.review import AprovacaoInvalidaError, RevisaoError, Revisoes

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
        print(f"\n--- SELEÇÃO DE SÍNTESE DE VOZ ---")
        print(f"Caso   : {caso_id}")
        print(f"Versão : v{versao} (vigente: {selecao['vigente']})")
        print(f"Minuta : {selecao['minuta']}")
        print(f"Roteiro: {selecao['roteiro']}")
        print(f"SHA-256 minuta : {selecao['minuta_sha256']}")
        print(f"SHA-256 roteiro: {selecao['roteiro_sha256']}")

        if not getattr(args, "confirmar", False):
            print("\n[CONFIRMAÇÃO NECESSÁRIA]")
            print("A síntese consome serviço de TTS e enviará estritamente o roteiro canônico aprovado.")
            print("Execute novamente com '--confirmar' para realizar a síntese.")
            return 0

        registry = ArtifactRegistry(results_dir, caso_id, base_dir=ROOT)
        registry.iniciar("audio", versao=versao)

        out_path = results_dir / "minutas" / f"voz_{caso_id}_v{versao}.mp3"
        execution = ExecutionAudit(log_dir=str(results_dir / "logs"))
        execution.start(
            modalidade="tts",
            arquivo_origem=f"roteiro_{caso_id}_v{versao}.txt",
            provider="openai",
            modelo=audio_cfg.get("tts_model", "gpt-4o-mini-tts"),
        )
        try:
            registro = sintetizar_roteiro(
                caso_id, versao, out_path, client=client, revisoes=revisoes, audio_cfg=audio_cfg
            )
            registry.concluir("audio", versao=versao, arquivo=out_path)
            execution.success(arquivo_saida=str(out_path), decisao_humana="pendente")
        except Exception as exc:
            registry.falhar("audio", versao=versao, erro=str(exc))
            execution.fail(erro=type(exc).__name__, mensagem=str(exc), decisao_humana="não aplicável")
            raise

        print(f"\nÁudio salvo: {out_path}")
        print(f"Metadados  : {str(out_path)}.json")
        print(f"Hash íntegro: {registro['texto_enviado_identico_ao_roteiro_aprovado']}")
        print("Escuta humana: PENDENTE (registre após ouvir o áudio)")

        if getattr(args, "verificar", False):
            print("\n--- TRANSCRIÇÃO DE RETORNO (VERIFICAÇÃO STT) ---")
            try:
                retorno = client.transcribe(str(out_path))
                texto_retorno = retorno["text"]
                roteiro_original = revisoes.ler_roteiro(caso_id, versao)
                taxa_wer = wer(roteiro_original, texto_retorno)
                print(f"WER da transcrição de retorno: {taxa_wer}")
                print("Nota: transcrição automática rotulada como indicial e falível; a escuta humana é a evidência principal.")
            except Exception as exc:
                print(f"Não foi possível executar a transcrição de retorno: {exc}")

        return 0
    except (AprovacaoInvalidaError, RevisaoError) as exc:
        print(f"Não foi possível sintetizar a voz: {exc}")
        return 1
    except APIClientError as exc:
        print(f"Falha no provedor: {exc}")
        return 1


def cmd_revisar(args: argparse.Namespace, config: dict) -> int:
    """Registra decisão humana sobre experimento de prompts ou sobre caso/minuta."""
    results_dir = configured_path(config, "results_dir", "resultados")

    # Caso: revisão de minuta institucional
    if args.caso:
        from src.review import Revisoes, RevisaoError
        caso_id = args.caso
        operador = args.operador or os.getenv("USER") or "operador"
        decisao = args.decisao
        if not decisao:
            print("Erro: --decisao (aprovar|rejeitar|gerar_novamente) é obrigatório.")
            return 1
        justificativa = args.justificativa
        if not justificativa:
            print("Erro: --justificativa é obrigatória.")
            return 1

        revisoes = Revisoes(results_dir)
        try:
            if decisao == "gerar_novamente":
                versao_base = args.versao or revisoes.versao_atual(caso_id) or 1
                revisoes.solicitar_nova_geracao(caso_id, versao_base, justificativa, operador)
                print(f"Solicitação de nova geração registrada para caso {caso_id} (base v{versao_base}): {justificativa}")
                return 0

            versao = args.versao
            if versao is None:
                versao = revisoes.versao_atual(caso_id)
                if versao is None:
                    versoes = [int(v) for v in revisoes._load(caso_id)["versoes"]]
                    if not versoes:
                        print(f"Nenhuma versão registrada para o caso {caso_id}.")
                        return 1
                    versao = max(versoes)

            entrada = revisoes.registrar_decisao(
                caso_id,
                versao,
                decisao,
                justificativa,
                operador,
                tornar_vigente=(decisao == "aprovar"),
            )
            estado = revisoes.estado_atendimento(caso_id)
            logger = AuditLogger(log_dir=str(results_dir / "logs"))
            logger.log_event(
                "revisao_humana_minuta",
                decisao,
                {
                    "caso": caso_id,
                    "versao": versao,
                    "operador": operador,
                    "justificativa": justificativa,
                    "minuta_sha256": entrada["minuta_sha256"],
                    "roteiro_sha256": entrada["roteiro_sha256"],
                },
            )
            print(f"\nDecisão registrada: {entrada['decisao'].upper()} (caso {caso_id}, versão {versao})")
            print(f"Operador  : {operador}")
            print(f"Estado    : {estado}")
            print(f"SHA-256 minuta : {entrada['minuta_sha256']}")
            print(f"SHA-256 roteiro: {entrada['roteiro_sha256']}")
            if decisao == "aprovar":
                print("A versão vigente foi definida automaticamente. Use 'voz' para sintetizar o roteiro.")
            return 0
        except RevisaoError as exc:
            print(f"Erro na revisão: {exc}")
            return 1

    # Prompt: revisão de experimentos de prompt (A, B, C)
    if args.prompt:
        if not args.decisao or not args.justificativa:
            print("Erro: revisar prompt exige --decisao e --justificativa.")
            return 1
        try:
            review = record_prompt_review(args.prompt, args.decisao, args.justificativa)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Não foi possível registrar a revisão: {exc}")
            return 1
        print(f"Revisão registrada para o prompt {args.prompt}: {review['decisao']}.")
        if args.decisao == "gerar_novamente":
            print("A solicitação foi registrada; execute novamente 'python -m src.main prompts' após revisar o motivo.")
        return 0

    print("Erro: comando revisar exige --prompt (A|B|C) ou --caso ID, com --decisao e --justificativa.")
    return 1


def cmd_vigente(args: argparse.Namespace, config: dict) -> int:
    """Define a versão vigente (versao_atual) da minuta de um caso."""
    from src.review import Revisoes, RevisaoError

    caso_id = args.caso
    if not caso_id:
        print("Erro: --caso é obrigatório para o comando vigente.")
        return 1
    if args.versao is None:
        print("Erro: --versao é obrigatório para o comando vigente.")
        return 1
    operador = args.operador or os.getenv("USER") or "operador"
    results_dir = configured_path(config, "results_dir", "resultados")
    revisoes = Revisoes(results_dir)
    try:
        revisoes.definir_versao_atual(caso_id, args.versao, operador)
        print(f"Versão vigente definida com sucesso: v{args.versao} para o caso {caso_id} (operador: {operador})")
        return 0
    except RevisaoError as exc:
        print(f"Erro ao definir versão vigente: {exc}")
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
    """Avalia STT, OCR, prompts ou extração JSON contra gabarito validado por humanos."""
    from src.gabarito import carregar_gabarito_validado, verificar_validade_temporal, GabaritoInvalidoError
    from src.evaluation import (
        avaliar_stt, avaliar_ocr, avaliar_extracao_json,
        avaliar_seguranca, avaliar_prompts_experimento, pontuacao_qualidade,
    )

    modalidade = getattr(args, "tipo", None) or args.modalidade
    if not modalidade:
        print("Erro: --tipo ou --modalidade (stt|ocr|extracao|seguranca|prompts) é obrigatório para avaliar.")
        return 1

    results_dir = configured_path(config, "results_dir", "resultados")
    log_path = results_dir / "logs" / "audit.jsonl"

    gabarito_path = args.gabarito
    if not gabarito_path:
        # Padrões automáticos para cada modalidade se não fornecido
        padroes = {
            "stt": ROOT / "dados/gabaritos/entrada_audio.json",
            "ocr": ROOT / "dados/gabaritos/entrada_pdf-imagem.json",
            "seguranca": ROOT / "dados/gabaritos/entrada_texto_injecao.json",
            "extracao": ROOT / "dados/gabaritos/entrada_texto.json",
            "prompts": ROOT / "dados/gabaritos/entrada_texto.json",
        }
        cand = padroes.get(modalidade)
        if cand and cand.exists():
            gabarito_path = str(cand)
        else:
            print("Erro: --gabarito é obrigatório no modo de avaliação.")
            return 1

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
            proc_dir = configured_path(config, "processed_dir", "dados/processados")
            if not args.arquivo:
                cands_txt = list(proc_dir.glob("*_transcricao_bruta.txt")) or list(proc_dir.glob("*_transcricao*.txt"))
                if cands_txt:
                    transcricao = cands_txt[0].read_text(encoding="utf-8")
                else:
                    cands = list(proc_dir.glob("*_transcricao.json"))
                    if cands:
                        t_dados = json.loads(cands[0].read_text(encoding="utf-8"))
                        transcricao = t_dados.get("texto_bruto", "")
                    else:
                        print("Erro: --arquivo com a transcrição bruta é obrigatório para avaliar stt.")
                        return 1
            else:
                arq_p = Path(args.arquivo)
                if arq_p.suffix == ".json":
                    t_dados = json.loads(arq_p.read_text(encoding="utf-8"))
                    transcricao = t_dados.get("texto_bruto", "")
                    if not transcricao:
                        txt_cand = arq_p.with_name(arq_p.stem + "_bruta.txt")
                        if not txt_cand.exists():
                            txt_cand = arq_p.with_suffix(".txt")
                        if txt_cand.exists():
                            transcricao = txt_cand.read_text(encoding="utf-8")
                else:
                    transcricao = arq_p.read_text(encoding="utf-8")

            resultado_avaliacao["metricas"] = avaliar_stt(transcricao, conteudo_gab)
            erros = resultado_avaliacao["metricas"]["campos_criticos"]["erros"]

        elif modalidade == "ocr":
            proc_dir = configured_path(config, "processed_dir", "dados/processados")
            if not args.arquivo:
                cands_txt = list(proc_dir.glob("*_ocr_corrigido.txt")) or list(proc_dir.glob("*_ocr_tesseract.txt")) or list(proc_dir.glob("*_ocr*.txt"))
                if cands_txt:
                    texto_ocr = cands_txt[0].read_text(encoding="utf-8")
                else:
                    cands = list(proc_dir.glob("*_ocr.json"))
                    if cands:
                        o_dados = json.loads(cands[0].read_text(encoding="utf-8"))
                        texto_ocr = o_dados.get("texto_tesseract", "") or o_dados.get("texto_corrigido", "")
                    else:
                        print("Erro: --arquivo com o texto OCR é obrigatório para avaliar ocr.")
                        return 1
            else:
                arq_p = Path(args.arquivo)
                if arq_p.suffix == ".json":
                    o_dados = json.loads(arq_p.read_text(encoding="utf-8"))
                    texto_ocr = o_dados.get("texto_tesseract", "") or o_dados.get("texto_corrigido", "")
                    if not texto_ocr:
                        txt_cand = arq_p.with_name(arq_p.stem + "_corrigido.txt")
                        if not txt_cand.exists():
                            txt_cand = arq_p.with_name(arq_p.stem + "_tesseract.txt")
                        if txt_cand.exists():
                            texto_ocr = txt_cand.read_text(encoding="utf-8")
                else:
                    texto_ocr = arq_p.read_text(encoding="utf-8")

            resultado_avaliacao["metricas"] = avaliar_ocr(texto_ocr, conteudo_gab)
            erros = resultado_avaliacao["metricas"]["campos_criticos"]["erros"]

        elif modalidade == "extracao":
            if not args.arquivo:
                cands = list((configured_path(config, "processed_dir", "dados/processados")).glob("*_estruturado.json"))
                if cands:
                    args.arquivo = str(cands[0])
                else:
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
                cand_inj = results_dir / "avaliacao_injecao_real.json"
                if cand_inj.exists():
                    args.arquivo = str(cand_inj)
                else:
                    cand_proc = Path("dados/processados/caso_injecao_estruturado.json")
                    if cand_proc.exists():
                        args.arquivo = str(cand_proc)
                    else:
                        print("Erro: --arquivo com a saída a testar é obrigatório para avaliar seguranca.")
                        return 1
            arq_p = Path(args.arquivo)
            if arq_p.suffix == ".json":
                try:
                    j_dados = json.loads(arq_p.read_text(encoding="utf-8"))
                    if "resultados" in j_dados and isinstance(j_dados["resultados"], list):
                        saida = " ".join([r.get("output", "") for r in j_dados["resultados"]])
                    elif "minuta" in j_dados:
                        saida = str(j_dados["minuta"])
                    else:
                        saida = arq_p.read_text(encoding="utf-8")
                except Exception:
                    saida = arq_p.read_text(encoding="utf-8")
            else:
                saida = arq_p.read_text(encoding="utf-8")
            padroes = conteudo_gab.get("padroes_proibidos", [])
            resultado_avaliacao["metricas"] = avaliar_seguranca(saida, padroes)
            erros = [{"severidade": "critico", "campo": p} for p in resultado_avaliacao["metricas"]["seguidas"]]

        elif modalidade == "prompts":
            prompts_path = Path(args.arquivo) if args.arquivo else results_dir / "avaliacao_prompts.json"
            if not prompts_path.exists():
                print(f"Erro: Arquivo de experimentos de prompts não encontrado: {prompts_path}")
                print("Execute primeiro 'python -m src.main prompts' para gerar os resultados.")
                return 1
            dados_exp = json.loads(prompts_path.read_text(encoding="utf-8"))
            resultado_avaliacao["metricas"] = avaliar_prompts_experimento(dados_exp, conteudo_gab)
            todos_erros = []
            for p_info in resultado_avaliacao["metricas"]["prompts"].values():
                todos_erros.extend(p_info.get("erros", []))
            erros = todos_erros

        else:
            print(f"Modalidade desconhecida: {modalidade}. Use stt, ocr, extracao, seguranca ou prompts.")
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


def cmd_fluxo(args: argparse.Namespace, config: dict) -> int:
    """Processa uma solicitação de ponta a ponta sem exigir gabarito."""
    from src.campos import extrair_campos, salvar_campos
    from src.review import Revisoes
    from src.roteiro import gerar_roteiro_leitura

    results_dir = configured_path(config, "results_dir", "resultados")
    saida_dir = configured_path(config, "processed_dir", "dados/processados")
    saida_dir.mkdir(parents=True, exist_ok=True)
    revisoes = Revisoes(results_dir)

    # Identificar entrada e modalidade
    arquivo_input = args.arquivo
    if not arquivo_input and args.texto is None:
        arquivo_input = str(default_input_path(config))

    arquivo_path = Path(arquivo_input) if arquivo_input else None
    if arquivo_path and not arquivo_path.is_absolute():
        arquivo_path = ROOT / arquivo_path

    if args.texto is not None:
        modalidade = "texto"
        origem_ref = "texto_cli"
        caso_id = args.caso or "caso_texto"
    else:
        assert arquivo_path is not None
        if not arquivo_path.exists():
            print(f"Erro: Arquivo não encontrado: {arquivo_path}")
            return 1
        sufixo = arquivo_path.suffix.lower()
        if sufixo in {".mp3", ".wav", ".m4a"}:
            modalidade = "audio"
        elif sufixo in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
            modalidade = "ocr"
        else:
            modalidade = "texto"
        origem_ref = arquivo_path.name
        caso_id = args.caso or arquivo_path.stem

    registry = ArtifactRegistry(results_dir, caso_id, base_dir=ROOT)
    if arquivo_path and arquivo_path.exists():
        registry.registrar_original(arquivo_path)

    print(f"\n=== FLUXO INTEGRADO — CASO: {caso_id} (MODALIDADE: {modalidade.upper()}) ===")
    print(f"Arquivo de origem: {origem_ref}")

    raw_text = ""
    campos = {}

    if modalidade == "audio":
        from src.audio import transcrever_audio
        client = _make_client(config)
        if client is None:
            print("OPENAI_API_KEY não configurada. Configure a chave para processar áudio.")
            return 1
        audio_cfg = config.get("audio", {})
        registry.iniciar("transcricao", versao=1)
        try:
            resultado = transcrever_audio(
                str(arquivo_path),
                client=client,
                audio_cfg=audio_cfg,
                caso_id=caso_id,
                saida_dir=saida_dir,
                revisar=not args.sem_revisao,
                origem_ref=origem_ref,
            )
            transcricao_path = saida_dir / f"{caso_id}_transcricao.json"
            registry.concluir("transcricao", versao=1, arquivo=transcricao_path)
            raw_text = resultado.get("texto_revisado") or resultado["texto_bruto"]
            campos = resultado["campos"]
        except Exception as exc:
            registry.falhar("transcricao", versao=1, erro=str(exc))
            print(f"Falha na transcrição: {exc}")
            return 1

    elif modalidade == "ocr":
        from src.vision import extrair_texto_documento
        client = _make_client(config)
        vision_cfg = config.get("vision", {})
        registry.iniciar("texto_ocr", versao=1)
        try:
            resultado = extrair_texto_documento(
                str(arquivo_path),
                client=client,
                vision_cfg=vision_cfg,
                caso_id=caso_id,
                saida_dir=saida_dir,
                forcar_vision=args.forcar_vision,
                corrigir=not args.sem_correcao,
                origem_ref=origem_ref,
            )
            ocr_path = saida_dir / f"{caso_id}_ocr.json"
            registry.concluir("texto_ocr", versao=1, arquivo=ocr_path)
            raw_text = resultado.get("texto_corrigido") or resultado.get("texto_vision") or resultado["texto_tesseract"]
            campos = resultado["campos"]
        except Exception as exc:
            registry.falhar("texto_ocr", versao=1, erro=str(exc))
            print(f"Falha no OCR: {exc}")
            return 1

    else:  # texto
        registry.iniciar("estruturado", versao=1)
        raw_text = args.texto if args.texto is not None else arquivo_path.read_text(encoding="utf-8")
        sha = sha256_file(arquivo_path) if arquivo_path and arquivo_path.exists() else None
        campos = extrair_campos(raw_text, origem=origem_ref, origem_sha256=sha, metodo="texto_original")

    # Salva proveniência por campo crítico
    campos_path = saida_dir / f"campos_{caso_id}.json"
    salvar_campos(campos_path, campos)
    salvar_campos(saida_dir / f"{caso_id}_campos.json", campos)

    print("\n--- CAMPOS CRÍTICOS EXTRAÍDOS ---")
    print(safe_json_blob(campos))

    # Bloqueio apenas se houver campo crítico INCERTO ou DIVERGENTE
    incertos = [nome for nome, item in campos.items() if item.get("status") in {"incerto", "divergente"}]
    if incertos:
        print(f"\n⚠ GERAÇÃO DA MINUTA SUSPENSA!")
        print(f"O(s) campo(s) crítico(s) {incertos} apresentam status incerto ou divergente.")
        print("Confirme ou corrija esses campos antes de prosseguir com a geração da minuta.")
        return 0

    # Extração estruturada e minuta
    data = extract_structured_data(raw_text)
    estruturado_path = saida_dir / f"{caso_id}_estruturado.json"
    save_json(estruturado_path, data)
    if modalidade != "texto":
        registry.iniciar("estruturado", versao=1)
    registry.concluir("estruturado", versao=1, arquivo=estruturado_path)

    minuta_texto = build_minuta(data)
    minuta_texto = f"{minuta_texto}\n\nFonte: {origem_ref}."
    roteiro_texto = gerar_roteiro_leitura(minuta_texto)

    versao = revisoes.registrar_versao(caso_id, minuta_texto, roteiro_texto)
    minuta_path, roteiro_path = revisoes._arquivos(caso_id, versao)

    registry.iniciar("minuta", versao=versao)
    registry.concluir("minuta", versao=versao, arquivo=minuta_path)
    registry.iniciar("roteiro_leitura", versao=versao)
    registry.concluir("roteiro_leitura", versao=versao, arquivo=roteiro_path)

    # Renderiza PDF institucional com brasão oficial
    from src.text_processing import render_minuta_pdf
    brasao_p = ROOT / "arquivos" / "brasao.png"
    pdf_path = minuta_path.with_suffix(".pdf")
    try:
        render_minuta_pdf(minuta_texto, pdf_path, brasao_path=brasao_p if brasao_p.exists() else None)
        registry.iniciar("minuta_pdf", versao=versao)
        registry.concluir("minuta_pdf", versao=versao, arquivo=pdf_path)
    except Exception as exc:
        print(f"[AVISO] Falha ao renderizar PDF da minuta: {exc}")

    execution = ExecutionAudit(log_dir=str(results_dir / "logs"))
    execution.start(
        modalidade=modalidade,
        arquivo_origem=origem_ref,
        provider="local",
        modelo="fluxo_integrado",
    )
    execution.success(
        arquivo_saida=[path_reference(minuta_path), path_reference(roteiro_path), path_reference(pdf_path)],
        decisao_humana="pendente",
        observacao="Fluxo integrado executado com sucesso; aguardando revisão humana.",
    )

    print("\n--- MINUTA INSTITUCIONAL GERADA (v1) ---")
    print(minuta_texto)
    print("\n--- ROTEIRO DE LEITURA CANÔNICO (v1) ---")
    print(roteiro_texto)
    print(f"\nArquivos salvos:")
    print(f"  Minuta : {minuta_path}")
    print(f"  PDF    : {pdf_path}")
    print(f"  Roteiro: {roteiro_path}")
    print(f"  Campos : {campos_path}")
    print("\n--- PRÓXIMOS PASSOS ---")
    print(f"  Aprovar: python -m src.main revisar --caso {caso_id} --versao {versao} --decisao aprovar --justificativa 'Dados conferidos' --operador 'Leo'")
    print(f"  Sintetizar voz: python -m src.main voz --caso {caso_id} --versao {versao} --confirmar")
    print(f"  Peça visual: python -m src.main imagem --caso {caso_id}")
    return 0


def cmd_relatorio(args: argparse.Namespace, config: dict) -> int:
    """Gera relatório consolidado de execuções, artefatos, revisões e avaliações."""
    from src.evaluation import taxa_aprovacao

    results_dir = configured_path(config, "results_dir", "resultados")
    log_path = results_dir / "logs" / "audit.jsonl"
    revisoes_dir = results_dir / "revisoes"

    relatorio: dict[str, Any] = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "execucoes": {"total": 0, "por_modalidade": {}, "por_provider": {}},
        "casos": {},
        "taxa_aprovacao": {},
        "avaliacoes": {},
    }

    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("event_type") == "iniciado":
                relatorio["execucoes"]["total"] += 1
                payload = ev.get("payload", {})
                mod = payload.get("modalidade", "desconhecida")
                prov = payload.get("provider", "desconhecido")
                relatorio["execucoes"]["por_modalidade"][mod] = relatorio["execucoes"]["por_modalidade"].get(mod, 0) + 1
                relatorio["execucoes"]["por_provider"][prov] = relatorio["execucoes"]["por_provider"].get(prov, 0) + 1

    decisoes_lista = []
    if revisoes_dir.exists():
        for rev_file in sorted(revisoes_dir.glob("*.json")):
            try:
                dados = json.loads(rev_file.read_text(encoding="utf-8"))
                caso_id = dados.get("caso_id", rev_file.stem)
                decisoes = dados.get("decisoes", [])
                for d in decisoes:
                    decisoes_lista.append(d.get("decisao"))
                relatorio["casos"][caso_id] = {
                    "versao_atual": dados.get("versao_atual"),
                    "total_versoes": len(dados.get("versoes", {})),
                    "decisoes": decisoes,
                }
            except Exception:
                pass

    relatorio["taxa_aprovacao"] = taxa_aprovacao(decisoes_lista)

    for aval_file in sorted(results_dir.glob("avaliacao_*.json")):
        try:
            dados = json.loads(aval_file.read_text(encoding="utf-8"))
            relatorio["avaliacoes"][aval_file.name] = {
                "modalidade": dados.get("modalidade"),
                "pontuacao": dados.get("pontuacao"),
            }
        except Exception:
            pass

    out_path = results_dir / "relatorio_consolidado.json"
    save_json(out_path, relatorio)

    print("\n" + "=" * 60)
    print("  RELATÓRIO CONSOLIDADO DO SISTEMA")
    print("=" * 60)
    print(f"Execuções registradas : {relatorio['execucoes']['total']}")
    print(f"  Por modalidade      : {relatorio['execucoes']['por_modalidade']}")
    print(f"  Por provedor        : {relatorio['execucoes']['por_provider']}")
    print(f"Casos em atendimento  : {len(relatorio['casos'])}")
    for cid, cinfo in relatorio["casos"].items():
        print(f"  - {cid}: vigente=v{cinfo['versao_atual']} ({cinfo['total_versoes']} versões)")
    print(f"Taxa de aprovação     : {relatorio['taxa_aprovacao']}")
    print(f"Avaliações salvas     : {len(relatorio['avaliacoes'])}")
    print(f"Relatório exportado em: {out_path}")
    print("=" * 60 + "\n")
    return 0


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def print_help() -> None:
    print(
        """
Uso:
  python -m src.main fluxo             [--arquivo F] [--texto T] [--caso ID]
  python -m src.main processar-texto   [--arquivo F] [--texto T]
  python -m src.main prompts           [--arquivo F]
  python -m src.main revisar           (--prompt (A|B|C) | --caso ID) --decisao D --justificativa J [--versao N] [--operador OP]
  python -m src.main vigente           --caso ID --versao N [--operador OP]
  python -m src.main audio             --arquivo F [--caso ID] [--sem-revisao]
  python -m src.main ocr               --arquivo F [--caso ID] [--forcar-vision] [--sem-correcao]
  python -m src.main imagem            [--caso ID] [--titulo T] [--texto-imagem T] [--usar-minuta] [--revisar-visual]
  python -m src.main voz               --caso ID [--versao N] [--confirmar] [--verificar]
  python -m src.main aprovar-minuta    --caso ID --operador OP --decisao (aprovar|rejeitar) --justificativa J (--arquivo-minuta F | --versao N)
  python -m src.main avaliar           --tipo (stt|ocr|extracao|seguranca|prompts) [--gabarito G] [--arquivo A] [--caso ID] [--origem O]
  python -m src.main relatorio
  python -m src.main logs
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
            "fluxo", "vigente", "relatorio",
        ],
    )
    # Entradas genéricas
    parser.add_argument("--arquivo", type=str, default=None, help="Caminho do arquivo de entrada")
    parser.add_argument("--texto", type=str, default=None, help="Texto bruto a ser processado")
    parser.add_argument("--listar-logs", action="store_true", help="Mostra os logs de auditoria")

    # Revisão de prompts e minutas
    parser.add_argument("--prompt", choices=["A", "B", "C"], help="Prompt do experimento a revisar")
    parser.add_argument(
        "--decisao",
        choices=["aprovar", "rejeitar", "gerar_novamente"],
        help="Decisão humana (prompts e minutas)",
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
    parser.add_argument("--usar-minuta", action="store_true", help="Usa a minuta aprovada para o texto da imagem")
    parser.add_argument("--revisar-visual", action="store_true", help="Registra aprovação visual humana da peça")

    # Voz (TTS)
    parser.add_argument("--confirmar", action="store_true", help="Confirma a síntese de voz (TTS)")
    parser.add_argument("--verificar", action="store_true", help="Executa transcrição de retorno para verificação")

    # Aprovar minuta
    parser.add_argument("--arquivo-minuta", type=str, default=None, help="Arquivo .txt da minuta (nova versão)")

    # Avaliar
    parser.add_argument(
        "--tipo",
        choices=["stt", "ocr", "extracao", "seguranca", "prompts"],
        help="Tipo de avaliação",
    )
    parser.add_argument(
        "--modalidade",
        choices=["stt", "ocr", "extracao", "seguranca", "prompts"],
        help="Modalidade de avaliação (alias de --tipo)",
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

    # --- Comandos principais ---
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
        return cmd_revisar(args, config)

    if args.command == "vigente":
        return cmd_vigente(args, config)

    if args.command == "relatorio":
        return cmd_relatorio(args, config)

    if args.command == "fluxo":
        return cmd_fluxo(args, config)

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

        pdf_path = minuta_path.with_suffix(".pdf")
        brasao_p = ROOT / "arquivos" / "brasao.png"
        try:
            from src.text_processing import render_minuta_pdf
            render_minuta_pdf(minuta, pdf_path, brasao_path=brasao_p if brasao_p.exists() else None)
        except Exception:
            pass

        execution.success(
            arquivo_saida=[path_reference(output_path), path_reference(minuta_path), path_reference(pdf_path)],
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
