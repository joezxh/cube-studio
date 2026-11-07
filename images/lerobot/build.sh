#!/bin/bash
# 从仓库根目录构建两个 lerobot 镜像（spec §6）
set -e
docker build -f images/lerobot/Dockerfile-import -t ccr.ccs.tencentyun.com/cube-studio/lerobot:import-cpu .
docker build -f images/lerobot/Dockerfile-gpu    -t ccr.ccs.tencentyun.com/cube-studio/lerobot:gpu-0.6.2 .
