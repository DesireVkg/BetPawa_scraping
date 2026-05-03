━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DÉPLOIEMENT RENDER — Guide complet
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FICHIERS À METTRE SUR GITHUB :
  scraper_betpawa.py
  server.py
  Dockerfile
  requirements.txt
  render.yaml

⚠️  NE PAS mettre session.json sur GitHub !
    (contient vos identifiants BetPawa)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE 1 — Générer session.json sur votre PC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python3 save_session.py
  # → ouvre navigateur → connexion → ENTREE → session.json généré

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE 2 — Convertir session.json en une seule ligne
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python3 -c "import json; print(json.dumps(json.load(open('session.json'))))"
  # → copier tout le résultat (une longue ligne JSON)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE 3 — Mettre les fichiers sur GitHub
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  git init aviator-scraper
  cd aviator-scraper
  # Copier : scraper_betpawa.py server.py Dockerfile requirements.txt render.yaml
  git add .
  git commit -m "aviator scraper"
  # Créer un repo sur github.com puis :
  git remote add origin https://github.com/TON_USER/aviator-scraper.git
  git push -u origin main

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE 4 — Déployer sur Render
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Aller sur https://render.com → Sign up with GitHub (sans carte)
  2. New → Web Service → connecter ton repo GitHub
  3. Render détecte automatiquement le Dockerfile
  4. Dans "Environment Variables" :
       Clé   : SESSION_JSON
       Valeur: [coller la longue ligne JSON de l'étape 2]
  5. Cliquer "Create Web Service"
  6. Attendre le build (~5 min, Chromium est lourd)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ÉTAPE 5 — Accéder aux données
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  → Dashboard live : https://aviator-scraper.onrender.com
    (affiche les tours en temps réel, refresh auto 15s)

  → Télécharger le CSV :
    Le CSV est dans le container. Pour le récupérer,
    ajouter une route /download dans server.py
    (voir note ci-dessous)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  LIMITATIONS DU FREE TIER RENDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - Le service se met en veille après 15 min d'inactivité
    → Visiter la page dashboard toutes les 15 min
    → OU utiliser UptimeRobot (gratuit) pour pinger toutes
       les 5 min : https://uptimerobot.com

  - Le disque est éphémère : si le container redémarre,
    le CSV est perdu. Solution : ajouter une sauvegarde
    vers Google Drive ou Pastebin (on peut faire ça).

  - 750h gratuites/mois = ~31 jours. Suffisant pour 1 mois.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
