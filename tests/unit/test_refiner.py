import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../refiner"))

from refiner.anthropic_refiner import AnthropicRefiner, _normalize_tag
from refiner.base import RefineResult, RefinerBase


def test_refine_result_defaults():
    r = RefineResult(content="hi")
    assert r.title is None
    assert r.tags == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Travel", "travel"),
        ("#Work-Stuff", "work-stuff"),
        ("café notes!", "cafnotes"),
        ("multi word", "multiword"),
        ("a" * 50, "a" * 40),
    ],
)
def test_normalize_tag(raw, expected):
    assert _normalize_tag(raw) == expected


def test_anthropic_refiner_requires_api_key():
    with pytest.raises(ValueError):
        AnthropicRefiner(api_key="")


def _fake_message(content="Cleaned text.", title="A Title", tags=None):
    """Build a fake Anthropic message with a single tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"content": content, "title": title, "tags": tags or []}
    msg = MagicMock()
    msg.content = [block]
    return msg


def _refiner_with_response(msg):
    """Construct an AnthropicRefiner without hitting the real SDK."""
    refiner = AnthropicRefiner.__new__(AnthropicRefiner)
    refiner._model = "test-model"
    refiner._client = MagicMock()
    refiner._client.messages.create.return_value = msg
    return refiner


def test_refine_parses_structured_output():
    refiner = _refiner_with_response(
        _fake_message(content="Cleaned.", title="Title", tags=["Work", "#Work", "ideas"])
    )
    result = refiner.refine("raw thought", "thought")
    assert result.content == "Cleaned."
    assert result.title == "Title"
    # Dedupes 'Work'/'#Work' after normalization; keeps 'ideas'.
    assert result.tags == ["work", "ideas"]


def test_refine_empty_content_raises():
    refiner = _refiner_with_response(_fake_message(content="   "))
    with pytest.raises(RuntimeError):
        refiner.refine("raw", "thought")


def test_refine_no_tool_use_raises():
    msg = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    msg.content = [text_block]
    refiner = _refiner_with_response(msg)
    with pytest.raises(RuntimeError):
        refiner.refine("raw", "thought")


def test_refine_backend_exception_wrapped():
    refiner = AnthropicRefiner.__new__(AnthropicRefiner)
    refiner._model = "test-model"
    refiner._client = MagicMock()
    refiner._client.messages.create.side_effect = ConnectionError("boom")
    with pytest.raises(RuntimeError, match="refine backend error"):
        refiner.refine("raw", "thought")


def test_caps_tags_at_five():
    refiner = _refiner_with_response(
        _fake_message(tags=[f"tag{i}" for i in range(10)])
    )
    result = refiner.refine("raw", "thought")
    assert len(result.tags) == 5


def test_is_subclass_of_base():
    assert issubclass(AnthropicRefiner, RefinerBase)
