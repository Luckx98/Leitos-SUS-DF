"""Extensão vetorial e tabela do experimento semântico.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-11

O número da ocupação continua em `consumo`. Esta tabela guarda a frase que o
warehouse já sabe dizer e o vetor dessa frase. A busca por cosseno não
recalcula paciente-dia nem substitui o limiar de 85%.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS semantico")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS semantico.trecho (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            cod_regiao_saude text NOT NULL,
            nome_regiao text NOT NULL,
            semana date NOT NULL,
            ano integer NOT NULL,
            ocupacao double precision NOT NULL,
            acima_de_85 boolean NOT NULL,
            capitulo_cid text,
            capitulo_nome text,
            texto text NOT NULL,
            embedding vector(384) NOT NULL,
            UNIQUE (cod_regiao_saude, semana)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS semantico.trecho")
    op.execute("DROP SCHEMA IF EXISTS semantico")
    op.execute("DROP EXTENSION IF EXISTS vector")
