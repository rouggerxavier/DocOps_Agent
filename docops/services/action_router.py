"""Roteador de ações cross-module para o chat.

Detecta comandos de ação na mensagem do usuário (criar tarefa, listar tarefas,
gerar flashcards) e os executa diretamente, sem passar pelo grafo RAG.

Padrão: retorna um dict com 'answer' e 'intent' se uma ação foi tomada,
ou None para cair no fluxo normal do RAG.
"""

from __future__ import annotations

import re
from sqlalchemy.orm import Session

from docops.logging import get_logger

logger = get_logger("docops.services.action_router")


# ── Padrões de detecção ───────────────────────────────────────────────────────

_TASK_CREATE = [
    re.compile(r"(?:cri(?:e|ar?|ou)|adiciona(?:r|e)?|nova?\s+tarefa|registra(?:r|e)?)[:\s]+(.{3,})", re.I),
    re.compile(r"^tarefa[:\s]+(.{3,})", re.I | re.M),
    re.compile(r"^to.?do[:\s]+(.{3,})", re.I | re.M),
    re.compile(r"lembrar?\s+(?:de\s+)?(.{5,})", re.I),
]

_LIST_TASKS = [
    re.compile(r"(?:lista(?:r|e)?|mostrar?|ver|exib(?:ir|e)?|quais?)\s+(?:minha[s]?\s+)?(?:tarefa[s]?|todo[s]?|afazere[s]?)", re.I),
    re.compile(r"(?:minha[s]?\s+)?tarefa[s]?\s*(?:pendente[s]?|abertas?|ativa[s]?)?$", re.I),
    re.compile(r"o\s+que\s+(?:tenho|preciso)\s+(?:fazer|estudar|entregar)", re.I),
    re.compile(r"(?:meu[s]?|minha[s]?)\s+(?:afazere[s]?|pendências?|lista\s+de\s+tarefa[s]?)", re.I),
]

_FC_GENERATE = [
    re.compile(r"(?:ger(?:e|ar?|ou)|cri(?:e|ar?|ou)|fazer?|faz)\s+flashcards?\s+(?:do?a?\s+|de\s+|sobre\s+|a\s+partir\s+de\s+)(.+)", re.I),
    re.compile(r"flashcards?\s+(?:do?a?\s+|de\s+|sobre\s+)(.+)", re.I),
    re.compile(r"(?:quero|gostaria\s+de)\s+(?:estudar|revisar)\s+(?:com\s+)?flashcards?\s+(?:do?a?\s+|de\s+|sobre\s+)(.+)", re.I),
]


# ── Entry point ───────────────────────────────────────────────────────────────

def maybe_answer_action_query(
    message: str, user_id: int, db: Session
) -> dict | None:
    """Detecta e executa comandos de ação cross-module.

    Returns:
        dict com 'answer' e 'intent' se uma ação foi detectada, None caso contrário.
    """
    # Criar tarefa
    for pattern in _TASK_CREATE:
        m = pattern.search(message)
        if m:
            title = m.group(1).strip()
            # Evita matches muito curtos ou que parecem ser frases completas sobre outro assunto
            if 3 <= len(title) <= 512 and not _looks_like_question(title):
                return _handle_create_task(title, user_id, db)

    # Listar tarefas
    for pattern in _LIST_TASKS:
        if pattern.search(message):
            return _handle_list_tasks(user_id, db)

    # Gerar flashcards
    for pattern in _FC_GENERATE:
        m = pattern.search(message)
        if m:
            doc_hint = m.group(1).strip().rstrip("?.,!").strip()
            if doc_hint:
                return _handle_flashcard_hint(doc_hint, user_id, db)

    return None


def _looks_like_question(text: str) -> bool:
    """Heurística simples para evitar confundir perguntas com títulos de tarefa."""
    return text.endswith("?") or text.lower().startswith(("o que", "como", "por que", "quando", "onde", "qual"))


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_create_task(title: str, user_id: int, db: Session) -> dict:
    from docops.db import crud
    try:
        task = crud.create_task_record(db, user_id=user_id, title=title, priority="normal")
        return {
            "answer": (
                f'✅ Tarefa criada: **"{task.title}"**\n\n'
                "Acesse a página de [Tarefas](/tasks) para ver, detalhar e marcar como concluída."
            ),
            "intent": "create_task",
        }
    except Exception as exc:
        logger.error("Falha ao criar tarefa via chat: %s", exc)
        return {
            "answer": "Não consegui criar a tarefa agora. Acesse a [página de Tarefas](/tasks) diretamente.",
            "intent": "create_task",
        }


