# gov-manifest：纯 CPU 血缘工具，无 CUDA 依赖（spec §3.2 GPU 算子约束不适用本算子）。
# 基础镜像 python:3.10-slim；构建期通过 GOV_IMAGE / GOV_GIT_COMMIT 注入血缘字段。
FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["python", "start.py"]
