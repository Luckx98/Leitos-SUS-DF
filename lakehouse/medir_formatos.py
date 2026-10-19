"""Medição de serialização e compressão sobre as internações carregadas (item E da E2).

    docker compose run --rm loader python -m lakehouse.medir_formatos > medicoes/e2/formatos_AAAA-MM-DD.txt

Só lê a origem. Mede:
1. Parquet sem compressão, snappy, zstd e gzip: tamanho, tempo de escrita e
   tempo de três consultas típicas no DuckDB (pontual, agregação de um ano,
   varredura completa).
2. Particionamento (zstd): sem partição, por ano e por mês de saída: número de
   arquivos, tamanho médio e tempo da consulta pontual (um hospital num mês).
3. Mensagens do CDC: JSON (formato do Debezium sem schema), Avro e os dois com
   compressão zstd por lote do produtor, sobre uma amostra de eventos.

Lê e grava em blocos para caber em pouca memória.
"""

from __future__ import annotations

import io
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb
import fastavro
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq

from lakehouse.esquemas import definicao
from lakehouse.lote import EXPORTACOES, para_arrow

CODECS = ("none", "snappy", "zstd", "gzip")
LINHAS_POR_BLOCO = 200_000
AMOSTRA_EVENTOS = 100_000

CONSULTAS = {
    "pontual (HRT, mar/2024)": """
        SELECT count(*), sum(valor_total) FROM {f}
        WHERE cnes = '0010499' AND dt_saida >= DATE '2024-03-01' AND dt_saida < DATE '2024-04-01'""",
    "agregação de 2024 (L5)": """
        SELECT cnes, especialidade, count(*), avg(dias_permanencia), avg(valor_total) FROM {f}
        WHERE dt_saida >= DATE '2024-01-01' AND dt_saida < DATE '2025-01-01' GROUP BY 1, 2""",
    "varredura completa (L6)": """
        SELECT year(dt_saida), left(municipio_estabelecimento, 2), count(*),
               count(*) FILTER (WHERE left(municipio_residencia, 2) <> left(municipio_estabelecimento, 2))
        FROM {f} GROUP BY 1, 2""",
}


def mediana_ms(con: duckdb.DuckDBPyConnection, sql: str, repeticoes: int = 3) -> float:
    con.execute(sql).fetchall()  # aquecimento
    tempos = []
    for _ in range(repeticoes):
        inicio = time.perf_counter()
        con.execute(sql).fetchall()
        tempos.append((time.perf_counter() - inicio) * 1000)
    return statistics.median(tempos)


def blocos(conexao: psycopg.Connection, esquema: pa.Schema):
    exportacao = next(e for e in EXPORTACOES if e.tabela == "internacao")
    agora = datetime.now(timezone.utc)
    with conexao.cursor(name="medicao") as cursor:
        cursor.itersize = LINHAS_POR_BLOCO
        cursor.execute(exportacao.consulta(), {"de": 0, "ate": 2**62})
        while linhas := cursor.fetchmany(LINHAS_POR_BLOCO):
            yield para_arrow(linhas, esquema, agora)


class Particionado:
    """Grava um arquivo por partição; os dados chegam ordenados por dt_saida."""

    def __init__(self, raiz: Path, esquema: pa.Schema, chave) -> None:
        self.raiz, self.esquema, self.chave = raiz, esquema, chave
        self.atual, self.escritor = None, None

    def escrever(self, tabela: pa.Table) -> None:
        valores = [self.chave(d) for d in tabela["dt_saida"].to_pylist()]
        inicio = 0
        for i in range(1, len(valores) + 1):
            if i == len(valores) or valores[i] != valores[inicio]:
                self._escrever_parte(valores[inicio], tabela.slice(inicio, i - inicio))
                inicio = i

    def _escrever_parte(self, valor: str, parte: pa.Table) -> None:
        if valor != self.atual:
            self.fechar()
            pasta = self.raiz / f"p={valor}"
            pasta.mkdir(parents=True)
            self.escritor = pq.ParquetWriter(pasta / "dados.parquet", self.esquema, compression="zstd")
            self.atual = valor
        self.escritor.write_table(parte)

    def fechar(self) -> None:
        if self.escritor:
            self.escritor.close()
            self.escritor = None


