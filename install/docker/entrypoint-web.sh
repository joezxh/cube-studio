#!/bin/bash
# Web-only 单机部署入口脚本（幂等初始化 + gunicorn 启动）
# 相比原 entrypoint.sh:
#   1. 初始化(create_db/db upgrade/create-admin/init)只在首次执行（以 /data/k8s/.web_initialized 为标记），
#      避免 fab create-admin 在用户已存在时报错导致容器退出（原脚本 set -ex 每次启动都会执行）。
#   2. 不依赖 kubeconfig，不连接 k8s，仅启动 Web 后端。
set -ex

export FLASK_APP=myapp:app

# 工作目录符号链接（沿用原 entrypoint.sh 逻辑，全部落在 /data/k8s/kubeflow 挂载目录内）
mkdir -p /data/k8s/kubeflow/pipeline/workspace /data/k8s/kubeflow/dataset /data/k8s/kubeflow/global
rm -f /home/myapp/myapp/static/mnt
ln -sfn /data/k8s/kubeflow/pipeline/workspace /home/myapp/myapp/static/mnt
rm -f /home/myapp/myapp/static/dataset
ln -sfn /data/k8s/kubeflow/dataset /home/myapp/myapp/static/dataset
rm -f /home/myapp/myapp/static/aihub
ln -sfn /cube-studio/aihub /home/myapp/myapp/static/aihub
rm -f /home/myapp/myapp/static/global
ln -sfn /data/k8s/kubeflow/global /home/myapp/myapp/static/global

cd /home/myapp

# 首次启动: 建库、建表、创建 admin、初始化权限与菜单
# 标记文件放在挂载目录(/data/k8s/kubeflow)内，容器重建后也不会重复初始化
if [ ! -f /data/k8s/kubeflow/.web_initialized ]; then
  python myapp/create_db.py
  myapp db upgrade
  myapp fab create-admin --username admin --firstname admin --lastname admin --email admin@tencent.com --password admin
  myapp init
  touch /data/k8s/kubeflow/.web_initialized
fi

# 表结构同步检查
python myapp/check_tables.py

# Web 后端服务（单机体验用 4 worker，足够 Web 端使用）
exec gunicorn --bind 0.0.0.0:80 --workers 4 --worker-class=gevent --timeout 300 \
  --forwarded-allow-ips="*" --limit-request-line 0 --limit-request-field_size 0 \
  --log-level=info --access-logfile - --error-logfile - --capture-output myapp:app
