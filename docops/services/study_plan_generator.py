"""Gerador de plano de estudos integrado: LLM → tasks + reminders + flashcards.

Fluxo:
  1. Recupera chunks do documento
  2. LLM gera plano estruturado (JSON) com tópicos e sessões diárias
  3. Cria tarefas (uma por tópico) com due_date = prazo
  4. Cria lembretes de sessão de estudo (um por dia até o prazo)
  5. Gera flashcards + agenda revisões SRS após o prazo
  6. Detecta conflitos com a agenda semanal do usuário
  7. Retorna plano em markdown + estatísticas + conflitos
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from docops.logging import get_logger

logger = get_logger("docops.services.study_plan_generator")


# ---------------------------------------------------------------------------
# Prompt de geração
# ---------------------------------------------------------------------------

_STUDY_PLAN_PROMPT = """\
Você é um especialista em planejamento de estudos. Crie um plano de estudos baseado no conteúdo abaixo.

Dados do estudante:
- Documento: {doc_name}
- Horas por dia disponíveis: {hours_per_day}h
- Prazo final: {deadline_str} ({days_remaining} dias a partir de hoje, {today})
- Total estimado de horas de estudo: ~{total_hours:.0f}h
- Horário preferido de estudo: {preferred_start_time} (início das sessões)

Conteúdo do documento:
{content}

Retorne APENAS um JSON válido (sem markdown, sem texto extra).
Formato:
{{
  "titulo": "Plano de Estudos — {doc_name}",
  "resumo": "2-3 frases descrevendo o plano e como está distribuído",
  "topicos": [
    {{
      "nome": "Nome do tópico/capítulo",
      "horas": 2.0,
      "descricao": "O que estudar neste tópico",
      "prioridade": "high|normal|low"
    }}
  ],
  "sessoes": [
    {{
      "data": "YYYY-MM-DD",
      "inicio": "HH:MM",
      "fim": "HH:MM",
      "topico": "Nome do tópico desta sessão",
      "descricao": "O que fazer nesta sessão específica"
    }}
  ]
}}

Regras:
- Máximo 10 tópicos principais (agrupe capítulos/seções relacionados)
- Sessões: uma por dia de amanhã até o prazo, {hours_per_day:.0f}h cada, início às {preferred_start_time}
- Se days_remaining > 14: pode pular sábados e domingos para descanso
- Prioridade: "high" = fundamentos essenciais; "normal" = conteúdo principal; "low" = material complementar
- Distribua progressivamente: do básico ao avançado
- Se days_remaining < 5: intensifique, inclua fins de semana
- Adapte o ritmo ao prazo disponível
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time_to_minutes(t: str) -> int:
    """Converte 'HH:MM' em minutos desde meia-noite."""
    try:
        h, m = map(int, t.split(":"))
        return h * 60 + m
    except Exception:
        return 0


def _minutes_to_time(minutes: int) -> str:
    """Converte minutos desde meia-noite em 'HH:MM'."""
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def _check_time_conflicts(
    sessoes: list[dict],
    db: Session,
    user_id: int,
) -> list[dict]:
    """Detecta conflitos entre sessões e a agenda semanal fixa do usuário."""
    from docops.db.crud import list_schedules_for_user

    schedules = list_schedules_for_user(db, user_id, active_only=True)
    if not schedules:
        return []

    conflicts = []
    seen_dates: set[str] = set()

    for sessao in sessoes:
        data_str = sessao.get("data", "")
        if data_str in seen_dates:
            continue
        inicio = sessao.get("inicio", "20:00")
        fim = sessao.get("fim", "22:00")

        try:
            session_date = datetime.strptime(data_str, "%Y-%m-%d").date()
            day_of_week = session_date.weekday()

            s_start = _time_to_minutes(inicio)
            s_end = _time_to_minutes(fim)

            for sched in schedules:
                if int(sched.day_of_week) != day_of_week or not sched.active:
                    continue
                r_start = _time_to_minutes(sched.start_time)
                r_end = _time_to_minutes(sched.end_time)
                # Verifica sobreposição de intervalos
                if s_start < r_end and s_end > r_start:
                    conflicts.append({
                        "date": data_str,
                        "session_time": f"{inicio}–{fim}",
                        "conflicting_with": sched.title,
                        "conflicting_time": f"{sched.start_time}–{sched.end_time}",
                    })
                    seen_dates.add(data_str)
                    break
        except Exception:
            pass

    return conflicts


