#!/usr/bin/env python3
"""
server.py
─────────
Serveur HTTP minimal requis par Render.
Lance le scraper en arrière-plan dans un thread séparé.
La session BetPawa est chargée depuis session.json (inclus dans le repo).
"""

import os
import json
import asyncio
import threading
import csv
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Charger la session depuis le fichier ────────────────────────
OUTPUT_FILE  = os.environ.get("OUTPUT_FILE", "resultats_betpawa.csv")
SESSION_FILE = "/app/session.json"

if Path(SESSION_FILE).exists():
    print("[INIT] session.json trouvé ✓", flush=True)
else:
    print("[INIT] ⚠️  session.json introuvable !", flush=True)
    SESSION_FILE = None


# ── Stats globales (affichées sur la page web) ───────────────────
stats = {
    "tours": 0,
    "derniere_cote": "—",
    "derniere_maj": "—",
    "status": "Démarrage...",
    "start_time": datetime.now().isoformat(timespec="seconds"),
}


# ── Serveur HTTP minimal ─────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        # Lire les dernières lignes du CSV
        recents = []
        try:
            with open(f"/app/{OUTPUT_FILE}", "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
                recents = rows[-11:][::-1]  # 10 derniers, plus récent en tête
        except Exception:
            pass

        lignes_html = ""
        for r in recents[1:]:  # skip header si présent
            if len(r) >= 4:
                try:
                    val = float(r[3])
                    couleur = "#4CAF50" if val >= 2.0 else "#f44336"
                except Exception:
                    couleur = "#aaa"
                lignes_html += f'<tr><td>{r[0]}</td><td>{r[1]}</td><td style="color:{couleur};font-weight:bold">{r[2]}</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="15">
  <title>Aviator Scraper</title>
  <style>
    body {{ font-family: monospace; background: #1a1a2e; color: #eee; padding: 2rem; }}
    h1 {{ color: #00d4ff; }} 
    .badge {{ display:inline-block; padding:4px 12px; border-radius:20px; margin:4px; }}
    .green {{ background:#1b5e20; color:#a5d6a7; }}
    .blue  {{ background:#0d47a1; color:#90caf9; }}
    table {{ border-collapse:collapse; margin-top:1rem; width:100%; max-width:500px; }}
    th {{ background:#0d47a1; padding:8px 16px; text-align:left; }}
    td {{ padding:6px 16px; border-bottom:1px solid #333; }}
    tr:hover {{ background:#ffffff11; }}
  </style>
</head>
<body>
  <h1>🛩️ Aviator Scraper — BetPawa</h1>
  <p>
    <span class="badge green">● {stats['status']}</span>
    <span class="badge blue">Tours: {stats['tours']}</span>
    <span class="badge blue">Dernière cote: {stats['derniere_cote']}</span>
  </p>
  <p style="color:#888">Démarré le {stats['start_time']} | Dernière MAJ: {stats['derniere_maj']} | Refresh auto 15s</p>
  <table>
    <tr><th>#</th><th>Timestamp</th><th>Cote</th></tr>
    {lignes_html if lignes_html else '<tr><td colspan="3" style="color:#888">En attente de données...</td></tr>'}
  </table>
</body>
</html>"""
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, *args):
        pass  # Silence les logs HTTP


def lancer_serveur():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[HTTP] Serveur sur port {port}", flush=True)
    server.serve_forever()


# ── Scraper (importé depuis scraper_betpawa.py) ──────────────────
import sys
sys.path.insert(0, "/app")

# On importe les fonctions du scraper
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

URL_BETPAWA   = "https://www.betpawa.cm/casino/game/3255"
IFRAME_DOMAIN = "spribegaming.com"
POLL_MS       = 300

JS_GET_ALL_PAYOUTS = """
() => {
    const els = document.querySelectorAll('[class*="payout"]');
    const results = [];
    for (const el of els) {
        const txt = el.innerText.trim();
        if (/^\\d+\\.\\d+x$/i.test(txt)) results.push(txt);
    }
    return results;
}
"""

def trouver_frame_spribe(page):
    for frame in page.frames:
        if IFRAME_DOMAIN in frame.url:
            return frame
    return None

async def lire_liste_payouts(frame):
    try:
        return await frame.evaluate(JS_GET_ALL_PAYOUTS)
    except Exception:
        return []

class ResultatCSV:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.count = 0
        if not self.filepath.exists():
            with open(self.filepath, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["#", "timestamp", "cote", "cote_numerique"])
        else:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self.count = sum(1 for _ in f) - 1
        print(f"[CSV] {self.count} tours existants dans {self.filepath}", flush=True)

    def enregistrer(self, cote_brute):
        self.count += 1
        ts = datetime.now().isoformat(timespec="seconds")
        try:
            valeur = float(cote_brute.lower().replace("x", "").strip())
        except ValueError:
            valeur = None
        with open(self.filepath, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([self.count, ts, cote_brute, valeur])
        return self.count, valeur


async def run_scraper():
    stats["status"] = "Démarrage navigateur..."

    session = None
    if SESSION_FILE and Path(SESSION_FILE).exists():
        with open(SESSION_FILE) as f:
            session = json.load(f)
        print("[SESSION] Chargée.", flush=True)
    else:
        print("[SESSION] Introuvable, abandon.", flush=True)
        stats["status"] = "❌ SESSION_JSON manquante"
        return

    csv_writer = ResultatCSV(f"/app/{OUTPUT_FILE}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = await browser.new_context(
            storage_state=session["storage_state"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
        )

        if session.get("local_storage"):
            await context.add_init_script(f"""
                const data = {json.dumps(session['local_storage'])};
                for (const [k, v] of Object.entries(data)) {{
                    try {{ localStorage.setItem(k, v); }} catch(e) {{}}
                }}
            """)

        page = await context.new_page()
        stats["status"] = "Chargement de la page..."
        print(f"[NAV] Ouverture {URL_BETPAWA}", flush=True)

        try:
            await page.goto(URL_BETPAWA, wait_until="domcontentloaded", timeout=60_000)
        except PlaywrightTimeout:
            print("[NAV] Timeout (normal)", flush=True)

        # Attendre le frame Spribe
        stats["status"] = "Attente du frame Spribe..."
        frame = None
        for _ in range(120):
            frame = trouver_frame_spribe(page)
            if frame:
                break
            await asyncio.sleep(1)

        if not frame:
            stats["status"] = "❌ Frame Spribe introuvable"
            await browser.close()
            return

        # Attendre la liste
        liste_actuelle = []
        for _ in range(60):
            liste_actuelle = await lire_liste_payouts(frame)
            if liste_actuelle:
                break
            await asyncio.sleep(1)

        if not liste_actuelle:
            stats["status"] = "❌ Liste payouts vide"
            await browser.close()
            return

        stats["status"] = "🟢 En cours"
        stats["tours"] = csv_writer.count
        print(f"[OK] Surveillance démarrée. Tête: {liste_actuelle[0]}", flush=True)

        erreurs = 0
        while True:
            if frame not in page.frames:
                frame = trouver_frame_spribe(page)
                if not frame:
                    await asyncio.sleep(2)
                    continue

            try:
                nouvelle_liste = await lire_liste_payouts(frame)
                erreurs = 0
            except Exception as e:
                erreurs += 1
                if erreurs >= 5:
                    print(f"[ERR] {e}", flush=True)
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=30_000)
                        for _ in range(30):
                            frame = trouver_frame_spribe(page)
                            if frame:
                                nl = await lire_liste_payouts(frame)
                                if nl:
                                    liste_actuelle = nl
                                    break
                            await asyncio.sleep(1)
                    except Exception:
                        pass
                    erreurs = 0
                await asyncio.sleep(2)
                continue

            if not nouvelle_liste:
                await asyncio.sleep(POLL_MS / 1000)
                continue

            if nouvelle_liste != liste_actuelle:
                tete_ancienne = liste_actuelle[0] if liste_actuelle else None
                nouveaux = []
                for i, cote in enumerate(nouvelle_liste):
                    if cote == tete_ancienne and nouvelle_liste[i:i+3] == liste_actuelle[:3]:
                        nouveaux = nouvelle_liste[:i]
                        break
                else:
                    nouveaux = nouvelle_liste[:1]

                for cote in reversed(nouveaux):
                    num, val = csv_writer.enregistrer(cote)
                    stats["tours"] = num
                    stats["derniere_cote"] = cote
                    stats["derniere_maj"] = datetime.now().strftime("%H:%M:%S")
                    print(f"[TOUR #{num}] {cote}", flush=True)

                liste_actuelle = nouvelle_liste

            await asyncio.sleep(POLL_MS / 1000)


def lancer_scraper():
    asyncio.run(run_scraper())


# ── Point d'entrée ───────────────────────────────────────────────
if __name__ == "__main__":
    # Lancer le scraper dans un thread séparé
    t = threading.Thread(target=lancer_scraper, daemon=True)
    t.start()

    # Lancer le serveur HTTP (bloquant, dans le thread principal)
    lancer_serveur()
