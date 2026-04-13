"""Reusable template catalog and helpers for artifact generation."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ArtifactTemplate:
    template_id: str
    label: str
    short_description: str
    long_description: str
    preview_title: str
    preview_sections: tuple[str, ...]
    artifact_types: tuple[str, ...]
    summary_modes: tuple[str, ...]
    default_for_summary_modes: tuple[str, ...]
    default_for_artifact_types: tuple[str, ...]
    prompt_directive: str

    def to_payload(self) -> dict[str, object]:
        return {
            "template_id": self.template_id,
            "label": self.label,
            "short_description": self.short_description,
            "long_description": self.long_description,
            "preview_title": self.preview_title,
            "preview_sections": list(self.preview_sections),
            "artifact_types": list(self.artifact_types),
            "summary_modes": list(self.summary_modes),
            "default_for_summary_modes": list(self.default_for_summary_modes),
            "default_for_artifact_types": list(self.default_for_artifact_types),
        }


_TEMPLATES: tuple[ArtifactTemplate, ...] = (
    ArtifactTemplate(
        template_id="brief",
        label="Brief de Estudo",
        short_description="Sintese objetiva para revisao rapida.",
        long_description=(
            "Template enxuto para estudar rapido, com foco em mensagem central, "
            "pontos-chave e proximos passos."
        ),
        preview_title="Estrutura do Brief",
        preview_sections=(
            "Resumo executivo",
            "Pontos-chave",
            "Checklist de revisao",
        ),
        artifact_types=("summary", "checklist", "artifact"),
        summary_modes=("brief",),
        default_for_summary_modes=("brief",),
        default_for_artifact_types=(),
        prompt_directive=(
            "Use uma estrutura concisa com secoes: Resumo executivo, "
            "Pontos-chave e Checklist de revisao."
        ),
    ),
    ArtifactTemplate(
        template_id="exam_pack",
        label="Exam Prep Pack",
        short_description="Pacote pronto para prova com foco pratico.",
        long_description=(
            "Template orientado a desempenho: conceitos que mais caem, "
            "armadilhas e trilha de treino."
        ),
        preview_title="Estrutura do Exam Pack",
        preview_sections=(
            "Mapa da prova",
            "Conceitos que mais caem",
            "Erros comuns e como evitar",
            "Plano de treino",
        ),
        artifact_types=("summary", "checklist", "artifact"),
        summary_modes=("brief", "deep"),
        default_for_summary_modes=(),
        default_for_artifact_types=("checklist", "artifact"),
        prompt_directive=(
            "Estruture como pacote de preparacao para prova, destacando "
            "prioridades de estudo, riscos e plano de treino."
        ),
    ),
    ArtifactTemplate(
        template_id="deep_dossier",
        label="Dossie Analitico",
        short_description="Analise profunda para estudo avancado.",
        long_description=(
            "Template para aprofundamento tecnico, com decomposicao por tema, "
            "evidencias e lacunas."
        ),
        preview_title="Estrutura do Dossie",
        preview_sections=(
            "Contexto e objetivo",
            "Analise por tema",
            "Evidencias e limitacoes",
            "Plano de consolidacao",
        ),
        artifact_types=("summary", "artifact"),
        summary_modes=("deep",),
        default_for_summary_modes=("deep",),
        default_for_artifact_types=(),
        prompt_directive=(
            "Entregue uma analise aprofundada por temas, incluindo evidencias, "
            "limitacoes e plano de consolidacao."
        ),
    ),
)

_TEMPLATE_INDEX = {item.template_id: item for item in _TEMPLATES}

_DEFAULT_BY_SUMMARY_MODE = {
    "brief": "brief",
    "deep": "deep_dossier",
}
_DEFAULT_BY_ARTIFACT_TYPE = {
    "checklist": "exam_pack",
    "artifact": "exam_pack",
    "summary": "brief",
}


def list_template_payloads(
    *,
    summary_mode: str | None = None,
    artifact_type: str | None = None,
) -> list[dict[str, object]]:
    selected: list[ArtifactTemplate] = []
    for template in _TEMPLATES:
        if summary_mode and summary_mode not in template.summary_modes:
            continue
        if artifact_type and artifact_type not in template.artifact_types:
            continue
        selected.append(template)
    return [item.to_payload() for item in selected]


def resolve_template(
    *,
    template_id: str | None = None,
    summary_mode: str | None = None,
    artifact_type: str | None = None,
) -> ArtifactTemplate:
    requested = _TEMPLATE_INDEX.get((template_id or "").strip()) if template_id else None
    if requested:
        if summary_mode and summary_mode not in requested.summary_modes:
            requested = None
        if artifact_type and artifact_type not in requested.artifact_types:
            requested = None
    if requested:
        return requested

    if summary_mode:
        default_for_mode = _DEFAULT_BY_SUMMARY_MODE.get(summary_mode)
        if default_for_mode and default_for_mode in _TEMPLATE_INDEX:
            candidate = _TEMPLATE_INDEX[default_for_mode]
            if not artifact_type or artifact_type in candidate.artifact_types:
                return candidate

    if artifact_type:
        default_for_type = _DEFAULT_BY_ARTIFACT_TYPE.get(artifact_type)
        if default_for_type and default_for_type in _TEMPLATE_INDEX:
            candidate = _TEMPLATE_INDEX[default_for_type]
            if not summary_mode or summary_mode in candidate.summary_modes:
                return candidate

    return _TEMPLATES[0]


def _normalize_whitespace(text: str) -> str:
    normalized = re.sub(r"\r\n?", "\n", str(text or ""))
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    return normalized.strip()


def apply_template_layout(
    body: str,
    *,
    template: ArtifactTemplate,
    heading: str,
    context_line: str,
    include_scaffold: bool = True,
) -> str:
    normalized = _normalize_whitespace(body)
    if "<!-- docops_template_id:" in normalized:
        return normalized
    if not normalized:
        normalized = "Sem conteudo suficiente para gerar este artefato."

    if not include_scaffold:
        return f"{normalized}\n"

    sections = "\n".join(f"- {item}" for item in template.preview_sections)
    return (
        f"<!-- docops_template_id: {template.template_id} -->\n"
        f"<!-- docops_template_label: {template.label} -->\n\n"
        f"# {heading}\n\n"
        f"> Template: **{template.label}**  \n"
        f"> {context_line}\n\n"
        "## Estrutura aplicada\n\n"
        f"{sections}\n\n"
        "## Conteudo\n\n"
        f"{normalized}\n"
    )

