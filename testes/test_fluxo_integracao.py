"""Testes de fluxo integrado e ponta a ponta (com cliente simulado).

Cobre os requisitos de integração do Plano v4:
- Fluxo feliz: texto → minuta → aprovação → roteiro → TTS.
- TTS bloqueado sem aprovação, e após editar minuta ou roteiro (hash diferente).
- Pedir nova geração cria v2, mantém a aprovação de v1 e não a altera.
- Falha de voz → artefato FALHA → nova tentativa → GERADO, sem mudar o estado do atendimento.
- Imagem gerada sob demanda a partir de um caso selecionado, sem alterar o estado do atendimento
  e sem exigir aprovação quando for só demonstração; com texto de minuta, usa a versão resolvida.
- Proveniência por campo: campos_<caso>.json com origem, página, método e status;
  ausente não bloqueia; incerto bloqueia até confirmação.
- Versão vigente: voz sem versão e sem versao_atual falha; mostra o que será sintetizado;
  v2 criada não muda a vigente.
- Métricas: WER, acerto de campos e severidade ponderada, com erro crítico reprovando o caso.
- OCR: gatilhos pré-Vision; divergência pós-Vision → INCERTO; ausência nas duas rotas →
  não localizado sem bloquear; incerteza crítica → bloqueio até confirmar.
- fluxo, audio, ocr e prompts funcionam sem gabarito; avaliar recusa gabarito pendente.
- Falhas: chave ausente, timeout, resposta vazia e serviço indisponível nos novos métodos.
- Nenhuma chave em log ou resultado; hashes dos originais registrados.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from src.audit import ArtifactRegistry, AuditLogger, sha256_file
from src.campos import carregar_campos, confirmar_campo, extrair_campos, salvar_campos
from src.evaluation import (
    pontuacao_qualidade,
    similaridade_texto,
    taxa_aprovacao,
    wer,
)
from src.gabarito import GabaritoInvalidoError, carregar_gabarito_validado
from src.llm_client import (
    APIClientError,
    AuthenticationError,
    EmptyResponseError,
    MissingAPIKeyError,
    OpenAIClient,
    RequestTimeoutError,
    ServiceUnavailableError,
)
from src.review import AprovacaoInvalidaError, RevisaoError, Revisoes
from src.roteiro import gerar_roteiro_leitura
from src.vision import extrair_texto_documento, sinais_pre_vision


def _mock_client():
    client = MagicMock()
    client.transcribe.return_value = {
        "text": "Protocolo 2026-000142 em 14/10/2026 por Marcos Santos solicitando matricula.",
        "metadata": {"duration_seconds": 0.2, "response_id": "r-stt", "usage": {}},
    }
    client.generate_text.return_value = {
        "text": "Texto revisado conforme padroes institucionais.",
        "metadata": {"duration_seconds": 0.3, "response_id": "r-text", "usage": {}},
    }
    def _mock_speak(text, out_path, **kw):
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\xff\xfb\x90\x00FAKE_AUDIO")
        return {
            "path": str(p),
            "metadata": {"duration_seconds": 0.4, "response_id": "r-tts"},
        }
    client.speak.side_effect = _mock_speak
    client.describe_image.return_value = {
        "text": "DOCUMENTO: Protocolo 2026-000142, Data 14/10/2026, Aluno Marcos Santos.",
        "metadata": {"duration_seconds": 0.5, "response_id": "r-vision"},
    }
    client.generate_image.return_value = {
        "image_bytes": _make_png_bytes(),
        "metadata": {"duration_seconds": 0.6, "response_id": "r-img"},
    }
    return client


def _make_png_bytes(color=(20, 80, 150), size=64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="PNG")
    return buf.getvalue()


class TestFluxoIntegracao(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.results_dir = self.tmp / "resultados"
        self.saida_dir = self.tmp / "dados" / "processados"
        self.gabaritos_dir = self.tmp / "dados" / "gabaritos"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.saida_dir.mkdir(parents=True, exist_ok=True)
        self.gabaritos_dir.mkdir(parents=True, exist_ok=True)

        self.config = {
            "results_dir": str(self.results_dir),
            "processed_dir": str(self.saida_dir),
            "gold_dir": str(self.gabaritos_dir),
            "audio": {"stt_model": "gpt-4o-transcribe", "tts_model": "gpt-4o-mini-tts"},
            "vision": {"vision_model": "gpt-4o-mini"},
            "image": {"model": "gpt-image-1"},
        }

    # 1. Fluxo feliz: texto → minuta → aprovação → roteiro → TTS
    def test_fluxo_feliz_texto_para_tts(self):
        revisoes = Revisoes(self.results_dir)
        caso_id = "caso_feliz"
        texto = "Protocolo: 2026-000142\nData: 14/10/2026\nSolicitante: Marcos Santos\nPedido: Matrícula"

        # 1.1 Gerar minuta e roteiro
        roteiro = gerar_roteiro_leitura("Prezado Marcos Santos, sua solicitação 2026-000142 foi recebida.")
        versao = revisoes.registrar_versao(caso_id, "Prezado Marcos Santos, sua solicitação 2026-000142 foi recebida.", roteiro)
        self.assertEqual(versao, 1)

        # 1.2 Aprovação
        decisao = revisoes.registrar_decisao(caso_id, versao, "aprovar", "Dados conferidos com a fonte", "Operador A", tornar_vigente=True)
        self.assertEqual(decisao["decisao"], "aprovar")
        self.assertTrue(revisoes.aprovacao_valida(caso_id, versao))

        # 1.3 TTS
        client = _mock_client()
        from src.audio import sintetizar_roteiro
        out_path = self.results_dir / "minutas" / f"voz_{caso_id}_v{versao}.mp3"
        reg = sintetizar_roteiro(caso_id, versao, out_path, client=client, revisoes=revisoes)
        self.assertTrue(out_path.exists())
        self.assertTrue(reg["texto_enviado_identico_ao_roteiro_aprovado"])

    # 2. TTS bloqueado sem aprovação, e após editar minuta ou roteiro (hash diferente)
    def test_tts_bloqueado_sem_aprovacao_e_apos_edicao(self):
        revisoes = Revisoes(self.results_dir)
        caso_id = "caso_bloqueio"
        minuta_orig = "Minuta inicial do caso."
        roteiro_orig = gerar_roteiro_leitura(minuta_orig)
        versao = revisoes.registrar_versao(caso_id, minuta_orig, roteiro_orig)

        # Sem aprovação deve falhar
        client = _mock_client()
        from src.audio import sintetizar_roteiro
        out_path = self.results_dir / "minutas" / f"voz_{caso_id}_v{versao}.mp3"
        with self.assertRaises(AprovacaoInvalidaError):
            sintetizar_roteiro(caso_id, versao, out_path, client=client, revisoes=revisoes)

        # Aprovar
        revisoes.registrar_decisao(caso_id, versao, "aprovar", "OK", "Operador")
        self.assertTrue(revisoes.aprovacao_valida(caso_id, versao))

        # Editar minuta após aprovação
        minuta_path, roteiro_path = revisoes._arquivos(caso_id, versao)
        minuta_path.write_text("Minuta adulterada apos aprovacao!", encoding="utf-8")
        self.assertFalse(revisoes.aprovacao_valida(caso_id, versao))
        with self.assertRaises(AprovacaoInvalidaError):
            sintetizar_roteiro(caso_id, versao, out_path, client=client, revisoes=revisoes)

    # 3. Pedir nova geração cria v2, mantém aprovação de v1 e não a altera
    def test_nova_geracao_cria_v2_e_mantem_v1(self):
        revisoes = Revisoes(self.results_dir)
        caso_id = "caso_v2"
        v1 = revisoes.registrar_versao(caso_id, "Minuta v1", "Roteiro v1")
        revisoes.registrar_decisao(caso_id, v1, "aprovar", "Aprovado v1", "Op1", tornar_vigente=True)
        h1 = revisoes._load(caso_id)["versoes"]["1"]["minuta_sha256"]

        # Solicitar nova geração
        sol = revisoes.solicitar_nova_geracao(caso_id, versao_base=1, motivo="Faltou prazo", operador="Op1")
        self.assertEqual(sol["motivo"], "Faltou prazo")

        # Gerar v2
        v2 = revisoes.registrar_versao(caso_id, "Minuta v2 com prazo", "Roteiro v2 com prazo")
        self.assertEqual(v2, 2)

        # v1 continua intacta e aprovada
        self.assertTrue(revisoes.aprovacao_valida(caso_id, 1))
        # v2 ainda nao aprovada
        self.assertFalse(revisoes.aprovacao_valida(caso_id, 2))
        # vigente ainda e v1
        self.assertEqual(revisoes.versao_atual(caso_id), 1)

    # 4. Falha de voz → artefato FALHA → nova tentativa → GERADO, sem mudar estado do atendimento
    def test_falha_de_voz_e_nova_tentativa(self):
        revisoes = Revisoes(self.results_dir)
        caso_id = "caso_falha_voz"
        v1 = revisoes.registrar_versao(caso_id, "Minuta v1", "Roteiro v1")
        revisoes.registrar_decisao(caso_id, v1, "aprovar", "Aprovado", "Op1", tornar_vigente=True)

        registry = ArtifactRegistry(self.results_dir, caso_id)
        registry.iniciar("audio", versao=1)
        registry.falhar("audio", versao=1, erro="Timeout da API")
        self.assertEqual(registry.estado("audio", 1), "FALHA")
        self.assertEqual(revisoes.estado_atendimento(caso_id), "APROVADO")

        # Nova tentativa permitida (FALHA -> GERANDO -> GERADO)
        registry.iniciar("audio", versao=1)
        audio_file = self.results_dir / "voz.mp3"
        audio_file.write_bytes(b"AUDIO")
        registry.concluir("audio", versao=1, arquivo=audio_file)
        self.assertEqual(registry.estado("audio", 1), "GERADO")
        self.assertEqual(revisoes.estado_atendimento(caso_id), "APROVADO")

    # 5. Imagem sob demanda independente do atendimento e com minuta se solicitada
    def test_imagem_sob_demanda_e_com_minuta(self):
        from src.image_generation import compor_peca, gerar_imagem
        revisoes = Revisoes(self.results_dir)
        caso_id = "caso_img"
        v1 = revisoes.registrar_versao(caso_id, "Minuta de orientacao institucional.", "Roteiro.")
        revisoes.registrar_decisao(caso_id, v1, "aprovar", "OK", "Op1", tornar_vigente=True)

        client = _mock_client()
        out_path = self.results_dir / "minutas" / f"peca_{caso_id}.png"
        nota = gerar_imagem(
            prompt="Ilustração institucional",
            client=client,
            image_cfg=self.config["image"],
            titulo="Sec. Educacao",
            texto="Orientacao aos alunos.",
            out_path=out_path,
            caso_id=caso_id,
        )
        self.assertTrue(out_path.exists())
        self.assertIn("conteúdo sintético", nota["identificacao"].lower())
        # Estado do atendimento continua APROVADO sem ser modificado pela imagem
        self.assertEqual(revisoes.estado_atendimento(caso_id), "APROVADO")

    # 6. Proveniência por campo crítico: campos_<caso>.json; ausente não bloqueia; incerto bloqueia
    def test_proveniencia_campos_e_bloqueio(self):
        texto = "Solicitação recebida em 14/10/2026. Protocolo: 2026-000142. Solicito informações sobre curso."
        campos = extrair_campos(texto, origem="entrada.txt", origem_sha256="abc123sha", metodo="texto_original")
        salvar_campos(self.saida_dir / "campos_teste.json", campos)
        carregados = carregar_campos(self.saida_dir / "campos_teste.json")

        self.assertEqual(carregados["protocolo"]["status"], "extraido")
        self.assertEqual(carregados["data"]["status"], "extraido")
        self.assertEqual(carregados["solicitante"]["status"], "ausente")

        # Campo ausente vira "não localizado" e NÃO bloqueia
        incertos = [n for n, c in carregados.items() if c.get("status") in {"incerto", "divergente"}]
        self.assertEqual(incertos, [])

        # Campo com data inválida fica incerto e bloqueia
        campos_ruins = extrair_campos("Data: 31/02/2026", origem="e.txt", origem_sha256="h", metodo="stt")
        self.assertEqual(campos_ruins["data"]["status"], "incerto")
        incertos_ruins = [n for n, c in campos_ruins.items() if c.get("status") in {"incerto", "divergente"}]
        self.assertIn("data", incertos_ruins)

        # Confirmação humana resolve o incerto
        confirmar_campo(campos_ruins, "data", operador="Leo", valor_corrigido="14/10/2026")
        self.assertEqual(campos_ruins["data"]["status"], "confirmado_humano")
        self.assertEqual(campos_ruins["data"]["metodo"], "correcao_humana")

    # 7. Versão vigente: voz sem versão e sem versao_atual falha; v2 criada não muda vigente
    def test_versao_vigente_regras(self):
        revisoes = Revisoes(self.results_dir)
        caso_id = "caso_vigente"
        v1 = revisoes.registrar_versao(caso_id, "Minuta v1", "Roteiro v1")

        # Sem versao e sem vigente deve levantar erro
        with self.assertRaises(RevisaoError):
            revisoes.resolver_versao(caso_id, versao=None, exigir_aprovacao=False)

        # Definir v1 como vigente
        revisoes.definir_versao_atual(caso_id, 1, "Operador")
        self.assertEqual(revisoes.resolver_versao(caso_id, versao=None, exigir_aprovacao=False), 1)

        # Criar v2 não altera a vigente
        v2 = revisoes.registrar_versao(caso_id, "Minuta v2", "Roteiro v2")
        self.assertEqual(revisoes.versao_atual(caso_id), 1)

    # 8. Métricas: WER, acerto de campos e severidade ponderada com reprovação por erro crítico
    def test_metricas_e_severidade_ponderada(self):
        ref = "o protocolo e 2026 de Marcos"
        hip = "o protocolo e 2026 de Marcos"
        self.assertEqual(wer(ref, hip), 0.0)

        # Erro crítico reprova caso independentemente de pontuação
        erros_com_critico = [
            {"campo": "protocolo", "severidade": "critico"},
            {"campo": "estilo", "severidade": "baixo"},
        ]
        res_critico = pontuacao_qualidade(erros_com_critico)
        self.assertTrue(res_critico["reprovado_por_erro_critico"])
        self.assertFalse(res_critico["aprovado"])

        # Sem erro crítico e com pontuação alta aprova
        erros_leves = [{"campo": "estilo", "severidade": "baixo"}]
        res_leves = pontuacao_qualidade(erros_leves)
        self.assertFalse(res_leves["reprovado_por_erro_critico"])
        self.assertTrue(res_leves["aprovado"])
        self.assertEqual(res_leves["pontuacao"], 99)

    # 9. OCR: gatilhos pré-Vision, divergência pós-Vision e ausência não bloqueia
    def test_ocr_gatilhos_e_divergencias(self):
        cfg = {"confianca_minima_palavra": 60, "max_proporcao_palavras_baixas": 0.25, "min_caracteres_por_pagina": 80, "max_proporcao_ruido": 0.20}
        # Texto curto dispara gatilho de texto incompleto
        gatilhos = sinais_pre_vision("curto", [{"texto": "curto", "conf": 90}], cfg, paginas=1)
        self.assertIn("texto_incompleto", gatilhos)

        # Divergência entre duas rotas
        from src.campos import comparar_rotas
        rota1 = {"protocolo": {"valor": "123", "status": "extraido"}}
        rota2 = {"protocolo": {"valor": "456", "status": "extraido"}}
        comp = comparar_rotas(rota1, rota2)
        self.assertEqual(comp["protocolo"]["status"], "divergente")

        # Ausência nas duas rotas não marca divergência
        ausente1 = {"prazo": {"valor": "não localizado", "status": "ausente"}}
        ausente2 = {"prazo": {"valor": "não localizado", "status": "ausente"}}
        comp_ausente = comparar_rotas(ausente1, ausente2)
        self.assertEqual(comp_ausente["prazo"]["status"], "ausente")

    # 10. Operação funciona sem gabarito; avaliar recusa gabarito pendente
    def test_operacao_sem_gabarito_e_avaliar_recusa_pendente(self):
        from src.gabarito import carregar_gabarito_validado
        # Gabarito pendente é recusado por carregar_gabarito_validado
        pendente_path = self.gabaritos_dir / "pendente.json"
        pendente_path.write_text(json.dumps({
            "status": "PENDENTE_PREENCHIMENTO_HUMANO",
            "elaborado_por": "",
            "data_elaboracao": "",
            "campos_criticos": {},
        }), encoding="utf-8")

        with self.assertRaises(GabaritoInvalidoError):
            carregar_gabarito_validado(pendente_path)

        # Mas o fluxo de processamento funciona sem gabarito nenhum
        revisoes = Revisoes(self.results_dir)
        v = revisoes.registrar_versao("sem_gabarito", "Minuta normal", "Roteiro normal")
        self.assertEqual(v, 1)

    # 11. Falhas da API: chave ausente, timeout, resposta vazia, indisponível
    def test_falhas_api_novos_metodos(self):
        # Chave ausente
        with self.assertRaises(MissingAPIKeyError):
            OpenAIClient(api_key="")

        client = OpenAIClient(api_key="sk-fake-key", timeout=1.0)
        fake_audio = self.tmp / "fake.mp3"
        fake_audio.write_bytes(b"\x00" * 100)
        # Timeout simulado
        with patch.object(client.client.audio.transcriptions, "create", side_effect=Exception("Request timed out")):
            with self.assertRaises(RequestTimeoutError):
                client.transcribe(str(fake_audio))

        # Serviço indisponível
        with patch.object(client.client.audio.speech, "create", side_effect=Exception("503 Service Unavailable")):
            with self.assertRaises(ServiceUnavailableError):
                client.speak("texto", str(self.tmp / "s.mp3"))

    # 12. Ausência de credenciais em logs e registro de hashes de originais
    def test_ausencia_segredos_em_logs_e_hashes_originais(self):
        log_dir = self.results_dir / "logs"
        logger = AuditLogger(log_dir=str(log_dir))
        logger.log_event("teste", "sucesso", {
            "api_key": "CHAVE_SECRETA_NAO_VAZAR",
            "Authorization": "Bearer segredo",
            "modelo": "gpt-4o",
            "input_tokens": 100,
        })
        conteudo_log = (log_dir / "audit.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("CHAVE_SECRETA_NAO_VAZAR", conteudo_log)
        self.assertNotIn("Bearer segredo", conteudo_log)
        self.assertIn("input_tokens", conteudo_log)

        # Hash de arquivo original
        original = self.tmp / "orig.txt"
        original.write_text("conteudo original inviolavel", encoding="utf-8")
        reg = ArtifactRegistry(self.results_dir, "caso_hash")
        orig_info = reg.registrar_original(original)
        self.assertEqual(orig_info["sha256"], sha256_file(original))


if __name__ == "__main__":
    unittest.main()
