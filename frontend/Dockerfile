# syntax=docker/dockerfile:1
# Клиентская часть: Node собирает статику, Nginx её раздаёт. На стендах
# к образу подключается cicd/<среда>/nginx.conf с прокси к API и Keycloak.

FROM node:22-alpine AS build
WORKDIR /app

# Сначала зависимости: слой node_modules пересобирается, только когда меняется
# package-lock.json. За корпоративным прокси корневой сертификат передаётся
# секретом сборки и в образ не попадает:
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
