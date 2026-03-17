# ──────────────────────────────────────────────
# Stage 1: Build do Frontend (React + Vite)
# ──────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/web

COPY web/package*.json ./
RUN npm ci

COPY web/ ./

# A URL da API em produção no Render aponta para o mesmo host (nginx faz proxy de /api/)
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ──────────────────────────────────────────────
# Stage 2: Imagem final com Python + nginx + supervisord
# ──────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Instala nginx e supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependências Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código-fonte do backend
COPY . .

# Arquivos estáticos do frontend
COPY --from=frontend-build /app/web/dist /usr/share/nginx/html

# Configurações do nginx e supervisord
COPY docker/nginx.render.conf /etc/nginx/sites-available/default
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Remove default nginx config
RUN rm -f /etc/nginx/sites-enabled/default && \
    ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

# Cria diretórios de dados
RUN mkdir -p /app/data/chroma /app/data/bm25 /app/docs /app/uploads /app/artifacts

# O Render define $PORT dinamicamente; o script de entrypoint substitui no nginx.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 10000

CMD ["/entrypoint.sh"]
