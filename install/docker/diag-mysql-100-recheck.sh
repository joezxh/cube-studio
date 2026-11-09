#!/bin/bash
# 外部 MySQL 192.168.100.232 复验（认证+库现状+字符集+写权限）
echo "=== 0. TCP ==="
timeout 5 bash -c 'echo > /dev/tcp/192.168.100.232/3306' && echo "TCP 3306 可达" || { echo "TCP 不可达"; exit 1; }
echo "=== 1a. 认证(默认TLS) ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -e "SELECT VERSION();" 2>&1 | grep -v "Using a password"
echo "=== 1b. 认证(禁用TLS) ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 --ssl-mode=DISABLED -e "SELECT VERSION();" 2>&1 | grep -v "Using a password"
echo "=== 2. kubeflow 库现状 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 --ssl-mode=DISABLED -e "SHOW CREATE DATABASE kubeflow; SELECT COUNT(*) AS tables_in_kubeflow FROM information_schema.tables WHERE table_schema='kubeflow';" 2>&1 | grep -v "Using a password"
echo "=== 3. 库内表样例(若非空) ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 --ssl-mode=DISABLED -D kubeflow -e "SHOW TABLES;" 2>&1 | grep -v "Using a password" | head -12
echo "=== 4. 写权限 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 --ssl-mode=DISABLED -D kubeflow -e "CREATE TABLE IF NOT EXISTS _conn_test(id int); DROP TABLE _conn_test; SELECT 1 AS write_ok;" 2>&1 | grep -v "Using a password"
