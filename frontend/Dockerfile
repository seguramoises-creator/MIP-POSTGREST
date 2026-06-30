# ─────────────────────────────────────────────────────────────
# Frontend MSM / VISTA — build Vite (Node) → servir estático con nginx
# ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
# En producción el frontend llama same-origin: nginx hace proxy de /api/v1 al
# backend. Por eso la base de la API es relativa (/api/v1), no un host fijo.
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ── Imagen final: nginx sirviendo el build + reverse proxy a la API ──
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
