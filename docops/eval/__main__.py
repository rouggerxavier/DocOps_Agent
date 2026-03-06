"""Run eval suites via `python -m docops.eval`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from docops.config import config
from eval.runner import EvalRunner, load_suite


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DocOps eval harness runner")
    parser.add_argument("--suite", required=True, help="Suite name or path to YAML file")
    parser.add_argument("--out", default="", help="Output report JSON path")
    parser.add_argument("--k", type=int, default=0, help="Override top_k")
    parser.add_argument(
        "--retrieval",
        default="",
        choices=["", "similarity", "mmr", "hybrid"],
        help="Retrieval mode override",
    )
    parser.add_argument(
        "--rerank",
        default="off",
        choices=["on", "off", "true", "false", "1", "0"],
        help="Enable reranker",
    )
    parser.add_argument("--seed", type=int, default=0, help="Seed (informational)")
    parser.add_argument("--strict", action="store_true", help="Strict factual citation mode")
    parser.add_argument("--max_cases", type=int, default=0, help="Limit number of cases")
    parser.add_argument("--mock", action="store_true", help="Mock mode (no LLM calls)")
    parser.add_argument(
        "--debug_grounding",
        "--debug-grounding",
        action="store_true",
        help="Enable grounding debug payloads while running eval.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("eval.log", encoding="utf-8"),
        ],
    )

    suite_path = Path(args.suite)
    if not suite_path.exists():
        candidate = config.eval_suites_dir / f"{args.suite}.yaml"
        if candidate.exists():
            suite_path = candidate
        else:
            print(f"Suite not found: {args.suite}", file=sys.stderr)
            return 1

    out_path = Path(args.out) if args.out else config.eval_output_dir / f"eval_{suite_path.stem}.json"
    rerank = args.rerank.lower() in {"on", "true", "1"}
    seed = args.seed or None
    max_cases = args.max_cases or None

    if args.debug_grounding:
        import os
        os.environ["DEBUG_GROUNDING"] = "true"

    agent_fn = None
    if args.mock:
        def _mock_agent(question: str) -> dict:
            return {
                "answer": (
                    "Nao encontrei informacao suficiente nos documentos para responder com seguranca."
                ),
                "retrieved_chunks": [],
            }
        agent_fn = _mock_agent

    runner = EvalRunner(
        suite_path=suite_path,
        top_k=args.k or config.top_k,
        retrieval=args.retrieval or config.retrieval_mode,
        rerank=rerank,
        seed=seed,
        strict=args.strict,
        max_cases=max_cases,
        agent_fn=agent_fn,
    )
    suite = load_suite(suite_path)
    report = runner.run()
    saved = runner.save(report, out_path)

    summary = report.summary
    print(f"Suite: {suite.suite_name}")
    print(f"Cases: {summary.get('total_cases', 0)}")
    print(f"Avg CitationCoverage: {summary.get('avg_citation_coverage', 0):.3f}")
    print(f"Avg CitationSupportRate: {summary.get('avg_citation_support_rate', 0):.3f}")
    print(f"Abstention accuracy: {summary.get('abstention_accuracy', 0):.3f}")
    print(f"Avg RetrievalRecall proxy: {summary.get('avg_retrieval_recall_proxy', 0):.3f}")
    print(f"Report: {saved}")

    if args.strict and summary.get("strict_pass_rate", 1.0) < 1.0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
