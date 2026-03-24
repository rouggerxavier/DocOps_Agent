# Docker Layout

Esta pasta centraliza toda a infraestrutura Docker do projeto.

## Arquivos

- `backend/Dockerfile`: imagem do backend FastAPI (porta `8000`).
- `frontend/Dockerfile`: build do frontend Vite + Nginx (porta `80`).
- `production/Dockerfile`: imagem unificada usada no deploy do Render.
- `nginx.conf`: configuração Nginx usada no container do frontend.
- `nginx.render.conf`: configuração alternativa para cenários de deploy com porta dinâmica.
- `entrypoint.sh`: entrypoint para stack com `supervisord`.
- `supervisord.conf`: processo supervisor (Uvicorn + Nginx) para container único.

## Uso local

Na raiz do projeto:

```bash
docker compose up --build
```

## Deploy Render

`render.yaml` aponta para:

- `docker/production/Dockerfile`
