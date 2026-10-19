import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from pyiceberg.catalog.sql import SqlCatalog

from lakehouse.brutos import chave, fonte_do_arquivo
from lakehouse.esquemas import COLUNAS, definicao
from lakehouse.lote import EXPORTACOES, gravar, marca_atual, para_arrow

AGORA = datetime(2026, 10, 19, tzinfo=timezone.utc)


def linha_leito(competencia: date, cnes: str, id_carga: int) -> tuple:
    valores = {c: None for c, _ in COLUNAS["leito"]}
    valores.update(competencia=competencia, cnes=cnes, cod_leito="01", tipo_leito="1",
                   qt_existente=10, qt_contratado=0, qt_sus=8, qt_nao_sus=2, id_carga=id_carga)
    return (*valores.values(), AGORA)  # última coluna: _commit_em


class TestGravacaoDoLote(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        catalogo = SqlCatalog("t", uri=f"sqlite:///{self.dir.name}/c.db", warehouse=f"file://{self.dir.name}")
        catalogo.create_namespace("lote")
        d = definicao("leito")
        self.tabela = catalogo.create_table("lote.leito", schema=d.schema, partition_spec=d.particao)
        self.esquema = self.tabela.schema().as_arrow()

    def lote(self, *linhas):
        return para_arrow(list(linhas), self.esquema, AGORA)

    def test_grava_e_registra_a_marca(self):
        linhas, arquivos = gravar(self.tabela, [self.lote(linha_leito(date(2025, 1, 1), "0010456", 7))], marca=7)
        self.assertEqual((linhas, arquivos), (1, 1))
        self.assertEqual(marca_atual(self.tabela), 7)
        dados = self.tabela.scan().to_arrow().to_pylist()[0]
        self.assertEqual((dados["_op"], dados["_lsn"], dados["_ingerido_em"]), ("c", None, AGORA))

    def test_varios_lotes_viram_um_so_commit(self):
        gravar(self.tabela, [self.lote(linha_leito(date(2025, 1, 1), "1", 1)),
                             self.lote(linha_leito(date(2025, 2, 1), "1", 1))], marca=1)
        self.assertEqual(self.tabela.scan().to_arrow().num_rows, 2)
        self.assertEqual(marca_atual(self.tabela), 1)

    def test_falha_no_meio_nao_grava_nada(self):
        gravar(self.tabela, [self.lote(linha_leito(date(2025, 1, 1), "1", 1))], marca=1)

        def lotes_com_falha():
            yield self.lote(linha_leito(date(2025, 2, 1), "2", 2))
            raise ConnectionError("origem caiu no meio da leitura")

        with self.assertRaises(ConnectionError):
            gravar(self.tabela, lotes_com_falha(), marca=2)
        self.tabela.refresh()
        self.assertEqual(self.tabela.scan().to_arrow().num_rows, 1)
        self.assertEqual(marca_atual(self.tabela), 1)

    def test_sem_linhas_nao_cria_snapshot(self):
        self.assertEqual(gravar(self.tabela, [], marca=5), (0, 0))
        self.assertIsNone(self.tabela.current_snapshot())
        self.assertEqual(marca_atual(self.tabela), 0)


class TestConsultasEBrutos(unittest.TestCase):
    def test_todas_as_tabelas_exportadas_com_filtro_pela_marca(self):
        self.assertEqual({e.tabela for e in EXPORTACOES}, set(COLUNAS))
        for e in EXPORTACOES:
            self.assertIn("> %(de)s", e.consulta())
            self.assertIn("<= %(ate)s", e.consulta())

    def test_chave_do_bruto_e_imutavel_por_conteudo(self):
        self.assertEqual(fonte_do_arquivo(Path("RDGO2607.dbc")), "SIH_RD")
        self.assertEqual(fonte_do_arquivo(Path("TAB_SIH_recorte.zip")), "REFERENCIA")
        a = chave(Path("RDDF2501.dbc"), "a" * 64)
        b = chave(Path("RDDF2501.dbc"), "b" * 64)
        self.assertNotEqual(a, b)  # mesmo nome, conteúdo diferente: dois objetos
        self.assertEqual(a, "bruto/SIH_RD/aaaaaaaaaaaaaaaa_RDDF2501.dbc")


if __name__ == "__main__":
    unittest.main()
