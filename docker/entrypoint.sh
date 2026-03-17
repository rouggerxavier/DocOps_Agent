#!/bin/sh
# O Render define a variável $PORT dinamicamente.
# Substituímos o placeholder no nginx.conf antes de iniciar.
PORT="${PORT:-10000}"

sed -i "s/RENDER_PORT/$PORT/g" /etc/nginx/sites-available/default

# Cria diretórios de log do supervisor se não existirem
mkdir -p /var/log/supervisor

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
