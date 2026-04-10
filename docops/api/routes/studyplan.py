"""Rota de plano de estudos — /api/studyplan."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path as _Path

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
    pdf_filename: str | None = None


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
Use headings (#, ##, ###), listas (- ou 1.), **negrito** e *itálico*.
Cada dia deve ser uma seção ## separada.
"""


def _generate_plan(topic: str, days: int, doc_names: list[str], user_id: int) -> str:
    from docops.config import config
    from google import genai

    context_section = ""
    if doc_names:
        from docops.rag.retriever import retrieve_for_docs
        chunks = retrieve_for_docs(
            doc_names_or_ids=doc_names,
            query=topic,
            user_id=user_id,
            top_k=15,
        )
        if chunks:
            texts = "\n\n".join(c.page_content[:600] for c in chunks[:10])
            context_section = f"Use o seguinte conteúdo dos documentos como base:\n\n{texts}\n\n"

    client = genai.Client(api_key=config.gemini_api_key)
    prompt = STUDY_PLAN_PROMPT.format(
        topic=topic,
        days=days,
        context_section=context_section,
    )

    response = client.models.generate_content(model=config.gemini_model, contents=prompt)
    return response.text.strip()


def _generate_pdf(plan_text: str, topic: str, output_path: str) -> None:
    """Gera PDF formatado a partir do plano em markdown."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "PlanTitle",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=12,
        textColor=HexColor("#1a1a2e"),
    ))
    styles.add(ParagraphStyle(
        "PlanH2",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=16,
        spaceAfter=6,
        textColor=HexColor("#16213e"),
    ))
    styles.add(ParagraphStyle(
        "PlanH3",
        parent=styles["Heading3"],
        fontSize=12,
        spaceBefore=10,
        spaceAfter=4,
        textColor=HexColor("#0f3460"),
    ))
    styles.add(ParagraphStyle(
        "PlanBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "PlanBullet",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        leftIndent=20,
        spaceAfter=2,
        bulletIndent=8,
    ))
    styles.add(ParagraphStyle(
        "PlanNumbered",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        leftIndent=20,
        spaceAfter=2,
    ))

    story: list = []

    # Title
    story.append(Paragraph(f"Plano de Estudos: {_escape_html(topic)}", styles["PlanTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#cccccc"), spaceAfter=12))

    for line in plan_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 6))
            continue

        # Headings
        if stripped.startswith("# "):
            text = _md_inline_to_html(stripped[2:])
            story.append(Paragraph(text, styles["PlanTitle"]))
            story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#dddddd"), spaceAfter=8))
        elif stripped.startswith("## "):
            text = _md_inline_to_html(stripped[3:])
            story.append(Paragraph(text, styles["PlanH2"]))
        elif stripped.startswith("### "):
            text = _md_inline_to_html(stripped[4:])
            story.append(Paragraph(text, styles["PlanH3"]))
        # Bullet lists
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = _md_inline_to_html(stripped[2:])
            story.append(Paragraph(f"\u2022 {text}", styles["PlanBullet"]))
        # Numbered lists
        elif re.match(r"^\d+\.\s", stripped):
            match = re.match(r"^(\d+\.)\s(.*)", stripped)
            if match:
                num, text = match.group(1), _md_inline_to_html(match.group(2))
                story.append(Paragraph(f"{num} {text}", styles["PlanNumbered"]))
        # Regular paragraph
        else:
            text = _md_inline_to_html(stripped)
            story.append(Paragraph(text, styles["PlanBody"]))

    doc.build(story)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_inline_to_html(text: str) -> str:
    """Converte **bold**, *italic* e `code` para tags HTML do ReportLab."""
    text = _escape_html(text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', text)
    return text


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

        from docops.tools.doc_tools import tool_write_artifact

        safe_topic = "".join(c if c.isalnum() or c in " _-" else "_" for c in payload.topic)[:60]

        # 1. Save .md artifact
        md_filename = f"study_plan_{safe_topic}.md"
        md_path = tool_write_artifact(md_filename, plan_text, current_user.id)
        md_final_name = None
        if md_path:
            md_final_name = _Path(str(md_path)).name
            crud.create_artifact_record(
                db,
                user_id=current_user.id,
                artifact_type="study_plan",
                filename=md_final_name,
                path=str(md_path),
                title=f"Plano de Estudos — {payload.topic}",
            )

        # 2. Generate and save .pdf artifact
        pdf_filename = f"study_plan_{safe_topic}.pdf"
        pdf_final_name = None
        try:
            # Get the artifact directory for the user
            from docops.storage.paths import get_user_artifacts_dir
            artifacts_dir = get_user_artifacts_dir(current_user.id)
            pdf_full_path = _Path(artifacts_dir) / pdf_filename
            pdf_full_path.parent.mkdir(parents=True, exist_ok=True)

            await asyncio.to_thread(_generate_pdf, plan_text, payload.topic, str(pdf_full_path))

            pdf_final_name = pdf_filename
            crud.create_artifact_record(
                db,
                user_id=current_user.id,
                artifact_type="study_plan_pdf",
                filename=pdf_final_name,
                path=str(pdf_full_path),
                title=f"Plano de Estudos (PDF) — {payload.topic}",
            )
        except Exception as pdf_err:
            logger.warning("Falha ao gerar PDF do plano: %s", pdf_err)

        return StudyPlanResponse(
            plan=plan_text,
            artifact_filename=md_final_name,
            pdf_filename=pdf_final_name,
        )
    except Exception:
        logger.exception("Erro ao gerar plano de estudos")
        raise HTTPException(status_code=500, detail="Erro interno ao gerar plano de estudos.")
