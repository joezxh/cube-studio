#!/bin/bash
# 502 修复验证：重启 frontend 重新加载 conf → 验证登录页/前端/JWT
cd /home/tianque/cube-studio/install/docker
echo "=== 1. nginx 配置语法检查+重启 frontend ==="
echo tianqueshuaige | sudo -S -p '' docker exec docker-frontend-1 nginx -t 2>&1
echo tianqueshuaige | sudo -S -p '' docker compose -f docker-compose.web.yml restart frontend
sleep 5
echo "=== 2. 验证 ==="
R1=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 'http://127.0.0.1/login/')
echo "登录页 /login/: $R1"
R2=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 'http://127.0.0.1/frontend/')
echo "前端页 /frontend/: $R2"
printf '%s' '{"username":"admin","password":"admin","provider":"db","refresh":true}' > /tmp/login.json
RESP=$(curl -s -X POST --max-time 15 http://127.0.0.1/api/v1/security/login -H 'Content-Type: application/json' -d @/tmp/login.json)
TOKEN=$(echo "$RESP" | sed 's/.*"access_token":"//; s/".*//')
if [ ${#TOKEN} -gt 50 ]; then echo "[PASS] admin JWT 登录成功 (len=${#TOKEN})"; else echo "[FAIL] 登录: $RESP"; fi
echo "=== 3. 容器状态 ==="
echo tianqueshuaige | sudo -S -p '' docker ps --format '{{.Names}} {{.Status}}' | grep -E '^docker-'
