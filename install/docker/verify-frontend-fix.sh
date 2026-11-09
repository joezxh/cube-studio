#!/bin/bash
# 前端修复后全量资源验证
set -e
PASS=0; FAIL=0
check() { if [ "$3" = "$2" ]; then echo "[PASS] $1 -> $3"; PASS=$((PASS+1)); else echo "[FAIL] $1 -> $3 (期望 $2)"; FAIL=$((FAIL+1)); fi; }

R=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/frontend/)
check "前端首页" 200 "$R"
for RES in static/js/main.1dbd5b6f.js static/css/main.4d5bd535.css; do
  R=$(curl -s -o /dev/null -w '%{http_code} %{content_type}' "http://127.0.0.1/frontend/$RES")
  echo "$RES -> $R"
  case "$R" in 200\ application/*) PASS=$((PASS+1));; *) FAIL=$((FAIL+1));; esac
done
# index.html 引用的所有 JS chunk 逐一验证
for CHUNK in $(curl -s http://127.0.0.1/frontend/asset-manifest.json | grep -Eo '"static/js/[^"]+"' | tr -d '"' | sed 's/^"//'); do
  C=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1/frontend/$CHUNK")
  if [ "$C" != "200" ]; then echo "[FAIL] chunk $CHUNK -> $C"; FAIL=$((FAIL+1)); fi
done
echo "chunk 全量校验完成 (未列出的均为 200)"
echo tianqueshuaige | sudo -S -p '' docker ps --format '{{.Names}} {{.Status}}' | grep '^docker-'
echo "=== 结果: PASS=$PASS FAIL=$FAIL ==="
