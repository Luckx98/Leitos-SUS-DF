"""Compactação: junta os arquivos pequenos de cada partição num arquivo só.

    python -m lakehouse.compactar               # lote.* e cdc.*
    python -m lakehouse.compactar --namespace lote

Cada competência nova acrescenta arquivos pequenos à partição do ano corrente, e
o CDC, com micro-lotes de poucos segundos, acrescenta muitos mais. Arquivos
pequenos deixam a leitura lenta (um pedido ao S3 e um rodapé Parquet por arquivo).

Para cada partição com mais de um arquivo: lê os dados, e numa única transação
apaga a partição e regrava tudo num arquivo. As propriedades do snapshot (marca
d'água do lote, offsets do CDC) são repetidas, para que a compactação não mude
de onde o lote e o consumidor continuam.

Não deve rodar em paralelo com um escritor da mesma tabela: se outro commit
entrar no meio, o Iceberg recusa este (concorrência otimista) e a tabela é pulada.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from pyiceberg.exceptions import CommitFailedException
from pyiceberg.expressions import AlwaysTrue, And, GreaterThanOrEqual, LessThan
from pyiceberg.table import Table

from lakehouse.catalogo import abrir_catalogo
from lakehouse.config import ConfigLakehouse
from lakehouse.esquemas import NAMESPACES, PARTICAO_ANUAL, TABELAS

log = logging.getLogger("lakehouse.compactar")

PREFIXOS_PRESERVADOS = ("lote.", "cdc.offset.", "janela.")


def propriedades_preservadas(tabela: Table) -> dict[str, str]:
    snapshot = tabela.current_snapshot()
    if snapshot is None:
        return {}
    resumo = snapshot.summary.additional_properties
    return {k: v for k, v in resumo.items() if k.startswith(PREFIXOS_PRESERVADOS)}


def grupos_de_arquivos(tabela: Table, coluna: str | None) -> dict[int | None, list[int]]:
    """Partição (ano desde 1970, ou None sem partição) -> tamanhos dos arquivos."""
    arquivos = tabela.inspect.files().to_pylist()
    grupos: dict[int | None, list[int]] = {}
    for a in arquivos:
        chave = a["partition"].get(f"{coluna}_ano") if coluna else None
        grupos.setdefault(chave, []).append(a["file_size_in_bytes"])
    return grupos


def filtro_da_particao(coluna: str | None, ano_desde_1970: int | None):
    if coluna is None:
        return AlwaysTrue()
    ano = 1970 + ano_desde_1970
    return And(GreaterThanOrEqual(coluna, date(ano, 1, 1).isoformat()), LessThan(coluna, date(ano + 1, 1, 1).isoformat()))


def compactar_tabela(tabela: Table, nome: str) -> tuple[int, int]:
    """Devolve (arquivos antes, arquivos depois)."""
    coluna = PARTICAO_ANUAL.get(nome)
    grupos = grupos_de_arquivos(tabela, coluna)
    antes = sum(len(t) for t in grupos.values())
    for particao, tamanhos in sorted(grupos.items(), key=lambda g: (g[0] is None, g[0])):
        if len(tamanhos) <= 1:
            continue
        filtro = filtro_da_particao(coluna, particao)
        dados = tabela.scan(row_filter=filtro).to_arrow()
        propriedades = propriedades_preservadas(tabela)
        with tabela.transaction() as transacao:
            transacao.delete(filtro, snapshot_properties=propriedades)
            transacao.append(dados, snapshot_properties=propriedades)
        rotulo = "sem partição" if particao is None else str(1970 + particao)
        log.info("  %-24s %-12s %3d arquivos (%6.2f MB) -> 1 arquivo, %d linhas",
                 nome, rotulo, len(tamanhos), sum(tamanhos) / 1e6, dados.num_rows)
        tabela.refresh()
    depois = sum(len(t) for t in grupos_de_arquivos(tabela, coluna).values())
    return antes, depois


def compactar(config: ConfigLakehouse, namespaces: tuple[str, ...] = NAMESPACES) -> None:
    catalogo = abrir_catalogo(config)
    for namespace in namespaces:
        for nome in TABELAS:
            tabela = catalogo.load_table(f"{namespace}.{nome}")
            if tabela.current_snapshot() is None:
                continue
            try:
                antes, depois = compactar_tabela(tabela, nome)
            except CommitFailedException as erro:
                log.warning("%s.%s pulada: outro escritor confirmou no meio (%s)", namespace, nome, erro)
                continue
            log.info("%s.%-23s arquivos: %4d -> %4d", namespace, nome, antes, depois)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("--namespace", choices=NAMESPACES)
    namespace = argumentos.parse_args().namespace
    compactar(ConfigLakehouse.do_ambiente(), (namespace,) if namespace else NAMESPACES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
