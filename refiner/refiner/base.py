from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RefineResult:
    """The cleaned-up output of a refine pass.

    `content` is the rewritten thought, ready to store. `title` is a short
    suggested title (may be None). `tags` are suggested lowercase tags.
    """

    content: str
    title: str | None = None
    tags: list[str] = field(default_factory=list)


class RefinerBase(ABC):
    """Abstract base class for AI cleanup providers.

    Implement this to add a local backend (e.g. Ollama) later. The contract:
    take a raw, unstructured thought and return a cleaned version that
    preserves the author's meaning and voice — never inventing facts.
    """

    @abstractmethod
    def refine(self, raw: str, content_type: str = "thought") -> RefineResult:
        """Clean up `raw` text and return structured output.

        Raises RuntimeError (or a subclass) on backend failure so callers can
        translate it into an HTTP error.
        """
        ...
