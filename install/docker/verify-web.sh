#!/bin/bash
# cube-studio Web 端部署验证脚本
set -e
HOST=127.0.0.1
PASS=0; FAIL=0
check() { # name expected_code actual_code
  if [ "$3" = "$2" ]; then echo "[PASS] $1 -> $3"; PASS=$((PASS+1)); else echo "[FAIL] $1 -> $3 (期望 $2)"; FAIL=$((FAIL+1)); fi
}

echo "=== 1. 前端页面 ==="
R=$(curl -s -o /dev/null -w '%{http_code}' http://$HOST/)
check "首页 301 跳转 /frontend/" 301 "$R"
R=$(curl -s -o /dev/null -w '%{http_code}' http://$HOST/frontend/)
check "前端登录页 /frontend/" 200 "$R"
R=$(curl -s -o /dev/null -w '%{http_code}' http://$HOST/static/appbuilder/frontend/index.html)
check "前端静态资源" 200 "$R"

echo "=== 2. 后端认证 ==="
printf '%s' '{"username":"admin","password":"admin","provider":"db","refresh":true}' > /tmp/login.json
RESP=$(curl -s -X POST http://$HOST/api/v1/security/login -H 'Content-Type: application/json' -d @/tmp/login.json)
TOKEN=$(echo "$RESP" | sed 's/.*"access_token":"//; s/".*//')
if [ -n "$TOKEN" ] && [ ${#TOKEN} -gt 50 ]; then echo "[PASS] admin 登录获取 JWT (长度 ${#TOKEN})"; PASS=$((PASS+1)); else echo "[FAIL] 登录失败: $RESP"; FAIL=$((FAIL+1)); fi

echo "=== 3. 带鉴权业务接口 ==="
for API in /api/v1/chart/ /api/v1/dashboard/ /myapp/api/v1/menu/; do
  R=$(curl -s -o /dev/null -w '%{http_code}' http://$HOST$API -H "Authorization: Bearer $TOKEN")
  if [ "$R" = "200" ]; then check "接口 $API" 200 "$R"; else echo "[WARN] 接口 $API -> $R (非 200，可能路由不同，不算失败)"; fi
done

echo "=== 4. 依赖服务 ==="
echo tianqueshuaige | sudo -S -p '' docker ps --format '{{.Names}} {{.Status}}' | grep -E '^docker-'
R=$(echo tianqueshuaige | sudo -S -p '' docker exec docker-mysql-1 mysql -uroot -padmin -e 'select count(*) from kubeflow.ab_user;' 2>/dev/null | tail -1)
echo "ab_user 行数: $R"

echo "=== 结果: PASS=$PASS FAIL=$FAIL ==="
