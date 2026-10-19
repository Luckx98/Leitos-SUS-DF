"""Esquemas e particionamento das tabelas Iceberg.

Cada tabela da origem existe em dois namespaces, um por caminho de ingestão:
`lote` (exportação incremental) e `cdc` (Debezium). Os dois têm o mesmo esquema,
para que possam ser reconciliados e comparados no ADR 0002.

As colunas de controle (prefixo `_`) registram de onde a linha veio e quando:
- `_op`: operação na origem (c = insert, r = leitura do snapshot);
- `_lsn`: posição no WAL (só no CDC);
- `_commit_em`: quando a linha foi gravada na origem;
- `_ingerido_em`: quando a linha foi gravada no Iceberg.
A diferença entre as duas últimas é a latência do caminho.

Todos os campos são opcionais no Iceberg: a integridade é garantida na origem
(PK, FK, CHECK) e conferida por reconciliação, não reimposta aqui.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import MonthTransform
from pyiceberg.types import (
    BooleanType,
    DateType,
    DecimalType,
    IcebergType,
    IntegerType,
    LongType,
    NestedField,
    StringType,
    TimestamptzType,
)

NAMESPACES = ("lote", "cdc")

CONTROLE: list[tuple[str, IcebergType]] = [
    ("_op", StringType()),
    ("_lsn", LongType()),
    ("_commit_em", TimestamptzType()),
    ("_ingerido_em", TimestamptzType()),
]

COLUNAS: dict[str, list[tuple[str, IcebergType]]] = {
    "carga": [
        ("id_carga", LongType()),
        ("fonte", StringType()),
        ("arquivo", StringType()),
        ("uf", StringType()),
        ("competencia", DateType()),
        ("sha256", StringType()),
        ("tamanho_bytes", LongType()),
        ("linhas_lidas", IntegerType()),
        ("linhas_inseridas", IntegerType()),
        ("linhas_rejeitadas", IntegerType()),
        ("iniciada_em", TimestamptzType()),
        ("concluida_em", TimestamptzType()),
        ("status", StringType()),
        ("mensagem", StringType()),
    ],
    "estabelecimento": [
        ("cnes", StringType()),
        ("primeira_carga", LongType()),
        ("dt_ingestao", TimestamptzType()),
    ],
    "estabelecimento_versao": [
        ("cnes", StringType()),
        ("competencia_inicio", DateType()),
        ("cod_municipio", StringType()),
        ("tipo_unidade", StringType()),
        ("tipo_gestao", StringType()),
        ("natureza_juridica", StringType()),
        ("cnpj_mantenedora", StringType()),
        ("vinculo_sus", BooleanType()),
        ("atende_internacao", BooleanType()),
        ("atende_urgencia", BooleanType()),
        ("id_carga", LongType()),
        ("dt_ingestao", TimestamptzType()),
    ],
    "leito": [
        ("competencia", DateType()),
        ("cnes", StringType()),
        ("cod_leito", StringType()),
        ("tipo_leito", StringType()),
        ("qt_existente", IntegerType()),
        ("qt_contratado", IntegerType()),
        ("qt_sus", IntegerType()),
        ("qt_nao_sus", IntegerType()),
        ("id_carga", LongType()),
        ("dt_ingestao", TimestamptzType()),
    ],
    "internacao": [
        ("competencia", DateType()),
        ("n_aih", StringType()),
        ("dt_saida", DateType()),
        ("id_carga", LongType()),
        ("ident", StringType()),
        ("cnes", StringType()),
        ("dt_internacao", DateType()),
        ("dias_permanencia", IntegerType()),
        ("qt_diarias", IntegerType()),
        ("especialidade", StringType()),
        ("carater_internacao", StringType()),
        ("complexidade", StringType()),
        ("cid_principal", StringType()),
        ("cid_secundario", StringType()),
        ("procedimento", StringType()),
        ("dias_uti", IntegerType()),
        ("marca_uti", StringType()),
        ("valor_total", DecimalType(12, 2)),
        ("valor_uti", DecimalType(12, 2)),
        ("idade", IntegerType()),
        ("cod_idade", StringType()),
        ("sexo", StringType()),
        ("raca_cor", StringType()),
        ("municipio_residencia", StringType()),
        ("municipio_estabelecimento", StringType()),
        ("obito", BooleanType()),
        ("tipo_gestao", StringType()),
        ("dt_ingestao", TimestamptzType()),
    ],
}

# Particionamento pelo mês do evento: a AIH que chega atrasada cai na partição
# do mês em que o paciente saiu, e o reprocessamento da janela de maturidade
# (3 meses) reescreve só essas partições. Tabelas pequenas não são particionadas
# para não gerar arquivos minúsculos.
PARTICAO_MENSAL: dict[str, str] = {
    "internacao": "dt_saida",
    "leito": "competencia",
}


@dataclass(frozen=True)
class DefinicaoTabela:
    nome: str
    schema: Schema
    particao: PartitionSpec


def definicao(nome: str) -> DefinicaoTabela:
    campos = [
        NestedField(field_id=i, name=coluna, field_type=tipo, required=False)
        for i, (coluna, tipo) in enumerate(COLUNAS[nome] + CONTROLE, start=1)
    ]
    schema = Schema(*campos)
    particao = PartitionSpec()
    if nome in PARTICAO_MENSAL:
        coluna = PARTICAO_MENSAL[nome]
        particao = PartitionSpec(
            PartitionField(
                source_id=schema.find_field(coluna).field_id,
                field_id=1000,
                transform=MonthTransform(),
                name=f"{coluna}_mes",
            )
        )
    return DefinicaoTabela(nome, schema, particao)


TABELAS = tuple(COLUNAS)


# Maturidade dos meses de evento (dado atrasado). Não é espelho da origem: é
# calculada no lakehouse a cada reprocessamento da janela (lakehouse/janela.py).
MESES_DE_MATURIDADE = 3  # 99,5% das AIHs chegam em até 3 competências (medido na E1)

ESQUEMA_MATURIDADE = Schema(
    NestedField(1, "uf", StringType(), required=False),
    NestedField(2, "mes_saida", DateType(), required=False),
    NestedField(3, "internacoes", LongType(), required=False),
    NestedField(4, "competencia_referencia", DateType(), required=False),
    NestedField(5, "meses_observados", IntegerType(), required=False),
    NestedField(6, "status", StringType(), required=False),
    NestedField(7, "calculado_em", TimestamptzType(), required=False),
)
