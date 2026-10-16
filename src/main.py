"""Ponto de entrada principal do protótipo.

O comando principal é:
    python -m src.main

Ele processa a entrada textual localmente e informa claramente quando a integração com
OpenAI depender de configuração manual da chave da API.
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


def print_help() -> None:
    print(
        """
Uso:
  python -m src.main processar-texto
  python -m src.main prompts
    python -m src.main revisar --prompt B --decisao aprovar --justificativa "..."
  python -m src.main logs
  python -m src.main --help

Opções:
  --arquivo      Caminho do arquivo de entrada (opcional)
  --texto        Texto bruto a ser processado (opcional)
  --listar-logs  Exibe o último log de auditoria
"""
    )


def main() -> int:
    load_dotenv(ROOT / ".env")
    config = load_config()
    parser = argparse.ArgumentParser(description="Central inteligente de atendimento institucional")
    parser.add_argument(
        "command",
        nargs="?",
        default="processar-texto",
        choices=["processar-texto", "prompts", "revisar", "logs"],
    )
    parser.add_argument("--arquivo", type=str, default=None, help="Caminho do arquivo de entrada")
    parser.add_argument("--texto", type=str, default=None, help="Texto bruto a ser processado")
    parser.add_argument("--listar-logs", action="store_true", help="Mostra os logs de auditoria")
    parser.add_argument("--prompt", choices=["A", "B", "C"], help="Prompt do experimento a revisar")
    parser.add_argument(
        "--decisao",
        choices=["aprovar", "rejeitar", "gerar_novamente"],
        help="Decisão humana sobre o resultado",
    )
    parser.add_argument("--justificativa", type=str, help="Justificativa da decisão humana")
    args = parser.parse_args()

    ensure_structure(config)

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

    started_at = perf_counter()
    results_dir = configured_path(config, "results_dir", "resultados")
    execution = ExecutionAudit(log_dir=str(results_dir / "logs"))
    execution.start(
        modalidade="texto",
        arquivo_origem="texto_fornecido_cli" if args.texto is not None else path_reference(Path(args.arquivo) if args.arquivo else default_input_path(config)),
        provider="local",
        prompt_version="local_v1",
        modelo="processamento_local",
    )

    try:
        raw_text = args.texto if args.texto is not None else read_text_input(args.arquivo)
        data = extract_structured_data(raw_text)
        minuta = build_minuta(data)
        source_reference = "texto fornecido diretamente" if args.texto is not None else path_reference(Path(args.arquivo) if args.arquivo else default_input_path(config))
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
