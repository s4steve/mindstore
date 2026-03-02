from abc import ABC, abstractmethod


class EmbedderBase(ABC):
    """Abstract base class for embedding providers.
    Implement this to add Voyage AI or OpenAI later."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single string, return list of floats."""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple strings, return list of embeddings."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimension count."""
        ...