def _generate_plan_json(
    doc_name: str,
    content: str,
    hours_per_day: float,
    deadline: date,
    preferred_start_time: str = "20:00",
) -> dict:
    from docops.config import config
    from google import genai

    today = date.today()
    days_remaining = max((deadline - today).days, 1)
    total_hours = days_remaining * hours_per_day
    deadline_str = deadline.strftime("%d/%m/%Y")

    prompt = _STUDY_PLAN_PROMPT.format(
        doc_name=doc_name,
        hours_per_day=hours_per_day,
        deadline_str=deadline_str,
        today=today.isoformat(),
        days_remaining=days_remaining,
        total_hours=max(total_hours, hours_per_day),
        content=content[:10000],
        preferred_start_time=preferred_start_time,
    )

    client = genai.Client(api_key=config.gemini_api_key)
    model = getattr(config, "gemini_model_cheap", None) or config.gemini_model
    response = client.models.generate_content(model=model, contents=prompt)
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"Nenhum JSON encontrado na resposta do LLM: {text[:200]}")
    return json.loads(match.group(0))


def _build_plan_markdown(
    plan_data: dict,
    hours_per_day: float,
    deadline: date,
    tasks_created: int,
    reminders_created: int,
    brief_summary: str = "",
) -> str:
    titulo = plan_data.get("titulo", "Plano de Estudos")
    resumo = plan_data.get("resumo", "")
    topicos = plan_data.get("topicos", [])
    sessoes = plan_data.get("sessoes", [])

    lines = [f"# {titulo}", ""]

    if brief_summary:
        lines += ["## Visão Geral do Documento", "", brief_summary, ""]

    if resumo:
        lines += ["## Sobre o Plano", "", resumo, ""]

    if topicos:
        lines.append("## Tópicos do Plano")
        for i, t in enumerate(topicos, 1):
            pri_emoji = {"high": "🔴", "normal": "🟡", "low": "🟢"}.get(
                t.get("prioridade", "normal"), "🟡"
            )
            nome = t.get("nome", "")
            horas = t.get("horas", 0)
            lines.append(f"{i}. {pri_emoji} **{nome}** — {horas:.0f}h")
            if t.get("descricao"):
                lines.append(f"   _{t['descricao']}_")
        lines.append("")

    if sessoes:
        lines.append(f"## Sessões de Estudo ({len(sessoes)} no calendário)")
        for s in sessoes[:7]:
            lines.append(
                f"- **{s.get('data', '')}** {s.get('inicio', '')}–{s.get('fim', '')}: "
                f"{s.get('topico', '')}"
            )
        if len(sessoes) > 7:
            lines.append(f"- _... e mais {len(sessoes) - 7} sessões no calendário_")
        lines.append("")

    lines.append(
        f"**Prazo:** {deadline.strftime('%d/%m/%Y')} · "
        f"**{hours_per_day:.0f}h/dia** · "
        f"{tasks_created} tarefas criadas · "
        f"{reminders_created} sessões no calendário"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def generate_study_plan(
    doc_name: str,
    doc_id: str,
    user_id: int,
    hours_per_day: float,
    deadline: date,
    db: Session,
    generate_flashcards: bool = True,
    num_cards: int = 15,
    preferred_start_time: str = "20:00",
) -> dict:
    """Gera e persiste um plano de estudos completo para um documento.

    Returns dict com:
        plan_text, tasks_created, reminders_created, sessions_count,
        deck_id, titulo, conflicts
    """
    from docops.db import crud
    from docops.rag.retriever import retrieve_for_doc

    # 1. Recupera conteúdo
    chunks = retrieve_for_doc(
        doc_name,
        query="conteúdo principal, tópicos, capítulos, introdução",
        doc_id=doc_id,
        user_id=user_id,
        top_k=40,
    )
    if not chunks:
        raise ValueError(f"Nenhum chunk encontrado para '{doc_name}'.")

    content = "\n\n".join(c.page_content[:600] for c in chunks[:30])

    # 2. Gera plano via LLM
    plan_data = _generate_plan_json(doc_name, content, hours_per_day, deadline, preferred_start_time)
    titulo = plan_data.get("titulo", f"Plano de Estudos — {doc_name}")
    topicos = plan_data.get("topicos", [])
    sessoes = plan_data.get("sessoes", [])

    # 3. Gera resumo breve do documento
    brief_summary = ""
    try:
        from docops.graph.graph import run as graph_run
        state = graph_run(
            query=f"Faça um resumo breve (máx 150 palavras) do documento '{doc_name}' com os principais conceitos.",
            user_id=user_id,
            extra={"doc_name": doc_name, "doc_id": doc_id, "summary_mode": "brief"},
        )
        brief_summary = state.get("answer", "")
        # Remove aviso de grounding (não relevante num resumo interno do plano)
        brief_summary = re.sub(
            r"\n*⚠️\s*Aviso de baixa evidência[^\n]*\n?", "", brief_summary
        ).strip()
        logger.info("Study plan: resumo breve gerado (%d chars)", len(brief_summary))
    except Exception as exc:
        logger.warning("Falha ao gerar resumo breve no plano: %s", exc)

    # 4. Cria tarefas por tópico
    tasks_created = 0
    deadline_dt = datetime.combine(deadline, datetime.min.time()).replace(tzinfo=timezone.utc)
    for topico in topicos:
        nome = str(topico.get("nome", "")).strip()
        if not nome:
            continue
        prioridade = topico.get("prioridade", "normal")
        if prioridade not in ("high", "normal", "low"):
            prioridade = "normal"
        try:
            crud.create_task_record(
                db,
                user_id=user_id,
                title=f"Estudar: {nome}",
                note=topico.get("descricao") or None,
                priority=prioridade,
                due_date=deadline_dt,
            )
            tasks_created += 1
        except Exception as exc:
            logger.warning("Falha ao criar tarefa '%s': %s", nome, exc)

    # 5. Cria lembretes de sessão de estudo com horário preferido
    reminders_created = 0
    for sessao in sessoes:
        data_str = sessao.get("data", "")
        # Respeita o horário preferido do usuário
        inicio = preferred_start_time
        try:
            h_s, m_s = map(int, inicio.split(":"))
            h_e = h_s + int(hours_per_day)
            m_e = m_s + int((hours_per_day % 1) * 60)
            if m_e >= 60:
                h_e += 1
                m_e -= 60
            fim = f"{h_e % 24:02d}:{m_e:02d}"
        except Exception:
            fim = sessao.get("fim", "22:00")

        topico_nome = sessao.get("topico", "Estudo")
        descricao_sessao = sessao.get("descricao") or None
        try:
            session_date = datetime.strptime(data_str, "%Y-%m-%d").date()
            h_s, m_s = map(int, inicio.split(":"))
            h_e, m_e = map(int, fim.split(":"))
            starts_at = datetime(
                session_date.year, session_date.month, session_date.day,
                h_s, m_s, tzinfo=timezone.utc,
            )
            ends_at = datetime(
                session_date.year, session_date.month, session_date.day,
                h_e, m_e, tzinfo=timezone.utc,
            )
            crud.create_reminder_record(
                db,
                user_id=user_id,
                title=f"📖 Sessão: {topico_nome}",
                starts_at=starts_at,
                ends_at=ends_at,
                note=descricao_sessao,
            )
            # Atualiza sessão com horário real para uso posterior
            sessao["inicio"] = inicio
            sessao["fim"] = fim
            reminders_created += 1
        except Exception as exc:
            logger.warning("Falha ao criar lembrete '%s': %s", data_str, exc)

    # 6. Flashcards + SRS após prazo
    deck_id: Optional[int] = None
    if generate_flashcards:
        try:
            from docops.api.routes.flashcards import _generate_cards
            from docops.api.routes.pipeline import _schedule_srs_reminders

            cards = _generate_cards(
                doc_name=doc_name,
                doc_id=doc_id,
                user_id=user_id,
                num_cards=num_cards,
                difficulty_mode="any",
            )
            deck = crud.create_flashcard_deck(
                db,
                user_id=user_id,
                title=f"Flashcards — {doc_name}",
                source_doc=doc_name,
                cards=cards,
            )
            deck_id = deck.id
            logger.info("Study plan: deck criado (id=%s, %d cards)", deck_id, len(cards))
            _schedule_srs_reminders(deck_id, deck.title, user_id, db)
        except Exception as exc:
            logger.warning("Falha ao gerar flashcards no plano: %s", exc)

    # 7. Detecta conflitos com agenda semanal
    conflicts = _check_time_conflicts(sessoes, db, user_id)
    if conflicts:
        logger.info(
            "Study plan: %d conflitos de horário detectados para user=%d",
            len(conflicts), user_id,
        )

    # 8. Monta markdown
    plan_text = _build_plan_markdown(
        plan_data, hours_per_day, deadline, tasks_created, reminders_created, brief_summary,
    )

    logger.info(
        "Plano de estudos gerado: %d tópicos, %d tarefas, %d sessões, deck_id=%s, %d conflitos",
        len(topicos), tasks_created, reminders_created, deck_id, len(conflicts),
    )

    return {
        "plan_text": plan_text,
        "tasks_created": tasks_created,
        "reminders_created": reminders_created,
        "sessions_count": len(sessoes),
        "deck_id": deck_id,
        "titulo": titulo,
        "conflicts": conflicts,
    }
