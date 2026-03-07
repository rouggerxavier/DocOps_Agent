"""LangGraph assembly: connects all nodes into the DocOps Agent graph."""

from typing import Any

from langgraph.graph import StateGraph, END

from docops.config import config
from docops.graph.state import AgentState
from docops.graph.nodes import (
    classify_intent,
    retrieve_node,
    synthesize,
    verify_grounding_node,
    retry_retrieve,
    finalize,
)
from docops.logging import get_logger

logger = get_logger("docops.graph.graph")


# ── Conditional edge: after verify_grounding ────────────────────────────────

def should_retry(state: AgentState) -> str:
    """Decide whether to retry retrieval or proceed to finalize."""
    if state.get("retry", False):
        return "retry"
    return "finalize"


# ── Build the graph ─────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Construct and compile the DocOps Agent graph."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("classify_intent", classify_intent)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("synthesize", synthesize)
    workflow.add_node("verify_grounding", verify_grounding_node)
    workflow.add_node("retry_retrieve", retry_retrieve)
    workflow.add_node("finalize", finalize)

    # Entry point
    workflow.set_entry_point("classify_intent")

    # Linear flow: classify → retrieve → synthesize → verify
    workflow.add_edge("classify_intent", "retrieve")
    workflow.add_edge("retrieve", "synthesize")
    workflow.add_edge("synthesize", "verify_grounding")

    # Conditional: retry or finalize
    workflow.add_conditional_edges(
        "verify_grounding",
        should_retry,
        {
            "retry": "retry_retrieve",
            "finalize": "finalize",
        },
    )

    # After retry: go back to retrieve
    workflow.add_edge("retry_retrieve", "retrieve")

    # End
    workflow.add_edge("finalize", END)

    return workflow.compile()


# Module-level compiled graph (lazy-initialized)
_graph = None


def get_graph():
    """Return the compiled graph, building it on first call."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run(
    query: str,
    top_k: int | None = None,
    extra: dict[str, Any] | None = None,
    user_id: int = 0,
) -> AgentState:
    """Run a single query through the agent graph and return the final state.

    Args:
        query: User's question or request.
        top_k: Override the default retrieval top_k.
        extra: Optional dict with intent-specific params (doc_name, topic, etc.).
        user_id: Authenticated user ID for multi-tenant isolation.

    Returns:
        The final AgentState with ``answer`` and ``sources_section`` populated.
    """
    graph = get_graph()

    initial_state: AgentState = {
        "query": query,
        "user_id": user_id,
        "top_k": top_k or config.top_k,
        "retry_count": 0,
        "repair_count": 0,
        "retry": False,
        "extra": extra or {},
    }

    logger.info(f"Running graph for user {user_id}, query: '{query[:80]}'")
    final_state = graph.invoke(initial_state)
    return final_state


def chat_loop() -> None:
    """Interactive CLI chat loop using the agent graph."""
    import json
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    console = Console()
    console.print(
        Panel(
            "[bold green]DocOps Agent[/bold green] -- Chat RAG\n"
            "[dim]Digite sua pergunta ou 'sair' para encerrar.[/dim]",
            border_style="green",
        )
    )

    while True:
        try:
            query = console.input("\n[bold cyan]Você:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Encerrando chat.[/dim]")
            break

        if not query:
            continue
        if query.lower() in {"sair", "exit", "quit", "q"}:
            console.print("[dim]Até logo![/dim]")
            break

        console.print("[dim]Processando...[/dim]")
        try:
            state = run(query)
            answer = state.get("answer", "Sem resposta.")
            console.print("\n[bold yellow]Agente:[/bold yellow]")
            console.print(Markdown(answer))
            if config.debug_grounding:
                grounding = state.get("grounding") or state.get("grounding_info")
                if grounding:
                    console.print(
                        Panel(
                            json.dumps(grounding, ensure_ascii=False, indent=2),
                            title="Grounding (debug)",
                            border_style="blue",
                        )
                    )
        except Exception as exc:
            console.print(f"[red]Erro: {exc}[/red]")
            logger.error(f"Graph execution failed: {exc}", exc_info=True)
