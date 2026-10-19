import tempfile
import unittest
from datetime import date, datetime, timezone

import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog

from lakehouse.compactar import compactar_tabela, propriedades_preservadas
from lakehouse.esquemas import definicao


class TestCompactacao(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        catalogo = SqlCatalog("t", uri=f"sqlite:///{self.dir.name}/c.db", warehouse=f"file://{self.dir.name}")
        catalogo.create_namespace("lote")
        d = definicao("internacao")
        self.tabela = catalogo.create_table("lote.internacao", schema=d.schema, partition_spec=d.particao)
        self.esquema = self.tabela.schema().as_arrow()

    def linhas(self, mes: int, n: int, id_carga: int) -> pa.Table:
        base = {c.name: None for c in self.esquema}
        return pa.Table.from_pylist(
            [dict(base, competencia=date(2025, mes, 1), dt_saida=date(2025, mes, 1), n_aih=f"{id_carga}{i:012d}",
                  id_carga=id_carga, _ingerido_em=datetime(2026, 1, 1, tzinfo=timezone.utc)) for i in range(n)],
            schema=self.esquema)

    def test_junta_arquivos_e_preserva_a_marca(self):
        for mes, carga in ((1, 1), (2, 2), (3, 3)):  # três incrementos: três arquivos no ano de 2025
            self.tabela.append(self.linhas(mes, 10, carga), snapshot_properties={"lote.id_carga_max": str(carga)})
        self.assertEqual(len(self.tabela.inspect.files()), 3)

        antes, depois = compactar_tabela(self.tabela, "internacao")

        self.assertEqual((antes, depois), (3, 1))
        self.assertEqual(self.tabela.scan().to_arrow().num_rows, 30)
        self.assertEqual(propriedades_preservadas(self.tabela), {"lote.id_carga_max": "3"})

    def test_particao_com_um_arquivo_nao_e_reescrita(self):
        self.tabela.append(self.linhas(1, 5, 1))
        snapshot = self.tabela.current_snapshot().snapshot_id
        compactar_tabela(self.tabela, "internacao")
        self.assertEqual(self.tabela.current_snapshot().snapshot_id, snapshot)


if __name__ == "__main__":
    unittest.main()
