FROM docker.io/library/python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY loader ./loader
COPY lakehouse ./lakehouse
COPY tests ./tests
COPY dados/amostra ./dados/amostra
COPY dados/referencia ./dados/referencia

CMD ["python", "-m", "loader"]
