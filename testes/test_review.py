import tempfile
import unittest
from pathlib import Path

from src.review import AprovacaoInvalidaError, RevisaoError, Revisoes, hash_texto, validar_caso_id
from src.roteiro import gerar_roteiro_leitura

MINUTA = (
    "# MINUTA INSTITUCIONAL (RASCUNHO)\n\n"
    "Protocolo: 2026-000142\n"
    "- Documentos necessários: não localizado.\n"
    "- Este é um rascunho e deve ser validado por pessoa responsável.\n"
)


class RoteiroTests(unittest.TestCase):
    def test_roteiro_remove_so_marcacao_e_e_deterministico(self):
        roteiro = gerar_roteiro_leitura(MINUTA)
        self.assertEqual(roteiro, gerar_roteiro_leitura(MINUTA))
        self.assertNotIn("#", roteiro)
        self.assertNotIn("- ", roteiro)
        for trecho in ("MINUTA INSTITUCIONAL (RASCUNHO)", "Protocolo: 2026-000142", "não localizado"):
            self.assertIn(trecho, roteiro)

    def test_roteiro_nao_acrescenta_palavras(self):
        palavras_minuta = set(MINUTA.replace("#", " ").replace("- ", " ").split())
        palavras_roteiro = set(gerar_roteiro_leitura(MINUTA).split())
        self.assertLessEqual(palavras_roteiro, palavras_minuta)

    def test_minuta_vazia_e_recusada(self):
        with self.assertRaises(ValueError):
            gerar_roteiro_leitura("   ")


class RevisaoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.rev = Revisoes(Path(self._tmp.name))

    def _aprovar(self, versao, vigente=False):
        return self.rev.registrar_decisao("caso1", versao, "aprovar", "Confere com a entrada.", "operador_a", vigente)

    def test_caso_id_invalido_e_recusado(self):
        with self.assertRaises(RevisaoError):
            validar_caso_id("../fora")

    def test_aprovacao_fica_ligada_ao_hash(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        self.assertEqual(self.rev.estado_atendimento("caso1"), "PENDENTE_REVISAO")
        self._aprovar(v1)
        self.assertTrue(self.rev.aprovacao_valida("caso1", v1))
        minuta_path = self.rev.minutas_dir / "minuta_caso1_v1.txt"
        minuta_path.write_text(MINUTA + "\nAcréscimo indevido.", encoding="utf-8")
        self.assertFalse(self.rev.aprovacao_valida("caso1", v1))
        with self.assertRaises(AprovacaoInvalidaError):
            self.rev.resolver_versao("caso1", v1)

    def test_editar_roteiro_tambem_invalida(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        self._aprovar(v1)
        (self.rev.minutas_dir / "roteiro_caso1_v1.txt").write_text("outro texto", encoding="utf-8")
        self.assertFalse(self.rev.aprovacao_valida("caso1", v1))
        with self.assertRaises(AprovacaoInvalidaError):
            self.rev.ler_roteiro("caso1", v1)

    def test_nao_aprova_arquivo_alterado_antes_da_decisao(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        (self.rev.minutas_dir / "minuta_caso1_v1.txt").write_text("alterada", encoding="utf-8")
        with self.assertRaises(RevisaoError):
            self._aprovar(v1)

    def test_rejeicao_e_estado_rejeitado(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        self.rev.registrar_decisao("caso1", v1, "rejeitar", "Omite a lacuna de documentos.", "operador_a")
        self.assertEqual(self.rev.estado_atendimento("caso1"), "REJEITADO")
        self.assertFalse(self.rev.aprovacao_valida("caso1", v1))

    def test_decisao_exige_justificativa_e_operador(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        with self.assertRaises(RevisaoError):
            self.rev.registrar_decisao("caso1", v1, "aprovar", "  ", "op")
        with self.assertRaises(RevisaoError):
            self.rev.registrar_decisao("caso1", v1, "aprovar", "ok", "")
        with self.assertRaises(RevisaoError):
            self.rev.registrar_decisao("caso1", v1, "enviar", "ok", "op")

    def test_versoes_sao_imutaveis_e_numeradas(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        v2 = self.rev.registrar_versao("caso1", MINUTA + "\nCorreção.")
        self.assertEqual((v1, v2), (1, 2))
        self.assertEqual((self.rev.minutas_dir / "minuta_caso1_v1.txt").read_text(encoding="utf-8"), MINUTA)

    def test_v2_nao_altera_vigente_nem_aprovacao_da_v1(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        self._aprovar(v1, vigente=True)
        self.rev.solicitar_nova_geracao("caso1", v1, "Corrigir um erro.", "operador_a")
        v2 = self.rev.registrar_versao("caso1", MINUTA + "\nCorreção.")
        self.assertEqual(self.rev.versao_atual("caso1"), 1)
        self.assertTrue(self.rev.aprovacao_valida("caso1", v1))
        self.assertEqual(self.rev.resolver_versao("caso1"), 1)
        with self.assertRaises(AprovacaoInvalidaError):
            self.rev.resolver_versao("caso1", v2)

    def test_sem_versao_e_sem_vigente_falha(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        self._aprovar(v1)
        with self.assertRaises(RevisaoError):
            self.rev.resolver_versao("caso1")

    def test_definir_vigente_e_historico(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        self._aprovar(v1)
        self.rev.definir_versao_atual("caso1", v1, "operador_a")
        self.assertEqual(self.rev.resolver_versao("caso1"), 1)
        self.assertEqual(self.rev._load("caso1")["historico_vigente"][0]["operador"], "operador_a")
        with self.assertRaises(RevisaoError):
            self.rev.definir_versao_atual("caso1", 9, "operador_a")

    def test_descrever_selecao_mostra_arquivos_e_hashes(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        self._aprovar(v1, vigente=True)
        info = self.rev.descrever_selecao("caso1", v1)
        self.assertTrue(info["vigente"])
        self.assertEqual(info["minuta_sha256"], hash_texto(MINUTA))
        self.assertTrue(info["roteiro"].endswith("roteiro_caso1_v1.txt"))

    def test_roteiro_lido_e_exatamente_o_aprovado(self):
        v1 = self.rev.registrar_versao("caso1", MINUTA)
        self._aprovar(v1)
        self.assertEqual(self.rev.ler_roteiro("caso1", v1), gerar_roteiro_leitura(MINUTA))

    def test_hash_normaliza_quebras_de_linha(self):
        self.assertEqual(hash_texto("a\r\nb"), hash_texto("a\nb"))


if __name__ == "__main__":
    unittest.main()
