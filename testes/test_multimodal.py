import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from src import campos as campos_mod
from src.audio import AudioInvalidoError, sintetizar_roteiro, transcrever_audio, validar_audio
from src.image_generation import (
    ITENS_REVISAO,
    compor_peca,
    gerar_imagem,
    montar_prompt,
    registrar_revisao_visual,
)
from src.llm_client import (
    APIClientError,
    AuthenticationError,
    EmptyResponseError,
    MissingAPIKeyError,
    OpenAIClient,
    RateLimitError,
    RequestTimeoutError,
    ServiceUnavailableError,
)
from src.review import AprovacaoInvalidaError, Revisoes
from src.vision import DocumentoInvalidoError, extrair_texto_documento, renderizar_paginas, sinais_pre_vision

CFG_VISION = {
    "confianca_minima_palavra": 60,
    "max_proporcao_palavras_baixas": 0.25,
    "min_caracteres_por_pagina": 20,
    "max_proporcao_ruido": 0.2,
}
TEXTO_OK = "Protocolo: 2026-000142 Data: 14/10/2026 Meu nome é Marcos Santos e solicito matrícula no curso."


def png_bytes(cor=(10, 90, 160), lado=64) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (lado, lado), cor).save(buffer, format="PNG")
    return buffer.getvalue()


def palavras(textos, conf):
    return [{"texto": t, "conf": conf} for t in textos]


class FakeSDK:
    """Substitui o SDK da OpenAI em testes (sem rede, sem custo)."""

    def __init__(self):
        self.audio = MagicMock()
        self.images = MagicMock()
        self.responses = MagicMock()


def cliente_com_sdk():
    cliente = OpenAIClient(api_key="chave-de-teste-fake", model="m-teste")
    cliente.client = FakeSDK()
    return cliente


