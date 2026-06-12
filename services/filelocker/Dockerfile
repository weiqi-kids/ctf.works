# filelocker — path traversal 漏洞服務(CONTRACTS.md §2.2)
# 零第三方依賴,僅需 Python 標準庫。
FROM python:3.12-slim

# 建立低權限使用者(不以 root 跑服務)
RUN useradd --create-home --uid 10001 locker

WORKDIR /app
COPY app.py /app/app.py

# data/ 用來存使用者檔案,需可寫;交給低權限 user
RUN mkdir -p /app/data && chown -R locker:locker /app

USER locker

EXPOSE 9090

CMD ["python3", "/app/app.py"]
