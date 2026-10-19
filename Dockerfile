FROM docker.io/library/python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Extensões do DuckDB na imagem: ler o Iceberg no S3 não depende de rede em tempo de execução.
RUN python -c "import duckdb; duckdb.sql('INSTALL iceberg; INSTALL httpfs')"

COPY alembic.ini .
COPY alembic ./alembic
COPY loader ./loader
COPY lakehouse ./lakehouse
COPY tests ./tests
COPY dados/amostra ./dados/amostra
COPY dados/referencia ./dados/referencia

CMD ["python", "-m", "loader"]
