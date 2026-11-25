# * One image for the API and the UI; Compose picks the command. Data loading stays on the host.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/app/.fastembed

COPY pyproject.toml ./
COPY src ./src
# ! Editable install: settings.py finds config/ and data/ relative to the source tree.
RUN pip install --no-cache-dir -e .

COPY config ./config
COPY data/seed/schema.sql ./data/seed/schema.sql
COPY ui ./ui

# * Bake the embedding model in, so the first question does not wait for a ~70 MB download.
RUN python -c "import yaml; from fastembed import TextEmbedding; \
TextEmbedding(yaml.safe_load(open('config/settings.yaml'))['embedding']['model'])"

EXPOSE 8000 8501
CMD ["uvicorn", "unirag.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
