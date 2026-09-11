# syntax=docker/dockerfile:1.7
# React (Vite) build served by nginx, which also reverse-proxies /api to the API container.

FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM nginx:1.27-alpine
# Replaces the image's default server block; the *.inc files aren't auto-loaded (only *.conf is).
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx/proxy_params.inc nginx/security_headers.inc /etc/nginx/conf.d/
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1/healthz || exit 1
