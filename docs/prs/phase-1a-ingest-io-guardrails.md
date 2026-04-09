# PR Description - Fase 1A: Ingest + I/O Guardrails

## Resumo

Esta PR implementa a Fase 1A do plano operacional com foco em seguranca de ingestao e robustez de I/O.
O objetivo foi eliminar superficies de risco em leitura/escrita de arquivos e reduzir chance de regressao operacional.

## Contexto do problema

Antes desta entrega, havia quatro riscos principais:

1. Validacao de path em `POST /api/ingest` baseada em prefixo textual (`startswith`), vulneravel a bypass.
2. Uploads sem limite explicito de tamanho em `POST /api/ingest/upload` e `POST /api/ingest/photo`.
3. `DELETE /api/docs/{doc_id}` podia tentar apagar arquivos fora da pasta de upload do usuario.
4. `GET /api/artifacts/{filename}/pdf` criava PDF temporario sem cleanup garantido apos resposta.

## O que foi alterado

### 1) Path hardening para ingest por path

- Adicionados utilitarios em `docops/storage/paths.py`:
  - `resolve_path(path)`
  - `is_path_within(path, base_dir)` (containment robusto via `relative_to` apos `resolve`)
- `docops/api/routes/ingest.py`:
  - `POST /api/ingest` agora usa containment real de path e nao mais comparacao textual.

### 2) Guardrails de tamanho para uploads

- `docops/config.py`:
  - nova propriedade `ingest_upload_max_bytes` (default 25 MiB)
  - nova propriedade `ingest_photo_max_bytes` (default 10 MiB)
- `docops/api/routes/ingest.py`:
  - implementada leitura/escrita em stream com contagem de bytes
  - resposta `HTTP 413` quando payload excede limite
  - cleanup best-effort de arquivo parcial em upload interrompido por limite

### 3) Delete seguro de arquivo fisico de documento

- `docops/api/routes/docs.py`:
  - `DELETE /api/docs/{doc_id}` so faz `unlink` quando `source_path` esta dentro de `get_user_upload_dir(user_id)`.
  - para arquivos externos, remove indice/registro sem apagar arquivo no disco.

### 4) Cleanup de temporario em PDF de artifact

- `docops/api/routes/artifact.py`:
  - `GET /api/artifacts/{filename}/pdf` agora agenda cleanup via background task apos envio do arquivo.
  - em caso de erro de geracao, remove temporario antes de retornar erro.

### 5) Documentacao de variaveis de ambiente

- `.env.example`:
  - adicionadas:
    - `INGEST_UPLOAD_MAX_BYTES=26214400`
    - `INGEST_PHOTO_MAX_BYTES=10485760`

## Testes adicionados

Arquivo: `tests/test_api.py`

- `test_ingest_path_rejects_prefix_bypass`
- `test_ingest_upload_rejects_oversized_file`
- `test_ingest_photo_rejects_oversized_file`
- `test_delete_doc_does_not_unlink_external_source`
- `test_artifact_pdf_temp_file_is_cleaned_up`

## Validacao executada

```bash
.\.venv\Scripts\python -m pytest -q tests/test_api.py tests/test_multi_tenancy.py
```

Resultado:

- `45 passed`

## Impacto e compatibilidade

- Sem breaking change de contrato de endpoint.
- Comportamentos novos esperados:
  - uploads acima do limite retornam `413`
  - ingest por path fora de area permitida continua retornando `403`, agora com validacao robusta
  - delete de documento nao remove arquivo externo ao upload do usuario
  - limpeza de PDF temporario reduz lixo em disco

## Checklist de entrega

- [x] Hardening de path traversal/bypass em ingest por path
- [x] Limite de upload em ingest/upload e ingest/photo
- [x] Delete seguro de arquivo fisico por escopo de usuario
- [x] Cleanup de PDF temporario
- [x] Testes de regressao e seguranca adicionados
- [x] Documentacao de configuracao atualizada
