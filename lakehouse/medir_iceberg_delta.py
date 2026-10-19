"""Iceberg x Delta Lake com os mesmos dados (ADR 0002).

    docker compose run --rm --no-deps loader python -m lakehouse.medir_iceberg_delta

Grava as internações com saída em 2024 nos dois formatos (Parquet zstd, disco
local, para isolar o formato do armazenamento) e mede:
1. escrita: tempo, tamanho e arquivos;
2. leitura pelo DuckDB (iceberg_scan x delta_scan), na agregação de 2024 (L5);
3. evolução de esquema: acrescentar uma coluna e ler linhas antigas e novas;
4. evolução de partição: de mês para ano, a mudança que esta entrega precisou
   fazer (medicoes/e2/formatos_2026-10-19.txt).
"""

from __future__ import annotations

import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import psycopg
import pyarrow as pa
import pyarrow.compute as pc
from deltalake import DeltaTable, write_deltalake
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.transforms import MonthTransform, YearTransform
from pyiceberg.types import StringType

from lakehouse.esquemas import definicao
from lakehouse.lote import EXPORTACOES, para_arrow

LINHAS_POR_BLOCO = 200_000
CONSULTA = """SELECT cnes, especialidade, count(*), avg(dias_permanencia), avg(valor_total)
              FROM {f} GROUP BY 1, 2"""


def mediana_ms(con, sql: str) -> float:
    con.execute(sql).fetchall()
    tempos = []
    for _ in range(3):
        inicio = time.perf_counter()
        con.execute(sql).fetchall()
        tempos.append((time.perf_counter() - inicio) * 1000)
    return statistics.median(tempos)


def tamanho(pasta: Path) -> tuple[float, int]:
    arquivos = list(pasta.rglob("*.parquet"))
    return sum(a.stat().st_size for a in arquivos) / 1e6, len(arquivos)


def blocos_2024(esquema: pa.Schema):
    exportacao = next(e for e in EXPORTACOES if e.tabela == "internacao")
    consulta = exportacao.consulta().replace(
        "WHERE t.id_carga > %(de)s AND t.id_carga <= %(ate)s",
        "WHERE t.dt_saida >= DATE '2024-01-01' AND t.dt_saida < DATE '2025-01-01'")
    agora = datetime.now(timezone.utc)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conexao, conexao.cursor(name="exp") as cursor:
        cursor.itersize = LINHAS_POR_BLOCO
        cursor.execute(consulta)
        while linhas := cursor.fetchmany(LINHAS_POR_BLOCO):
            yield para_arrow(linhas, esquema, agora)


