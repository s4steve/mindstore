import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../embedder"))

from embedder.local import SentenceTransformerEmbedder


def test_embed_returns_384_floats():
    embedder = SentenceTransformerEmbedder()
    result = embedder.embed("Hello, world!")
    assert isinstance(result, list)
    assert len(result) == 384
    assert all(isinstance(v, float) for v in result)


def test_embed_batch_returns_correct_shape():
    embedder = SentenceTransformerEmbedder()
    texts = ["First sentence", "Second sentence", "Third sentence"]
    result = embedder.embed_batch(texts)
    assert isinstance(result, list)
    assert len(result) == 3
    for embedding in result:
        assert len(embedding) == 384


def test_dimensions_property():
    embedder = SentenceTransformerEmbedder()
    assert embedder.dimensions == 384


def test_different_texts_produce_different_embeddings():
    embedder = SentenceTransformerEmbedder()
    e1 = embedder.embed("cats and dogs")
    e2 = embedder.embed("quantum physics")
    assert e1 != e2


def test_similar_texts_are_closer():
    """Semantically similar texts should have higher cosine similarity."""
    import math

    embedder = SentenceTransformerEmbedder()
    e_cat = embedder.embed("I love my cat")
    e_dog = embedder.embed("I love my dog")
    e_unrelated = embedder.embed("The stock market crashed")

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb)

    sim_similar = cosine(e_cat, e_dog)
    sim_unrelated = cosine(e_cat, e_unrelated)
    assert sim_similar > sim_unrelated
