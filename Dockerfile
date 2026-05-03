# Image de base avec Python + Chromium pour Playwright
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Fichiers du scraper
COPY scraper_betpawa.py .
COPY server.py .
COPY session.json .

# Port Render (utilise la variable PORT, défaut 10000)
EXPOSE 10000

CMD ["python3", "server.py"]
