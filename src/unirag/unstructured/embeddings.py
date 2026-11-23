# * Local CPU embeddings with fastembed (ONNX, no torch). The model name comes from settings.
from functools import lru_cache

from fastembed import TextEmbedding

from unirag.config.settings import get_settings


@lru_cache
def _model() -> TextEmbedding:
    # * First call downloads the model (~70 MB) to the fastembed cache.
    return TextEmbedding(get_settings().embedding_model)


def embed(texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in _model().embed(texts)]


def to_pgvector(vector: list[float]) -> str:
    # * pgvector reads the text form '[0.1,0.2,...]', so no extra adapter library is needed.
    return "[" + ",".join(map(str, vector)) + "]"
