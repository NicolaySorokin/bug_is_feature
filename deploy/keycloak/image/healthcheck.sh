#!/bin/bash
# Готов ли Keycloak: /health/ready на порту управления. curl и wget в образе нет,
# поэтому запрос идёт через /dev/tcp.
exec 3<> /dev/tcp/127.0.0.1/9000 || exit 1
printf 'GET /health/ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3
head -n 1 <&3 | grep -q ' 200 '
