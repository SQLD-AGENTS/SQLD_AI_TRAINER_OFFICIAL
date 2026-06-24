# ---- build stage ----
FROM node:24-alpine AS build
WORKDIR /app

COPY package*.json ./
# npm ci(엄격 정합)가 아닌 install(reconcile): Vite8(Rolldown)의 wasm 폴백 optional dep
# (@emnapi/*)이 환경별로 다른 버전으로 해석돼 lockfile 검사가 깨짐. install은 lockfile을
# 힌트로 쓰되 불일치는 보정하므로 cross-environment에서 안전.
RUN npm install --no-audit --no-fund
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
