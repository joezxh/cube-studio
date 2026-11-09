#!/bin/bash
# MySQL 凭据复验 + kubeflow 库现状检查
echo "=== 1. 认证测试 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -e "SELECT VERSION(); SHOW DATABASES;" 2>&1 | grep -v "Using a password"
echo "=== 2. kubeflow 库现状 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -D kubeflow -e "SHOW TABLES; SELECT COUNT(*) AS ab_user_rows FROM ab_user;" 2>&1 | grep -v "Using a password" | head -20
echo "=== 3. 写权限测试(建/删临时表) ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -D kubeflow -e "CREATE TABLE IF NOT EXISTS _conn_test(id int); DROP TABLE _conn_test; SELECT 'write-ok';" 2>&1 | grep -v "Using a password"
