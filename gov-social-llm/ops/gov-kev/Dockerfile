# gov-kev：kev 上游 Apache-2.0；镜像构建期 clone 并用 uv 锁定依赖（P0 需验证内网可达 github/PyPI）。
# 依赖通过 uv 项目隔离，不污染系统 python；权重不打入镜像，运行时由 /mnt/gov 挂载。
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-cache-dir git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /work
RUN git clone --depth 1 https://github.com/jaredpalmer/kev.git && cd kev && uv sync --extra serve
COPY . /app
# 与全局约束⑤一致：GPU 底座编译目标架构（sm_89/sm_120）；纯命令生成时不影响
ENV TORCH_CUDA_ARCH_LIST="8.9;12.0"
ENTRYPOINT ["uv", "run", "--project", "/work/kev", "python", "/app/start.py"]
