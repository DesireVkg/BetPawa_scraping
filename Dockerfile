# Image de base avec Python + Chromium pour Playwright
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Fichiers du scraper
COPY scraper_betpawa.py .
COPY server.py .

# session.json sera injectée via variable d'environnement (voir server.py)
# On ne la copie PAS dans l'image pour ne pas exposer les credentials

# Port requis par Render
EXPOSE 8080

CMD ["python3", "server.py"]
