# gov-sft：GPU 微调算子（spec §3.4 选型规则、全局约束⑤）。
# 基础=LLaMA-Factory 官方镜像（开源），其 CUDA≥12.8 以支持 sm_89(4090)/sm_120(5090)；
# 教师/学生底座权重不打入镜像，运行时从 /mnt/gov/models 挂载读取。
FROM hiyouga/llamafactory:latest
# 覆盖为本地 RTX 4090/5090 架构，避免基础镜像默认 arch 列表不含 sm_120 时内核 JIT 失败
ENV TORCH_CUDA_ARCH_LIST="8.9;12.0"
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
ENTRYPOINT ["python", "start.py"]
