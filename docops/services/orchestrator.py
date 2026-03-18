"""Orquestrador inteligente de ações cross-module.

Substitui e expande o action_router com parser LLM capaz de:
  1. Detectar intents complexos e cascades multi-step
  2. Extrair entidades (tópico, prazo, documento, deck)
  3. Executar sequências de ações nos módulos existentes

Cascades implementados:
  cascade_study_event    — "tenho prova de X na sexta" → tarefa + lembretes de estudo
  cascade_doc_review     — "revise X com flashcards" → deck + agendamento de revisões SRS
  cascade_task_deadline  — "entregar Y na quinta" → tarefa com due_date + lembrete
  schedule_fc_reviews    — "agende revisões dos flashcards de X" → lembretes SRS

Fluxo no chat.py:
  orchestrator.maybe_orchestrate() → dict (answer + intent) | None
  → None → calendar_assistant → RAG graph
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from docops.logging import get_logger

logger = get_logger("docops.services.orchestrator")

# ---------------------------------------------------------------------------
# Prompt do parser LLM
# ---------------------------------------------------------------------------

_PARSE_TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

_PARSER_PROMPT = f"""\
Você é um parser de intenções para um assistente pessoal. Hoje é {_PARSE_TODAY}.

Analise a mensagem do usuário e retorne APENAS um JSON válido (sem markdown, sem texto extra).

Intents possíveis:
- "cascade_study_event"  → usuário menciona prova, exame, avaliação com prazo/data
- "cascade_study_plan"   → usuário quer criar um plano de estudos para um documento/tema
- "cascade_doc_review"   → usuário quer revisar/estudar um documento específico com flashcards
- "cascade_task_deadline"→ usuário menciona entrega, deadline, prazo de um trabalho/projeto
- "schedule_fc_reviews"  → usuário quer agendar revisões de flashcards já existentes
- "create_task"          → criar tarefa simples sem prazo específico
- "list_tasks"           → listar tarefas pendentes
- "flashcard_hint"       → pede flashcards de um documento sem cascade
- "cascade_create_note"  → usuário quer criar/salvar uma anotação, nota ou lembrete textual
- "cascade_create_summary" → usuário quer fazer um resumo de um documento específico
- "rag"                  → pergunta sobre documentos, dúvida, QA — deve ir pro RAG

Regras:
- Se a mensagem for uma pergunta factual ou pedir informação de documento → "rag"
- Se mencionar prova/exame/teste + data → "cascade_study_event"
- Se mencionar "plano de estudos", "cronograma de estudos", "me ajuda a estudar [doc]", "estudar [doc] até [data]" → "cascade_study_plan"
- Se mencionar entrega/prazo/deadline de projeto/trabalho + data → "cascade_task_deadline"
- Se mencionar "cria uma nota", "salva essa anotação", "anota isso", "registra isso" → "cascade_create_note"
- Se mencionar "resumo de", "resumir [doc]", "faz um resumo", "sumarize" → "cascade_create_summary"
- Datas relativas: "amanhã"=+1d, "depois de amanhã"=+2d, "semana que vem"=+7d, "próxima semana"=+7d
- Se não houver data clara, deadline_iso = null
- doc_hint: nome ou parte do nome do documento mencionado, null se não mencionado
- topic: assunto principal (ex: "física", "cálculo diferencial"), null se não mencionado
- task_title: título limpo da tarefa (começa com verbo), null se não aplicável
- deck_hint: parte do nome do deck/documento para flashcards
- hours_per_day: horas por dia de estudo mencionadas (número float), null se não mencionado
- content: conteúdo ou texto da nota que o usuário quer salvar, null se não especificado

Formato de resposta:
{{
  "intent": "<intent>",
  "entities": {{
    "topic": "<string ou null>",
    "task_title": "<string ou null>",
    "doc_hint": "<string ou null>",
    "deck_hint": "<string ou null>",
    "deadline_iso": "<YYYY-MM-DD ou null>",
    "deadline_label": "<descrição legível da data ou null>",
    "hours_per_day": "<float ou null>",
    "content": "<string ou null>"
  }}
}}