def _handle_list_tasks(user_id: int, db: Session) -> dict:
    from docops.db import crud
    try:
        tasks = crud.list_tasks_for_user(db, user_id, status="pending")
        doing = crud.list_tasks_for_user(db, user_id, status="doing")
        all_active = (doing or []) + (tasks or [])

        if not all_active:
            all_tasks = crud.list_tasks_for_user(db, user_id)
            if not all_tasks:
                return {
                    "answer": (
                        "Você não tem tarefas ainda. Crie uma dizendo:\n\n"
                        "> **Tarefa: nome da tarefa**\n\n"
                        "Ou acesse a [página de Tarefas](/tasks)."
                    ),
                    "intent": "list_tasks",
                }
            return {
                "answer": (
                    f"Você tem **{len(all_tasks)} tarefa(s)** mas todas já estão concluídas! 🎉\n\n"
                    "[Ver histórico completo →](/tasks)"
                ),
                "intent": "list_tasks",
            }

        status_icons = {"pending": "🔲", "doing": "🔄", "done": "✅"}
        priority_icons = {"high": "🔴", "normal": "🟡", "low": "⚪"}

        lines = []
        for t in all_active[:10]:
            s_icon = status_icons.get(t.status, "🔲")
            p_icon = priority_icons.get(t.priority, "🟡")
            lines.append(f"{s_icon} {p_icon} {t.title}")

        answer = f"**Suas tarefas ativas** ({len(all_active)} total):\n\n" + "\n".join(lines)
        if len(all_active) > 10:
            answer += f"\n\n_...e mais {len(all_active) - 10} tarefas._"
        answer += "\n\n[Gerenciar todas as tarefas →](/tasks)"

        return {"answer": answer, "intent": "list_tasks"}

    except Exception as exc:
        logger.error("Falha ao listar tarefas via chat: %s", exc)
        return {
            "answer": "Não consegui carregar suas tarefas. Acesse a [página de Tarefas](/tasks) diretamente.",
            "intent": "list_tasks",
        }


def _handle_flashcard_hint(doc_hint: str, user_id: int, db: Session) -> dict:
    from docops.db import crud
    try:
        docs = crud.list_documents_for_user(db, user_id)
        if not docs:
            return {
                "answer": (
                    "Você ainda não inseriu nenhum documento. "
                    "Adicione um na [página de Inserção](/ingest) e depois gere flashcards."
                ),
                "intent": "flashcards_hint",
            }

        hint_lower = doc_hint.lower()
        matched = next(
            (d for d in docs if hint_lower in d.file_name.lower() or d.file_name.lower() in hint_lower),
            None,
        )

        if matched:
            return {
                "answer": (
                    f"Encontrei o documento **\"{matched.file_name}\"**!\n\n"
                    f"Acesse [Flashcards](/flashcards) → **Gerar Deck** e selecione esse documento.\n\n"
                    f"Ou use o **Smart Digest** na [página de Documentos](/docs) para gerar resumo + flashcards + tarefas de uma vez."
                ),
                "intent": "flashcards_hint",
            }

        doc_list = "\n".join(f"- {d.file_name}" for d in docs[:5])
        return {
            "answer": (
                f"Não encontrei nenhum documento com \"{doc_hint}\" no nome.\n\n"
                f"Seus documentos disponíveis:\n{doc_list}\n\n"
                "Acesse [Flashcards](/flashcards) para selecionar o documento correto."
            ),
            "intent": "flashcards_hint",
        }

    except Exception as exc:
        logger.error("Falha ao processar dica de flashcards via chat: %s", exc)
        return {
            "answer": "Acesse a [página de Flashcards](/flashcards) para gerar flashcards do seu documento.",
            "intent": "flashcards_hint",
        }
