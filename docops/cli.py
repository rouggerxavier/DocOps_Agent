"""DocOps Agent CLI — entry point for all commands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="docops",
    help="DocOps Agent -- Operate over your documents with AI.",
    no_args_is_help=True,
)
console = Console()


def _check_api_key() -> None:
    """Fail early with a helpful message if GEMINI_API_KEY is missing."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        console.print(
            "[red]ERROR: GEMINI_API_KEY not set.[/red]\n"
            "Copy [bold].env.example[/bold] to [bold].env[/bold] and add your key,\n"
            "or export it: [bold]export GEMINI_API_KEY=your_key[/bold]"
        )
        raise typer.Exit(code=1)


# ── ingest ────────────────────────────────────────────────────────────────────

@app.command("ingest")
def ingest_cmd(
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Directory to ingest"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Single file to ingest"),
    chunk_size: int = typer.Option(0, "--chunk-size", help="Override chunk size"),
    chunk_overlap: int = typer.Option(0, "--chunk-overlap", help="Override chunk overlap"),
) -> None:
    """Ingest documents into the vector store."""
    _check_api_key()

    from docops.config import config
    from docops.ingestion.loaders import load_directory, load_file
    from docops.ingestion.splitter import split_documents
    from docops.ingestion.indexer import index_chunks

    cs = chunk_size or config.chunk_size
    co = chunk_overlap or config.chunk_overlap

    if file:
        if not file.exists():
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(code=1)
        console.print(f"[cyan]Loading file: {file}[/cyan]")
        docs = load_file(file)
    elif path:
        if not path.exists():
            console.print(f"[red]Directory not found: {path}[/red]")
            raise typer.Exit(code=1)
        console.print(f"[cyan]Loading directory: {path}[/cyan]")
        docs = load_directory(path)
    else:
        # Default to config.docs_dir
        docs_dir = config.docs_dir
        console.print(f"[cyan]Loading from default docs dir: {docs_dir}[/cyan]")
        docs = load_directory(docs_dir)

    if not docs:
        console.print(
            "[yellow]WARNING: No documents loaded. "
            "Add PDF, MD, or TXT files to your docs/ folder.[/yellow]"
        )
        raise typer.Exit(code=0)

    console.print(f"[green]OK: Loaded {len(docs)} document(s)[/green]")

    with console.status("Splitting into chunks..."):
        chunks = split_documents(docs, chunk_size=cs, chunk_overlap=co)
    console.print(f"[green]OK: Split into {len(chunks)} chunks[/green]")

    with console.status("Indexing into Chroma..."):
        count = index_chunks(chunks)
    console.print(f"[green]OK: Indexed {count} chunks[/green]")

    # Build BM25 index for hybrid search
    with console.status("Building BM25 index..."):
        from docops.rag.hybrid import build_bm25_index
        build_bm25_index(chunks)
    console.print("[green]OK: BM25 index built[/green]")

    console.print("[bold green]Ingestion complete![/bold green]")


# ── chat ──────────────────────────────────────────────────────────────────────

@app.command("chat")
def chat_cmd(
    debug_grounding: bool = typer.Option(
        False,
        "--debug-grounding",
        help="Show grounding verifier details in interactive chat.",
    ),
) -> None:
    """Start an interactive chat with your documents."""
    _check_api_key()

    if debug_grounding:
        import os
        os.environ["DEBUG_GROUNDING"] = "true"

    from docops.graph.graph import chat_loop

    console.print(
        Panel(
            "[bold]DocOps Agent[/bold] — RAG Chat\n"
            "[dim]Type your question. Type 'sair' or 'exit' to quit.[/dim]",
            border_style="green",
        )
    )
    chat_loop()


# ── list-docs ─────────────────────────────────────────────────────────────────

