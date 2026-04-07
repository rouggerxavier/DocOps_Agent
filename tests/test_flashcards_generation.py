from __future__ import annotations

import pytest
from fastapi import HTTPException

from docops.api.routes import flashcards


def test_dedupe_cards_removes_repeated_questions_and_normalizes_difficulty():
    cards = [
        {"front": "O que e regressao linear?", "back": "Um modelo linear.", "difficulty": "facil"},
        {"front": "  O QUE E REGRESSAO LINEAR ? ", "back": "Mesmo conceito.", "difficulty": "media"},
        {"front": "Quando usar regularizacao?", "back": "Para reduzir overfitting.", "difficulty": "desconhecida"},
    ]

    result = flashcards._dedupe_cards(cards)

    assert len(result) == 2
    assert result[0]["front"] == "O que e regressao linear?"
    assert result[1]["difficulty"] == "media"


def test_collect_flashcards_repairs_distribution_across_attempts():
    batches = [
        [
            {"front": "Pergunta facil 1", "back": "Resposta 1", "difficulty": "facil"},
            {"front": "Pergunta facil 1", "back": "Resposta repetida", "difficulty": "facil"},
            {"front": "Pergunta facil 2", "back": "Resposta 2", "difficulty": "facil"},
            {"front": "Pergunta media 1", "back": "Resposta 3", "difficulty": "media"},
        ],
        [
            {"front": "Pergunta dificil 1", "back": "Resposta 4", "difficulty": "dificil"},
        ],
    ]
    calls: list[tuple[int, str, list[str]]] = []

    def fake_fetch_batch(*, num_cards: int, difficulty_instruction: str, excluded_fronts: list[str]):
        calls.append((num_cards, difficulty_instruction, excluded_fronts))
        return batches.pop(0)

    result = flashcards._collect_flashcards(
        fake_fetch_batch,
        total_cards=4,
        target_counts={"facil": 2, "media": 1, "dificil": 1},
    )

    assert len(result) == 4
    assert flashcards._count_cards_by_difficulty(result) == {"facil": 2, "media": 1, "dificil": 1}
    assert len({flashcards._normalize_card_text(card["front"]) for card in result}) == 4
    assert len(calls) == 2
    assert "dificil" in calls[1][1]


def test_collect_flashcards_raises_when_distribution_cannot_be_met():
    def fake_fetch_batch(*, num_cards: int, difficulty_instruction: str, excluded_fronts: list[str]):
        return [
            {"front": f"Pergunta facil {num_cards}", "back": "Resposta", "difficulty": "facil"},
        ]

    with pytest.raises(HTTPException) as exc_info:
        flashcards._collect_flashcards(
            fake_fetch_batch,
            total_cards=3,
            target_counts={"facil": 1, "media": 1, "dificil": 1},
        )

    assert exc_info.value.status_code == 502
    assert "distribuicao pedida" in str(exc_info.value.detail)
