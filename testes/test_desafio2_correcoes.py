"""Regressões locais do Desafio 2; todos os provedores externos são simulados."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.audit import AuditLogger
from src.llm_client import CallLimitExceededError, OpenAIClient, StructuredOutputError
from src.nlp import _normalizar_entidades, processar_solicitacao
from src.rag import _append_query_log, _conflito, consultar_rag, registrar_revisao_rag
from src.schemas import EntidadeLiteral, FichaSolicitacao, RespostaRAG


ROOT = Path(__file__).resolve().parent.parent


class FakeBudgetedProvider:
    def __init__(self):
        self.api_calls_made = 0
        self.max_calls_per_run = None

    def begin_run(self, max_calls=None):
        self.max_calls_per_run = max_calls
        self.api_calls_made = 0


def _chunk(chunk_id="chunk-a", *, similarity=0.8, conflict=None):
    meta = {
        "document_id": "DOC-1", "file_name": "doc.txt", "title": "Documento fictício",
        "version": "1", "section_id": "sec-1", "section": "Regra", "authority_rank": 1,
    }
    if conflict:
        meta.update({"conflict_key": "docs", "conflict_value": conflict,
                     "effective_from": "2026-01-01", "effective_to": "2026-12-31"})
    return {"chunk_id": chunk_id, "text": "Fonte factual fictícia", "metadata": meta,
            "distance": 1-similarity, "similarity": similarity}


def _rag_config(root: Path, *, provider="openai", limit=3):
    return {"desafio2": {
        "llm": {"provider": "openai", "model": "gpt-4o-mini", "max_calls_per_run": limit,
                "max_retries": 1, "timeout_seconds": 1, "max_output_tokens": 500},
        "generation": {"provider": provider, "model": "gpt-4o-mini"},
        "versions": {"rag_prompt": "rag_institucional.v2", "rag_schema": "rag-answer.v1"},
        "retrieval": {"top_k": 3, "min_similarity": 0.4},
        "chunking": {"strategy_selected": "structural"},
        "paths": {"results_directory": str(root / "resultados")},
    }}


class Desafio2CorrectionTests(unittest.TestCase):
    def test_entity_schema_has_semantic_types_and_local_extraction_preserves_minimized_data(self):
        source = (ROOT / "dados/originais/solicitacoes/SOL-001_audio_desafio1.txt").read_text(encoding="utf-8")
        ficha = FichaSolicitacao(
            versao_esquema="solicitacao.v2", protocolo="2026-000142", data="14 de outubro de 2026",
            solicitante="Marcos Vinícius de Almeida Santos", assunto="efetivação de matrícula",
            pedido="Solicita matrícula no curso técnico.", categoria="solicitacao_servico", resumo="Solicita matrícula.",
            entidades=[EntidadeLiteral(tipo="local", texto_literal="1.200 horas", observacao=None),
                       EntidadeLiteral(tipo="local", texto_literal="noturno", observacao=None)],
            campos_ausentes=[], inferencias=[], revisao_humana_necessaria=True, motivo_revisao=None,
        )
        enriched, changes = _normalizar_entidades(ficha, source)
        entities = {item.texto_literal: item.tipo for item in enriched.entidades}
        self.assertEqual(entities["1.200 horas"], "carga_horaria")
        self.assertEqual(entities["noturno"], "turno")
        self.assertEqual(entities["12 de agosto de 2008"], "data")
        self.assertEqual(entities["Cuiabá"], "local")
        self.assertIn("entidades estruturadas e literais foram completadas/normalizadas localmente", changes)
        self.assertEqual(entities["Eixo Tecnol\u00f3gico de Sa\u00fade"], "outro")
        course_source = (ROOT / "dados/originais/solicitacoes/SOL-002_texto.txt").read_text(encoding="utf-8")
        course_ficha = ficha.model_copy(update={"entidades": [
            EntidadeLiteral(tipo="curso", texto_literal="T\u00e9cnico em Administra\u00e7\u00e3o", observacao=None),
            EntidadeLiteral(tipo="turno", texto_literal="noturno", observacao=None),
        ]})
        course_ficha, _ = _normalizar_entidades(course_ficha, course_source)
        course_entities = {item.texto_literal: item.tipo for item in course_ficha.entidades}
        self.assertNotIn("Administra\u00e7\u00e3o", course_entities)
        self.assertEqual(course_entities["T\u00e9cnico em Administra\u00e7\u00e3o"], "curso")
        self.assertEqual(course_entities["turno noturno"], "turno")

    def test_gabarito_excludes_unsupported_date_and_covers_manual_entity_types(self):
        gold = json.loads((ROOT / "dados/gabaritos/desafio2_solicitacoes.json").read_text(encoding="utf-8"))
        cases = {item["solicitacao_id"]: item for item in gold["solicitacoes"]}
        self.assertNotIn("01/02/2027", cases["SOL-001"]["entidades"])
        self.assertIn("12 de agosto de 2008", cases["SOL-001"]["entidades"])
        self.assertEqual(cases["SOL-002"]["entidades_tipos"]["turno noturno"], "turno")
        self.assertEqual(cases["SOL-001"]["entidades_tipos"]["1.200 horas"], "carga_horaria")
        self.assertEqual(cases["SOL-001"]["entidades_tipos"]["noturno"], "turno")
        self.assertEqual(cases["SOL-001"]["entidades_tipos"]["Eixo Tecnol\u00f3gico de Sa\u00fade"], "outro")
        self.assertFalse(any("?" in key for case in cases.values() for key in case.get("entidades_tipos", {})))
        self.assertIn("pedido", cases["SOL-006"]["campos"])
        self.assertEqual(cases["SOL-001"]["campos"]["assunto"], "efetiva\u00e7\u00e3o de matr\u00edcula em curso t\u00e9cnico")
        self.assertEqual(cases["SOL-002"]["campos"]["assunto"], "Matr\u00edcula no curso T\u00e9cnico em Administra\u00e7\u00e3o")
        self.assertEqual(cases["SOL-003"]["campos"]["assunto"], "Informa\u00e7\u00f5es sobre in\u00edcio e turno do curso T\u00e9cnico em Administra\u00e7\u00e3o")
        self.assertIn("matr\u00edcula", cases["SOL-006"]["campos"]["pedido"])
        self.assertNotIn("?", " ".join(str(value) for case in cases.values() for value in case.get("campos", {}).values() if value))

    def test_embeddings_accept_missing_dimensions_and_enforce_explicit_dimensions_and_budget(self):
        client = OpenAIClient(api_key="test-key", max_calls_per_run=1)
        create = Mock(return_value=SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])], usage=None))
        client.client.embeddings.create = create
        result = client.create_embeddings(["texto"], model="fake-embedding", dimensions=None)
        self.assertEqual(result["vectors"], [[0.1, 0.2]])
        with self.assertRaises(CallLimitExceededError):
            client.create_embeddings(["texto"], model="fake-embedding", dimensions=None)
        self.assertEqual(create.call_count, 1)

        client2 = OpenAIClient(api_key="test-key")
        client2.client.embeddings.create = Mock(
            return_value=SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])], usage=None)
        )
        with self.assertRaises(StructuredOutputError):
            client2.create_embeddings(["texto"], model="fake-embedding", dimensions=3)

    def test_audit_sanitizer_drops_content_and_redacts_secret_patterns(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = AuditLogger(directory)
            logger.log_event("test", "sucesso", {
                "question": "Nome Ana pessoa@example.test", "api_key": "secret-key",
                "note": "CPF 123.456.789-00 Bearer abcdefghijklmnop",
                "usage": {"input_tokens": 7},
            })
            saved = json.loads((Path(directory) / "audit.jsonl").read_text(encoding="utf-8"))
            rendered = json.dumps(saved, ensure_ascii=False)
            self.assertNotIn("Ana", rendered)
            self.assertNotIn("secret-key", rendered)
            self.assertNotIn("123.456.789-00", rendered)
            self.assertNotIn("abcdefghijklmnop", rendered)
            self.assertEqual(saved["payload"]["usage"]["input_tokens"], 7)

    def test_query_log_uses_central_sanitizer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queries.jsonl"
            _append_query_log(path, {"question": "Ana pessoa@example.test", "question_hash": "abc", "status": "ok"})
            line = path.read_text(encoding="utf-8")
            self.assertNotIn("Ana", line)
            self.assertNotIn("pessoa@example.test", line)
            self.assertIn("question_hash", line)

    def test_conflict_requires_related_question_and_two_equal_priority_claims(self):
        chunks = [_chunk("a", conflict="identity"), _chunk("b", conflict="certificate")]
        config = {"conflict_query_terms": {"docs": ["documento", "matricula"]}}
        self.assertIsNone(_conflito(chunks, "2026-10-30", "Qual o valor da bolsa?", config))
        self.assertIsNotNone(_conflito(chunks, "2026-10-30", "Quais documentos da matrícula?", config))

    def test_model_cannot_turn_unverified_conflict_or_abstention_into_final_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _rag_config(root)
            provider = FakeBudgetedProvider()

            def retrieve(*args, **kwargs):
                kwargs["client"].api_calls_made += 1
                return [_chunk()]

            conflict_response = RespostaRAG(respondida_pelas_fontes=False, conflito_na_evidencia=True,
                                            resposta="", citacoes=[], motivo_revisao="modelo")
            with patch("src.rag.search_chunks", side_effect=retrieve), patch(
                "src.rag._generate", return_value=(conflict_response, {"provider": "openai", "model": "fake"})
            ):
                result = consultar_rag("Pergunta factual", config=config, client=provider)
            self.assertEqual(result["status"], "revisao_humana")
            self.assertEqual(result["decision_reason"], "conflito_do_modelo_sem_contradicao_verificada")
            self.assertTrue(result["generation_called"] is False)

            provider = FakeBudgetedProvider()
            abstention = RespostaRAG(respondida_pelas_fontes=False, conflito_na_evidencia=False,
                                     resposta="", citacoes=[], motivo_revisao="sem evidência")
            with patch("src.rag.search_chunks", side_effect=retrieve), patch(
                "src.rag._generate", return_value=(abstention, {"provider": "openai", "model": "fake"})
            ):
                result = consultar_rag("Pergunta factual", config=config, client=provider)
            self.assertEqual(result["status"], "revisao_humana")
            self.assertEqual(result["decision_reason"], "abstencao_do_modelo_com_trechos_acima_do_limiar")

    def test_empty_retrieval_abstains_before_generation_and_logs_complete_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            config = _rag_config(Path(directory))
            provider = FakeBudgetedProvider()
            chunk = _chunk(similarity=0.2)

            def retrieve(*args, **kwargs):
                kwargs["client"].api_calls_made += 1
                return [chunk]

            with patch("src.rag.search_chunks", side_effect=retrieve), patch("src.rag._generate") as generate:
                result = consultar_rag("Pergunta sem suporte", config=config, client=provider)
            self.assertEqual(result["status"], "sem_evidencia")
            self.assertFalse(result["generation_called"])
            generate.assert_not_called()
            logs = (Path(directory) / "resultados/logs/consultas.jsonl").read_text(encoding="utf-8")
            self.assertIn('"provider"', logs)
            self.assertIn('"model"', logs)
            self.assertIn('"generation_called": false', logs)
            self.assertIn('"error_type"', logs)
            self.assertIn('"duration_seconds"', logs)
            self.assertIn('"human_decision": "pendente"', logs)

    def test_rag_provider_failure_is_sanitized_and_requires_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            config = _rag_config(Path(directory))
            provider = FakeBudgetedProvider()

            def retrieve(*args, **kwargs):
                kwargs["client"].api_calls_made += 1
                return [_chunk()]

            with patch("src.rag.search_chunks", side_effect=retrieve), patch(
                "src.rag._generate", side_effect=RuntimeError("Bearer fake-secret user@example.test")
            ):
                result = consultar_rag("Pergunta", config=config, client=provider)
            self.assertEqual(result["status"], "revisao_humana")
            self.assertEqual(result["error_type"], "RuntimeError")
            self.assertNotIn("fake-secret", result["message"])
            self.assertNotIn("user@example.test", result["message"])
            saved = Path(result["result_path"]).read_text(encoding="utf-8")
            self.assertNotIn('"question":', saved)
            log = (Path(directory) / "resultados/logs/consultas.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("user@example.test", log)
            self.assertIn('"error_type": "RuntimeError"', log)

    def test_rag_review_decision_is_logged_without_free_text_justification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _rag_config(root)
            result_dir = root / "resultados/rag"
            result_dir.mkdir(parents=True)
            execution_id = "execution-review"
            (result_dir / f"{execution_id}.json").write_text(json.dumps({
                "execution_id": execution_id, "status": "sem_evidencia", "human_decision": "pendente",
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                registrar_revisao_rag(execution_id, "aprovada", "Não há evidência", config=config)
            result = registrar_revisao_rag(execution_id, "revisar", "Conferir com pessoa@example.test", config=config)
            self.assertEqual(result["human_decision"], "revisar")
            log = (root / "resultados/logs/consultas.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("pessoa@example.test", log)
            self.assertIn("justification_hash", log)

    def test_nlp_does_not_persist_original_request_and_records_schema_and_prompt_versions(self):
        class FakeStructuredProvider:
            def parse_structured(self, **kwargs):
                return {"parsed": FichaSolicitacao(
                    versao_esquema="solicitacao.v2", protocolo="FIC-001", data="14/10/2026",
                    solicitante="Ana Pessoa", assunto="informações sobre matrícula", pedido="Solicita informação.",
                    categoria="informacao", resumo="Ana solicita informações sobre matrícula.", entidades=[],
                    campos_ausentes=[], inferencias=[], revisao_humana_necessaria=True, motivo_revisao=None,
                ), "metadata": {"provider": "fake", "model": "fake-model", "usage": {}}}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {
                "results_dir": str(root / "results"), "processed_dir": str(root / "processed"),
                "desafio2": {"llm": {"provider": "openai", "max_calls_per_run": 2},
                             "versions": {"nlp_prompt": "compreensao_solicitacao.v3", "nlp_schema": "solicitacao.v2"},
                             "paths": {"results_directory": str(root / "results"),
                                       "processados_directory": str(root / "processed")}},
            }
            raw = "Protocolo FIC-001 em 14/10/2026; Ana Pessoa solicita informações sobre matrícula."
            result = processar_solicitacao(raw, solicitacao_id="CASE-1", config=config,
                                           cliente=FakeStructuredProvider())
            saved = Path(result["arquivo_saida"]).read_text(encoding="utf-8")
            self.assertEqual(result["schema_version"], "solicitacao.v2")
            self.assertEqual(result["prompt_version"], "compreensao_solicitacao.v3")
            self.assertNotIn(raw, saved)
            self.assertNotIn("entrada_original_local", json.loads(saved))


if __name__ == "__main__":
    unittest.main()
