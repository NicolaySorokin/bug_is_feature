# syntax=docker/dockerfile:1
# Клиентская часть: Node собирает статику, Nginx её раздаёт.
#
# Этот же образ - единая точка входа стенда: в каждой среде к нему
# подключается конфигурация cicd/<среда>/nginx.conf, которая кроме
# статики проксирует API и Keycloak. Своя конфигурация образа ниже нужна
# только для запуска образа отдельно - она раздаёт одну статику.

FROM node:22-alpine AS build
WORKDIR /app

# Сначала зависимости: слой с node_modules пересобирается, только когда
# меняется package-lock.json.
# За корпоративным прокси с подменой сертификатов корневой сертификат
# передаётся секретом сборки и в образ не попадает:
#   docker build --secret id=ca,src=corporate-ca.crt ./frontend
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca; fi; \
    npm ci --no-audit --no-fund

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
