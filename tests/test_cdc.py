import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog

from lakehouse.cdc import (
    chave, chaves_ja_gravadas, converter, deduplicar_no_lote, evento_para_linha, offset_gravado,
)
from lakehouse.esquemas import definicao

AGORA = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)

# Formato observado no tópico leitos.public.internacao (Debezium 3.6, JSON sem schema).
EVENTO = {
    "before": None,
    "after": {
        "competencia": 20089, "n_aih": "5325100156541", "dt_saida": 20098, "id_carga": 5, "ident": "1",
        "cnes": "0010456", "dt_internacao": 20091, "dias_permanencia": 7, "qt_diarias": 7,
        "especialidade": "03", "carater_internacao": "02", "complexidade": "02", "cid_principal": "J189",
        "cid_secundario": None, "procedimento": "0303140151", "dias_uti": 0, "marca_uti": "00",
        "valor_total": "526.72", "valor_uti": "0.00", "idade": 53, "cod_idade": "4", "sexo": "3",
        "raca_cor": "03", "municipio_residencia": "530010", "municipio_estabelecimento": "530010",
        "obito": False, "tipo_gestao": "2", "dt_ingestao": "2026-10-19T05:43:55.967403Z",
    },
    "source": {"lsn": 47732376, "ts_ms": 1792388644853, "snapshot": "first_in_data_collection"},
    "op": "r",
}


class TestConversao(unittest.TestCase):
    def setUp(self):
        self.esquema = definicao("internacao").schema.as_arrow()

    def test_tipos_do_debezium(self):
        self.assertEqual(converter(20098, pa.date32()), date(2025, 1, 10))
        self.assertEqual(converter("526.72", pa.decimal128(12, 2)), Decimal("526.72"))
        self.assertEqual(converter("2026-10-19T05:43:55.967403Z", pa.timestamp("us", tz="UTC")),
                         datetime(2026, 10, 19, 5, 43, 55, 967403, tzinfo=timezone.utc))
        self.assertIsNone(converter(None, pa.date32()))

    def test_evento_vira_linha_com_controle(self):
        linha = evento_para_linha(EVENTO, self.esquema, AGORA)
        self.assertEqual(linha["dt_saida"], date(2025, 1, 10))
        self.assertEqual((linha["_op"], linha["_lsn"], linha["_ingerido_em"]), ("r", 47732376, AGORA))
        self.assertEqual(linha["_commit_em"], datetime.fromtimestamp(1792388644.853, timezone.utc))
        pa.Table.from_pylist([linha], schema=self.esquema)  # cabe no esquema do Iceberg

    def test_evento_sem_after_e_ignorado(self):
        self.assertIsNone(evento_para_linha({"before": {}, "after": None, "op": "d"}, self.esquema, AGORA))


class TestDeduplicacao(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        catalogo = SqlCatalog("t", uri=f"sqlite:///{self.dir.name}/c.db", warehouse=f"file://{self.dir.name}")
        catalogo.create_namespace("cdc")
        d = definicao("internacao")
        self.tabela = catalogo.create_table("cdc.internacao", schema=d.schema, partition_spec=d.particao)
        self.esquema = self.tabela.schema().as_arrow()
        self.linha = evento_para_linha(EVENTO, self.esquema, AGORA)

    def test_reenvio_no_mesmo_lote(self):
        outra = dict(self.linha, n_aih="5325100156542")
        self.assertEqual(len(deduplicar_no_lote([self.linha, self.linha, outra], "internacao")), 2)

    def test_reenvio_de_linha_ja_gravada(self):
        self.tabela.append(pa.Table.from_pylist([self.linha], schema=self.esquema),
                           snapshot_properties={"cdc.offset.leitos.public.internacao": "1"})
        existentes = chaves_ja_gravadas(self.tabela, "internacao", [self.linha])
        self.assertIn(chave(self.linha, "internacao"), existentes)
        # Mesma AIH em outra carga (republicação) é outra chave: não é descartada.
        self.assertNotIn(chave(dict(self.linha, id_carga=6), "internacao"), existentes)

    def test_offset_vem_do_snapshot(self):
        self.assertIsNone(offset_gravado(self.tabela, "leitos.public.internacao"))
        self.tabela.append(pa.Table.from_pylist([self.linha], schema=self.esquema),
                           snapshot_properties={"cdc.offset.leitos.public.internacao": "20995"})
        self.assertEqual(offset_gravado(self.tabela, "leitos.public.internacao"), 20995)


if __name__ == "__main__":
    unittest.main()