Mensagem do usuário: {{MESSAGE}}
"""


# ---------------------------------------------------------------------------
# Funções auxiliares de data
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _parse_date_from_text(text: str) -> datetime | None:
    """Tenta parsear datas relativas comuns em português."""
    now = datetime.now(timezone.utc)
    t = text.lower()

    # "DD de Mês" ou "dia DD de Mês" (ex: "10 de abril", "dia 5 de maio")
    m = re.search(
        r"(?:dia\s+)?(\d{1,2})\s+de\s+(janeiro|fevereiro|mar[çc]o|abril|maio|junho|"
        r"julho|agosto|setembro|outubro|novembro|dezembro)(?:\s+de\s+(\d{4}))?",
        t,
    )
    if m:
        day = int(m.group(1))
        month_raw = m.group(2).replace("março", "março").replace("marco", "março")
        month = _MONTH_MAP.get(month_raw)
        year = int(m.group(3)) if m.group(3) else now.year
        if month:
            try:
                candidate = datetime(year, month, day, tzinfo=timezone.utc)
                # Se a data já passou neste ano, avança para o próximo
                if candidate < now and not m.group(3):
                    candidate = datetime(year + 1, month, day, tzinfo=timezone.utc)
                return candidate
            except ValueError:
                pass

    # "DD/MM" ou "DD/MM/YYYY"
    m2 = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", t)
    if m2:
        day, month = int(m2.group(1)), int(m2.group(2))
        year = int(m2.group(3)) if m2.group(3) else now.year
        try:
            candidate = datetime(year, month, day, tzinfo=timezone.utc)
            if candidate < now and not m2.group(3):
                candidate = datetime(year + 1, month, day, tzinfo=timezone.utc)
            return candidate
        except ValueError:
            pass

    patterns = [
        (r"hoje", 0),
        (r"amanh[ãa]", 1),
        (r"depois de amanh[ãa]", 2),
        (r"em (\d+) dias?", None),
        (r"daqui a (\d+) dias?", None),
        (r"próxima semana|semana que vem|próximas? semana", 7),
        (r"em (\d+) semanas?", None),
        (r"daqui a (\d+) semanas?", None),
        (r"próximas? (\d+) dias?", None),
        (r"sexta(?:-feira)?", None),
        (r"quinta(?:-feira)?", None),
        (r"quarta(?:-feira)?", None),
        (r"terça(?:-feira)?", None),
        (r"segunda(?:-feira)?", None),
        (r"sábado", None),
        (r"domingo", None),
    ]

    weekday_map = {
        "segunda": 0, "terça": 1, "quarta": 2, "quinta": 3,
        "sexta": 4, "sábado": 5, "domingo": 6,
    }

    for pattern, delta in patterns:
        m3 = re.search(pattern, t)
        if m3:
            if delta is not None:
                return now + timedelta(days=delta)
            if m3.lastindex and m3.lastindex >= 1:
                try:
                    val = int(m3.group(1))
                    # semanas → dias
                    mult = 7 if "semana" in pattern else 1
                    return now + timedelta(days=val * mult)
                except (ValueError, IndexError):
                    pass
            for name, wd in weekday_map.items():
                if name in pattern:
                    days_ahead = (wd - now.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    return now + timedelta(days=days_ahead)

    # ISO date YYYY-MM-DD
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso:
        try:
            return datetime.strptime(iso.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def _reminder_times_for_deadline(deadline: datetime) -> list[tuple[str, datetime]]:
    """Retorna lembretes SRS para um prazo: D-3, D-1 e D-day manhã."""
    now = datetime.now(timezone.utc)
    slots = []
    for label, delta_days, hour in [("Revisão inicial", -3, 19), ("Véspera", -1, 19), ("Dia da prova", 0, 7)]:
        t = deadline.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=delta_days)
        if t > now + timedelta(hours=1):
            slots.append((label, t))
    return slots


def _srs_review_times(from_dt: datetime) -> list[tuple[str, datetime]]:
    """Revisões SRS clássicas: +1d, +3d, +7d a partir de hoje."""
    now = from_dt
    return [
        ("1ª revisão", now + timedelta(days=1)),
        ("2ª revisão", now + timedelta(days=3)),
        ("3ª revisão", now + timedelta(days=7)),
    ]


# ---------------------------------------------------------------------------
# Parser LLM
# ---------------------------------------------------------------------------

def _llm_parse(message: str) -> dict[str, Any] | None:
    """Chama o LLM barato para parsear a intenção. Retorna dict ou None se erro."""
    try:
        from docops.config import config
        from google import genai

        client = genai.Client(api_key=config.gemini_api_key)
        model = getattr(config, "gemini_model_cheap", None) or config.gemini_model
        prompt = _PARSER_PROMPT.replace("{MESSAGE}", message)
        logger.info("Orchestrator: chamando LLM parser (model=%s)", model)
        response = client.models.generate_content(model=model, contents=prompt)
        raw = response.text.strip()
        logger.info("Orchestrator: LLM raw=%r", raw[:200])
        # Extrai JSON mesmo se vier com markdown ao redor
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            logger.info("Orchestrator: nenhum JSON encontrado na resposta do LLM")
            return None
        parsed = json.loads(match.group(0))
        logger.info("Orchestrator: parsed=%s", parsed)
        return parsed
    except Exception as exc:
        logger.info("Orchestrator: LLM parser falhou — %s: %s", type(exc).__name__, exc)
        return None


# ---------------------------------------------------------------------------
# Executores de cascade
# ---------------------------------------------------------------------------

def _exec_cascade_study_event(entities: dict, user_id: int, db: Session) -> dict:
    """Prova/exame próximo → tarefa de estudo + lembretes escalonados."""
    from docops.db import crud

    topic = entities.get("topic") or "Estudo"
    deadline_iso = entities.get("deadline_iso")
    deadline_label = entities.get("deadline_label") or deadline_iso or "prazo"

    deadline_dt = None
    if deadline_iso:
        try:
            deadline_dt = datetime.strptime(deadline_iso, "%Y-%m-%d").replace(
                hour=9, minute=0, tzinfo=timezone.utc
            )
        except ValueError:
            pass

    # 1. Criar tarefa
    task_title = f"Estudar {topic}"
    try:
        task = crud.create_task_record(
            db,
            user_id=user_id,
            title=task_title,
            priority="high",
            due_date=deadline_dt,
        )
        task_line = f'✅ Tarefa criada: **"{task.title}"** (alta prioridade)'
    except Exception as exc:
        logger.error("Falha ao criar tarefa no cascade_study_event: %s", exc)
        task_line = f"⚠️ Não foi possível criar a tarefa."

    # 2. Criar lembretes de estudo
    reminder_lines = []
    if deadline_dt:
        reminders = _reminder_times_for_deadline(deadline_dt)
        for label, dt in reminders:
            try:
                r = crud.create_reminder_record(
                    db,
                    user_id=user_id,
                    title=f"📚 {label} — {topic}",
                    starts_at=dt,
                    note=f"Revisão programada automaticamente para: {topic}",
                )
                reminder_lines.append(f"📅 {label}: {dt.strftime('%d/%m %H:%M')}")
            except Exception as exc:
                logger.error("Falha ao criar lembrete: %s", exc)
                reminder_lines.append(f"⚠️ Lembrete '{label}' não criado.")

    answer_parts = [
        f"🎯 Entendido! Organizei o estudo de **{topic}** para **{deadline_label}**:\n",
        task_line,
    ]
    if reminder_lines:
        answer_parts.append("\n**Lembretes criados no calendário:**")
        answer_parts.extend(reminder_lines)

    answer_parts.append("\nVeja seus [Lembretes →](/schedule) e [Tarefas →](/tasks)")

    return {"answer": "\n".join(answer_parts), "intent": "cascade_study_event"}


def _exec_cascade_doc_review(entities: dict, user_id: int, db: Session) -> dict:
    """Documento → deck de flashcards + agendamento de revisões SRS."""
    from docops.db import crud

    doc_hint = entities.get("doc_hint") or ""
    docs = crud.list_documents_for_user(db, user_id)

    if not docs:
        return {
            "answer": "Você ainda não inseriu documentos. Adicione na [Inserção](/ingest) primeiro.",
            "intent": "cascade_doc_review",
        }

    # Localiza documento por dica
    hint_lower = doc_hint.lower()
    matched_doc = next(
        (d for d in docs if hint_lower and (hint_lower in d.file_name.lower() or d.file_name.lower() in hint_lower)),
        docs[0] if len(docs) == 1 else None,
    )

    if not matched_doc:
        doc_list = "\n".join(f"- {d.file_name}" for d in docs[:5])
        return {
            "answer": (
                f'Não encontrei documento com "{doc_hint}". Documentos disponíveis:\n{doc_list}\n\n'
                "Tente ser mais específico ou use o [Smart Digest](/docs)."
            ),
            "intent": "cascade_doc_review",
        }

    # Gera flashcards
    deck_id = None
    deck_line = ""
    try:
        from docops.api.routes.flashcards import _generate_cards
        cards = _generate_cards(
            doc_name=matched_doc.file_name,
            doc_id=matched_doc.doc_id,
            user_id=user_id,
            num_cards=10,
            difficulty_mode="any",
        )
        deck = crud.create_flashcard_deck(
            db,
            user_id=user_id,
            source_doc=matched_doc.file_name,
            title=f"Flashcards — {matched_doc.file_name}",
            cards=cards,
        )
        deck_id = deck.id
        deck_line = f"🃏 Deck criado: **{len(cards)} flashcards** de _{matched_doc.file_name}_"
    except Exception as exc:
        logger.error("Falha ao gerar flashcards no cascade_doc_review: %s", exc)
        deck_line = "⚠️ Não foi possível gerar flashcards agora. Tente pelo [menu de Documentos](/docs)."

    # Agenda revisões SRS
    reminder_lines = []
    if deck_id:
        now = datetime.now(timezone.utc)
        for label, dt in _srs_review_times(now):
            try:
                crud.create_reminder_record(
                    db,
                    user_id=user_id,
                    title=f"🔁 {label} — flashcards de {matched_doc.file_name}",
                    starts_at=dt.replace(hour=19, minute=0, second=0),
                    note=f"Revisão espaçada automática. Deck ID: {deck_id}",
                )
                reminder_lines.append(f"📅 {label}: {dt.strftime('%d/%m')}")
            except Exception as exc:
                logger.error("Falha ao criar lembrete SRS: %s", exc)

    answer_parts = [
        f"📚 Tudo pronto para revisar **{matched_doc.file_name}**!\n",
        deck_line,
    ]
    if reminder_lines:
        answer_parts.append("\n**Revisões SRS agendadas no calendário:**")
        answer_parts.extend(reminder_lines)

    answer_parts.append(f"\n[Estudar os flashcards →](/flashcards)")

    return {"answer": "\n".join(answer_parts), "intent": "cascade_doc_review"}


def _exec_cascade_task_deadline(entities: dict, user_id: int, db: Session) -> dict:
    """Entrega/projeto com prazo → tarefa com due_date + lembrete D-1."""
    from docops.db import crud

    task_title = entities.get("task_title") or entities.get("topic") or "Entrega"
    deadline_iso = entities.get("deadline_iso")
    deadline_label = entities.get("deadline_label") or deadline_iso or "prazo definido"

    deadline_dt = None
    if deadline_iso:
        try:
            deadline_dt = datetime.strptime(deadline_iso, "%Y-%m-%d").replace(
                hour=23, minute=59, tzinfo=timezone.utc
            )
        except ValueError:
            pass

    # Criar tarefa
    try:
        task = crud.create_task_record(
            db,
            user_id=user_id,
            title=task_title,
            priority="high",
            due_date=deadline_dt,
        )
        task_line = f'✅ Tarefa: **"{task.title}"** — prazo: {deadline_label}'
    except Exception as exc:
        logger.error("Falha ao criar tarefa deadline: %s", exc)
        task_line = "⚠️ Não foi possível criar a tarefa."

    # Lembrete D-1
    reminder_line = ""
    if deadline_dt:
        reminder_dt = (deadline_dt - timedelta(days=1)).replace(hour=9, minute=0)
        now = datetime.now(timezone.utc)
        if reminder_dt > now:
            try:
                crud.create_reminder_record(
                    db,
                    user_id=user_id,
                    title=f"⚠️ Amanhã é a entrega: {task_title}",
                    starts_at=reminder_dt,
                    note="Lembrete automático criado pelo orquestrador.",
                )
                reminder_line = f"📅 Lembrete criado para {reminder_dt.strftime('%d/%m')} às 09:00"
            except Exception as exc:
                logger.error("Falha ao criar lembrete de entrega: %s", exc)

    answer_parts = [f"📋 Registrei sua entrega:\n", task_line]
    if reminder_line:
        answer_parts.append(reminder_line)
    answer_parts.append("\n[Ver Tarefas →](/tasks) · [Calendário →](/schedule)")

    return {"answer": "\n".join(answer_parts), "intent": "cascade_task_deadline"}


def _exec_schedule_fc_reviews(entities: dict, user_id: int, db: Session) -> dict:
    """Agenda revisões SRS para um deck de flashcards existente."""
    from docops.db import crud

    deck_hint = entities.get("deck_hint") or entities.get("doc_hint") or ""
    decks = crud.list_flashcard_decks_for_user(db, user_id)

    if not decks:
        return {
            "answer": "Você ainda não tem decks de flashcards. Crie um na [página de Documentos](/docs) usando o Smart Digest.",
            "intent": "schedule_fc_reviews",
        }

    hint_lower = deck_hint.lower()
    matched = next(
        (d for d in decks if hint_lower and (hint_lower in d.title.lower() or hint_lower in (d.source_doc or "").lower())),
        decks[0] if len(decks) == 1 else None,
    )

    if not matched:
        deck_list = "\n".join(f"- {d.title}" for d in decks[:5])
        return {
            "answer": f"Não encontrei o deck. Seus decks:\n{deck_list}\n\nSeja mais específico.",
            "intent": "schedule_fc_reviews",
        }

    now = datetime.now(timezone.utc)
    reminder_lines = []
    for label, dt in _srs_review_times(now):
        try:
            crud.create_reminder_record(
                db,
                user_id=user_id,
                title=f"🔁 {label} — {matched.title}",
                starts_at=dt.replace(hour=19, minute=0, second=0),
                note=f"Revisão espaçada. Deck: {matched.title}",
            )
            reminder_lines.append(f"📅 {label}: {dt.strftime('%d/%m')} às 19h")
        except Exception as exc:
            logger.error("Falha ao criar lembrete SRS: %s", exc)

    answer = (
        f"🔁 Revisões agendadas para **{matched.title}**:\n\n"
        + "\n".join(reminder_lines)
        + "\n\n[Ver Calendário →](/schedule)"
    )
    return {"answer": answer, "intent": "schedule_fc_reviews"}


# ---------------------------------------------------------------------------
# Cascade: Plano de Estudos (multi-turn)
# ---------------------------------------------------------------------------

# Pendências de plano de estudos por user_id (em memória — suficiente para 1 sessão)
_pending_study_plans: dict[int, dict] = {}


def _extract_followup_info(message: str) -> dict:
    """Extrai horas/dia e prazo de uma resposta de follow-up simples."""
    result: dict = {}

    # Horas: "2h", "2 horas", "1.5h por dia", "3 horas diárias"
    h_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:h(?:oras?)?|hrs?)(?:\s*(?:por|ao|\/)\s*dia)?",
        message,
        re.IGNORECASE,
    )
    if h_match:
        try:
            result["hours_per_day"] = float(h_match.group(1).replace(",", "."))
        except ValueError:
            pass

    # Prazo: usa o parser de datas existente
    dt = _parse_date_from_text(message)
    if dt:
        result["deadline_iso"] = dt.strftime("%Y-%m-%d")
        result["deadline_label"] = dt.strftime("%d/%m/%Y")

    return result


def _exec_cascade_study_plan(entities: dict, user_id: int, db: Session) -> dict:
    """Cria plano de estudos completo: tarefas + sessões no calendário + flashcards."""
    from docops.db import crud
    from datetime import date as _date

    doc_hint = entities.get("doc_hint") or entities.get("topic") or ""
    hours_raw = entities.get("hours_per_day")
    deadline_iso = entities.get("deadline_iso")

    # Resolve horas (pode vir como string "2.0" do LLM)
    hours_per_day: float | None = None
    if hours_raw is not None:
        try:
            hours_per_day = float(hours_raw)
        except (ValueError, TypeError):
            pass

    # Verifica se faltam informações → pergunta ao usuário
    missing = []
    if not hours_per_day:
        missing.append("quantas horas por dia você pode dedicar (ex: 2h)")
    if not deadline_iso:
        missing.append("até quando quer concluir o estudo (ex: 20/04, em 2 semanas)")

    if missing:
        # Armazena o que já temos para o próximo turn
        _pending_study_plans[user_id] = {
            "entities": entities,
            "missing": list(missing),
        }
        questions = " e ".join(missing)
        doc_part = f" de **{doc_hint}**" if doc_hint else ""
        return {
            "answer": (
                f"Para criar seu plano de estudos{doc_part}, preciso saber: "
                f"{questions}?"
            ),
            "intent": "cascade_study_plan_ask",
        }

    # Temos tudo — localiza documento
    docs = crud.list_documents_for_user(db, user_id)
    if not docs:
        _pending_study_plans.pop(user_id, None)
        return {
            "answer": "Você ainda não inseriu documentos. Adicione na [Inserção](/ingest) primeiro.",
            "intent": "cascade_study_plan",
        }

    hint_lower = doc_hint.lower()
    matched_doc = next(
        (d for d in docs if hint_lower and (
            hint_lower in d.file_name.lower() or d.file_name.lower() in hint_lower
        )),
        docs[0] if len(docs) == 1 else None,
    )

    if not matched_doc:
        doc_list = "\n".join(f"- {d.file_name}" for d in docs[:5])
        _pending_study_plans.pop(user_id, None)
        return {
            "answer": (
                f'Não encontrei documento com "{doc_hint}". Disponíveis:\n{doc_list}\n\n'
                "Tente ser mais específico."
            ),
            "intent": "cascade_study_plan",
        }

    try:
        deadline = _date.fromisoformat(deadline_iso)
    except (ValueError, TypeError):
        _pending_study_plans.pop(user_id, None)
        return {
            "answer": "Não consegui interpretar a data. Tente novamente com formato DD/MM ou 'em X dias'.",
            "intent": "cascade_study_plan",
        }

    if deadline <= _date.today():
        _pending_study_plans.pop(user_id, None)
        return {
            "answer": "O prazo precisa ser uma data futura. Tente novamente.",
            "intent": "cascade_study_plan",
        }

    # Executa o gerador
    _pending_study_plans.pop(user_id, None)
    try:
        from docops.services.study_plan_generator import generate_study_plan
        result = generate_study_plan(
            doc_name=matched_doc.file_name,
            doc_id=matched_doc.doc_id,
            user_id=user_id,
            hours_per_day=hours_per_day,
            deadline=deadline,
            db=db,
            generate_flashcards=True,
            num_cards=12,
        )
    except Exception as exc:
        logger.error("Falha ao gerar plano de estudos: %s", exc)
        return {
            "answer": "Ocorreu um erro ao gerar o plano de estudos. Tente pela [página de Plano de Estudos](/study-plan).",
            "intent": "cascade_study_plan",
        }

    # Salva plano no banco
    try:
        from docops.db import crud as _crud
        plan_record = _crud.create_study_plan_record(
            db,
            user_id=user_id,
            titulo=result["titulo"],
            doc_name=matched_doc.file_name,
            plan_text=result["plan_text"],
            tasks_created=result["tasks_created"],
            reminders_created=result["reminders_created"],
            sessions_count=result["sessions_count"],
            deck_id=result["deck_id"],
            hours_per_day=hours_per_day,
            deadline_date=deadline_iso,
        )
        logger.info("Cascade study plan: plano salvo (id=%d)", plan_record.id)
    except Exception as exc:
        logger.warning("Falha ao salvar plano de estudos no cascade: %s", exc)

    sessions = result["sessions_count"]
    tasks = result["tasks_created"]
    deck_note = " + flashcards criados" if result["deck_id"] else ""
    conflicts = result.get("conflicts", [])

    answer = (
        f"📚 Plano de estudos criado para **{matched_doc.file_name}**!\n\n"
        f"- ✅ **{tasks} tarefas** por tópico criadas\n"
        f"- 📅 **{sessions} sessões de estudo** no calendário ({hours_per_day:.0f}h/dia){deck_note}\n"
        f"- Prazo: **{deadline.strftime('%d/%m/%Y')}**\n\n"
        f"[Ver Plano →](/study-plan) · [Ver Tarefas →](/tasks) · [Ver Calendário →](/schedule)"
    )
    if result["deck_id"]:
        answer += " · [Flashcards →](/flashcards)"

    if conflicts:
        conflict_items = "\n".join(
            f"  - {c['date']}: sessão {c['session_time']} conflita com **{c['conflicting_with']}** ({c['conflicting_time']})"
            for c in conflicts[:3]
        )
        answer += f"\n\n⚠️ **{len(conflicts)} conflito(s) de horário detectado(s):**\n{conflict_items}"
        answer += "\nVerifique seu [Calendário →](/schedule) para ajustar se necessário."

    return {"answer": answer, "intent": "cascade_study_plan"}


# ---------------------------------------------------------------------------
# Cascade: Criar Nota
# ---------------------------------------------------------------------------

def _exec_cascade_create_note(entities: dict, user_id: int, db: Session, original_message: str) -> dict:
    """Cria uma nota com o conteúdo fornecido pelo usuário."""
    from docops.db import crud

    topic = entities.get("topic") or entities.get("task_title") or "Nota"
    content_raw = entities.get("content") or ""

    # Se o usuário não forneceu conteúdo, usa a mensagem original como corpo
    if not content_raw:
        content_raw = original_message

    title = f"Nota: {topic}"
    try:
        note = crud.create_note_record(
            db,
            user_id=user_id,
            title=title,
            content=content_raw,
        )
        return {
            "answer": (
                f"📝 Nota criada: **{note.title}**\n\n"
                f"[Ver Notas →](/notes)"
            ),
            "intent": "cascade_create_note",
        }
    except Exception as exc:
        logger.error("Falha ao criar nota: %s", exc)
        return {
            "answer": "Não foi possível criar a nota. Tente pela [página de Notas](/notes).",
            "intent": "cascade_create_note",
        }


def _exec_cascade_create_summary(entities: dict, user_id: int, db: Session) -> dict:
    """Orienta o usuário a criar um resumo via página de Artefatos."""
    doc_hint = entities.get("doc_hint") or ""

    if doc_hint:
        return {
            "answer": (
                f"📄 Para criar um resumo de **{doc_hint}**, acesse [Artefatos →](/artifacts) "
                f"e clique em **Resumir Documento**. Você pode escolher:\n\n"
                f"- **Resumo Breve** — síntese concisa com os pontos principais\n"
                f"- **Resumo Aprofundado** — análise detalhada seção por seção\n\n"
                f"O resumo será salvo automaticamente em seus artefatos."
            ),
            "intent": "cascade_create_summary",
        }
    return {
        "answer": (
            "📄 Para criar um resumo de um documento, acesse [Artefatos →](/artifacts) "
            "e clique em **Resumir Documento**.\n\n"
            "Você pode escolher entre Resumo Breve e Resumo Aprofundado."
        ),
        "intent": "cascade_create_summary",
    }


# ---------------------------------------------------------------------------
# Entry point principal
# ---------------------------------------------------------------------------

# Intents simples que delegam para o action_router existente (sem cascade)
_SIMPLE_INTENTS = {"create_task", "list_tasks", "flashcard_hint"}
# Intents que devem cair no RAG ou calendar_assistant
_PASSTHROUGH_INTENTS = {"rag", "calendar"}


def maybe_orchestrate(message: str, user_id: int, db: Session) -> dict | None:  # noqa: C901
    """Tenta orquestrar a mensagem com parser LLM + cascades.

    Returns:
        dict com 'answer' e 'intent' se a mensagem foi tratada,
        None para cair no fluxo seguinte (calendar_assistant → RAG).
    """
    # Mensagens muito curtas raramente são cascades — pula parser
    if len(message.strip()) < 10:
        return None

    # ── Verifica se há um plano de estudos pendente para este usuário ──────
    if user_id in _pending_study_plans:
        pending = _pending_study_plans[user_id]
        followup = _extract_followup_info(message)
        if followup:
            # Mescla o que o usuário respondeu com as entidades já coletadas
            merged_entities = {**pending["entities"], **followup}
            logger.info("Orchestrator: follow-up study_plan para user=%d, merged=%s", user_id, merged_entities)
            return _exec_cascade_study_plan(merged_entities, user_id, db)
        # Resposta não parseável — cancela o pending e trata normalmente
        _pending_study_plans.pop(user_id, None)

    parsed = _llm_parse(message)
    if not parsed:
        logger.debug("Parser LLM não retornou JSON válido.")
        return None

    intent = parsed.get("intent", "rag")
    entities = parsed.get("entities", {})

    logger.info("Orchestrator: intent=%s entities=%s", intent, entities)

    # Cascades multi-step
    if intent == "cascade_study_event":
        return _exec_cascade_study_event(entities, user_id, db)

    if intent == "cascade_study_plan":
        return _exec_cascade_study_plan(entities, user_id, db)

    if intent == "cascade_doc_review":
        return _exec_cascade_doc_review(entities, user_id, db)

    if intent == "cascade_task_deadline":
        return _exec_cascade_task_deadline(entities, user_id, db)

    if intent == "schedule_fc_reviews":
        return _exec_schedule_fc_reviews(entities, user_id, db)

    if intent == "cascade_create_note":
        return _exec_cascade_create_note(entities, user_id, db, message)

    if intent == "cascade_create_summary":
        return _exec_cascade_create_summary(entities, user_id, db)

    # Ações simples — delega pro action_router que já funciona bem com regex
    if intent in _SIMPLE_INTENTS:
        from docops.services.action_router import maybe_answer_action_query
        result = maybe_answer_action_query(message, user_id, db)
        if result:
            return result
        # Se regex não pegou, tenta executar baseado nas entidades do LLM
        if intent == "create_task":
            title = entities.get("task_title") or message.strip()
            from docops.services.action_router import _handle_create_task
            return _handle_create_task(title, user_id, db)
        if intent == "list_tasks":
            from docops.services.action_router import _handle_list_tasks
            return _handle_list_tasks(user_id, db)
        if intent == "flashcard_hint":
            hint = entities.get("doc_hint") or entities.get("deck_hint") or ""
            from docops.services.action_router import _handle_flashcard_hint
            return _handle_flashcard_hint(hint, user_id, db)

    # intent == "rag" ou "calendar" → retorna None para cair no fluxo normal
    return None
