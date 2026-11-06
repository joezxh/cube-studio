# gov-distill-filter：CPU 算子（纯数据过滤，无 GPU 依赖）。python:3.10-slim。
FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["python", "start.py"]
