"""Benchmark reproduzível de deep summary por perfil de execução.

Uso:
    python eval/benchmark_deep_summary.py \
        --doc "documento.pdf" \
        --email user@example.com \
        --password senha \
        --profiles fast,balanced,model_first,model_first_plus,model_first_plus_max,strict \
        --runs 10 \
        --warmup 1

Saída: JSON + Markdown em artifacts/benchmarks/
"""
from __future__ import annotations

import argparse
import io
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# Ensure stdout/stderr use UTF-8 on Windows regardless of terminal encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUT_DIR = _REPO_ROOT / "artifacts" / "benchmarks"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _login(base_url: str, email: str, password: str) -> str:
    """POST /api/auth/login → Bearer token."""
    resp = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _summarize(
    base_url: str,
    token: str,
    doc: str,
    profile: str,
    timeout: int = 600,
) -> tuple[dict[str, Any], float]:
    """POST /api/summarize → (response_json, wall_ms).

    Returns (body_dict, elapsed_ms).  On HTTP error returns
    ({"error": ..., "status_code": ...}, elapsed_ms).
    """
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "doc": doc,
        "save": False,
        "summary_mode": "deep",
        "debug_summary": True,
        "deep_profile": profile,
    }
    t0 = time.monotonic()
    try:
        resp = requests.post(
            f"{base_url}/api/summarize",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        if resp.status_code in (200, 422):  # 422 = strict fail-closed
            body = resp.json()
            if isinstance(body, dict) and "status_code" not in body:
                body = {**body, "status_code": resp.status_code}
            return body, elapsed_ms
        return {"error": resp.text, "status_code": resp.status_code}, elapsed_ms
    except requests.Timeout:
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        return {"error": "timeout", "status_code": 0}, elapsed_ms
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        return {"error": str(exc), "status_code": 0}, elapsed_ms


# ---------------------------------------------------------------------------
# Metrics extraction helpers
# ---------------------------------------------------------------------------

def _safe(d: Any, *keys: str, default: Any = None) -> Any:
    """Safe nested dict access."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
        if cur is None:
            return default
    return cur


def _extract_run_metrics(body: dict[str, Any], wall_ms: float) -> dict[str, Any]:
    """Extract scalar quality/latency metrics from one summarize response."""
    diag = body.get("summary_diagnostics") or {}
    error = body.get("error")
    status_code = body.get("status_code", 200)
    detail = body.get("detail", {})

    # HTTP-level error or timeout
    if error and not diag:
        return {
            "wall_ms": wall_ms,
            "error": error,
            "status_code": status_code,
            "accepted": False,
            # fill remaining with None
            "weak_ratio": None,
            "outline_coverage_score": None,
            "rubric_score": None,
            "inference_density": None,
            "corrective_passes_used": None,
            "blocking_reasons": [],
            "deoverreach_triggered": None,
            "deoverreach_accepted": None,
            "resynthesis_triggered": None,
            "resynthesis_accepted": None,
            "internal_total_ms": None,
            "stage_timings_ms": {},
        }

    # strict fail-closed can arrive with/without explicit status_code in body
    strict_fail_closed = (
        status_code == 422
        or (
            not diag
            and isinstance(detail, dict)
            and detail.get("error") == "deep_summary_quality_gate_failed"
        )
    )
    if strict_fail_closed and not diag:
        return {
            "wall_ms": wall_ms,
            "error": "strict_fail_closed_422",
            "status_code": 422,
            "accepted": False,
            "blocking_reasons": detail.get("blocking_reasons", []),
            "weak_ratio": None,
            "outline_coverage_score": None,
            "rubric_score": None,
            "inference_density": None,
            "corrective_passes_used": None,
            "deoverreach_triggered": None,
            "deoverreach_accepted": None,
            "resynthesis_triggered": None,
            "resynthesis_accepted": None,
            "internal_total_ms": None,
            "stage_timings_ms": {},
        }

    final = diag.get("final", {}) or {}
    grounding = diag.get("grounding", {}) or {}
    deoverreach = diag.get("deoverreach", {}) or {}
    resynthesis = diag.get("resynthesis", {}) or {}
    latency = diag.get("latency", {}) or {}
    rubric = diag.get("rubric", {}) or {}
    rubric_overall = _safe(rubric, "overall_score")

    return {
        "wall_ms": wall_ms,
        "error": None,
        "status_code": status_code,
        # quality
        "accepted": bool(final.get("accepted", False)),
        "blocking_reasons": final.get("blocking_reasons") or [],
        "weak_ratio": _safe(grounding, "weak_ratio"),
        "outline_coverage_score": _safe(diag, "outline_coverage", "score"),
        "rubric_score": (
            rubric_overall if rubric_overall is not None else _safe(diag, "rubric_score")
        ),
        "inference_density": _safe(diag, "inference_density", "inference_density"),
        # corrective cost
        "corrective_passes_used": diag.get("corrective_passes_used"),
        "deoverreach_triggered": _safe(deoverreach, "triggered"),
        "deoverreach_accepted": _safe(deoverreach, "accepted"),
        "resynthesis_triggered": resynthesis.get("triggered") if isinstance(resynthesis, dict) else None,
        "resynthesis_accepted": resynthesis.get("accepted") if isinstance(resynthesis, dict) else None,
        # internal timing
        "internal_total_ms": latency.get("total_ms"),
        "stage_timings_ms": latency.get("stage_timings_ms") or {},
    }


# ---------------------------------------------------------------------------
# Statistical aggregation
# ---------------------------------------------------------------------------

def _percentile(data: list[float], p: float) -> float | None:
    """p-th percentile (0-100) of sorted list."""
    if not data:
        return None
    data_s = sorted(data)
    idx = (p / 100) * (len(data_s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(data_s) - 1)
    frac = idx - lo
    return round(data_s[lo] + frac * (data_s[hi] - data_s[lo]), 1)


def _json_sanitize(value: Any) -> Any:
    """Convert non-JSON-safe floats (NaN/Inf) to None recursively."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: _json_sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_sanitize(v) for v in value]
    return value


def _mean_notnone(values: list[Any]) -> float | None:
    nums = [v for v in values if v is not None]
    return round(statistics.mean(nums), 4) if nums else None


def _rate(values: list[Any]) -> float | None:
    bools = [bool(v) for v in values if v is not None]
    return round(sum(bools) / len(bools), 4) if bools else None


def _blocking_dist(runs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in runs:
        for reason in r.get("blocking_reasons") or []:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _stage_means(runs: list[dict[str, Any]]) -> dict[str, float | None]:
    all_stages: dict[str, list[float]] = {}
    for r in runs:
        for stage, ms in (r.get("stage_timings_ms") or {}).items():
            all_stages.setdefault(stage, []).append(ms)
    return {s: _mean_notnone(vals) for s, vals in all_stages.items()}


def aggregate_profile(
    profile: str,
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute aggregate statistics for one profile's runs."""
    wall_times = [r["wall_ms"] for r in runs if r.get("error") is None]

    return {
        "profile": profile,
        "n_runs": len(runs),
        "n_errors": sum(1 for r in runs if r.get("error") is not None),
        # latency (wall clock)
        "latency": {
            "mean_ms": _mean_notnone(wall_times),
            "median_ms": _percentile(wall_times, 50),
            "p90_ms": _percentile(wall_times, 90),
            "p95_ms": _percentile(wall_times, 95),
            "min_ms": round(min(wall_times), 1) if wall_times else None,
            "max_ms": round(max(wall_times), 1) if wall_times else None,
        },
        # quality
        "quality": {
            "accepted_rate": _rate([r["accepted"] for r in runs]),
            "mean_weak_ratio": _mean_notnone([r["weak_ratio"] for r in runs]),
            "mean_outline_coverage": _mean_notnone([r["outline_coverage_score"] for r in runs]),
            "mean_rubric_score": _mean_notnone([r["rubric_score"] for r in runs]),
            "mean_inference_density": _mean_notnone([r["inference_density"] for r in runs]),
            "blocking_distribution": _blocking_dist(runs),
        },
        # corrective cost
        "corrective": {
            "mean_passes_used": _mean_notnone([r["corrective_passes_used"] for r in runs]),
            "deoverreach_trigger_rate": _rate([r["deoverreach_triggered"] for r in runs]),
            "deoverreach_accept_rate": _rate([r["deoverreach_accepted"] for r in runs]),
            "resynthesis_trigger_rate": _rate([r["resynthesis_triggered"] for r in runs]),
            "resynthesis_accept_rate": _rate([r["resynthesis_accepted"] for r in runs]),
        },
        # internal timing
        "internal_latency": {
            "mean_total_ms": _mean_notnone([r["internal_total_ms"] for r in runs]),
            "mean_stage_ms": _stage_means(runs),
        },
    }


# ---------------------------------------------------------------------------
# Recommendation rule
# ---------------------------------------------------------------------------

def recommend_profile(aggregates: list[dict[str, Any]], threshold: float = 0.8) -> dict[str, Any]:
    """Choose best profile given aggregates.

    Rule:
    1. Filter profiles with accepted_rate >= threshold.
    2. Among those, pick the one with lowest p95_ms.
    3. If none qualify, pick highest accepted_rate and flag risk.
    """
    qualified = [
        agg for agg in aggregates
        if (agg["quality"]["accepted_rate"] or 0.0) >= threshold
    ]
    risk = len(qualified) == 0

    candidates = qualified if qualified else aggregates

    def _sort_key(agg: dict[str, Any]) -> tuple[float, float]:
        ar = agg["quality"]["accepted_rate"] or 0.0
        p95 = agg["latency"]["p95_ms"] or float("inf")
        if risk:
            return (-ar, p95)
        return (p95, -ar)

    best = min(candidates, key=_sort_key)

    return {
        "recommended_profile": best["profile"],
        "accepted_rate_threshold": threshold,
        "qualified_profiles": [a["profile"] for a in qualified],
        "risk": risk,
        "risk_message": (
            f"Nenhum perfil atingiu accepted_rate >= {threshold:.0%}. "
            "Recomendação com base em maior accepted_rate — revisar quality gates."
            if risk else None
        ),
        "reasoning": (
            f"Menor p95_ms ({best['latency']['p95_ms']} ms) "
            f"entre perfis com accepted_rate >= {threshold:.0%}."
            if not risk else
            f"Maior accepted_rate ({best['quality']['accepted_rate']:.1%}) — risk flag ativo."
        ),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt(v: Any, fmt: str = ".1f") -> str:
    if v is None:
        return "N/A"
    try:
        return f"{v:{fmt}}"
    except Exception:  # noqa: BLE001
        return str(v)


def build_markdown_report(
    doc: str,
    aggregates: list[dict[str, Any]],
    recommendation: dict[str, Any],
    meta: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# Benchmark Deep Summary — Relatório Comparativo")
    lines.append("")
    lines.append(f"**Documento:** `{doc}`  ")
    lines.append(f"**Data:** {meta['timestamp']}  ")
    lines.append(f"**Rodadas por perfil:** {meta['runs_per_profile']}  ")
    lines.append(f"**Warmup:** {meta['warmup_runs']}  ")
    lines.append(f"**Servidor:** `{meta['base_url']}`")
    lines.append("")

    # ── Latência ──────────────────────────────────────────────────────────
    lines.append("## Latência (wall-clock, ms)")
    lines.append("")
    lines.append("| Perfil | mean | median | p90 | p95 | min | max | erros |")
    lines.append("|--------|-----:|-------:|----:|----:|----:|----:|------:|")
    for agg in aggregates:
        lat = agg["latency"]
        lines.append(
            f"| **{agg['profile']}** "
            f"| {_fmt(lat['mean_ms'])} "
            f"| {_fmt(lat['median_ms'])} "
            f"| {_fmt(lat['p90_ms'])} "
            f"| {_fmt(lat['p95_ms'])} "
            f"| {_fmt(lat['min_ms'])} "
            f"| {_fmt(lat['max_ms'])} "
            f"| {agg['n_errors']} |"
        )
    lines.append("")

    # ── Qualidade ─────────────────────────────────────────────────────────
    lines.append("## Qualidade")
    lines.append("")
    lines.append("| Perfil | accepted_rate | weak_ratio | outline_cov | rubric | inf_density |")
    lines.append("|--------|-------------:|-----------:|------------:|-------:|------------:|")
    for agg in aggregates:
        q = agg["quality"]
        lines.append(
            f"| **{agg['profile']}** "
            f"| {_fmt(q['accepted_rate'], '.1%')} "
            f"| {_fmt(q['mean_weak_ratio'], '.3f')} "
            f"| {_fmt(q['mean_outline_coverage'], '.3f')} "
            f"| {_fmt(q['mean_rubric_score'], '.3f')} "
            f"| {_fmt(q['mean_inference_density'], '.3f')} |"
        )
    lines.append("")

    # ── Custo corretivo ───────────────────────────────────────────────────
    lines.append("## Custo Corretivo")
    lines.append("")
    lines.append("| Perfil | passes_médio | deoverreach_trig | deoverreach_acc | resynth_trig | resynth_acc |")
    lines.append("|--------|------------:|-----------------:|----------------:|-------------:|------------:|")
    for agg in aggregates:
        c = agg["corrective"]
        lines.append(
            f"| **{agg['profile']}** "
            f"| {_fmt(c['mean_passes_used'], '.2f')} "
            f"| {_fmt(c['deoverreach_trigger_rate'], '.1%')} "
            f"| {_fmt(c['deoverreach_accept_rate'], '.1%')} "
            f"| {_fmt(c['resynthesis_trigger_rate'], '.1%')} "
            f"| {_fmt(c['resynthesis_accept_rate'], '.1%')} |"
        )
    lines.append("")

    # ── Timing interno ────────────────────────────────────────────────────
    lines.append("## Timing Interno (diagnóstico, médias em ms)")
    lines.append("")
    all_stages: list[str] = []
    for agg in aggregates:
        for s in (agg["internal_latency"]["mean_stage_ms"] or {}):
            if s not in all_stages:
                all_stages.append(s)

    if all_stages:
        header = "| Perfil | total_ms | " + " | ".join(all_stages) + " |"
        sep = "|--------|--------:|" + "|".join(["-------:"] * len(all_stages)) + "|"
        lines.append(header)
        lines.append(sep)
        for agg in aggregates:
            il = agg["internal_latency"]
            stage_cells = " | ".join(
                _fmt(il["mean_stage_ms"].get(s), ".1f") for s in all_stages
            )
            lines.append(
                f"| **{agg['profile']}** "
                f"| {_fmt(il['mean_total_ms'], '.1f')} "
                f"| {stage_cells} |"
            )
        lines.append("")

    # ── Blocking reasons ─────────────────────────────────────────────────
    has_blocking = any(
        agg["quality"]["blocking_distribution"] for agg in aggregates
    )
    if has_blocking:
        lines.append("## Distribuição de Blocking Reasons")
        lines.append("")
        for agg in aggregates:
            bd = agg["quality"]["blocking_distribution"]
            if bd:
                lines.append(f"### {agg['profile']}")
                for reason, count in sorted(bd.items(), key=lambda x: -x[1]):
                    lines.append(f"- `{reason}`: {count}×")
                lines.append("")

    # ── Recomendação ──────────────────────────────────────────────────────
    lines.append("## Recomendação de Perfil Default")
    lines.append("")
    rec = recommendation
    if rec["risk"]:
        lines.append(f"> **[RISCO]:** {rec['risk_message']}")
        lines.append("")
    lines.append(f"**Perfil recomendado: `{rec['recommended_profile']}`**")
    lines.append("")
    lines.append(f"- Threshold accepted_rate: {rec['accepted_rate_threshold']:.0%}")
    lines.append(f"- Perfis qualificados: {', '.join(rec['qualified_profiles']) or 'nenhum'}")
    lines.append(f"- Critério: {rec['reasoning']}")
    lines.append("")

    return "\n".join(lines)


def print_terminal_summary(
    aggregates: list[dict[str, Any]],
    recommendation: dict[str, Any],
) -> None:
    print("\n" + "=" * 70)
    print("  BENCHMARK DEEP SUMMARY — RESUMO")
    print("=" * 70)
    print(f"{'Perfil':<12} {'p95_ms':>8} {'accepted':>9} {'weak_ratio':>11} {'passes':>7}")
    print("-" * 52)
    for agg in aggregates:
        p95 = agg["latency"]["p95_ms"]
        ar = agg["quality"]["accepted_rate"]
        wr = agg["quality"]["mean_weak_ratio"]
        cp = agg["corrective"]["mean_passes_used"]
        print(
            f"{agg['profile']:<12} "
            f"{_fmt(p95):>8} "
            f"{_fmt(ar, '.1%'):>9} "
            f"{_fmt(wr, '.3f'):>11} "
            f"{_fmt(cp, '.2f'):>7}"
        )
    rec = recommendation
    print("-" * 52)
    flag = " [RISCO]" if rec["risk"] else ""
    print(f"\n→ Recomendado: {rec['recommended_profile']}{flag}")
    print(f"  {rec['reasoning']}")
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(
    doc: str,
    profiles: list[str],
    runs: int,
    warmup: int,
    base_url: str,
    email: str,
    password: str,
    out_json: Path,
    out_md: Path,
    accepted_threshold: float = 0.8,
) -> dict[str, Any]:
    print(f"\n[benchmark] Login em {base_url} ...")
    token = _login(base_url, email, password)
    print(f"[benchmark] Autenticado. Documento: {doc!r}")
    print(f"[benchmark] Perfis: {profiles}  |  Runs: {runs}  |  Warmup: {warmup}")

    all_profile_runs: dict[str, list[dict[str, Any]]] = {}

    for profile in profiles:
        print(f"\n[benchmark] === Perfil: {profile} ===")

        # warmup
        if warmup > 0:
            print(f"[benchmark]   Warmup ({warmup} rodada(s))...")
            for _ in range(warmup):
                _summarize(base_url, token, doc, profile)

        # measured runs
        runs_data: list[dict[str, Any]] = []
        for i in range(runs):
            body, wall_ms = _summarize(base_url, token, doc, profile)
            metrics = _extract_run_metrics(body, wall_ms)
            runs_data.append(metrics)
            status = "OK" if metrics["accepted"] else ("--" if not metrics.get("error") else "ERR")
            print(
                f"[benchmark]   run {i+1:2d}/{runs}  "
                f"{status}  wall={wall_ms:.0f}ms  "
                f"passes={metrics['corrective_passes_used']}"
            )

        all_profile_runs[profile] = runs_data

    # aggregate
    aggregates = [
        aggregate_profile(p, runs_data)
        for p, runs_data in all_profile_runs.items()
    ]
    recommendation = recommend_profile(aggregates, threshold=accepted_threshold)

    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "doc": doc,
        "profiles": profiles,
        "runs_per_profile": runs,
        "warmup_runs": warmup,
        "base_url": base_url,
        "accepted_threshold": accepted_threshold,
    }

    report = {
        "meta": meta,
        "aggregates": aggregates,
        "recommendation": recommendation,
        "runs": {p: all_profile_runs[p] for p in profiles},
    }

    # save outputs
    out_json.parent.mkdir(parents=True, exist_ok=True)
    safe_report = _json_sanitize(report)
    out_json.write_text(
        json.dumps(safe_report, indent=2, ensure_ascii=True, allow_nan=False),
        encoding="utf-8",
    )
    print(f"\n[benchmark] JSON → {out_json}")

    md_text = build_markdown_report(doc, aggregates, recommendation, meta)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md_text, encoding="utf-8", errors="replace")
    print(f"[benchmark] MD  → {out_md}")

    print_terminal_summary(aggregates, recommendation)
    return safe_report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Benchmark reproduzível de deep summary por perfil.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--doc", required=True, help="Nome do documento no sistema (file_name).")
    p.add_argument("--profiles", default="fast,balanced,model_first,model_first_plus,model_first_plus_max,strict",
                   help="Perfis separados por vírgula.")
    p.add_argument("--runs", type=int, default=10, help="Rodadas medidas por perfil.")
    p.add_argument("--warmup", type=int, default=1, help="Rodadas de warmup por perfil.")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL da API.")
    p.add_argument("--email", required=True, help="E-mail do usuário para login.")
    p.add_argument("--password", required=True, help="Senha do usuário para login.")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p.add_argument("--out-json",
                   default=str(_DEFAULT_OUT_DIR / f"benchmark_{ts}.json"),
                   help="Caminho do relatório JSON.")
    p.add_argument("--out-md",
                   default=str(_DEFAULT_OUT_DIR / f"benchmark_{ts}.md"),
                   help="Caminho do relatório Markdown.")
    p.add_argument("--accepted-threshold", type=float, default=0.8,
                   help="Taxa mínima de accepted para qualificar perfil na recomendação.")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    if not profiles:
        print("ERRO: --profiles não pode estar vazio.", file=sys.stderr)
        return 1

    run_benchmark(
        doc=args.doc,
        profiles=profiles,
        runs=args.runs,
        warmup=args.warmup,
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        out_json=Path(args.out_json),
        out_md=Path(args.out_md),
        accepted_threshold=args.accepted_threshold,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
