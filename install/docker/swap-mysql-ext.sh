#!/bin/bash
# MySQL 切换执行脚本：预检 → 移除标记 → 应用编排
set -e
echo "=== 1. PyMySQL 明文连通预检（与 myapp 同镜像同驱动） ==="
echo tianqueshuaige | sudo -S -p '' docker run --rm cube-studio-dashboard:web-local python -c "import pymysql; c=pymysql.connect(host='192.168.100.232',port=3306,user='kubeflow',password='kubeflow',database='kubeflow',charset='utf8mb4'); print('pymysql OK server=', c.get_server_info())"

echo "=== 2. 移除初始化标记（外部库为空，需完整建表+初始化） ==="
echo tianqueshuaige | sudo -S -p '' rm -f /home/tianque/cube-studio/install/docker/data/k8s/.web_initialized
ls /home/tianque/cube-studio/install/docker/data/k8s/

echo "=== 3. 应用新编排（下线自建 mysql，重建 myapp） ==="
cd /home/tianque/cube-studio/install/docker
echo tianqueshuaige | sudo -S -p '' docker compose -f docker-compose.web.yml up -d --remove-orphans 2>&1 | tail -10
