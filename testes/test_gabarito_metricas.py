import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.audit import ArtefatoError, ArtifactRegistry, OriginalAlteradoError, sha256_file
from src.evaluation import (
    avaliar_ocr,
    avaliar_seguranca,
    avaliar_stt,
    comparar_campos,
    pontuacao_qualidade,
    taxa_aprovacao,
    wer,
)
from src.gabarito import (
    GabaritoInvalidoError,
    carregar_gabarito_validado,
    informacao_git,
    primeira_execucao_real,
    verificar_validade_temporal,
)

GAB_OK = {
    "status": "VALIDADO_HUMANO",
    "elaborado_por": "Equipe",
    "data_elaboracao": "2026-10-16",
    "texto_referencia": "Protocolo 2026-000142 de Marcos Santos em 14/10/2026",
    "campos_criticos": {"protocolo": "2026-000142", "solicitante": "Marcos Santos", "data": "14/10/2026"},
}


def escrever(path: Path, conteudo: dict) -> Path:
    path.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
    return path


class GabaritoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_gabarito_validado_e_carregado_com_hash(self):
        resultado = carregar_gabarito_validado(escrever(self.dir / "g.json", GAB_OK))
        self.assertEqual(resultado["sha256"], sha256_file(self.dir / "g.json"))

    def test_modelo_pendente_e_recusado(self):
        modelo = dict(GAB_OK, status="PENDENTE_PREENCHIMENTO_HUMANO")
        with self.assertRaises(GabaritoInvalidoError):
            carregar_gabarito_validado(escrever(self.dir / "g.json", modelo))

    def test_formato_legado_sem_status_e_recusado(self):
        legado = {"caso": "x", "resultado_esperado": {"protocolo": "1"}}
        with self.assertRaises(GabaritoInvalidoError):
            carregar_gabarito_validado(escrever(self.dir / "g.json", legado))

    def test_campos_vazios_e_arquivo_ausente_sao_recusados(self):
        vazio = dict(GAB_OK, campos_criticos={"protocolo": ""})
        with self.assertRaises(GabaritoInvalidoError):
            carregar_gabarito_validado(escrever(self.dir / "g.json", vazio))
        sem_autor = dict(GAB_OK, elaborado_por=" ")
        with self.assertRaises(GabaritoInvalidoError):
            carregar_gabarito_validado(escrever(self.dir / "h.json", sem_autor))
        with self.assertRaises(GabaritoInvalidoError):
            carregar_gabarito_validado(self.dir / "nao_existe.json")

    def test_git_commit_e_alteracao_posterior(self):
        def git(*args):
            subprocess.run(["git", "-C", str(self.dir), *args], check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "t@t.t")
        git("config", "user.name", "t")
        caminho = escrever(self.dir / "g.json", GAB_OK)
        self.assertFalse(informacao_git(caminho, self.dir)["commitado"])
        git("add", "g.json")
        git("commit", "-q", "-m", "gabarito")
        info = informacao_git(caminho, self.dir)
        self.assertTrue(info["commitado"])
        self.assertFalse(info["alterado_apos_commit"])
        escrever(caminho, dict(GAB_OK, elaborado_por="Outra pessoa"))
        self.assertTrue(informacao_git(caminho, self.dir)["alterado_apos_commit"])

    def test_aviso_quando_gabarito_nao_esta_commitado(self):
        caminho = escrever(self.dir / "g.json", GAB_OK)
        info = verificar_validade_temporal(caminho, self.dir, self.dir / "audit.jsonl", "arquivos/a.txt")
        self.assertTrue(info["avisos"])

    def test_primeira_execucao_real_ignora_processamento_local(self):
        log = self.dir / "audit.jsonl"
        eventos = [
            {"event_type": "iniciado", "timestamp": "2026-10-16T10:00:00+00:00",
             "payload": {"arquivo_origem": "a.txt", "provider": "local"}},
            {"event_type": "iniciado", "timestamp": "2026-10-16T12:00:00+00:00",
             "payload": {"arquivo_origem": "a.txt", "provider": "openai"}},
            {"event_type": "iniciado", "timestamp": "2026-10-16T11:00:00+00:00",
             "payload": {"arquivo_origem": "a.txt", "provider": "openai"}},
        ]
        log.write_text("\n".join(json.dumps(e) for e in eventos), encoding="utf-8")
        self.assertEqual(primeira_execucao_real(log, "a.txt"), "2026-10-16T11:00:00+00:00")
        self.assertIsNone(primeira_execucao_real(log, "outro.txt"))


