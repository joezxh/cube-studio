#!/bin/bash
# 外部 MySQL 192.168.110.232 验证（认证+库现状+写权限）
echo "=== 0. TCP 连通性 ==="
timeout 5 bash -c 'echo > /dev/tcp/192.168.110.232/3306' && echo "TCP 3306 可达" || { echo "TCP 3306 不可达，中止"; exit 1; }
echo "=== 1. 认证+版本+库列表 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.110.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -e "SELECT VERSION(); SHOW DATABASES;" 2>&1 | grep -v "Using a password"
echo "=== 2. kubeflow 库现状 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.110.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -D kubeflow -e "SHOW TABLES;" 2>&1 | grep -v "Using a password" | head -20
echo "=== 3. 写权限测试 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.110.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -D kubeflow -e "CREATE TABLE IF NOT EXISTS _conn_test(id int); DROP TABLE _conn_test; SELECT 'write-ok' AS result;" 2>&1 | grep -v "Using a password"
