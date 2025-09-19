# Image chính thức của Playwright (đã có Chrome/Chromium + deps)
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

# Cần ffmpeg để xử lý media (nếu dùng bản nâng cao)
USER root
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài Python packages của dự án
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . /app

# Chạy bot
ENV PYTHONUNBUFFERED=1
CMD ["python", "bot.py"]
