#!/bin/bash
# MySQL 重试确认
for i in 1 2 3; do
  echo "--- 第 $i 次 ---"
  echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 --ssl-mode=PREFERRED -e "SELECT 1;" 2>&1 | grep -v "Using a password"
  sleep 2
done
echo "--- 端口连通性 ---"
timeout 5 bash -c 'echo > /dev/tcp/192.168.100.232/3306' && echo "TCP 3306 可达" || echo "TCP 3306 不可达"
