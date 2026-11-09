#!/bin/bash
# MySQL 切换后验证：等待初始化 → 表数量 → 容器 → Web 登录
echo "=== 1. 等待 myapp 初始化+启动（最多 240s） ==="
for i in $(seq 1 24); do
  sleep 10
  ST=$(echo tianqueshuaige | sudo -S -p '' docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' docker-myapp-1 2>/dev/null)
  BOOT=$(echo tianqueshuaige | sudo -S -p '' docker logs --tail 30 docker-myapp-1 2>&1 | grep -c 'Booting worker')
  echo "[$((i*10))s] state=$ST booting_workers=$BOOT"
  [ "$BOOT" -ge 1 ] && break
done
echo "=== 2. 容器状态（mysql 应已移除） ==="
echo tianqueshuaige | sudo -S -p '' docker ps --format '{{.Names}} {{.Status}}' | grep -E '^docker-'
echo "=== 3. myapp 日志尾部 ==="
echo tianqueshuaige | sudo -S -p '' docker logs --tail 60 docker-myapp-1 2>&1 | grep -iE 'error|refused|denied|Traceback|Table|Listening at|Booting|Admin User' | tail -12
echo "=== 4. 外部 kubeflow 库表数量 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 --ssl-mode=DISABLED -D kubeflow -e "SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema='kubeflow'; SELECT username FROM ab_user LIMIT 3;" 2>&1 | grep -v "Using a password"
echo "=== 5. Web 端验证 ==="
printf '%s' '{"username":"admin","password":"admin","provider":"db","refresh":true}' > /tmp/login.json
RESP=$(curl -s -X POST http://127.0.0.1/api/v1/security/login -H 'Content-Type: application/json' -d @/tmp/login.json)
TOKEN=$(echo "$RESP" | sed 's/.*"access_token":"//; s/".*//')
if [ ${#TOKEN} -gt 50 ]; then echo "[PASS] admin JWT 登录成功 (len=${#TOKEN})"; else echo "[FAIL] 登录: $RESP"; fi
R=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/frontend/)
echo "前端页面: $R"
echo "=== 6. 外部 Redis db11 仍正常 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm ccr.ccs.tencentyun.com/cube-studio/redis:7.4 redis-cli -h 192.168.100.159 -p 6379 -a 'tqbibydiu@2025@redis' --no-auth-warning -n 11 DBSIZE 2>&1 | tail -1
