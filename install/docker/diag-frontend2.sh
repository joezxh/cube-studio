#!/bin/bash
# 前端 JS 二次诊断: static/js 子目录与完整路径
FE_DIR=/home/tianque/cube-studio/myapp/static/appbuilder/frontend
JS=main.1dbd5b6f.js

echo "=== 1. 服务器 static/js 目录 ==="
ls -la "$FE_DIR/static/js/" 2>/dev/null | head -10
echo "--- static/css ---"
ls "$FE_DIR/static/css/" 2>/dev/null | head -5
echo "--- 本地 index.html 引用 vs 实际文件 hash 对照 ---"
grep -Eo 'main\.[a-f0-9]+\.(js|css)' "$FE_DIR/index.html" | sort -u
ls "$FE_DIR/static/js/" 2>/dev/null | grep -Eo 'main\.[a-f0-9]+\.js' | sort -u

echo "=== 2. curl 完整 JS 路径 ==="
curl -s -o /dev/null -w '完整JS路径: %{http_code} %{content_type} 大小:%{size_download}\n' "http://127.0.0.1/frontend/static/js/$JS"
curl -s "http://127.0.0.1/frontend/static/js/$JS" | head -c 80; echo

echo "=== 3. 容器内 static/js ==="
echo tianqueshuaige | sudo -S -p '' docker exec docker-frontend-1 sh -c 'ls /data/web/frontend/static/js/ | head; ls /data/web/frontend/static/css/ | head -3'

echo "=== 4. nginx access log ==="
echo tianqueshuaige | sudo -S -p '' docker exec docker-frontend-1 sh -c 'grep "main." /data/log/nginx/access.log 2>/dev/null | tail -6'
