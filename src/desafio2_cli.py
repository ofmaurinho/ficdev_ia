"""Comandos locais dos serviços do Desafio 2, sem acoplamento a Streamlit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.nlp import avaliar_conjunto_solicitacoes, processar_arquivo_solicitacao
from src.llm_client import APIClientError
from src.rag import consultar_rag, registrar_revisao_rag
from src.rag_evaluation import avaliar_chunking
from src.schemas import demonstrar_json_vs_schema
from src.vector_store import IndexErrorRAG, indexar_acervo, listar_documentos_indexados

ROOT = Path(__file__).resolve().parent.parent


def _config(path: str | None) -> dict[str, Any]:
    config_path = Path(path) if path else ROOT / "config.json"
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    return json.loads(config_path.read_text(encoding="utf-8"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serviços de extração, índice e RAG do Desafio Prático 2")
    parser.add_argument("--config", help="Caminho de configuração JSON; padrão config.json")
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("indexar", help="Indexa somente os documentos do manifesto fictício (requer embeddings)")
    index.add_argument("--estrategia", choices=("structural", "fixed_400_overlap_80"))
    index.add_argument("--listar", action="store_true", help="Lista os documentos já persistidos")
    retrieve = commands.add_parser("avaliar-recuperacao", help="Compara as duas estratégias nas cinco perguntas respondíveis")
    retrieve.add_argument("--estrategia", action="append", choices=("structural", "fixed_400_overlap_80"))
    process = commands.add_parser("compreender", help="Extrai e valida a ficha de um TXT ou JSON de STT/OCR")
    process.add_argument("--arquivo", required=True)
    process.add_argument("--id")
    commands.add_parser("avaliar-solicitacoes", help="Executa RF14/RF15 nos seis casos; requer geração configurada")
    rag = commands.add_parser("consultar", help="Consulta RAG com fontes, abstenção e auditoria")
    rag.add_argument("--pergunta", required=True)
    rag.add_argument("--ficha", help="JSON de ficha validada opcional")
    rag.add_argument("--top-k", type=int)
    rag.add_argument("--estrategia", choices=("structural", "fixed_400_overlap_80"))
    review = commands.add_parser("revisar", help="Registra decisão humana de uma execução RAG")
    review.add_argument("--execution-id", required=True)
    review.add_argument("--decisao", required=True, choices=("aprovada", "rejeitada", "revisar"))
    review.add_argument("--justificativa", required=True)
    commands.add_parser("demonstrar-schema", help="Compara JSON sintático e validação Pydantic sem API")
    commands.add_parser("listar", help="Lista documentos presentes no índice persistente")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = _config(args.config)
    try:
        if args.command == "indexar":
            result = listar_documentos_indexados(config=config) if args.listar else indexar_acervo(strategy=args.estrategia, config=config)
        elif args.command == "avaliar-recuperacao":
            result = avaliar_chunking(config=config, strategies=tuple(args.estrategia or ("structural", "fixed_400_overlap_80")))
        elif args.command == "compreender":
            source = Path(args.arquivo)
            if not source.is_absolute():
                source = ROOT / source
            result = processar_arquivo_solicitacao(source, solicitacao_id=args.id, config=config)
        elif args.command == "avaliar-solicitacoes":
            result = avaliar_conjunto_solicitacoes(config=config)
        elif args.command == "consultar":
            ficha = None
            if args.ficha:
                ficheiro = Path(args.ficha)
                if not ficheiro.is_absolute():
                    ficheiro = ROOT / ficheiro
                data = json.loads(ficheiro.read_text(encoding="utf-8"))
                ficha = data.get("ficha", data)
            result = consultar_rag(args.pergunta, ficha_solicitacao=ficha, config=config,
                                   top_k=args.top_k, strategy=args.estrategia)
        elif args.command == "revisar":
            result = registrar_revisao_rag(args.execution_id, args.decisao, args.justificativa, config=config)
        elif args.command == "demonstrar-schema":
            result = demonstrar_json_vs_schema()
        else:
            result = listar_documentos_indexados(config=config)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as exc:
        # Evita imprimir conteúdo bruto da solicitação, credenciais ou corpos de exceções do SDK.
        safe_message = str(exc) if isinstance(exc, (APIClientError, IndexErrorRAG, ValueError, FileNotFoundError)) else "Falha controlada no serviço; consulte o log sanitizado."
        print(json.dumps({"status": "revisao_humana", "error_type": type(exc).__name__, "message": safe_message}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
