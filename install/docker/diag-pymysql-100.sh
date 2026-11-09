#!/bin/bash
# PyMySQL 两种模式预检 100.232（MySQL 8.0.11 caching_sha2 认证）
echo "=== PyMySQL 明文 ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm cube-studio-dashboard:web-local python -c "import pymysql; c=pymysql.connect(host='192.168.100.232',port=3306,user='kubeflow',password='kubeflow',database='kubeflow',charset='utf8mb4'); print('plain OK', c.get_server_info())" 2>&1 | tail -3
echo "=== PyMySQL SSL ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm cube-studio-dashboard:web-local python -c "import pymysql; c=pymysql.connect(host='192.168.100.232',port=3306,user='kubeflow',password='kubeflow',database='kubeflow',charset='utf8mb4',ssl={'ssl':True}); print('ssl OK', c.get_server_info())" 2>&1 | tail -3
