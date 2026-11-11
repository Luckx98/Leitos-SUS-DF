FROM docker.io/library/python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Extensões do DuckDB na imagem: ler o Iceberg no S3 não depende de rede em tempo de execução.
RUN python -c "import duckdb; duckdb.sql('INSTALL iceberg; INSTALL httpfs; INSTALL delta; INSTALL postgres')"
# O modelo cabe na imagem para a amostra subir sem rede. 384 dimensões, multilíngue, ~0,22 GB.
ENV FASTEMBED_CACHE_PATH=/app/modelos
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='/app/modelos')"
ENV MODELO_OFFLINE=1

COPY alembic.ini .
COPY alembic ./alembic
COPY loader ./loader
COPY lakehouse ./lakehouse
COPY tests ./tests
COPY dados/amostra ./dados/amostra
COPY dados/referencia ./dados/referencia
COPY sql ./sql
COPY transformacao ./transformacao
COPY orquestracao ./orquestracao
COPY painel ./painel
COPY semantico ./semantico

CMD ["python", "-m", "loader"]
