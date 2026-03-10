from __future__ import annotations

from docops.llm.content import content_to_text, response_text


def test_content_to_text_with_plain_string():
    assert content_to_text("abc") == "abc"


def test_content_to_text_with_block_list():
    payload = [
        {"type": "text", "text": "Linha 1"},
        {"type": "text", "text": "Linha 2"},
    ]
    assert content_to_text(payload) == "Linha 1\nLinha 2"


def test_content_to_text_with_nested_parts():
    payload = {
        "parts": [
            {"text": "Parte A"},
            {"text": "Parte B"},
        ]
    }
    assert content_to_text(payload) == "Parte A\nParte B"


def test_response_text_uses_content_attribute():
    class Resp:
        def __init__(self, content):
            self.content = content

    resp = Resp([{"type": "text", "text": "Texto normalizado"}])
    assert response_text(resp) == "Texto normalizado"

