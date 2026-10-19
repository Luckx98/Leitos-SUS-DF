import unittest

from pyiceberg.transforms import YearTransform

from lakehouse.esquemas import CONTROLE, NAMESPACES, TABELAS, definicao


class TestEsquemas(unittest.TestCase):
    def test_ids_de_campo_unicos(self):
        for nome in TABELAS:
            with self.subTest(tabela=nome):
                ids = [f.field_id for f in definicao(nome).schema.fields]
                self.assertEqual(len(ids), len(set(ids)))

    def test_colunas_de_controle_em_todas(self):
        for nome in TABELAS:
            colunas = {f.name for f in definicao(nome).schema.fields}
            for controle, _ in CONTROLE:
                self.assertIn(controle, colunas, nome)

    def test_internacao_particionada_pelo_ano_de_saida(self):
        d = definicao("internacao")
        (campo,) = d.particao.fields
        self.assertIsInstance(campo.transform, YearTransform)
        self.assertEqual(d.schema.find_field(campo.source_id).name, "dt_saida")

    def test_tabelas_pequenas_sem_particao(self):
        for nome in ("carga", "estabelecimento", "estabelecimento_versao", "leito"):
            self.assertEqual(len(definicao(nome).particao.fields), 0, nome)

    def test_dois_caminhos(self):
        self.assertEqual(set(NAMESPACES), {"lote", "cdc"})


if __name__ == "__main__":
    unittest.main()
