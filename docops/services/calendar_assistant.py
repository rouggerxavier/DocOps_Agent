"""Calendar assistant — LLM-based intent detection and data extraction.

Replaces all keyword/regex matching with a single Gemini call that:
1. Classifies intent (read_calendar | create_reminder | create_schedule | none)
2. Extracts structured data as JSON

No keywords. No regex heuristics for intent. The LLM handles all linguistic variation.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from docops.db.crud import (
    create_reminder_record,
    create_schedule_record,
    list_reminders_for_user,
    list_schedules_for_user,
)

_WEEKDAY_NAMES = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]

# Prompt enviado ao Gemini para classificar e extrair dados do calendário
_CALENDAR_LLM_PROMPT = """\
Você é um assistente de calendário. Analise a mensagem do usuário e responda SOMENTE com JSON válido.

Hoje é {today}. Dia da semana de hoje: {today_weekday}.

Identifique a intenção e extraia dados conforme o esquema abaixo.

---

INTENÇÕES POSSÍVEIS:
- "none": não é relacionado a calendário/agenda/rotina/lembretes/cronograma
- "read_calendar": usuário quer saber o que tem na agenda (hoje, amanhã, semana, etc.)
- "create_reminder": usuário quer criar UM lembrete/evento pontual (data+hora específica)
- "create_schedule": usuário quer criar blocos fixos/recorrentes na semana (rotina semanal)
- "clarification_needed": a mensagem é ambígua e seria necessário perguntar de volta para agir corretamente

---

ESQUEMA JSON:

Para "none":
{{"intent": "none"}}

Para "clarification_needed":
{{"intent": "clarification_needed", "question": "pergunta de clarificação curta e direta"}}

Para "read_calendar":
{{"intent": "read_calendar", "target_date": "YYYY-MM-DD"}}

Para "create_reminder":
{{
  "intent": "create_reminder",
  "title": "título do lembrete",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM"
}}

Para "create_schedule":
{{
  "intent": "create_schedule",
  "blocks": [
    {{
      "title": "nome da atividade",
      "days": [0, 1, 2, 3, 4, 5, 6],
      "start_time": "HH:MM",
      "end_time": "HH:MM"
    }}
  ]
}}

LEGENDA de "days": 0=segunda, 1=terça, 2=quarta, 3=quinta, 4=sexta, 5=sábado, 6=domingo.

---

REGRAS IMPORTANTES:
- Responda APENAS com JSON. Nenhum texto antes ou depois.
- Para "create_schedule", extraia TODOS os blocos mencionados. Cada combinação única de (título, horário) vira um bloco com os dias correspondentes.
- Se o usuário disser "todo dia menos X", inclua todos os dias exceto X.
- Se o usuário disser "segunda a quinta", inclua segunda(0), terça(1), quarta(2), quinta(3).
- "horário livre" NÃO é um bloco — ignore.
- Datas relativas: "hoje"={today}, "amanhã"={tomorrow}, "próxima segunda"=calcule.
- Se a hora de fim não for mencionada, assuma 1 hora depois do início.
- Se a data não for mencionada para lembrete, assuma hoje.
- Se a mensagem for ambígua e você não conseguir extrair os dados necessários com confiança, use "clarification_needed" com uma pergunta direta e concisa. Exemplos: "Você quer criar um lembrete pontual ou um bloco recorrente na semana?", "Em qual data você quer o lembrete?"
- Só use "clarification_needed" quando for realmente impossível inferir a intenção. Se houver informação suficiente, mesmo que incompleta, tente extrair e use defaults razoáveis.

---

