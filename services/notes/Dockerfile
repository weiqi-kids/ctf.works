# notes 服務容器 — Flask, port 8080
# 以低權限 user 執行,避免容器內 root。
FROM python:3.12-slim

# 不寫 .pyc、輸出不緩衝,容器 log 即時可見
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先裝依賴(善用 layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製服務程式
COPY app.py .

# 建立低權限使用者並切換(不以 root 跑服務)
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080

# 直接用 Flask 內建 server 起服務(工坊鍛造用途,非生產)
CMD ["python", "app.py"]
