# Roadmap de Execucao Operacional

Atualizado em: 2026-04-08

## Objetivo

Consolidar as fases de hardening e evolucao do DocOps Agent com foco em:

- seguranca de ingestao e I/O
- isolamento multi-tenant
- confiabilidade operacional
- previsibilidade de comportamento em producao

## Status geral

| Fase | Nome | Status | Observacao |
|---|---|---|---|
| 1A | Ingest + I/O Guardrails | Concluida | Entregue nesta branch |
| 1B | Backups e resiliencia local | Pendente | Proxima fase tecnica |
| 2 | Observabilidade e operacao | Pendente | Sem inicio |
| 3 | Qualidade e automatizacao | Pendente | Sem inicio |
| 4 | Escala e performance | Pendente | Sem inicio |

## Fase 1A (Concluida)

### Problemas atacados

1. Bypass de validacao de path no endpoint `POST /api/ingest` por comparacao de prefixo textual.
2. Upload sem limite de tamanho em `POST /api/ingest/upload` e `POST /api/ingest/photo`.
3. Risco de delete fisico fora da pasta de upload do usuario em `DELETE /api/docs/{doc_id}`.
4. Arquivo PDF temporario sem limpeza em `GET /api/artifacts/{filename}/pdf`.

### O que foi implementado

#### 1) Hardening de path resolution e containment

- Criado utilitario de resolucao segura em `docops/storage/paths.py`:
  - `resolve_path(path)`
  - `is_path_within(path, base_dir)` com `relative_to` apos `resolve`
- Endpoint `POST /api/ingest` agora usa containment real de path:
  - remove logica fragil baseada em `startswith`
  - mantem resposta `403` para path fora dos diretorios permitidos

#### 2) Limites de upload (guardrail de I/O)

- Novas propriedades de configuracao em `docops/config.py`:
  - `ingest_upload_max_bytes` (default: `25 * 1024 * 1024`)
  - `ingest_photo_max_bytes` (default: `10 * 1024 * 1024`)
- Endpoint `POST /api/ingest/upload`:
  - escrita em stream por chunks
  - bloqueio em excesso com `HTTP 413`
  - limpeza best-effort de arquivo parcial quando excede limite
- Endpoint `POST /api/ingest/photo`:
  - leitura em stream por chunks
  - bloqueio em excesso com `HTTP 413`
  - OCR nao e executado quando payload excede limite

#### 3) Delete seguro de arquivos de documento

- `DELETE /api/docs/{doc_id}` agora so remove arquivo fisico quando:
  - o arquivo existe
  - e arquivo regular
  - esta dentro de `get_user_upload_dir(current_user.id)`
- Se o `source_path` for externo, o registro SQL e os vetores sao removidos, mas o arquivo externo nao e apagado.

#### 4) Limpeza de PDF temporario

- `GET /api/artifacts/{filename}/pdf` agora:
  - remove o arquivo temporario em caso de erro de geracao
  - registra cleanup em background apos resposta com sucesso
- Resultado: evita acumulo de temporarios em disco.

### Arquivos alterados na fase 1A

- `docops/storage/paths.py`
- `docops/config.py`
- `docops/api/routes/ingest.py`
- `docops/api/routes/docs.py`
- `docops/api/routes/artifact.py`
- `tests/test_api.py`
- `.env.example`

### Evidencia de validacao

Comando executado:

```bash
.\.venv\Scripts\python -m pytest -q tests/test_api.py tests/test_multi_tenancy.py
```

Resultado:

- `45 passed`
- sem falhas regressivas nas suites executadas

### Testes novos relevantes (fase 1A)

- bloqueio de bypass de prefixo em ingest por path
- bloqueio de upload acima do limite em ingest/upload
- bloqueio de upload acima do limite em ingest/photo
- garantia de nao deletar arquivo externo em delete de documento
- garantia de cleanup de PDF temporario em endpoint de conversao

## Proximos passos recomendados

1. Subir PR da fase 1A com a descricao em `docs/prs/phase-1a-ingest-io-guardrails.md`.
2. Definir escopo fechado da fase 1B (backup/restore e resiliencia).
3. Adicionar suite dedicada de seguranca para regressao de path traversal e oversized uploads.