@app.command("list-docs")
def list_docs_cmd() -> None:
    """List all documents currently indexed in the vector store."""
    _check_api_key()

    from docops.tools.doc_tools import tool_list_docs

    docs = tool_list_docs()

    if not docs:
        console.print(
            "[yellow]No documents indexed yet. "
            "Run:[/yellow] [bold]python -m docops ingest --path docs/[/bold]"
        )
        return

    table = Table(title="Indexed Documents", border_style="green")
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Chunks", justify="right")
    table.add_column("Source")

    for doc in docs:
        table.add_row(
            doc["file_name"],
            str(doc["chunk_count"]),
            doc["source"],
        )

    console.print(table)


# ── summarize ────────────────────────────────────────────────────────────────

@app.command("summarize")
def summarize_cmd(
    doc: str = typer.Option(..., "--doc", "-d", help="Document file name to summarize"),
    save: bool = typer.Option(False, "--save", "-s", help="Save summary to artifacts/"),
) -> None:
    """Generate a structured summary for a specific document."""
    _check_api_key()

    from docops.graph.graph import run

    console.print(f"[cyan]Summarizing: {doc}[/cyan]")
    with console.status("Generating summary..."):
        state = run(
            query=f"Faça um resumo completo do documento {doc}",
            extra={"doc_name": doc},
        )
    answer = state.get("answer", "No answer generated.")
    console.print(Markdown(answer))

    if save:
        from docops.tools.doc_tools import tool_write_artifact
        stem = Path(doc).stem
        path = tool_write_artifact(f"summary_{stem}.md", answer)
        console.print(f"\n[green]Saved to {path}[/green]")


# ── compare ──────────────────────────────────────────────────────────────────

@app.command("compare")
def compare_cmd(
    doc1: str = typer.Option(..., "--doc1", help="First document file name"),
    doc2: str = typer.Option(..., "--doc2", help="Second document file name"),
    save: bool = typer.Option(False, "--save", "-s", help="Save comparison to artifacts/"),
) -> None:
    """Compare two documents side by side."""
    _check_api_key()

    from docops.rag.retriever import retrieve_for_doc
    from docops.rag.citations import build_context_block
    from docops.graph.graph import run

    console.print(f"[cyan]Comparing: {doc1} vs {doc2}[/cyan]")

    with console.status("Retrieving chunks..."):
        chunks2 = retrieve_for_doc(doc2, f"conteúdo principal de {doc2}")
        context2 = build_context_block(chunks2)

    with console.status("Generating comparison..."):
        state = run(
            query=f"Compare {doc1} e {doc2}",
            extra={
                "doc1": doc1,
                "doc2": doc2,
                "context2": context2,
            },
        )

    answer = state.get("answer", "No answer generated.")
    console.print(Markdown(answer))

    if save:
        from docops.tools.doc_tools import tool_write_artifact
        stem1 = Path(doc1).stem
        stem2 = Path(doc2).stem
        path = tool_write_artifact(f"comparison_{stem1}_vs_{stem2}.md", answer)
        console.print(f"\n[green]Saved to {path}[/green]")


# ── artifact ─────────────────────────────────────────────────────────────────

