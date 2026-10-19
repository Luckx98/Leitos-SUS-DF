"""Caminho de CDC: consome os eventos do Debezium no Redpanda e grava em cdc.*.

    python -m lakehouse.cdc

Semântica de entrega:
- O Debezium entrega pelo menos uma vez: depois de uma queda, ele pode
  reenviar eventos já publicados (com offsets novos no tópico).
- O consumidor grava o offset lido de cada tópico como propriedade do snapshot
  do Iceberg, no mesmo commit dos dados. Ao reiniciar, retoma desse offset, e
  não do offset confirmado no Redpanda: reprocessar mensagens já gravadas
  não acontece.
- Para os reenvios do Debezium, cada micro-lote é deduplicado pela chave
  primária da origem, dentro do lote e contra as linhas já gravadas nas
  partições que o lote toca.
Resultado: efetivamente exatamente uma vez no Iceberg, por tabela.

Variáveis: KAFKA_BOOTSTRAP, CDC_LINHAS_POR_LOTE, CDC_SEGUNDOS_POR_LOTE,
CDC_SAIR_OCIOSO_S (encerra depois de N segundos sem mensagens; 0 = nunca),
CDC_DEDUP (1 = deduplica pela chave; 0 = desliga, só para a demonstração),
CDC_DO_INICIO (1 = relê os tópicos desde o início, ignorando o offset do Iceberg).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pyarrow as pa
from confluent_kafka import OFFSET_BEGINNING, Consumer, TopicPartition
from pyiceberg.expressions import And, GreaterThanOrEqual, LessThanOrEqual
from pyiceberg.table import Table

from lakehouse.catalogo import abrir_catalogo
from lakehouse.config import ConfigLakehouse
from lakehouse.esquemas import PARTICAO_MENSAL, TABELAS

log = logging.getLogger("lakehouse.cdc")

PREFIXO_TOPICO = "leitos.public."
PROPRIEDADE_OFFSET = "cdc.offset"  # próximo offset a ler, por tópico (uma partição por tópico)

CHAVES = {
    "carga": ("id_carga",),
    "estabelecimento": ("cnes",),
    "estabelecimento_versao": ("cnes", "competencia_inicio"),
    "leito": ("competencia", "cnes", "cod_leito", "id_carga"),
    "internacao": ("competencia", "n_aih", "dt_saida", "id_carga"),
}

EPOCA = date(1970, 1, 1)


def converter(valor, tipo: pa.DataType):
    """Valor do JSON do Debezium para o tipo Arrow da tabela Iceberg."""
    if valor is None:
        return None
    if pa.types.is_date32(tipo):
        return EPOCA + timedelta(days=valor)  # DATE chega como dias desde 1970
    if pa.types.is_timestamp(tipo):
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if pa.types.is_decimal(tipo):
        return Decimal(valor)  # NUMERIC chega como texto (decimal.handling.mode=string)
    return valor


def evento_para_linha(evento: dict, esquema: pa.Schema, ingerido_em: datetime) -> dict | None:
    """Um evento do Debezium vira uma linha; None para eventos sem linha nova."""
    depois = evento.get("after")
    if depois is None:  # delete ou tombstone: não ocorre numa origem insert-only
        return None
    linha = {c.name: converter(depois.get(c.name), c.type) for c in esquema if not c.name.startswith("_")}
    fonte = evento.get("source", {})
    linha["_op"] = evento.get("op")
    linha["_lsn"] = fonte.get("lsn")
    linha["_commit_em"] = datetime.fromtimestamp(fonte["ts_ms"] / 1000, timezone.utc) if fonte.get("ts_ms") else None
    linha["_ingerido_em"] = ingerido_em
    return linha


def chave(linha: dict, tabela: str) -> tuple:
    return tuple(linha[c] for c in CHAVES[tabela])


def deduplicar_no_lote(linhas: list[dict], tabela: str) -> list[dict]:
    vistas, unicas = set(), []
    for linha in linhas:
        k = chave(linha, tabela)
        if k not in vistas:
            vistas.add(k)
            unicas.append(linha)
    return unicas


def chaves_ja_gravadas(iceberg: Table, tabela: str, linhas: list[dict]) -> set[tuple]:
    """Chaves já presentes no Iceberg, lidas só das partições que o lote toca."""
    if iceberg.current_snapshot() is None:
        return set()
    filtro = None
    coluna = PARTICAO_MENSAL.get(tabela)
    if coluna:
        datas = [l[coluna] for l in linhas if l[coluna] is not None]
        if datas:
            filtro = And(GreaterThanOrEqual(coluna, min(datas).isoformat()),
                         LessThanOrEqual(coluna, max(datas).isoformat()))
    varredura = iceberg.scan(selected_fields=CHAVES[tabela], **({"row_filter": filtro} if filtro else {}))
    existentes = varredura.to_arrow()
    return set(zip(*(existentes[c].to_pylist() for c in CHAVES[tabela])))


def offset_gravado(iceberg: Table, topico: str) -> int | None:
    snapshot = iceberg.current_snapshot()
    if snapshot is None:
        return None
    valor = snapshot.summary.get(f"{PROPRIEDADE_OFFSET}.{topico}")
    return int(valor) if valor is not None else None


@dataclass
class Estatistica:
    eventos: int = 0
    gravadas: int = 0
    duplicadas: int = 0
    lotes: int = 0


class ConsumidorCdc:
    def __init__(self, config: ConfigLakehouse, dedup: bool = True, do_inicio: bool = False) -> None:
        self.catalogo = abrir_catalogo(config)
        self.dedup = dedup
        self.do_inicio = do_inicio  # ignora o offset do Iceberg e relê tudo (demonstração)
        self.tabelas = {t: self.catalogo.load_table(f"cdc.{t}") for t in TABELAS}
        self.esquemas = {t: tab.schema().as_arrow() for t, tab in self.tabelas.items()}
        self.estatistica = {t: Estatistica() for t in TABELAS}
        self.kafka = Consumer({
            "bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP", "redpanda:9092"),
            "group.id": "lakehouse-cdc",
            "enable.auto.commit": False,  # a posição oficial é a do Iceberg
            "auto.offset.reset": "earliest",
        })
        self._atribuir()

    def _atribuir(self) -> None:
        """Retoma cada tópico do offset gravado no Iceberg, não do Redpanda."""
        particoes = []
        for tabela, iceberg in self.tabelas.items():
            topico = PREFIXO_TOPICO + tabela
            offset = None if self.do_inicio else offset_gravado(iceberg, topico)
            particoes.append(TopicPartition(topico, 0, OFFSET_BEGINNING if offset is None else offset))
            log.info("%s: retomando do offset %s", topico, "inicial" if offset is None else offset)
        self.kafka.assign(particoes)

    def _gravar(self, tabela: str, eventos: list, ingerido_em: datetime) -> None:
        topico = PREFIXO_TOPICO + tabela
        proximo_offset = eventos[-1].offset() + 1
        linhas = [l for m in eventos if (l := evento_para_linha(json.loads(m.value()), self.esquemas[tabela], ingerido_em))]
        est = self.estatistica[tabela]
        est.eventos += len(eventos)
        if self.dedup:
            unicas = deduplicar_no_lote(linhas, tabela)
            existentes = chaves_ja_gravadas(self.tabelas[tabela], tabela, unicas)
            novas = [l for l in unicas if chave(l, tabela) not in existentes]
            est.duplicadas += len(linhas) - len(novas)
        else:
            novas = linhas
        if not novas:
            # Lote só com duplicatas: o offset avança no próximo commit desta tabela.
            # Se o consumidor parar antes, relê e descarta de novo; não duplica.
            return
        propriedades = {f"{PROPRIEDADE_OFFSET}.{topico}": str(proximo_offset)}
        self.tabelas[tabela].append(pa.Table.from_pylist(novas, schema=self.esquemas[tabela]),
                                    snapshot_properties=propriedades)
        est.gravadas += len(novas)
        est.lotes += 1
        self.kafka.commit(offsets=[TopicPartition(topico, 0, proximo_offset)], asynchronous=True)  # só para monitorar atraso

    def executar(self, linhas_por_lote: int, segundos_por_lote: float, sair_ocioso: float) -> None:
        ultimo_evento = time.monotonic()
        while True:
            inicio, lote = time.monotonic(), []
            while len(lote) < linhas_por_lote and time.monotonic() - inicio < segundos_por_lote:
                mensagens = self.kafka.consume(num_messages=min(10_000, linhas_por_lote - len(lote)), timeout=1.0)
                lote += [m for m in mensagens if m.error() is None and m.value() is not None]
            if lote:
                ultimo_evento = time.monotonic()
                ingerido_em = datetime.now(timezone.utc)
                por_tabela: dict[str, list] = {}
                for m in lote:
                    por_tabela.setdefault(m.topic().removeprefix(PREFIXO_TOPICO), []).append(m)
                for tabela, eventos in por_tabela.items():
                    self._gravar(tabela, eventos, ingerido_em)
                log.info("lote: %d eventos (%s)", len(lote),
                         ", ".join(f"{t} {len(e)}" for t, e in por_tabela.items()))
            elif sair_ocioso and time.monotonic() - ultimo_evento > sair_ocioso:
                break
        for tabela, est in self.estatistica.items():
            log.info("cdc.%-23s %8d eventos, %8d gravadas, %6d duplicadas descartadas, %4d commits",
                     tabela, est.eventos, est.gravadas, est.duplicadas, est.lotes)
        self.kafka.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    consumidor = ConsumidorCdc(ConfigLakehouse.do_ambiente(), dedup=os.environ.get("CDC_DEDUP", "1") == "1",
                               do_inicio=os.environ.get("CDC_DO_INICIO", "0") == "1")
    consumidor.executar(
        linhas_por_lote=int(os.environ.get("CDC_LINHAS_POR_LOTE", "50000")),
        segundos_por_lote=float(os.environ.get("CDC_SEGUNDOS_POR_LOTE", "5")),
        sair_ocioso=float(os.environ.get("CDC_SAIR_OCIOSO_S", "0")),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
