"""Rota de plano de estudos — /api/studyplan."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from docops.auth.dependencies import get_current_user
from docops.db import crud
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger

logger = get_logger("docops.api.studyplan")
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class StudyPlanRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=512)
    days: int = Field(default=7, ge=1, le=90)
    doc_names: list[str] = Field(default_factory=list)


class StudyPlanResponse(BaseModel):
    plan: str
    artifact_filename: str | None = None


# ── Geração ───────────────────────────────────────────────────────────────────

STUDY_PLAN_PROMPT = """\
Você é um especialista em planejamento de estudos.
Crie um plano de estudos detalhado para o tópico "{topic}" em {days} dias.

{context_section}

O plano deve incluir:
1. Visão geral do que será estudado
2. Divisão dia a dia com objetivos claros
3. Recursos sugeridos e técnicas de estudo
4. Pontos de revisão usando repetição espaçada
5. Critérios de autoavaliação

Formate em Markdown com seções bem definidas.
Use listas, sub-seções e destaques para facilitar a leitura.
"""


def _generate_plan(topic: str, days: int, doc_names: list[str], user_id: int) -> str:
    from docops.config import config
    import google.generativeai as genai

    context_section = ""
    if doc_names:
        from docops.rag.retriever import retrieve
        chunks = retrieve(
            query=topic,
            user_id=user_id,
            top_k=15,
            doc_names=doc_names,
        )
        if chunks:
            texts = "\n\n".join(c.page_content[:600] for c in chunks[:10])
            context_section = f"Use o seguinte conteúdo dos documentos como base:\n\n{texts}\n\n"

    genai.configure(api_key=config.gemini_api_key)
    model = genai.GenerativeModel(config.gemini_model)
    prompt = STUDY_PLAN_PROMPT.format(
        topic=topic,
        days=days,
        context_section=context_section,
    )

    response = model.generate_content(prompt)
    return response.text.strip()


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/studyplan", response_model=StudyPlanResponse)
async def create_study_plan(
    payload: StudyPlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        plan_text = await asyncio.to_thread(
            _generate_plan,
            payload.topic,
            payload.days,
            payload.doc_names,
            current_user.id,
        )

        # Salva como artefato
        from pathlib import Path as _Path
        from docops.tools.doc_tools import tool_write_artifact

        safe_topic = "".join(c if c.isalnum() or c in " _-" else "_" for c in payload.topic)[:60]
        artifact_filename = f"study_plan_{safe_topic}.md"
        artifact_path = tool_write_artifact(artifact_filename, plan_text, current_user.id)

        filename = None
        if artifact_path:
            filename = _Path(str(artifact_path)).name
            crud.create_artifact_record(
                db,
                user_id=current_user.id,
                artifact_type="study_plan",
                filename=filename,
                path=str(artifact_path),
                title=f"Plano de Estudos — {payload.topic}",
            )

        return StudyPlanResponse(plan=plan_text, artifact_filename=filename)
    except Exception as e:
        logger.exception("Erro ao gerar plano de estudos: %s", e)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar plano: {e}")
