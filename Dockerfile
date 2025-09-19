FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl ffmpeg \
    libnss3 libatk-bridge2.0-0 libx11-xcb1 libxcomposite1 libxrandr2 \
    libasound2 libxdamage1 libgbm1 libpangocairo-1.0-0 libgtk-3-0 libxss1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps

COPY . /app
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
