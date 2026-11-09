#!/bin/bash
# 外部 Redis 切换后验证
echo "=== 1. 容器状态 ==="
echo tianqueshuaige | sudo -S -p '' docker ps --format '{{.Names}} {{.Status}}' | grep -E '^docker-'
echo "=== 2. myapp 启动日志(错误过滤) ==="
echo tianqueshuaige | sudo -S -p '' docker logs --tail 300 docker-myapp-1 2>&1 | grep -iE 'error|refused|denied|traceback|Listening at|Booting worker' | tail -8
echo "=== 3. 外部 Redis db11/12/13 写入情况 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm ccr.ccs.tencentyun.com/cube-studio/redis:7.4 redis-cli -h 192.168.100.159 -p 6379 -a 'tqbibydiu@2025@redis' --no-auth-warning -n 11 DBSIZE
echo tianqueshuaige | sudo -S -p '' docker run --rm ccr.ccs.tencentyun.com/cube-studio/redis:7.4 redis-cli -h 192.168.100.159 -p 6379 -a 'tqbibydiu@2025@redis' --no-auth-warning -n 12 DBSIZE
echo tianqueshuaige | sudo -S -p '' docker run --rm ccr.ccs.tencentyun.com/cube-studio/redis:7.4 redis-cli -h 192.168.100.159 -p 6379 -a 'tqbibydiu@2025@redis' --no-auth-warning INFO keyspace 2>/dev/null | tail -6
echo "=== 4. Web 端验证 ==="
printf '%s' '{"username":"admin","password":"admin","provider":"db","refresh":true}' > /tmp/login.json
RESP=$(curl -s -X POST http://127.0.0.1/api/v1/security/login -H 'Content-Type: application/json' -d @/tmp/login.json)
TOKEN=$(echo "$RESP" | sed 's/.*"access_token":"//; s/".*//')
if [ ${#TOKEN} -gt 50 ]; then echo "[PASS] admin JWT 登录成功 (len=${#TOKEN})"; else echo "[FAIL] 登录: $RESP"; fi
R=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/frontend/)
echo "前端页面: $R"
