#!/bin/bash
# Готов ли Keycloak принимать запросы: /health/ready на порту управления.
# В образе Keycloak нет curl и wget, поэтому HTTP-запрос - через /dev/tcp.
exec 3<> /dev/tcp/127.0.0.1/9000 || exit 1
printf 'GET /health/ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3
head -n 1 <&3 | grep -q ' 200 '
