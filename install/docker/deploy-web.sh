#!/bin/bash
# cube-studio Web-only 单机部署脚本（在服务器上执行）
# 用法: bash deploy-web.sh
set -ex

DEPLOY_ROOT=/home/tianque/cube-studio
cd "$DEPLOY_ROOT"

# 1. 导入镜像
docker load -i /home/tianque/cube-studio-deploy-images.tar.gz

# 2. 准备数据目录（mysql 数据、k8s 工作目录占位）
cd "$DEPLOY_ROOT/install/docker"
mkdir -p data/mysql data/k8s

# 3. 启动全部服务
docker compose -f docker-compose.web.yml up -d

# 4. 等待服务就绪并查看状态
sleep 30
docker compose -f docker-compose.web.yml ps
echo "===== myapp 日志（最后 50 行）====="
docker compose -f docker-compose.web.yml logs --tail=50 myapp || true
echo "===== 部署完成，验证: curl -sI http://127.0.0.1/ ====="
curl -sI http://127.0.0.1/ | head -5
