# gov-distill-gen：CPU 算子（仅通过 HTTP 调用教师服务，本身不需 GPU）。
# 基础镜像 python:3.10-slim；教师权重/服务不在本镜像，运行时经 --endpoint 指向集群内教师服务。
FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["python", "start.py"]