class LLMClientMultimodalTests(unittest.TestCase):
    def setUp(self):
        self.cliente = cliente_com_sdk()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.audio = self.dir / "a.mp3"
        self.audio.write_bytes(b"fake-audio")

    def test_transcribe_devolve_texto_e_metadados_sem_chave(self):
        self.cliente.client.audio.transcriptions.create.return_value = MagicMock(text="  olá mundo  ", usage=None)
        r = self.cliente.transcribe(str(self.audio), model="stt-x", language="pt")
        self.assertEqual(r["text"], "olá mundo")
        self.assertEqual(r["metadata"]["model"], "stt-x")
        self.assertNotIn("chave-de-teste-fake", json.dumps(r["metadata"], default=str))
        kwargs = self.cliente.client.audio.transcriptions.create.call_args.kwargs
        self.assertEqual((kwargs["model"], kwargs["language"]), ("stt-x", "pt"))

    def test_transcribe_vazio(self):
        self.cliente.client.audio.transcriptions.create.return_value = MagicMock(text="   ")
        with self.assertRaises(EmptyResponseError):
            self.cliente.transcribe(str(self.audio), model="stt-x")

    def test_falhas_do_provedor_viram_erros_compreensiveis(self):
        casos = [
            (Exception("Request timed out."), RequestTimeoutError),
            (Exception("Incorrect API key provided"), AuthenticationError),
            (Exception("RateLimitError: Error code: 429"), RateLimitError),
            (Exception("InternalServerError: 503 Service Unavailable"), ServiceUnavailableError),
            (Exception("algo inesperado"), APIClientError),
        ]
        for excecao, esperado in casos:
            with self.subTest(msg=str(excecao)):
                self.cliente.client.audio.transcriptions.create.side_effect = excecao
                with self.assertRaises(esperado):
                    self.cliente.transcribe(str(self.audio), model="stt-x")

    def test_chave_ausente(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(MissingAPIKeyError):
                OpenAIClient(api_key="")

    def test_speak_grava_audio_e_envia_texto_identico(self):
        self.cliente.client.audio.speech.create.return_value = MagicMock(content=b"MP3DATA", usage=None)
        saida = self.dir / "sub" / "voz.mp3"
        r = self.cliente.speak("Texto exato.", str(saida), model="tts-x", voice="alloy", instructions="calmo")
        self.assertEqual(saida.read_bytes(), b"MP3DATA")
        kwargs = self.cliente.client.audio.speech.create.call_args.kwargs
        self.assertEqual(kwargs["input"], "Texto exato.")
        self.assertEqual(r["metadata"]["bytes_audio"], 7)

    def test_speak_vazio_e_texto_vazio(self):
        self.cliente.client.audio.speech.create.return_value = MagicMock(content=b"")
        with self.assertRaises(EmptyResponseError):
            self.cliente.speak("oi", str(self.dir / "v.mp3"), model="m", voice="v")
        with self.assertRaises(ValueError):
            self.cliente.speak("  ", str(self.dir / "v.mp3"), model="m", voice="v")

    def test_describe_image_envia_imagem_e_devolve_texto(self):
        self.cliente.client.responses.create.return_value = MagicMock(output_text="texto lido", id="r1", usage=None)
        r = self.cliente.describe_image(png_bytes(), "Transcreva.", model="vis-x")
        self.assertEqual(r["text"], "texto lido")
        mensagens = self.cliente.client.responses.create.call_args.kwargs["input"]
        partes = mensagens[-1]["content"]
        self.assertEqual(partes[1]["type"], "input_image")
        self.assertTrue(partes[1]["image_url"].startswith("data:image/png;base64,"))
        with self.assertRaises(ValueError):
            self.cliente.describe_image(b"", "x")

    def test_generate_image_decodifica_e_trata_vazio(self):
        item = MagicMock(b64_json=base64.b64encode(b"PNGDATA").decode(), revised_prompt=None)
        self.cliente.client.images.generate.return_value = MagicMock(data=[item], usage=None)
        r = self.cliente.generate_image("prompt", model="img-x")
        self.assertEqual(r["image_bytes"], b"PNGDATA")
        self.cliente.client.images.generate.return_value = MagicMock(data=[], usage=None)
        with self.assertRaises(EmptyResponseError):
            self.cliente.generate_image("prompt", model="img-x")


class AudioTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_validacao_de_extensao_e_tamanho(self):
        ok = self.dir / "a.mp3"
        ok.write_bytes(b"x" * 10)
        self.assertEqual(validar_audio(ok)["extensao"], ".mp3")
        ruim = self.dir / "a.exe"
        ruim.write_bytes(b"x")
        vazio = self.dir / "v.mp3"
        vazio.write_bytes(b"")
        grande = self.dir / "g.mp3"
        grande.write_bytes(b"x" * 2048)
        for caminho, kw in [(ruim, {}), (vazio, {}), (grande, {"max_mb": 0.001}), (self.dir / "nao.mp3", {})]:
            with self.assertRaises(AudioInvalidoError):
                validar_audio(caminho, **kw)

    def test_transcricao_preserva_bruto_e_extrai_campos_do_bruto(self):
        audio = self.dir / "voz.mp3"
        audio.write_bytes(b"fake")
        cliente = MagicMock()
        cliente.transcribe.return_value = {"text": TEXTO_OK, "metadata": {"model": "stt"}}
        cliente.generate_text.return_value = {"text": "TEXTO REVISADO DIFERENTE 99/99/9999", "metadata": {}}
        r = transcrever_audio(str(audio), client=cliente, caso_id="c1", saida_dir=self.dir / "out")
        self.assertEqual(r["texto_bruto"], TEXTO_OK)
        self.assertNotEqual(r["texto_revisado"], r["texto_bruto"])
        self.assertEqual(r["campos"]["protocolo"]["valor"], "2026-000142")
        self.assertEqual(r["campos"]["protocolo"]["metodo"], "stt")
        self.assertEqual((self.dir / "out" / "c1_transcricao_bruta.txt").read_text(encoding="utf-8"), TEXTO_OK)
        self.assertTrue((self.dir / "out" / "campos_c1.json").exists())
        prompt = cliente.generate_text.call_args.args[0]
        self.assertIn("<transcricao_nao_confiavel>", prompt)

    def test_transcricao_sem_revisao_nao_chama_llm(self):
        audio = self.dir / "voz.mp3"
        audio.write_bytes(b"fake")
        cliente = MagicMock()
        cliente.transcribe.return_value = {"text": TEXTO_OK, "metadata": {}}
        r = transcrever_audio(str(audio), client=cliente, revisar=False)
        cliente.generate_text.assert_not_called()
        self.assertIsNone(r["texto_revisado"])

    def test_tts_bloqueado_sem_aprovacao_e_apos_edicao(self):
        rev = Revisoes(self.dir / "res")
        v1 = rev.registrar_versao("c1", "Minuta com não localizado.")
        cliente = MagicMock()
        with self.assertRaises(AprovacaoInvalidaError):
            sintetizar_roteiro("c1", v1, self.dir / "v.mp3", client=cliente, revisoes=rev)
        rev.registrar_decisao("c1", v1, "aprovar", "ok", "op")
        (rev.minutas_dir / "roteiro_c1_v1.txt").write_text("texto adulterado", encoding="utf-8")
        with self.assertRaises(AprovacaoInvalidaError):
            sintetizar_roteiro("c1", v1, self.dir / "v.mp3", client=cliente, revisoes=rev)
        cliente.speak.assert_not_called()

    def test_tts_le_exatamente_o_roteiro_aprovado(self):
        rev = Revisoes(self.dir / "res")
        v1 = rev.registrar_versao("c1", "# Título\n- Documentos: não localizado.\n")
        rev.registrar_decisao("c1", v1, "aprovar", "ok", "op")
        saida = self.dir / "v.mp3"

        def falso_speak(texto, out, **kw):
            Path(out).write_bytes(b"MP3")
            return {"path": out, "metadata": {"bytes_audio": 3}}

        cliente = MagicMock()
        cliente.speak.side_effect = falso_speak
        registro = sintetizar_roteiro("c1", v1, saida, client=cliente, revisoes=rev, audio_cfg={"tts_voice": "alloy"})
        enviado = cliente.speak.call_args.args[0]
        self.assertEqual(enviado, (rev.minutas_dir / "roteiro_c1_v1.txt").read_text(encoding="utf-8"))
        self.assertIn("não localizado", enviado)
        self.assertTrue(registro["texto_enviado_identico_ao_roteiro_aprovado"])
        self.assertTrue(Path(str(saida) + ".json").exists())
        self.assertFalse(registro["escuta_humana_registrada"])


class CamposTests(unittest.TestCase):
    def test_extrai_com_origem_e_marca_ausentes(self):
        c = campos_mod.extrair_campos("Sem dados aqui.", origem="a.pdf", origem_sha256="h", metodo="tesseract", pagina=1)
        self.assertTrue(all(item["status"] == "ausente" for item in c.values()))
        self.assertEqual(c["protocolo"]["valor"], campos_mod.NAO_LOCALIZADO)
        self.assertEqual(campos_mod.campos_pendentes(c), [])  # ausência legítima não bloqueia

    def test_data_invalida_vira_incerta_e_bloqueia(self):
        c = campos_mod.extrair_campos(
            "Protocolo: 2026-000142 em 31/02/2026", origem="a.pdf", origem_sha256="h", metodo="tesseract", pagina=1
        )
        self.assertEqual(c["data"]["status"], "incerto")
        self.assertIn("data", campos_mod.campos_pendentes(c))

    def test_extraido_de_stt_exige_confirmacao_mas_texto_original_nao(self):
        stt = campos_mod.extrair_campos(TEXTO_OK, origem="a.mp3", origem_sha256="h", metodo="stt")
        self.assertIn("protocolo", campos_mod.campos_pendentes(stt))
        txt = campos_mod.extrair_campos(TEXTO_OK, origem="a.txt", origem_sha256="h", metodo="texto_original")
        self.assertEqual(campos_mod.campos_pendentes(txt), [])

    def test_confirmar_campo_com_correcao_preserva_original(self):
        c = campos_mod.extrair_campos(TEXTO_OK, origem="a.mp3", origem_sha256="h", metodo="stt")
        campos_mod.confirmar_campo(c, "protocolo", "operador_a", valor_corrigido="2026-000143")
        self.assertEqual(c["protocolo"]["status"], "confirmado_humano")
        self.assertEqual(c["protocolo"]["valor_extraido_original"], "2026-000142")
        self.assertEqual(c["protocolo"]["metodo"], "correcao_humana")
        with self.assertRaises(campos_mod.CampoError):
            campos_mod.confirmar_campo(c, "inexistente", "op")
        with self.assertRaises(campos_mod.CampoError):
            campos_mod.confirmar_campo(c, "data", "")

    def test_comparar_rotas_marca_divergencia_e_mantem_ausencia_comum(self):
        a = campos_mod.extrair_campos(TEXTO_OK, origem="a", origem_sha256="h", metodo="tesseract")
        b = campos_mod.extrair_campos(TEXTO_OK.replace("000142", "000148"), origem="a", origem_sha256="h", metodo="vision")
        r = campos_mod.comparar_rotas(a, b)
        self.assertEqual(r["protocolo"]["status"], "divergente")
        self.assertEqual(r["protocolo"]["valor_alternativo"], "2026-000148")
        vazio = campos_mod.extrair_campos("nada", origem="a", origem_sha256="h", metodo="tesseract")
        vazio2 = campos_mod.extrair_campos("nada", origem="a", origem_sha256="h", metodo="vision")
        self.assertTrue(all(i["status"] == "ausente" for i in campos_mod.comparar_rotas(vazio, vazio2).values()))


class VisionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.doc = self.dir / "doc.png"
        self.doc.write_bytes(png_bytes())

    def test_sem_gatilhos_para_texto_limpo(self):
        sinais = sinais_pre_vision(TEXTO_OK, palavras(TEXTO_OK.split(), 95), CFG_VISION)
        self.assertEqual(sinais, [])

    def test_gatilhos_independentes_da_confianca_media(self):
        # Média alta, mas uma palavra com dígito tem confiança baixa -> dispara.
        ws = palavras(TEXTO_OK.split(), 99)
        ws[1] = {"texto": "2026-000142", "conf": 30}
        self.assertIn("palavra_critica_baixa_confianca", sinais_pre_vision(TEXTO_OK, ws, CFG_VISION))

    def test_outros_gatilhos(self):
        self.assertIn("texto_incompleto", sinais_pre_vision("oi", palavras(["oi"], 99), CFG_VISION))
        self.assertIn("nenhuma_palavra_reconhecida", sinais_pre_vision("", [], CFG_VISION))
        ruido = "~~ ## ^^ x y z w ## ~~ @@ ;; ## q r s t u"
        self.assertIn("ruido_excessivo", sinais_pre_vision(ruido, palavras(ruido.split(), 99), CFG_VISION))
        self.assertTrue(
            any("data_invalida" in s for s in sinais_pre_vision("Data 31/02/2026 " + TEXTO_OK, palavras(["a"], 99), CFG_VISION))
        )
        self.assertTrue(
            any("protocolo_sem_valor" in s for s in sinais_pre_vision("Protocolo: ??? " * 3, palavras(["a"], 99), CFG_VISION))
        )

    def test_formato_nao_suportado_e_arquivo_ausente(self):
        txt = self.dir / "a.txt"
        txt.write_text("x")
        with self.assertRaises(DocumentoInvalidoError):
            renderizar_paginas(txt)
        with self.assertRaises(DocumentoInvalidoError):
            renderizar_paginas(self.dir / "nao.pdf")

    def _executar(self, texto_tess, conf, cliente, **kw):
        ws = palavras(texto_tess.split(), conf)
        with patch("src.vision.ocr_tesseract", return_value={"texto": texto_tess, "palavras": ws}):
            return extrair_texto_documento(str(self.doc), client=cliente, vision_cfg=CFG_VISION, **kw)

    def test_vision_nao_e_chamado_quando_ocr_local_basta(self):
        cliente = MagicMock()
        r = self._executar(TEXTO_OK, 95, cliente, corrigir=False)
        cliente.describe_image.assert_not_called()
        self.assertFalse(r["vision_usado"])
        self.assertIn("local", r["aviso_privacidade"])

    def test_fallback_aciona_vision_e_divergencia_vai_para_confirmacao(self):
        cliente = MagicMock()
        cliente.describe_image.return_value = {"text": TEXTO_OK.replace("000142", "000148"), "metadata": {"m": 1}}
        cliente.generate_text.return_value = {"text": "corrigido", "metadata": {}}
        r = self._executar(TEXTO_OK, 30, cliente, saida_dir=self.dir / "out", caso_id="c1")
        self.assertTrue(r["vision_usado"])
        self.assertIn("baixa_confianca_proporcao", r["gatilhos_pre_vision"])
        self.assertEqual(r["campos"]["protocolo"]["status"], "divergente")
        self.assertIn("protocolo", campos_mod.campos_pendentes(r["campos"]))
        self.assertEqual(r["texto_tesseract"], TEXTO_OK)  # bruto preservado
        self.assertEqual(r["texto_corrigido"], "corrigido")
        prompt = cliente.describe_image.call_args.args[1]
        self.assertIn("DADO", prompt)
        self.assertTrue((self.dir / "out" / "c1_ocr_tesseract.txt").exists())
        self.assertTrue((self.dir / "out" / "c1_ocr_vision.txt").exists())
        self.assertTrue((self.dir / "out" / "campos_c1.json").exists())

    def test_ausencia_nas_duas_rotas_nao_bloqueia(self):
        cliente = MagicMock()
        cliente.describe_image.return_value = {"text": "formulário em branco sem dados", "metadata": {}}
        cliente.generate_text.return_value = {"text": "x", "metadata": {}}
        r = self._executar("formulario em branco sem dados", 30, cliente)
        self.assertTrue(all(i["status"] == "ausente" for i in r["campos"].values()))
        self.assertEqual(campos_mod.campos_pendentes(r["campos"]), [])

    def test_sem_cliente_registra_que_vision_nao_esta_disponivel(self):
        r = self._executar("x y", 20, None)
        self.assertFalse(r["vision_usado"])
        self.assertIn("vision_indisponivel_sem_cliente", r["gatilhos_pre_vision"])

    def test_campo_com_palavra_de_baixa_confianca_fica_incerto(self):
        ws = palavras(TEXTO_OK.split(), 99)
        ws[1] = {"texto": "2026-000142", "conf": 20}
        with patch("src.vision.ocr_tesseract", return_value={"texto": TEXTO_OK, "palavras": ws}):
            r = extrair_texto_documento(str(self.doc), client=None, vision_cfg=CFG_VISION)
        self.assertEqual(r["campos"]["protocolo"]["status"], "incerto")


class ImagemTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.brasao = self.dir / "brasao.png"
        self.brasao.write_bytes(png_bytes((200, 200, 0), 40))

    def test_prompt_estruturado_exige_todos_os_campos(self):
        p = montar_prompt("s", "c", "e", "i", "1:1", ["sem texto"])
        for rotulo in ("Sujeito:", "Composição:", "Estilo:", "Iluminação:", "Proporção:", "Restrições:"):
            self.assertIn(rotulo, p)
        with self.assertRaises(ValueError):
            montar_prompt("", "c", "e", "i", "1:1", ["x"])
        with self.assertRaises(ValueError):
            montar_prompt("s", "c", "e", "i", "1:1", [])

    def test_composicao_gera_png_com_faixa_de_rotulo(self):
        saida = compor_peca(png_bytes((250, 250, 250), 128), titulo="Matrícula", texto="Orientação.", out_path=self.dir / "p.png", brasao_path=self.brasao, lado=512)
        imagem = Image.open(saida)
        self.assertEqual(imagem.size, (512, 512))
        self.assertLess(sum(imagem.getpixel((5, 505))[:3]), 120)  # rodapé escuro com o rótulo

    def _gerar(self):
        cliente = MagicMock()
        cliente.generate_image.return_value = {"image_bytes": png_bytes((250, 250, 250), 128), "metadata": {"model": "img"}}
        return gerar_imagem(
            "prompt estruturado", client=cliente, image_cfg={"model": "img", "size": "1024x1024"},
            titulo="Matrícula", texto="Orientação.", out_path=self.dir / "p.png", caso_id="c1", brasao_path=self.brasao,
        ), cliente

    def test_nota_de_proveniencia_nasce_pendente_e_nao_utilizavel(self):
        nota, cliente = self._gerar()
        self.assertEqual(nota["identificacao"], "Gerado por IA — conteúdo sintético")
        self.assertEqual(nota["prompt"], "prompt estruturado")
        self.assertFalse(nota["utilizavel"])
        self.assertEqual(nota["revisao_visual"]["status"], "pendente")
        self.assertFalse(nota["pessoa_real"])
        self.assertTrue((self.dir / "p.png.proveniencia.json").exists())
        self.assertEqual(cliente.generate_image.call_args.kwargs["model"], "img")

    def test_revisao_visual_aprova_so_com_todos_os_itens(self):
        self._gerar()
        nota_path = self.dir / "p.png.proveniencia.json"
        ok = {item: True for item in ITENS_REVISAO}
        self.assertTrue(registrar_revisao_visual(nota_path, "op", ok)["utilizavel"])
        ruim = dict(ok, maos=False)
        nota = registrar_revisao_visual(nota_path, "op", ruim, "mão estranha")
        self.assertFalse(nota["utilizavel"])
        self.assertEqual(nota["revisao_visual"]["status"], "reprovada")
        with self.assertRaises(ValueError):
            registrar_revisao_visual(nota_path, "op", {"texto": True})
        with self.assertRaises(ValueError):
            registrar_revisao_visual(nota_path, "", ok)

    def test_imagem_alterada_apos_geracao_impede_revisao(self):
        self._gerar()
        (self.dir / "p.png").write_bytes(png_bytes((1, 2, 3), 64))
        with self.assertRaises(ValueError):
            registrar_revisao_visual(self.dir / "p.png.proveniencia.json", "op", {i: True for i in ITENS_REVISAO})


if __name__ == "__main__":
    unittest.main()