@app.command("artifact")
def artifact_cmd(
    type_: str = typer.Option(..., "--type", "-t", help="Artifact type: study_plan, summary, checklist"),
    topic: str = typer.Option(..., "--topic", help="Topic or subject for the artifact"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output filename"),
) -> None:
    """Generate and save a structured artifact (study plan, checklist, etc.)."""
    _check_api_key()

    from docops.graph.graph import run
    from docops.tools.doc_tools import tool_write_artifact

    intent_map = {
        "study_plan": "study_plan",
        "summary": "summary",
        "checklist": "checklist",
        "artifact": "artifact",
    }
    intent = intent_map.get(type_, "artifact")

    console.print(f"[cyan]Generating {type_}: {topic}[/cyan]")

    with console.status(f"Generating {type_}..."):
        state = run(
            query=f"Gere um {type_} sobre: {topic}",
            extra={"topic": topic},
        )

    answer = state.get("answer", "No answer generated.")
    console.print(Markdown(answer))

    fname = output or f"{type_}_{topic[:30].replace(' ', '_')}.md"
    path = tool_write_artifact(fname, answer)
    console.print(f"\n[green]Saved to {path}[/green]")


# ── eval ─────────────────────────────────────────────────────────────────────

@app.command("eval")
def eval_cmd(
    suite: str = typer.Option(..., "--suite", "-s", help="Suite name or path to YAML file"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output JSON path"),
    k: int = typer.Option(0, "--k", help="Override top_k for retrieval"),
    retrieval: str = typer.Option("", "--retrieval", help="Retrieval mode: similarity|mmr|hybrid"),
    rerank: str = typer.Option("off", "--rerank", help="Reranking: on|off"),
    seed: int = typer.Option(0, "--seed", help="Random seed (informational)"),
    strict: bool = typer.Option(False, "--strict", help="Fail if factual case lacks full citation coverage"),
    max_cases: int = typer.Option(0, "--max-cases", help="Limit number of cases to run"),
    mock: bool = typer.Option(False, "--mock", help="Use mock LLM (for CI, no API calls)"),
    debug_grounding: bool = typer.Option(
        False,
        "--debug-grounding",
        help="Enable grounding debug payloads while running eval.",
    ),
) -> None:
    """Run an eval suite and write a JSON report to artifacts/."""
    if not mock:
        _check_api_key()

    import logging
    import os

    if debug_grounding:
        os.environ["DEBUG_GROUNDING"] = "true"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("eval.log", encoding="utf-8"),
        ],
    )

    # Add project root to sys.path so `eval.runner` is importable
    import sys
    from pathlib import Path as _P

    project_root = _P(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from docops.config import config as cfg
    from eval.runner import EvalRunner, load_suite

    # Resolve suite path
    suite_path = _P(suite)
    if not suite_path.exists():
        candidate = cfg.eval_suites_dir / f"{suite}.yaml"
        if candidate.exists():
            suite_path = candidate
        else:
            console.print(f"[red]Suite not found: {suite}[/red]")
            raise typer.Exit(code=1)

    # Resolve output path
    out_path = _P(out) if out else cfg.eval_output_dir / f"eval_{suite_path.stem}.json"

    runner_kwargs: dict = {
        "suite_path": suite_path,
        "top_k": k or cfg.top_k,
        "retrieval": retrieval or cfg.retrieval_mode,
        "rerank": rerank.lower() in ("on", "true", "1"),
        "seed": seed or None,
        "strict": strict,
        "max_cases": max_cases or None,
    }

    if mock:
        console.print("[yellow]Mock mode: using stub agent (no API calls)[/yellow]")

        def _mock_agent(question: str) -> dict:
            return {
                "answer": (
                    "Não encontrei informação suficiente nos documentos para responder "
                    "essa pergunta com precisão."
                ),
                "retrieved_chunks": [],
            }

        runner_kwargs["agent_fn"] = _mock_agent

    runner = EvalRunner(**runner_kwargs)
    loaded = load_suite(suite_path)
    n_cases = min(len(loaded.cases), runner_kwargs.get("max_cases") or len(loaded.cases))

    console.print(
        Panel(
            f"[bold]DocOps Eval[/bold] — suite: [cyan]{loaded.suite_name}[/cyan]\n"
            f"[dim]{str(loaded.description).strip()[:120]}[/dim]\n\n"
            f"Cases: {n_cases} | top_k: {runner_kwargs['top_k']} | "
            f"retrieval: {runner_kwargs['retrieval']} | "
            f"rerank: {runner_kwargs['rerank']} | strict: {strict}",
            border_style="blue",
        )
    )

    with console.status("Running eval suite..."):
        report = runner.run()

    saved_path = runner.save(report, out_path)

    s = report.summary
    table = Table(title="Eval Summary", border_style="blue")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Total cases", str(s.get("total_cases", 0)))
    table.add_row("Errors", str(s.get("errors", 0)))
    table.add_row("Avg CitationCoverage", f"{s.get('avg_citation_coverage', 0):.3f}")
    table.add_row("Avg CitationSupportRate", f"{s.get('avg_citation_support_rate', 0):.3f}")
    table.add_row("Abstention accuracy", f"{s.get('abstention_accuracy', 0):.3f}")
    table.add_row("Avg RetrievalRecall proxy", f"{s.get('avg_retrieval_recall_proxy', 0):.3f}")
    table.add_row("MustCite pass rate", f"{s.get('must_cite_pass_rate', 0):.3f}")
    table.add_row("Expected match rate", f"{s.get('expected_match_rate', 0):.3f}")
    table.add_row("Strict pass rate", f"{s.get('strict_pass_rate', 0):.3f}")
    console.print(table)
    console.print(f"\n[green]Report saved to {saved_path}[/green]")

    if strict and s.get("strict_pass_rate", 1.0) < 1.0:
        console.print(
            "[red]STRICT MODE: strict_pass_rate < 1.0 — factual cases missing citations.[/red]"
        )
        raise typer.Exit(code=1)


# ── eval-summary ──────────────────────────────────────────────────────────────

@app.command("eval-summary")
def eval_summary_cmd(
    suite: str = typer.Option(
        "deep_summary_regression",
        "--suite",
        "-s",
        help="Suite name or path to deep-summary YAML file",
    ),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output JSON path"),
) -> None:
    """Run offline deep-summary regression suite (structure/coverage/grounding/citations)."""
    from docops.config import config as cfg
    from eval.deep_summary_runner import (
        DeepSummaryRegressionRunner,
        load_deep_summary_suite,
    )

    suite_path = Path(suite)
    if not suite_path.exists():
        candidate = cfg.eval_suites_dir / f"{suite}.yaml"
        if candidate.exists():
            suite_path = candidate
        else:
            console.print(f"[red]Deep-summary suite not found: {suite}[/red]")
            raise typer.Exit(code=1)

    out_path = Path(out) if out else cfg.eval_output_dir / f"eval_{suite_path.stem}.json"
    loaded = load_deep_summary_suite(suite_path)
    console.print(
        Panel(
            f"[bold]Deep Summary Regression[/bold]\n"
            f"Suite: [cyan]{loaded.suite_name}[/cyan]\n"
            f"Cases: {len(loaded.cases)}",
            border_style="blue",
        )
    )

    runner = DeepSummaryRegressionRunner(suite_path=suite_path)
    with console.status("Running deep-summary regression suite..."):
        report = runner.run()
    saved = runner.save(report, out_path)

    s = report.summary
    table = Table(title="Deep Summary Eval Summary", border_style="blue")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Total cases", str(s.get("total_cases", 0)))
    table.add_row("Passed", str(s.get("passed_cases", 0)))
    table.add_row("Failed", str(s.get("failed_cases", 0)))
    table.add_row("Pass rate", f"{s.get('pass_rate', 0):.3f}")
    table.add_row("Avg coverage", f"{s.get('avg_coverage_score', 0):.3f}")
    table.add_row("Avg weak grounding", f"{s.get('avg_weak_grounding_ratio', 0):.3f}")
    console.print(table)
    console.print(f"\n[green]Report saved to {saved}[/green]")

    if int(s.get("failed_cases", 0)) > 0:
        raise typer.Exit(code=1)


# ── serve ─────────────────────────────────────────────────────────────────────

@app.command("serve")
def serve_cmd(
    host: str = typer.Option("0.0.0.0", "--host", "-H", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes"),
) -> None:
    """Start the DocOps Agent FastAPI web server."""
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]ERROR: uvicorn not installed.[/red]\n"
            "Run: [bold]pip install uvicorn[standard][/bold]"
        )
        raise typer.Exit(code=1)

    console.print(
        Panel(
            f"[bold]DocOps Agent API[/bold]\n"
            f"[dim]http://{host}:{port}/api/health[/dim]\n"
            f"[dim]Swagger UI: http://{host}:{port}/api/docs-ui[/dim]",
            border_style="green",
        )
    )
    uvicorn.run(
        "docops.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


# ── Module entry point ────────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
