import re

from .base import RefinerBase, RefineResult

SYSTEM_PROMPT = """\
You are the cleanup step of a personal knowledge store called Mindstore. The \
user dictates or jots down raw, unstructured thoughts and you turn them into a \
clean entry that is worth keeping.

Your job:
- Fix spelling, grammar, punctuation, and capitalisation.
- Tidy structure: break run-ons into sentences; use short paragraphs or a \
bulleted list when the content is clearly a list. Keep formatting minimal and \
plain-text (no Markdown headings).
- Preserve the author's original meaning, intent, and voice. Do NOT add facts, \
opinions, conclusions, or details that were not in the input.
- Do NOT pad or expand. If the raw text is already clean, return it nearly \
unchanged. Aim to keep it about the same length.
- Strip filler verbal tics ("um", "like", "you know", "I guess") only when they \
carry no meaning.

Also produce:
- title: a concise title (max ~8 words), or null if the thought is too short to \
warrant one.
- tags: 0-5 short lowercase topical tags (single words or hyphenated), no '#'. \
Only tags clearly supported by the content.

Always return your answer by calling the save_thought tool."""

SAVE_TOOL = {
    "name": "save_thought",
    "description": "Return the cleaned-up thought ready to store in Mindstore.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The cleaned-up thought text, ready to store.",
            },
            "title": {
                "type": ["string", "null"],
                "description": "A concise title, or null if not warranted.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "0-5 short lowercase topical tags, no '#'.",
            },
        },
        "required": ["content", "tags"],
    },
}


def _normalize_tag(raw: str) -> str:
    """Match the web UI's tag rules: lowercase, [a-z0-9_-], max 40 chars."""
    return re.sub(r"[^a-z0-9_-]", "", raw.strip().lower())[:40]


class AnthropicRefiner(RefinerBase):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        if not api_key:
            raise ValueError("AnthropicRefiner requires a non-empty api_key")
        # Imported lazily so the package (and a future local backend) can be
        # used without the anthropic SDK installed.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model

    def refine(self, raw: str, content_type: str = "thought") -> RefineResult:
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[SAVE_TOOL],
                tool_choice={"type": "tool", "name": "save_thought"},
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Clean up this raw {content_type}:\n\n{raw}"
                        ),
                    }
                ],
            )
        except Exception as exc:  # network, auth, rate limit, etc.
            raise RuntimeError(f"refine backend error: {exc}") from exc

        tool_use = next(
            (block for block in message.content if block.type == "tool_use"), None
        )
        if tool_use is None:
            raise RuntimeError("refine backend returned no structured output")

        data = tool_use.input
        content = (data.get("content") or "").strip()
        if not content:
            raise RuntimeError("refine backend returned empty content")

        title = data.get("title")
        if isinstance(title, str):
            title = title.strip() or None
        else:
            title = None

        tags: list[str] = []
        for t in data.get("tags") or []:
            norm = _normalize_tag(str(t))
            if norm and norm not in tags:
                tags.append(norm)
            if len(tags) >= 5:
                break

        return RefineResult(content=content, title=title, tags=tags)