Mensagem do usuário: {message}
"""


def _local_tz():
    return datetime.now().astimezone().tzinfo or timezone.utc


def _call_gemini(prompt: str) -> str:
    """Call Gemini via LangChain and return raw text response."""
    from docops.llm.router import build_chat_model
    from langchain_core.messages import HumanMessage

    llm = build_chat_model(route="cheap", temperature=0.0)
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content
    # LangChain with Gemini may return a list of content blocks
    if isinstance(content, list):
        text_parts = [
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
            if not isinstance(block, dict) or block.get("type") == "text"
        ]
        return "".join(text_parts)
    return str(content)


def _parse_llm_json(raw: str) -> dict:
    """Extract JSON from LLM response, tolerating markdown code fences."""
    # Strip markdown code fences if present
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    return json.loads(text)


def maybe_answer_calendar_query(message: str, user_id: int, db: Session) -> dict | None:
    """
    Use Gemini to detect calendar intent and extract structured data.
    Returns a response dict if this is a calendar message, or None to pass through to RAG.
    """
    tz = _local_tz()
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)

    prompt = _CALENDAR_LLM_PROMPT.format(
        today=today.isoformat(),
        today_weekday=_WEEKDAY_NAMES[today.weekday()],
        tomorrow=tomorrow.isoformat(),
        message=message,
    )

    try:
        raw = _call_gemini(prompt)
        data = _parse_llm_json(raw)
    except Exception as exc:
        from docops.logging import get_logger
        get_logger("docops.services.calendar_assistant").warning(
            "LLM calendar parse failed: %s | raw=%r", exc, locals().get("raw", "")
        )
        return None

    intent = data.get("intent", "none")

    if intent == "none":
        return None

    if intent == "clarification_needed":
        question = data.get("question") or "Não entendi completamente. Pode dar mais detalhes sobre o que você quer fazer no calendário?"
        return {
            "answer": question,
            "intent": "calendar_clarification",
            "sources": [],
            "calendar_action": None,
        }

    if intent == "read_calendar":
        return _handle_read(data, user_id, db, today, tz)

    if intent == "create_reminder":
        return _handle_create_reminder(data, user_id, db, today, tz)

    if intent == "create_schedule":
        return _handle_create_schedule(data, user_id, db)

    return None


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_read(data: dict, user_id: int, db: Session, today: date, tz: Any) -> dict:
    raw_date = data.get("target_date")
    try:
        target_date = date.fromisoformat(raw_date) if raw_date else today
    except ValueError:
        target_date = today

    day_start = datetime.combine(target_date, time.min, tzinfo=tz)
    day_end = datetime.combine(target_date, time.max, tzinfo=tz)
    reminders = list_reminders_for_user(db, user_id, start_from=day_start, end_to=day_end)
    schedules = [
        item
        for item in list_schedules_for_user(db, user_id, active_only=True)
        if int(item.day_of_week) == int(target_date.weekday())
    ]
    schedules = sorted(schedules, key=lambda s: (s.start_time, s.end_time))

    date_label = target_date.strftime("%d/%m/%Y")
    if not reminders and not schedules:
        return {
            "answer": (
                f"Para {date_label}, não encontrei compromissos nem tarefas fixas no seu calendário.\n\n"
                "Posso criar lembretes ou blocos de cronograma para você — é só pedir!"
            ),
            "intent": "calendar",
            "sources": [],
            "calendar_action": None,
        }

    lines = [f"Para {date_label}, encontrei o seguinte no seu calendário:\n"]
    if reminders:
        lines.append("**Lembretes:**")
        for r in reminders:
            start_local = r.starts_at.astimezone(tz)
            hour_label = "dia inteiro" if r.all_day else start_local.strftime("%H:%M")
            extra = f" — {r.note}" if r.note else ""
            lines.append(f"- {hour_label} — {r.title}{extra}")
    if schedules:
        lines.append("\n**Cronograma fixo do dia:**")
        for s in schedules:
            extra = f" — {s.note}" if s.note else ""
            lines.append(f"- {s.start_time} às {s.end_time} — {s.title}{extra}")

    return {"answer": "\n".join(lines), "intent": "calendar", "sources": [], "calendar_action": None}


def _handle_create_reminder(data: dict, user_id: int, db: Session, today: date, tz: Any) -> dict:
    title = (data.get("title") or "Lembrete").strip()

    raw_date = data.get("date")
    try:
        target_date = date.fromisoformat(raw_date) if raw_date else today
    except ValueError:
        target_date = today

    raw_start = data.get("start_time", "09:00") or "09:00"
    raw_end = data.get("end_time") or ""

    try:
        sh, sm = (int(x) for x in raw_start.split(":"))
    except Exception:
        sh, sm = 9, 0
    try:
        eh, em = (int(x) for x in raw_end.split(":")) if raw_end else (min(sh + 1, 23), sm)
    except Exception:
        eh, em = min(sh + 1, 23), sm

    starts_at = datetime.combine(target_date, time(sh, sm), tzinfo=tz)
    ends_at = datetime.combine(target_date, time(eh, em), tzinfo=tz)

    reminder = create_reminder_record(
        db,
        user_id=user_id,
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=False,
    )

    date_label = target_date.strftime("%d/%m/%Y")
    time_label = f"{sh:02d}:{sm:02d}"
    return {
        "answer": f"✅ Lembrete criado com sucesso!\n\n**{title}**\n📅 {date_label} às {time_label}",
        "intent": "calendar_create_reminder",
        "sources": [],
        "calendar_action": {
            "type": "reminder_created",
            "id": reminder.id,
            "title": title,
            "date": date_label,
            "time": time_label,
        },
    }


def _handle_create_schedule(data: dict, user_id: int, db: Session) -> dict:
    blocks_data = data.get("blocks") or []

    if not blocks_data:
        return {
            "answer": (
                "Entendi que você quer criar um cronograma semanal, mas não consegui identificar "
                "os blocos. Tente descrever com dias e horários, por exemplo:\n\n"
                "> \"segunda e quarta das 8 às 10 academia, terça e quinta das 14 às 16 reunião\""
            ),
            "intent": "calendar_create_schedule",
            "sources": [],
            "calendar_action": None,
        }

    created = []
    for block in blocks_data:
        title = (block.get("title") or "Atividade").strip()
        days = block.get("days") or []
        raw_start = block.get("start_time", "08:00") or "08:00"
        raw_end = block.get("end_time", "09:00") or "09:00"

        # Normalize time format
        def _norm_time(t: str) -> str:
            parts = t.split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return f"{h:02d}:{m:02d}"

        start_time = _norm_time(raw_start)
        end_time = _norm_time(raw_end)

        for day in days:
            if not isinstance(day, int) or not (0 <= day <= 6):
                continue
            record = create_schedule_record(
                db,
                user_id=user_id,
                title=title,
                day_of_week=day,
                start_time=start_time,
                end_time=end_time,
                active=True,
            )
            created.append({
                "title": title,
                "day_of_week": day,
                "start_time": start_time,
                "end_time": end_time,
                "id": record.id,
            })

    lines = ["✅ Cronograma semanal criado!\n"]
    for b in created:
        day_name = _WEEKDAY_NAMES[b["day_of_week"]].capitalize()
        lines.append(f"- **{b['title']}** — {day_name}, {b['start_time']} às {b['end_time']}")

    return {
        "answer": "\n".join(lines),
        "intent": "calendar_create_schedule",
        "sources": [],
        "calendar_action": {
            "type": "schedule_created",
            "blocks": created,
        },
    }
