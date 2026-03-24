FROM node:20-alpine AS build

WORKDIR /app/web

COPY web/package*.json ./
RUN npm ci

COPY web/ ./

ARG VITE_API_URL=http://localhost:5173
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

FROM nginx:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web/dist /usr/share/nginx/html

EXPOSE 80
