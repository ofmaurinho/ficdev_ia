"""Testes de integração do CLI (main.py).

Todos os comandos são testados com mocks para evitar chamadas reais à API.
Princípios:
- Cada teste exercita o caminho feliz E um caminho de erro.
- Nenhum teste cria arquivos permanentes; usa tmp_path do pytest ou tmpdir.
- O argparse é invocado via sys.argv para garantir parsing real.
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent


def _make_client_mock(
    transcribe_text: str = "texto transcrito",
    generate_text_result: str | None = None,
    speak_ok: bool = True,
    image_bytes: bytes = b"PNG_FAKE",
) -> MagicMock:
    client = MagicMock()
    client.transcribe.return_value = {
        "text": transcribe_text,
        "metadata": {"duration_seconds": 0.1, "response_id": "mock-id", "usage": {}},
    }
    gt_text = generate_text_result or json.dumps({
        "protocolo": "P-001",
        "data": "2025-01-01",
        "solicitante": "João Silva",
        "assunto": "Matrícula",
        "solicitacao": "Solicito matrícula",
        "categoria": "solicitacao_servico",
        "campos_ausentes": [],
        "confianca": 0.9,
        "revisao_humana_necessaria": True,
        "minuta": "Minuta institucional de resposta.",
        "fontes": ["entrada.txt"],
    })
    client.generate_text.return_value = {
        "text": gt_text,
        "metadata": {"duration_seconds": 0.2, "response_id": "mock-id", "usage": {}},
    }
    client.speak.return_value = {
        "audio_bytes": b"\xff\xfb",
        "metadata": {"duration_seconds": 0.3, "response_id": "mock-id"},
    }
    client.describe_image.return_value = {
        "text": "Texto visível no documento.",
        "metadata": {"duration_seconds": 0.1, "response_id": "mock-id"},
    }
    client.generate_image.return_value = {
        "image_bytes": image_bytes,
        "metadata": {"duration_seconds": 0.5, "response_id": "mock-id"},
    }
    return client


def _run_main(argv: list[str]) -> int:
    """Executa main() com os argumentos dados e retorna o código de saída."""
    from src.main import main

    with patch.object(sys, "argv", ["src.main"] + argv):
        return main()


def _write_audio(tmp: Path, name: str = "audio.mp3", size: int = 1024) -> Path:
    p = tmp / name
    p.write_bytes(b"\x00" * size)
    return p


def _write_pdf_stub(tmp: Path, name: str = "doc.pdf") -> Path:
    """Cria um stub mínimo de PDF (não real, mas com cabeçalho correto)."""
    p = tmp / name
    p.write_bytes(b"%PDF-1.4 minimal stub\n")
    return p


def _write_gabarito(tmp: Path, conteudo: dict | None = None) -> Path:
    p = tmp / "gabarito.json"
    if conteudo is None:
        conteudo = {
            "status": "VALIDADO_HUMANO",
            "elaborado_por": "Equipe",
            "data_elaboracao": "2025-01-01",
            "texto_referencia": "protocolo P001 data 2025-01-01 João Silva",
            "campos_criticos": {
                "protocolo": "P001",
                "data": "2025-01-01",
                "solicitante": "João Silva",
            },
            "resultado_esperado": {
                "protocolo": "P001",
                "data": "2025-01-01",
                "solicitante": "João Silva",
            },
        }
    p.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
    return p


class TestProcessarTexto(unittest.TestCase):
    """Comando processar-texto (padrão, sem API)."""

    def setUp(self):
        self.patch_config = patch("src.main.load_config")
        self.mock_config = self.patch_config.start()

    def tearDown(self):
        self.patch_config.stop()

    def _config(self, tmp: Path) -> dict:
        return {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0,
            "max_output_tokens": 1500,
            "timeout_seconds": 30,
            "input_dir": str(tmp),
            "default_input_file": "entrada.txt",
            "gold_dir": str(tmp / "gabaritos"),
            "processed_dir": str(tmp / "processados"),
            "results_dir": str(tmp / "resultados"),
            "audio": {},
            "vision": {},
            "image": {},
        }

    def test_processar_texto_padrao(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            entrada = tmp / "entrada.txt"
            entrada.write_text(
                "Protocolo: P-001\nData: 2025-01-01\nSolicitante: Maria\nSolicitação: cadastro escolar.",
                encoding="utf-8",
            )
            ret = _run_main(["processar-texto"])
            self.assertEqual(ret, 0)

    def test_processar_texto_arquivo_inexistente(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            ret = _run_main(["processar-texto", "--arquivo", str(tmp / "nao_existe.txt")])
            self.assertEqual(ret, 1)


class TestComandoAudio(unittest.TestCase):
    """Comando audio: STT com mock do cliente."""

    def setUp(self):
        self.patch_config = patch("src.main.load_config")
        self.patch_client = patch("src.main._make_client")
        self.mock_config = self.patch_config.start()
        self.mock_make_client = self.patch_client.start()

    def tearDown(self):
        self.patch_config.stop()
        self.patch_client.stop()

    def _config(self, tmp: Path) -> dict:
        return {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "max_output_tokens": 1500,
            "timeout_seconds": 30,
            "gold_dir": str(tmp / "gabaritos"),
            "processed_dir": str(tmp / "processados"),
            "results_dir": str(tmp / "resultados"),
            "audio": {"stt_model": "gpt-4o-transcribe", "idioma": "pt", "extensoes": [".mp3", ".wav", ".m4a"], "max_mb": 25},
            "vision": {},
            "image": {},
        }

    def test_audio_ok(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            client = _make_client_mock()
            self.mock_make_client.return_value = client
            audio = _write_audio(tmp)

            # Patch sha256_file para não depender do conteúdo real
            with patch("src.audio.sha256_file", return_value="abc123"), \
                 patch("src.audio.duracao_audio", return_value=5.0):
                ret = _run_main(["audio", "--arquivo", str(audio), "--caso", "teste01", "--sem-revisao"])

            self.assertEqual(ret, 0)
            client.transcribe.assert_called_once()

    def test_audio_sem_chave(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            self.mock_make_client.return_value = None  # sem chave
            audio = _write_audio(tmp)
            ret = _run_main(["audio", "--arquivo", str(audio)])
            self.assertEqual(ret, 1)

    def test_audio_sem_arquivo(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            self.mock_make_client.return_value = _make_client_mock()
            ret = _run_main(["audio"])
            self.assertEqual(ret, 1)

    def test_audio_extensao_invalida(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            self.mock_make_client.return_value = _make_client_mock()
            arquivo = tmp / "audio.ogg"
            arquivo.write_bytes(b"\x00" * 100)
            ret = _run_main(["audio", "--arquivo", str(arquivo)])
            self.assertEqual(ret, 1)


class TestComandoOCR(unittest.TestCase):
    """Comando ocr: OCR híbrido com mock do Tesseract e Vision."""

    def setUp(self):
        self.patch_config = patch("src.main.load_config")
        self.patch_client = patch("src.main._make_client")
        self.mock_config = self.patch_config.start()
        self.mock_make_client = self.patch_client.start()

    def tearDown(self):
        self.patch_config.stop()
        self.patch_client.stop()

    def _config(self, tmp: Path) -> dict:
        return {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "timeout_seconds": 30,
            "gold_dir": str(tmp / "gabaritos"),
            "processed_dir": str(tmp / "processados"),
            "results_dir": str(tmp / "resultados"),
            "audio": {},
            "vision": {"ocr_lang": "por", "dpi": 200, "confianca_minima_palavra": 60,
                       "max_proporcao_palavras_baixas": 0.25, "min_caracteres_por_pagina": 80,
                       "max_proporcao_ruido": 0.2, "vision_model": "gpt-4o-mini", "max_paginas": 5},
            "image": {},
        }

    def test_ocr_imagem_png(self):
        """OCR de imagem PNG via mock de tesseract e renderizar_paginas."""
        import tempfile
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            client = _make_client_mock()
            self.mock_make_client.return_value = client

            img_path = tmp / "doc.png"
            Image.new("RGB", (100, 100), color=(255, 255, 255)).save(str(img_path))

            tess_result = {
                "texto": "Protocolo P-001 João Silva 2025-01-01",
                "palavras": [{"texto": "Protocolo", "conf": 95.0}, {"texto": "P-001", "conf": 90.0}],
            }
            with patch("src.vision.ocr_tesseract", return_value=tess_result), \
                 patch("src.audit.sha256_file", return_value="abc123"):
                ret = _run_main(["ocr", "--arquivo", str(img_path), "--caso", "doc01", "--sem-correcao"])

            self.assertEqual(ret, 0)

    def test_ocr_sem_arquivo(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            self.mock_make_client.return_value = _make_client_mock()
            ret = _run_main(["ocr"])
            self.assertEqual(ret, 1)

    def test_ocr_arquivo_inexistente(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            self.mock_make_client.return_value = _make_client_mock()
            ret = _run_main(["ocr", "--arquivo", str(tmp / "nao_existe.pdf")])
            self.assertEqual(ret, 1)


class TestComandoImagem(unittest.TestCase):
    """Comando imagem: geração de peça visual com mock da API."""

    def setUp(self):
        self.patch_config = patch("src.main.load_config")
        self.patch_client = patch("src.main._make_client")
        self.mock_config = self.patch_config.start()
        self.mock_make_client = self.patch_client.start()

    def tearDown(self):
        self.patch_config.stop()
        self.patch_client.stop()

    def _config(self, tmp: Path) -> dict:
        return {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "timeout_seconds": 30,
            "gold_dir": str(tmp / "gabaritos"),
            "processed_dir": str(tmp / "processados"),
            "results_dir": str(tmp / "resultados"),
            "audio": {},
            "vision": {},
            "image": {"model": "gpt-image-1", "size": "1024x1024", "quality": "medium",
                      "rotulo": "Gerado por IA — conteúdo sintético", "brasao": "arquivos/brasao.png"},
        }

    def test_imagem_ok(self):
        import tempfile
        from PIL import Image
        import io

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            client = _make_client_mock()

            # Imagem PNG válida em bytes
            buf = io.BytesIO()
            Image.new("RGB", (64, 64), color=(0, 128, 200)).save(buf, format="PNG")
            client.generate_image.return_value = {
                "image_bytes": buf.getvalue(),
                "metadata": {"duration_seconds": 0.5, "response_id": "mock"},
            }
            self.mock_make_client.return_value = client

            with patch("src.audit.sha256_file", return_value="abc123"):
                ret = _run_main(["imagem", "--caso", "caso01"])

            self.assertEqual(ret, 0)

    def test_imagem_sem_chave(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            self.mock_make_client.return_value = None
            ret = _run_main(["imagem", "--caso", "caso01"])
            self.assertEqual(ret, 1)


class TestComandoVoz(unittest.TestCase):
    """Comando voz: TTS do roteiro aprovado."""

    def setUp(self):
        self.patch_config = patch("src.main.load_config")
        self.patch_client = patch("src.main._make_client")
        self.mock_config = self.patch_config.start()
        self.mock_make_client = self.patch_client.start()

    def tearDown(self):
        self.patch_config.stop()
        self.patch_client.stop()

    def _config(self, tmp: Path) -> dict:
        return {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "timeout_seconds": 30,
            "gold_dir": str(tmp / "gabaritos"),
            "processed_dir": str(tmp / "processados"),
            "results_dir": str(tmp / "resultados"),
            "audio": {"tts_model": "gpt-4o-mini-tts", "tts_voice": "alloy"},
            "vision": {},
            "image": {},
        }

    def test_voz_sem_caso(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            self.mock_make_client.return_value = _make_client_mock()
            ret = _run_main(["voz"])
            self.assertEqual(ret, 1)

    def test_voz_sem_aprovacao(self):
        """Caso sem minuta aprovada deve falhar com RevisaoError."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            self.mock_make_client.return_value = _make_client_mock()
            # Não criamos nenhuma aprovação => RevisaoError
            ret = _run_main(["voz", "--caso", "caso_inexistente", "--versao", "1"])
            self.assertEqual(ret, 1)

    def test_voz_com_aprovacao(self):
        """Caso com minuta aprovada deve sintetizar o áudio."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            client = _make_client_mock()
            self.mock_make_client.return_value = client

            # Prepara minuta aprovada diretamente via Revisoes
            from src.review import Revisoes

            rev = Revisoes(tmp / "resultados")
            versao = rev.registrar_versao("caso_voz", "Prezado cidadão, sua solicitação foi recebida.")
            rev.registrar_decisao("caso_voz", versao, "aprovar", "OK", "operador", tornar_vigente=True)

            # speak deve gravar o arquivo de áudio
            def mock_speak(texto, out_path, **kw):
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_bytes(b"\xff\xfb")
                return {"audio_bytes": b"\xff\xfb", "metadata": {"duration_seconds": 0.3, "response_id": "mock"}}

            client.speak.side_effect = mock_speak

            with patch("src.audit.sha256_file", return_value="abc123"):
                ret = _run_main(["voz", "--caso", "caso_voz", "--versao", str(versao)])

            self.assertEqual(ret, 0)


class TestComandoAprovarMinuta(unittest.TestCase):
    """Comando aprovar-minuta: registro de versão e decisão."""

    def setUp(self):
        self.patch_config = patch("src.main.load_config")
        self.mock_config = self.patch_config.start()

    def tearDown(self):
        self.patch_config.stop()

    def _config(self, tmp: Path) -> dict:
        return {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "timeout_seconds": 30,
            "gold_dir": str(tmp / "gabaritos"),
            "processed_dir": str(tmp / "processados"),
            "results_dir": str(tmp / "resultados"),
            "audio": {},
            "vision": {},
            "image": {},
        }

    def test_aprovar_nova_versao(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            minuta_txt = tmp / "minuta.txt"
            minuta_txt.write_text("Prezado cidadão, sua solicitação foi analisada.", encoding="utf-8")
            ret = _run_main([
                "aprovar-minuta",
                "--caso", "caso_ap01",
                "--arquivo-minuta", str(minuta_txt),
                "--operador", "Ana",
                "--decisao", "aprovar",
                "--justificativa", "Texto adequado.",
            ])
            self.assertEqual(ret, 0)

    def test_aprovar_sem_caso(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            ret = _run_main(["aprovar-minuta", "--operador", "Ana", "--decisao", "aprovar",
                              "--justificativa", "OK."])
            self.assertEqual(ret, 1)

    def test_aprovar_minuta_inexistente(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            ret = _run_main([
                "aprovar-minuta",
                "--caso", "caso_ap02",
                "--arquivo-minuta", str(tmp / "nao_existe.txt"),
                "--operador", "Ana",
                "--decisao", "aprovar",
                "--justificativa", "OK.",
            ])
            self.assertEqual(ret, 1)

    def test_rejeitar_versao_existente(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg

            # Registra versão sem aprovar
            from src.review import Revisoes

            rev = Revisoes(tmp / "resultados")
            versao = rev.registrar_versao("caso_rej", "Texto a revisar.")

            ret = _run_main([
                "aprovar-minuta",
                "--caso", "caso_rej",
                "--versao", str(versao),
                "--operador", "Carlos",
                "--decisao", "rejeitar",
                "--justificativa", "Precisa de correção.",
            ])
            self.assertEqual(ret, 0)


class TestComandoAvaliar(unittest.TestCase):
    """Comando avaliar: avaliação com gabarito validado."""

    def setUp(self):
        self.patch_config = patch("src.main.load_config")
        self.mock_config = self.patch_config.start()

    def tearDown(self):
        self.patch_config.stop()

    def _config(self, tmp: Path) -> dict:
        return {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "timeout_seconds": 30,
            "gold_dir": str(tmp / "gabaritos"),
            "processed_dir": str(tmp / "processados"),
            "results_dir": str(tmp / "resultados"),
            "audio": {},
            "vision": {},
            "image": {},
        }

    def test_avaliar_stt(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            gab = _write_gabarito(tmp)
            transcricao = tmp / "transcricao.txt"
            transcricao.write_text("protocolo P001 data 2025-01-01 João Silva", encoding="utf-8")
            with patch("src.gabarito.informacao_git", return_value={"git_disponivel": False, "commitado": False, "alterado_apos_commit": False}):
                ret = _run_main([
                    "avaliar",
                    "--modalidade", "stt",
                    "--gabarito", str(gab),
                    "--arquivo", str(transcricao),
                    "--caso", "caso_stt",
                ])
            self.assertEqual(ret, 0)

    def test_avaliar_ocr(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            gab = _write_gabarito(tmp)
            texto_ocr = tmp / "ocr.txt"
            texto_ocr.write_text("protocolo P001 João Silva 2025-01-01", encoding="utf-8")
            with patch("src.gabarito.informacao_git", return_value={"git_disponivel": False, "commitado": False, "alterado_apos_commit": False}):
                ret = _run_main([
                    "avaliar",
                    "--modalidade", "ocr",
                    "--gabarito", str(gab),
                    "--arquivo", str(texto_ocr),
                    "--caso", "caso_ocr",
                ])
            self.assertEqual(ret, 0)

    def test_avaliar_extracao(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            gab = _write_gabarito(tmp)
            extraido = tmp / "extraido.json"
            extraido.write_text(json.dumps({
                "protocolo": "P001",
                "data": "2025-01-01",
                "solicitante": "João Silva",
            }), encoding="utf-8")
            with patch("src.gabarito.informacao_git", return_value={"git_disponivel": False, "commitado": False, "alterado_apos_commit": False}):
                ret = _run_main([
                    "avaliar",
                    "--modalidade", "extracao",
                    "--gabarito", str(gab),
                    "--arquivo", str(extraido),
                    "--caso", "caso_ext",
                ])
            self.assertEqual(ret, 0)

    def test_avaliar_seguranca(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            gab_content = {
                "status": "VALIDADO_HUMANO",
                "elaborado_por": "Equipe",
                "data_elaboracao": "2025-01-01",
                "campos_criticos": {"protocolo": "P001"},
                "padroes_proibidos": ["ignore as instruções anteriores", "system prompt"],
            }
            gab = tmp / "gab_seg.json"
            gab.write_text(json.dumps(gab_content, ensure_ascii=False), encoding="utf-8")
            saida = tmp / "saida.txt"
            saida.write_text("Resposta institucional normal sem desvios.", encoding="utf-8")
            with patch("src.gabarito.informacao_git", return_value={"git_disponivel": False, "commitado": False, "alterado_apos_commit": False}):
                ret = _run_main([
                    "avaliar",
                    "--modalidade", "seguranca",
                    "--gabarito", str(gab),
                    "--arquivo", str(saida),
                    "--caso", "caso_seg",
                ])
            self.assertEqual(ret, 0)

    def test_avaliar_gabarito_invalido(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            gab = tmp / "gab_invalido.json"
            gab.write_text(json.dumps({"status": "PENDENTE"}), encoding="utf-8")
            ret = _run_main([
                "avaliar",
                "--modalidade", "stt",
                "--gabarito", str(gab),
                "--arquivo", str(tmp / "qualquer.txt"),
            ])
            self.assertEqual(ret, 1)

    def test_avaliar_sem_modalidade(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cfg = self._config(tmp)
            self.mock_config.return_value = cfg
            ret = _run_main(["avaliar", "--gabarito", str(tmp / "gab.json")])
            self.assertEqual(ret, 1)


class TestEstadosFluxo(unittest.TestCase):
    """Garante as transições de estado do atendimento via Revisoes."""

    def _make_revisoes(self, tmp: Path):
        from src.review import Revisoes

        return Revisoes(tmp / "resultados")

    def test_estado_recebido(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            rev = self._make_revisoes(Path(td))
            self.assertEqual(rev.estado_atendimento("caso_x"), "RECEBIDO")

    def test_estado_pendente(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            rev = self._make_revisoes(Path(td))
            rev.registrar_versao("caso_p", "Minuta.")
            self.assertEqual(rev.estado_atendimento("caso_p"), "PENDENTE_REVISAO")

    def test_estado_aprovado(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            rev = self._make_revisoes(Path(td))
            v = rev.registrar_versao("caso_a", "Minuta aprovada.")
            rev.registrar_decisao("caso_a", v, "aprovar", "OK", "op", tornar_vigente=True)
            self.assertEqual(rev.estado_atendimento("caso_a"), "APROVADO")

    def test_estado_rejeitado(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            rev = self._make_revisoes(Path(td))
            v = rev.registrar_versao("caso_r", "Minuta rejeitada.")
            rev.registrar_decisao("caso_r", v, "rejeitar", "Texto incorreto", "op")
            self.assertEqual(rev.estado_atendimento("caso_r"), "REJEITADO")

    def test_estado_aprovado_apos_rejeicao(self):
        """Dois ciclos: rejeita v1, aprova v2."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            rev = self._make_revisoes(Path(td))
            v1 = rev.registrar_versao("caso_ciclo", "Versão ruim.")
            rev.registrar_decisao("caso_ciclo", v1, "rejeitar", "Erro", "op")
            v2 = rev.registrar_versao("caso_ciclo", "Versão corrigida.")
            rev.registrar_decisao("caso_ciclo", v2, "aprovar", "OK", "op", tornar_vigente=True)
            self.assertEqual(rev.estado_atendimento("caso_ciclo"), "APROVADO")
            self.assertEqual(rev.versao_atual("caso_ciclo"), v2)


if __name__ == "__main__":
    unittest.main()
