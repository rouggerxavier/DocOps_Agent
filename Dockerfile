# ──────────────────────────────────────────────
# Stage 1: Build do Frontend (React + Vite)
# ──────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/web

COPY web/package*.json ./
RUN npm ci

COPY web/ ./

RUN npm run build

# ──────────────────────────────────────────────
# Stage 2: Imagem final — Python + uvicorn
# O FastAPI serve os estáticos gerados pelo Vite
# ──────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependências Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código-fonte do backend
COPY . .

# Copia o build do frontend para dentro do projeto (web/dist/)
# O app.py já resolve esse caminho via Path(__file__).parent.parent.parent / "web" / "dist"
COPY --from=frontend-build /app/web/dist /app/web/dist

# Cria diretórios de dados
RUN mkdir -p /app/data/chroma /app/data/bm25 /app/docs /app/uploads /app/artifacts

# O Render define $PORT dinamicamente
EXPOSE 10000

CMD ["sh", "-c", "python -m uvicorn docops.api.app:app --host 0.0.0.0 --port ${PORT:-10000}"]
