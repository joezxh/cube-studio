#!/bin/bash
# 502 诊断：容器状态 / myapp 日志 / frontend→myapp 连通 / nginx 错误日志
echo "=== 1. 容器状态 ==="
echo tianqueshuaige | sudo -S -p '' docker ps -a --format '{{.Names}} {{.Status}}' | grep -E '^docker-'
echo "=== 2. myapp 容器IP ==="
echo tianqueshuaige | sudo -S -p '' docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' docker-myapp-1
echo "=== 3. myapp 日志尾部(错误) ==="
echo tianqueshuaige | sudo -S -p '' docker logs --tail 40 docker-myapp-1 2>&1 | grep -iE 'error|refused|denied|Traceback|Listening|Booting|reset' | tail -8
echo "=== 4. frontend 容器内 curl myapp ==="
echo tianqueshuaige | sudo -S -p '' docker exec docker-frontend-1 sh -c 'wget -q -S -O /dev/null --timeout=5 http://myapp:80/ 2>&1 | head -3 || curl -sS -o /dev/null -w "%{http_code}\n" --max-time 5 http://myapp:80/ 2>&1'
echo "=== 5. nginx error log 尾部 ==="
echo tianqueshuaige | sudo -S -p '' docker logs --tail 15 docker-frontend-1 2>&1 | tail -8
echo "=== 6. 宿主机 curl 登录页 ==="
curl -s -o /dev/null -w 'http_code=%{http_code}\n' --max-time 8 'http://127.0.0.1/login/'