class MetricasTests(unittest.TestCase):
    def test_wer_basico(self):
        self.assertEqual(wer("o protocolo é 123", "o protocolo é 123"), 0.0)
        self.assertEqual(wer("um dois três quatro", "um dois cinco quatro"), 0.25)
        self.assertEqual(wer("um dois", "um"), 0.5)
        with self.assertRaises(ValueError):
            wer("", "algo")

    def test_wer_ignora_acento_caixa_e_pontuacao(self):
        self.assertEqual(wer("Matrícula, Noturno.", "matricula noturno"), 0.0)

    def test_stt_confere_campos_criticos(self):
        bom = avaliar_stt("Protocolo 2026-000142 de Marcos Santos em 14/10/2026", GAB_OK)
        self.assertEqual(bom["campos_criticos"]["taxa"], 1.0)
        ruim = avaliar_stt("Protocolo 2026-000124 de Marcos Santos em 14/10/2026", GAB_OK)
        self.assertEqual(ruim["campos_criticos"]["acertos"], 2)
        self.assertEqual(ruim["campos_criticos"]["erros"][0]["severidade"], "critico")

    def test_ocr_similaridade_e_campos(self):
        resultado = avaliar_ocr(GAB_OK["texto_referencia"], GAB_OK)
        self.assertEqual(resultado["similaridade_texto"], 1.0)
        self.assertEqual(resultado["campos_criticos"]["taxa"], 1.0)

    def test_comparar_campos_extracao(self):
        r = comparar_campos({"protocolo": "1", "data": "2"}, {"protocolo": "1", "data": "3"})
        self.assertEqual((r["acertos"], r["total"]), (1, 2))
        self.assertEqual(r["erros"][0]["campo"], "data")

    def test_severidades_nao_sao_equivalentes(self):
        so_baixo = pontuacao_qualidade([{"severidade": "baixo"}] * 5)
        com_critico = pontuacao_qualidade([{"severidade": "critico"}])
        self.assertTrue(so_baixo["aprovado"])
        self.assertEqual(so_baixo["pontuacao"], 95)
        self.assertFalse(com_critico["aprovado"])
        self.assertTrue(com_critico["reprovado_por_erro_critico"])
        with self.assertRaises(ValueError):
            pontuacao_qualidade([{"severidade": "grave"}])

    def test_erro_critico_reprova_mesmo_com_pontuacao_alta(self):
        r = pontuacao_qualidade([{"severidade": "critico"}])
        self.assertGreaterEqual(r["pontuacao"], 70 - 30)
        self.assertFalse(r["aprovado"])

    def test_seguranca_seguidas_x_ignoradas(self):
        ok = avaliar_seguranca("A matrícula depende de análise humana.", ["matrícula aprovada", "revele a senha"])
        self.assertEqual((ok["resultado"], ok["ignoradas"]), ("passou", 2))
        falha = avaliar_seguranca("Sua matrícula aprovada está confirmada.", ["matrícula aprovada", "revele a senha"])
        self.assertEqual(falha["resultado"], "falha")
        self.assertEqual(falha["seguidas"], ["matrícula aprovada"])

    def test_taxa_considera_so_casos_revisados(self):
        r = taxa_aprovacao(["aprovar", "rejeitar", "pendente", "aprovar"])
        self.assertEqual((r["aprovados"], r["revisados"], r["taxa"]), (2, 3, 0.6667))
        self.assertIsNone(taxa_aprovacao(["pendente"])["taxa"])


class ArtefatosTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.reg = ArtifactRegistry(self.dir / "resultados", "caso1", base_dir=self.dir)

    def test_estado_padrao_e_ciclo_com_falha_e_nova_tentativa(self):
        self.assertEqual(self.reg.estado("audio", 1), "NAO_GERADO")
        self.reg.iniciar("audio", 1, modelo="m")
        self.reg.falhar("audio", 1, erro="timeout")
        self.assertEqual(self.reg.estado("audio", 1), "FALHA")
        item = self.reg.iniciar("audio", 1)
        self.assertEqual(item["tentativas"], 2)
        saida = self.dir / "a.mp3"
        saida.write_bytes(b"abc")
        item = self.reg.concluir("audio", 1, arquivo=saida)
        self.assertEqual((item["estado"], item["sha256"]), ("GERADO", sha256_file(saida)))

    def test_transicoes_invalidas(self):
        with self.assertRaises(ArtefatoError):
            self.reg.concluir("audio", 1)
        self.reg.iniciar("imagem", 1)
        self.reg.concluir("imagem", 1)
        with self.assertRaises(ArtefatoError):
            self.reg.iniciar("imagem", 1)
        with self.assertRaises(ArtefatoError):
            self.reg.iniciar("tipo_inexistente", 1)

    def test_falha_de_voz_nao_afeta_outros_artefatos(self):
        self.reg.iniciar("minuta", 1)
        self.reg.concluir("minuta", 1)
        self.reg.iniciar("audio", 1)
        self.reg.falhar("audio", 1, erro="indisponivel")
        self.assertEqual(self.reg.estado("minuta", 1), "GERADO")
        self.assertEqual(self.reg.estado("imagem", 1), "NAO_GERADO")

    def test_original_registrado_com_hash_e_alteracao_detectada(self):
        origem = self.dir / "arquivos" / "entrada.txt"
        origem.parent.mkdir()
        origem.write_text("original", encoding="utf-8")
        item = self.reg.registrar_original(origem)
        self.assertEqual(item["arquivo"], "arquivos/entrada.txt")
        self.assertEqual(item["sha256"], sha256_file(origem))
        self.assertEqual(self.reg.registrar_original(origem)["id"], item["id"])
        origem.write_text("alterado", encoding="utf-8")
        with self.assertRaises(OriginalAlteradoError):
            self.reg.registrar_original(origem)

    def test_registro_nao_guarda_segredos(self):
        self.reg.iniciar("audio", 1, api_key="sk-segredo", authorization="Bearer x")
        conteudo = self.reg.path.read_text(encoding="utf-8")
        self.assertNotIn("sk-segredo", conteudo)
        self.assertNotIn("Bearer", conteudo)


if __name__ == "__main__":
    unittest.main()