def evento_debezium(linha: dict, lsn: int) -> dict:
    """Envelope no formato observado no tópico (Debezium 3.6, JSON sem schema)."""
    def valor(v):
        if isinstance(v, datetime):
            return v.isoformat().replace("+00:00", "Z")
        if isinstance(v, date):
            return (v - date(1970, 1, 1)).days
        if isinstance(v, Decimal):
            return str(v)
        return v
    depois = {k: valor(v) for k, v in linha.items() if not k.startswith("_")}
    ts = 1792388644853
    return {
        "before": None, "after": depois,
        "source": {"version": "3.6.3.Final", "connector": "postgresql", "name": "leitos", "ts_ms": ts,
                   "snapshot": "false", "db": "leitos", "sequence": f'["{lsn - 64}","{lsn}"]', "ts_us": ts * 1000,
                   "ts_ns": ts * 1_000_000, "schema": "public", "table": "internacao", "txId": 912, "lsn": lsn,
                   "xmin": None},
        "transaction": None, "op": "c", "ts_ms": ts + 40, "ts_us": (ts + 40) * 1000, "ts_ns": (ts + 40) * 1_000_000,
    }


def esquema_avro(esquema: pa.Schema) -> dict:
    tipos = {pa.types.is_date32: "int", pa.types.is_int32: "int", pa.types.is_int64: "long",
             pa.types.is_boolean: "boolean", pa.types.is_decimal: "string", pa.types.is_timestamp: "string"}
    campos = []
    for c in esquema:
        if c.name.startswith("_"):
            continue
        tipo = next((t for teste, t in tipos.items() if teste(c.type)), "string")
        campos.append({"name": c.name, "type": ["null", tipo]})
    fonte = {"type": "record", "name": "Fonte", "fields": [
        {"name": n, "type": t} for n, t in [("version", "string"), ("connector", "string"), ("name", "string"),
                                             ("ts_ms", "long"), ("snapshot", "string"), ("db", "string"),
                                             ("sequence", "string"), ("ts_us", "long"), ("ts_ns", "long"),
                                             ("schema", "string"), ("table", "string"), ("txId", "long"),
                                             ("lsn", "long"), ("xmin", ["null", "long"])]]}
    return {"type": "record", "name": "Envelope", "fields": [
        {"name": "before", "type": ["null", {"type": "record", "name": "Valor", "fields": campos}]},
        {"name": "after", "type": ["null", "Valor"]},
        {"name": "source", "type": fonte},
        {"name": "transaction", "type": ["null", "string"]},
        {"name": "op", "type": "string"},
        {"name": "ts_ms", "type": "long"}, {"name": "ts_us", "type": "long"}, {"name": "ts_ns", "type": "long"},
    ]}


def tamanho_comprimido(mensagens: list[bytes], lote_bytes: int) -> int:
    """Kafka/Redpanda comprimem por lote do produtor: soma dos lotes comprimidos."""
    codec, total, lote, atual = pa.Codec("zstd"), 0, [], 0
    for m in mensagens:
        lote.append(m)
        atual += len(m)
        if atual >= lote_bytes:
            total += len(codec.compress(b"".join(lote)))
            lote, atual = [], 0
    if lote:
        total += len(codec.compress(b"".join(lote)))
    return total


