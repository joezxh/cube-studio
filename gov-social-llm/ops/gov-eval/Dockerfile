# gov-eval：CPU 算子（指标计算本地完成，smoke/bench 经 HTTP 调用被测服务，本身不需 GPU）。
FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["python", "start.py"]
