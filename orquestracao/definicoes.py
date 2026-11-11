"""Grafo da E3: lote, marts, publicação com retry, freshness e backfill por ano."""

from dagster import (
    AssetExecutionContext,
    AssetSelection,
    DefaultScheduleStatus,
    Definitions,
    Failure,
    RetryPolicy,
    ScheduleDefinition,
    StaticPartitionsDefinition,
    asset,
    define_asset_job,
)

PARTICOES_ANO = StaticPartitionsDefinition([str(ano) for ano in range(2021, 2027)])


@asset(group_name="e3", description="O lakehouse de lote tem snapshot de internação.")
def lote_conferido() -> None:
    from transformacao.fontes import conferir_lote

    conferir_lote()


@asset(deps=[lote_conferido], group_name="e3", description="dbt build das camadas staging, intermediate e marts.")
def marts() -> None:
    from transformacao.pipeline import construir

    construir()


def _falhar_se_marcado() -> None:
    from transformacao.caminhos import caminho_duckdb

    flag = caminho_duckdb().parent / "falhar_publicacao"
    if flag.exists():
        flag.unlink()
        raise Failure(
            "Publicação indisponível: a dependência foi derrubada de propósito. "
            "O retry publica em seguida."
        )


@asset(
    deps=[marts],
    group_name="e3",
    retry_policy=RetryPolicy(max_retries=1, delay=1),
    description="Copia os marts para o schema consumo. A primeira tentativa falha se o arquivo de falha existir.",
)
def publicar_consumo() -> None:
    _falhar_se_marcado()
    from transformacao.publicar import publicar

    publicar()


@asset(deps=[publicar_consumo], group_name="e3", description="Confere o SLA de 24 horas da ocupação semanal.")
def freshness() -> dict:
    from transformacao.publicar import ler_freshness

    linha = ler_freshness()
    if not linha["dentro_do_sla"]:
        raise Failure(f"fora do SLA de {linha['sla_horas']} h: atraso {linha['atraso_horas']}")
    return linha


@asset(
    partitions_def=PARTICOES_ANO,
    group_name="backfill",
    description="Reconstrói um ano e publica só esse ano no consumo, sem apagar os outros.",
)
def consumo_ano(context: AssetExecutionContext) -> None:
    from transformacao.pipeline import construir
    from transformacao.publicar import publicar

    ano = int(context.partition_key)
    construir([ano], serie_completa=False)
    publicar([ano], substituir=False)


pipeline_analitico = define_asset_job("pipeline_analitico", selection=AssetSelection.groups("e3"))
republicar = define_asset_job("republicar", selection=AssetSelection.assets(publicar_consumo))
backfill_ano = define_asset_job("backfill_ano", selection=AssetSelection.assets(consumo_ano))

agenda_diaria = ScheduleDefinition(
    job=pipeline_analitico,
    cron_schedule="0 6 * * *",
    execution_timezone="America/Sao_Paulo",
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=[lote_conferido, marts, publicar_consumo, freshness, consumo_ano],
    jobs=[pipeline_analitico, republicar, backfill_ano],
    schedules=[agenda_diaria],
)
