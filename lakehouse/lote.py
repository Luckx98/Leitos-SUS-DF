"""Caminho de lote: exporta incrementalmente a origem para as tabelas lote.* do Iceberg.

    python -m lakehouse.lote

Como a origem é insert-only e toda linha aponta para a carga que a trouxe, o
incremento é "tudo com id_carga maior que o último exportado". Essa marca d'água
é gravada como propriedade do snapshot do Iceberg, no mesmo commit dos dados:
ou entram os dados e a marca, ou não entra nada. Reexecutar não duplica, e uma
falha no meio deixa a tabela como estava.

Pressuposto: as cargas são confirmadas na ordem do id_carga (um loader por vez).
Dois loaders em paralelo poderiam confirmar o id 11 antes do 10, e o 10 ficaria
abaixo da marca.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg
import pyarrow as pa
from pyiceberg.table import Table

from lakehouse.brutos import enviar_brutos
from lakehouse.catalogo import abrir_catalogo
from lakehouse.config import ConfigLakehouse
from lakehouse.esquemas import COLUNAS

log = logging.getLogger("lakehouse.lote")

PROPRIEDADE_MARCA = "lote.id_carga_max"
LINHAS_POR_LOTE = 250_000


@dataclass(frozen=True)
class Exportacao:
    tabela: str
    coluna_marca: str  # coluna que liga a linha à carga
    ordem: str  # ordem de leitura: agrupa as linhas da mesma partição no mesmo arquivo

    def consulta(self) -> str:
        colunas = ", ".join(f"t.{c}" for c, _ in COLUNAS[self.tabela])
        if self.tabela == "carga":
            return f"""
                SELECT {colunas}, t.concluida_em AS _commit_em FROM carga t
                WHERE t.id_carga > %(de)s AND t.id_carga <= %(ate)s ORDER BY {self.ordem}
            """
        return f"""
            SELECT {colunas}, c.concluida_em AS _commit_em
            FROM {self.tabela} t JOIN carga c ON c.id_carga = t.{self.coluna_marca}
            WHERE t.{self.coluna_marca} > %(de)s AND t.{self.coluna_marca} <= %(ate)s
            ORDER BY {self.ordem}
        """


EXPORTACOES = (
    Exportacao("carga", "id_carga", "t.id_carga"),
    Exportacao("estabelecimento", "primeira_carga", "t.cnes"),
    Exportacao("estabelecimento_versao", "id_carga", "t.cnes, t.competencia_inicio"),
    Exportacao("leito", "id_carga", "t.competencia, t.cnes"),
    Exportacao("internacao", "id_carga", "t.dt_saida, t.cnes"),
)


def marca_atual(tabela: Table) -> int:
    snapshot = tabela.current_snapshot()
    if snapshot is None:
        return 0
    return int(snapshot.summary.get(PROPRIEDADE_MARCA) or 0)


def para_arrow(linhas: list[tuple], esquema: pa.Schema, ingerido_em: datetime) -> pa.Table:
    """Linhas da consulta (colunas da tabela + _commit_em) para o esquema Arrow do Iceberg."""
    n = len(linhas)
    colunas = list(zip(*linhas))
    valores = {nome: colunas[i] for i, nome in enumerate(esquema.names[: len(colunas) - 1])}
    valores["_commit_em"] = colunas[-1]
    valores["_op"] = ["c"] * n
    valores["_lsn"] = [None] * n
    valores["_ingerido_em"] = [ingerido_em] * n
    return pa.table({c.name: pa.array(valores[c.name], type=c.type) for c in esquema}, schema=esquema)


def gravar(tabela: Table, lotes: Iterable[pa.Table], marca: int) -> tuple[int, int]:
    """Grava os lotes numa única transação, com a marca d'água no snapshot.

    Devolve (linhas, arquivos). Sem linhas, não cria snapshot.
    """
    linhas = arquivos_antes = 0
    snapshot = tabela.current_snapshot()
    if snapshot is not None:
        arquivos_antes = int(snapshot.summary.get("total-data-files") or 0)
    with tabela.transaction() as transacao:
        for lote in lotes:
            if lote.num_rows:
                transacao.append(lote, snapshot_properties={PROPRIEDADE_MARCA: str(marca)})
                linhas += lote.num_rows
    if not linhas:
        return 0, 0
    tabela.refresh()
    arquivos = int(tabela.current_snapshot().summary.get("total-data-files") or 0) - arquivos_antes
    return linhas, arquivos


def _ler(conexao: psycopg.Connection, exportacao: Exportacao, de: int, ate: int,
         esquema: pa.Schema, ingerido_em: datetime) -> Iterator[pa.Table]:
    with conexao.cursor(name=f"lote_{exportacao.tabela}") as cursor:
        cursor.itersize = LINHAS_POR_LOTE
        cursor.execute(exportacao.consulta(), {"de": de, "ate": ate})
        while linhas := cursor.fetchmany(LINHAS_POR_LOTE):
            yield para_arrow(linhas, esquema, ingerido_em)


def exportar(config: ConfigLakehouse) -> list[dict]:
    catalogo = abrir_catalogo(config)
    resultados = []
    # REPEATABLE READ: a marca superior e as linhas lidas vêm do mesmo instante da origem.
    with psycopg.connect(config.database_url) as conexao:
        conexao.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        ate = conexao.execute("SELECT coalesce(max(id_carga), 0) FROM carga").fetchone()[0]
        for exportacao in EXPORTACOES:
            tabela = catalogo.load_table(f"lote.{exportacao.tabela}")
            de = marca_atual(tabela)
            inicio = time.monotonic()
            if de >= ate:
                linhas, arquivos = 0, 0
            else:
                ingerido_em = datetime.now(timezone.utc)
                lotes = _ler(conexao, exportacao, de, ate, tabela.schema().as_arrow(), ingerido_em)
                linhas, arquivos = gravar(tabela, lotes, ate)
            segundos = time.monotonic() - inicio
            resultados.append(
                {"tabela": exportacao.tabela, "marca_antes": de, "marca_depois": ate if linhas else de,
                 "linhas": linhas, "arquivos": arquivos, "segundos": round(segundos, 1)}
            )
            log.info("lote.%-23s marca %d -> %d: %9d linhas, %3d arquivos, %6.1f s",
                     exportacao.tabela, de, ate if linhas else de, linhas, arquivos, segundos)
    return resultados


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = ConfigLakehouse.do_ambiente()
    enviar_brutos(config)
    exportar(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
