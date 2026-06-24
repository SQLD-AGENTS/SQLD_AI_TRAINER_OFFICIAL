# ---- build stage ----
# node:24 → npm 11 (lockfile이 로컬 npm 11로 생성됨. npm 10이면 optional dep 해석이 달라 npm ci 실패)
FROM node:24-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci
COPY . .

# Vite는 빌드타임에 VITE_* 를 번들에 인라인 → 반드시 build ARG로 주입
ARG VITE_API_URL
ARG VITE_GOOGLE_CLIENT_ID
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
RUN npm run build

# ---- serve stage ----
FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