def main() -> int:
    raiz = Path(tempfile.mkdtemp(prefix="iceberg_delta_"))
    d = definicao("internacao")
    esquema = d.schema.as_arrow()
    mensal = PartitionSpec(PartitionField(source_id=d.schema.find_field("dt_saida").field_id, field_id=1000,
                                          transform=MonthTransform(), name="dt_saida_mes"))
    catalogo = SqlCatalog("m", uri=f"sqlite:///{raiz}/catalogo.db", warehouse=f"file://{raiz}/iceberg")
    catalogo.create_namespace("m")
    iceberg = catalogo.create_table("m.internacao", schema=d.schema, partition_spec=mensal,
                                    properties={"write.parquet.compression-codec": "zstd"})
    caminho_delta = str(raiz / "delta")
    tempo = {"iceberg": 0.0, "delta": 0.0}
    linhas = 0

    # Delta não tem partição oculta: precisa de uma coluna física com o mês.
    for bloco in blocos_2024(esquema):
        linhas += bloco.num_rows
        inicio = time.perf_counter()
        iceberg.append(bloco)
        tempo["iceberg"] += time.perf_counter() - inicio
        mes = pc.strftime(pc.cast(bloco["dt_saida"], pa.timestamp("s")), format="%Y-%m")
        inicio = time.perf_counter()
        write_deltalake(caminho_delta, bloco.append_column("dt_saida_mes", mes), mode="append",
                        partition_by=["dt_saida_mes"])
        tempo["delta"] += time.perf_counter() - inicio

    con = duckdb.connect()
    con.execute("LOAD iceberg; LOAD delta")
    leitura = {"iceberg": f"iceberg_scan('{iceberg.metadata_location}')", "delta": f"delta_scan('{caminho_delta}')"}

    print(f"# Iceberg x Delta — {datetime.now():%Y-%m-%d %H:%M} — {linhas} internações com saída em 2024")
    print("\n## 1 e 2. Escrita (particionado por mês) e leitura pelo DuckDB (agregação L5)")
    print(f"{'formato':<8} {'escrita s':>9} {'MB':>7} {'arquivos':>8} {'leitura ms':>10}")
    for nome, pasta in (("iceberg", raiz / "iceberg"), ("delta", raiz / "delta")):
        mb, n = tamanho(pasta)
        print(f"{nome:<8} {tempo[nome]:>9.1f} {mb:>7.1f} {n:>8} {mediana_ms(con, CONSULTA.format(f=leitura[nome])):>10.1f}")

    print("\n## 3. Evolução de esquema: nova coluna 'faixa_etaria'")
    novas = next(blocos_2024(esquema)).slice(0, 1000)
    faixa = pa.array(["60+"] * novas.num_rows)
    inicio = time.perf_counter()
    with iceberg.update_schema() as atualizacao:
        atualizacao.add_column("faixa_etaria", StringType())
    iceberg.append(novas.append_column("faixa_etaria", faixa).cast(iceberg.schema().as_arrow()))
    t_iceberg = time.perf_counter() - inicio
    inicio = time.perf_counter()
    mes = pc.strftime(pc.cast(novas["dt_saida"], pa.timestamp("s")), format="%Y-%m")
    write_deltalake(caminho_delta, novas.append_column("dt_saida_mes", mes).append_column("faixa_etaria", faixa),
                    mode="append", partition_by=["dt_saida_mes"], schema_mode="merge")
    t_delta = time.perf_counter() - inicio
    for nome, segundos in (("iceberg", t_iceberg), ("delta", t_delta)):
        if nome == "iceberg":
            origem = f"iceberg_scan('{catalogo.load_table('m.internacao').metadata_location}')"
        else:
            origem = leitura["delta"]
        nulos, preenchidas = con.execute(
            f"SELECT count(*) FILTER (WHERE faixa_etaria IS NULL), count(faixa_etaria) FROM {origem}").fetchone()
        print(f"{nome:<8} {segundos:>6.2f} s | linhas antigas com a coluna nula: {nulos} | novas preenchidas: {preenchidas}"
              " | arquivos antigos reescritos: 0")

    print("\n## 4. Evolução de partição: de mês para ano")
    iceberg = catalogo.load_table("m.internacao")
    mb_antes, n_antes = tamanho(raiz / "iceberg")
    inicio = time.perf_counter()
    with iceberg.update_spec() as especificacao:
        especificacao.remove_field("dt_saida_mes")
        especificacao.add_field("dt_saida", YearTransform(), "dt_saida_ano")
    t_iceberg = time.perf_counter() - inicio
    mb_depois, n_depois = tamanho(raiz / "iceberg")
    print(f"iceberg  {t_iceberg:>6.2f} s | só metadados: arquivos {n_antes} -> {n_depois} (os antigos seguem válidos;"
          " os novos já saem por ano)")
    dados = DeltaTable(caminho_delta).to_pyarrow_table()
    ano = pc.strftime(pc.cast(dados["dt_saida"], pa.timestamp("s")), format="%Y")
    inicio = time.perf_counter()
    write_deltalake(caminho_delta, dados.drop(["dt_saida_mes"]).append_column("dt_saida_ano", ano), mode="overwrite",
                    partition_by=["dt_saida_ano"], schema_mode="overwrite")
    t_delta = time.perf_counter() - inicio
    print(f"delta    {t_delta:>6.2f} s | reescreve a tabela inteira ({dados.num_rows} linhas) e muda a coluna"
          " física de partição: quem filtrava por dt_saida_mes precisa mudar a consulta")
    return 0


if __name__ == "__main__":
    sys.exit(main())
