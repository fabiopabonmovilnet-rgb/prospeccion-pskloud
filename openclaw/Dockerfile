FROM python:3.12-slim

WORKDIR /app

# Install Chromium + Playwright system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libegl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Streamlit dashboard dependencies (pinned starlette for FastAPI compat)
RUN pip install --no-cache-dir streamlit pandas openpyxl "starlette>=0.37.2,<0.39.0"

# Install Playwright browsers (Chromium)
RUN python -m playwright install chromium

COPY . .
RUN chmod +x /app/start.sh

ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
ENV CHROME_PATH=/usr/bin/chromium

EXPOSE 9000
EXPOSE 8501

CMD ["/app/start.sh"]
