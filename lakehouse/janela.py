"""Dado atrasado: reprocessa a janela de maturidade e classifica os meses de evento.

    python -m lakehouse.janela              # janela padrão de 3 meses
    python -m lakehouse.janela --meses 6

O SIH processa a AIH depois da alta: 35% chegam 1 a 3 competências depois do mês
em que o paciente saiu (medido na E1). Como lote.internacao é particionada pelo
mês de saída, cada competência nova acrescenta linhas em partições antigas.
O tratamento explícito tem duas partes:

1. Reprocessamento da janela: as partições dos últimos N meses de saída são
   sobrescritas, numa operação atômica do Iceberg, com o estado atual da origem
   (até a marca d'água do lote). É idempotente e corrige o que o incremento
   possa ter perdido (por exemplo, uma carga confirmada fora de ordem).
2. Maturidade: lote.maturidade marca cada mês de saída como "provisório"
   (menos de 3 competências observadas depois dele) ou "maduro". Análises de
   sazonalidade devem usar só meses maduros; os provisórios entram marcados.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone

import psycopg
import pyarrow as pa
import pyarrow.compute as pc
from pyiceberg.expressions import GreaterThanOrEqual

from lakehouse.catalogo import abrir_catalogo
from lakehouse.config import ConfigLakehouse
from lakehouse.esquemas import ESQUEMA_MATURIDADE, MESES_DE_MATURIDADE
from lakehouse.lote import EXPORTACOES, LINHAS_POR_LOTE, PROPRIEDADE_MARCA, marca_atual, para_arrow

log = logging.getLogger("lakehouse.janela")


def somar_meses(dia: date, meses: int) -> date:
    total = dia.year * 12 + dia.month - 1 + meses
    return date(total // 12, total % 12 + 1, 1)


def meses_entre(inicio: date, fim: date) -> int:
    return (fim.year - inicio.year) * 12 + fim.month - inicio.month


def status(meses_observados: int) -> str:
    return "maduro" if meses_observados >= MESES_DE_MATURIDADE else "provisório"


def contagem_por_mes(tabela, inicio: date) -> dict[date, int]:
    dados = tabela.scan(row_filter=GreaterThanOrEqual("dt_saida", inicio.isoformat()),
                        selected_fields=("dt_saida",)).to_arrow()
    if dados.num_rows == 0:
        return {}
    meses = pc.floor_temporal(dados["dt_saida"], unit="month")
    contagem = pa.table({"m": meses}).group_by("m").aggregate([("m", "count")])
    return dict(zip(contagem["m"].to_pylist(), contagem["m_count"].to_pylist()))


def reprocessar_janela(config: ConfigLakehouse, meses: int) -> None:
    catalogo = abrir_catalogo(config)
    tabela = catalogo.load_table("lote.internacao")
    marca = marca_atual(tabela)
    exportacao = next(e for e in EXPORTACOES if e.tabela == "internacao")
    with psycopg.connect(config.database_url) as conexao:
        conexao.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        ultima = conexao.execute(
            "SELECT max(competencia) FROM carga_vigente c WHERE fonte = 'SIH_RD' AND id_carga <= %s", (marca,)
        ).fetchone()[0]
        if ultima is None:
            log.info("nada exportado ainda; nada a reprocessar")
            return
        inicio = somar_meses(ultima, -meses)
        log.info("competência mais recente exportada: %s | janela: saídas a partir de %s | marca d'água: %d",
                 ultima, inicio, marca)
        antes = contagem_por_mes(tabela, inicio)

        esquema = tabela.schema().as_arrow()
        ingerido_em = datetime.now(timezone.utc)
        consulta = exportacao.consulta().replace(
            "WHERE t.id_carga > %(de)s AND t.id_carga <= %(ate)s",
            "WHERE t.id_carga <= %(ate)s AND t.dt_saida >= %(inicio)s",
        )

        # Sobrescrita atômica: numa única transação, apaga as partições da janela e
        # grava o estado atual da origem. A marca d'água é repetida para o lote não
        # reexportar. (pyiceberg 0.12 não grava fluxo em tabela particionada, por
        # isso delete + append em blocos, em vez de overwrite com RecordBatchReader.)
        propriedades = {PROPRIEDADE_MARCA: str(marca), "janela.inicio": inicio.isoformat()}
        with tabela.transaction() as transacao, conexao.cursor(name="janela") as cursor:
            transacao.delete(GreaterThanOrEqual("dt_saida", inicio.isoformat()), snapshot_properties=propriedades)
            cursor.itersize = LINHAS_POR_LOTE
            cursor.execute(consulta, {"ate": marca, "inicio": inicio})
            while linhas := cursor.fetchmany(LINHAS_POR_LOTE):
                transacao.append(para_arrow(linhas, esquema, ingerido_em), snapshot_properties=propriedades)
    tabela.refresh()
    depois = contagem_por_mes(tabela, inicio)
    for mes in sorted(set(antes) | set(depois)):
        log.info("  saídas de %s: %7d linhas antes -> %7d depois", mes.strftime("%m/%Y"), antes.get(mes, 0), depois.get(mes, 0))
    calcular_maturidade(catalogo, tabela)


def calcular_maturidade(catalogo, tabela) -> None:
    dados = tabela.scan(selected_fields=("dt_saida", "competencia", "municipio_estabelecimento")).to_arrow()
    uf = pc.utf8_slice_codeunits(dados["municipio_estabelecimento"], 0, 2)
    t = pa.table({"uf": uf, "mes": pc.floor_temporal(dados["dt_saida"], unit="month"), "competencia": dados["competencia"]})
    ref = t.group_by("uf").aggregate([("competencia", "max")])
    referencia = dict(zip(ref["uf"].to_pylist(), ref["competencia_max"].to_pylist()))
    por_mes = t.group_by(["uf", "mes"]).aggregate([("mes", "count")]).to_pylist()
    agora = datetime.now(timezone.utc)
    nomes_uf = {"53": "DF", "52": "GO"}
    linhas = []
    for r in sorted(por_mes, key=lambda r: (r["uf"], r["mes"])):
        observados = meses_entre(r["mes"], referencia[r["uf"]])
        linhas.append({"uf": nomes_uf.get(r["uf"], r["uf"]), "mes_saida": r["mes"], "internacoes": r["mes_count"],
                       "competencia_referencia": referencia[r["uf"]], "meses_observados": observados,
                       "status": status(observados), "calculado_em": agora})
    maturidade = catalogo.load_table("lote.maturidade")
    maturidade.overwrite(pa.Table.from_pylist(linhas, schema=ESQUEMA_MATURIDADE.as_arrow()))
    provisorios = [f"{l['uf']} {l['mes_saida']:%m/%Y}" for l in linhas if l["status"] == "provisório"]
    log.info("lote.maturidade: %d meses, %d provisórios (%s)", len(linhas), len(provisorios),
             ", ".join(provisorios[-8:]))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("--meses", type=int, default=MESES_DE_MATURIDADE)
    reprocessar_janela(ConfigLakehouse.do_ambiente(), argumentos.parse_args().meses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
