"""Usuário de replicação e publicação lógica para o CDC (Debezium).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19
"""

import os

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TABELAS = ("carga", "estabelecimento", "estabelecimento_versao", "leito", "internacao")


def upgrade() -> None:
    senha = os.environ.get("DEBEZIUM_PASSWORD", "debezium").replace("'", "''")

    # Papel com o mínimo para o Debezium: replicação lógica e leitura das
    # tabelas publicadas (para o snapshot inicial). Não escreve em nada.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'debezium') THEN
                CREATE ROLE debezium WITH LOGIN REPLICATION PASSWORD '{senha}';
            END IF;
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO debezium")
    op.execute(f"GRANT SELECT ON {', '.join(TABELAS)} TO debezium")

    # Só as tabelas de dados e o controle de carga entram no fluxo de mudanças;
    # as tabelas de referência vão pelo lote.
    op.execute(f"CREATE PUBLICATION leitos_cdc FOR TABLE {', '.join(TABELAS)}")


def downgrade() -> None:
    op.execute("DROP PUBLICATION IF EXISTS leitos_cdc")
    op.execute(f"REVOKE SELECT ON {', '.join(TABELAS)} FROM debezium")
    op.execute("REVOKE USAGE ON SCHEMA public FROM debezium")
    op.execute("DROP ROLE IF EXISTS debezium")