def main() -> int:
    esquema = definicao("internacao").schema.as_arrow()
    pasta = Path(tempfile.mkdtemp(prefix="formatos_"))
    escritores = {c: pq.ParquetWriter(pasta / f"{c}.parquet", esquema, compression=c) for c in CODECS}
    tempo_escrita = dict.fromkeys(CODECS, 0.0)
    por_ano = Particionado(pasta / "por_ano", esquema, lambda d: f"{d:%Y}")
    por_mes = Particionado(pasta / "por_mes", esquema, lambda d: f"{d:%Y-%m}")
    eventos: list[dict] = []
    linhas = 0

    print(f"# Medição de formatos — {datetime.now():%Y-%m-%d %H:%M}")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conexao:
        for bloco in blocos(conexao, esquema):
            linhas += bloco.num_rows
            for codec, escritor in escritores.items():
                inicio = time.perf_counter()
                escritor.write_table(bloco)
                tempo_escrita[codec] += time.perf_counter() - inicio
            por_ano.escrever(bloco)
            por_mes.escrever(bloco)
            if len(eventos) < AMOSTRA_EVENTOS:
                eventos += bloco.slice(0, AMOSTRA_EVENTOS - len(eventos)).to_pylist()
    for escritor in escritores.values():
        escritor.close()
    por_ano.fechar()
    por_mes.fechar()
    print(f"# internações: {linhas}")

    con = duckdb.connect()
    print("\n## 1. Compressão do Parquet (arquivo único, dados ordenados por dt_saida)")
    print(f"{'codec':<8} {'tamanho MB':>10} {'B/linha':>8} {'escrita s':>9} " + " ".join(f"{n:>26}" for n in CONSULTAS))
    for codec in CODECS:
        arquivo = pasta / f"{codec}.parquet"
        tamanho = arquivo.stat().st_size
        tempos = [mediana_ms(con, sql.format(f=f"read_parquet('{arquivo}')")) for sql in CONSULTAS.values()]
        print(f"{codec:<8} {tamanho / 1e6:>10.1f} {tamanho / linhas:>8.1f} {tempo_escrita[codec]:>9.1f} "
              + " ".join(f"{t:>23.1f} ms" for t in tempos))

    print("\n## 2. Particionamento (zstd)")
    print(f"{'variante':<14} {'arquivos':>8} {'MB médio/arquivo':>16} {'pontual (1 hospital, 1 mês)':>28}")
    filtro = "cnes = '0010499' AND dt_saida >= DATE '2024-03-01' AND dt_saida < DATE '2024-04-01'"
    variantes = {
        "sem partição": (f"read_parquet('{pasta / 'zstd.parquet'}') WHERE {filtro}",
                         [pasta / "zstd.parquet"]),
        "por ano": (f"read_parquet('{pasta / 'por_ano'}/*/*.parquet', hive_partitioning = true) WHERE p = '2024' AND {filtro}",
                    list((pasta / "por_ano").rglob("*.parquet"))),
        "por mês": (f"read_parquet('{pasta / 'por_mes'}/*/*.parquet', hive_partitioning = true) WHERE p = '2024-03' AND {filtro}",
                    list((pasta / "por_mes").rglob("*.parquet"))),
    }
    for nome, (origem, arquivos) in variantes.items():
        media = statistics.mean(a.stat().st_size for a in arquivos) / 1e6
        tempo = mediana_ms(con, f"SELECT count(*), sum(valor_total) FROM {origem}")
        print(f"{nome:<14} {len(arquivos):>8} {media:>16.2f} {tempo:>25.1f} ms")

    print(f"\n## 3. Mensagens do CDC ({len(eventos)} eventos de internação)")
    envelopes = [evento_debezium(e, 47_732_376 + i * 64) for i, e in enumerate(eventos)]
    em_json = [json.dumps(e, separators=(",", ":")).encode() for e in envelopes]
    schema = fastavro.parse_schema(esquema_avro(esquema))
    em_avro = []
    for e in envelopes:
        buffer = io.BytesIO()
        fastavro.schemaless_writer(buffer, schema, e)
        em_avro.append(b"\0" + (1).to_bytes(4, "big") + buffer.getvalue())  # 5 bytes do schema registry
    print(f"{'formato':<26} {'B/evento':>9} {'3,67 mi de eventos (GB)':>24}")
    for nome, mensagens, lote in [("JSON", em_json, None), ("JSON + zstd (lote 16 KB)", em_json, 16_384),
                                  ("JSON + zstd (lote 1 MB)", em_json, 1_048_576), ("Avro", em_avro, None),
                                  ("Avro + zstd (lote 16 KB)", em_avro, 16_384), ("Avro + zstd (lote 1 MB)", em_avro, 1_048_576)]:
        total = tamanho_comprimido(mensagens, lote) if lote else sum(map(len, mensagens))
        por_evento = total / len(mensagens)
        print(f"{nome:<26} {por_evento:>9.1f} {por_evento * linhas / 1e9:>24.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
