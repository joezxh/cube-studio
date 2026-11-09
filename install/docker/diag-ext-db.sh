#!/bin/bash
# 外部 MySQL/Redis 连通性与鉴权诊断
set -x

echo "=== 1. 外部 MySQL 192.168.100.232 连通+鉴权 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -e "SHOW DATABASES;" 2>&1 | grep -v "Using a password"

echo "=== 2. 外部 MySQL kubeflow 库表现状 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -D kubeflow -e "SHOW TABLES;" 2>&1 | grep -v "Using a password" | head -15
echo tianqueshuaige | sudo -S -p '' docker run --rm mysql:8.0.32 mysql -h192.168.100.232 -P3306 -ukubeflow -pkubeflow --connect-timeout=10 -D kubeflow -e "SELECT COUNT(*) AS users FROM ab_user;" 2>&1 | grep -v "Using a password" | tail -2

echo "=== 3. 外部 Redis 192.168.100.159 连通+鉴权+db11 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm ccr.ccs.tencentyun.com/cube-studio/redis:7.4 redis-cli -h 192.168.100.159 -p 6379 -a 'tqbibydiu@2025@redis' -n 11 --no-auth-warning PING 2>&1
echo tianqueshuaige | sudo -S -p '' docker run --rm ccr.ccs.tencentyun.com/cube-studio/redis:7.4 redis-cli -h 192.168.100.159 -p 6379 -a 'tqbibydiu@2025@redis' --no-auth-warning INFO keyspace 2>&1 | head -10
