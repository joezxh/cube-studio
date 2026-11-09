#!/bin/bash
# 前端 JS 404-fallback 诊断脚本
FE_DIR=/home/tianque/cube-studio/myapp/static/appbuilder/frontend
JS=main.1dbd5b6f.js

echo "=== 1. 服务器挂载目录 $FE_DIR ==="
ls -la "$FE_DIR" 2>/dev/null | head -25

echo "=== 2. index.html 引用的资源(src/href) ==="
grep -Eo '(src|href)="[^"]*"' "$FE_DIR/index.html" 2>/dev/null | head -20

echo "=== 3. curl 请求 JS 实际返回 ==="
curl -s -o /dev/null -w 'frontend/main.js: %{http_code} %{content_type}\n' "http://127.0.0.1/frontend/$JS"
curl -s "http://127.0.0.1/frontend/$JS" | head -c 150; echo
curl -s -o /dev/null -w 'static/appbuilder/frontend/main.js: %{http_code} %{content_type}\n' "http://127.0.0.1/static/appbuilder/frontend/$JS"

echo "=== 4. nginx 容器内实际挂载内容 ==="
echo tianqueshuaige | sudo -S -p '' docker exec docker-frontend-1 sh -c 'ls /data/web/frontend | head -15; echo ---; ls /data/web/static/appbuilder/frontend | head -5'

echo "=== 5. nginx access log 中 main.js 相关请求 ==="
echo tianqueshuaige | sudo -S -p '' docker logs --tail 200 docker-frontend-1 2>&1 | grep "$JS" | tail -5
