#!/usr/bin/env python3
"""
scraper_betpawa.py
──────────────────
Scraper BetPawa Aviator — tourne headless sur VPS.
Charge la session depuis session.json (generee par save_session.py).

Usage :
    python3 scraper_betpawa.py                  # tourne indefiniment
    python3 scraper_betpawa.py --duree 604800   # 7 jours
    python3 scraper_betpawa.py -o data.csv
    python3 scraper_betpawa.py --stats
"""

import asyncio
import csv
import json
import argparse
import signal
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

URL_BETPAWA   = "https://www.betpawa.cm/casino/game/3255"
IFRAME_DOMAIN = "spribegaming.com"
SESSION_FILE  = "session.json"
POLL_MS       = 300

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def log(msg, color=RESET):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{ts}] {msg}{RESET}", flush=True)


# ──────────────────────────────────────────────────────────
# Lire toute la liste des payouts dans le frame
# ──────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────
# Chargement de la session
# ──────────────────────────────────────────────────────────
def charger_session():
    path = Path(SESSION_FILE)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────
# Attente du frame + liste initiale
# ──────────────────────────────────────────────────────────
async def attendre_frame_et_liste(page, timeout_s=120):
    log("Attente du frame spribegaming.com ...", YELLOW)
    debut = asyncio.get_event_loop().time()

    frame = None
    while asyncio.get_event_loop().time() - debut < timeout_s:
        frame = trouver_frame_spribe(page)
        if frame:
            log(f"Frame trouve : {frame.url[:80]}", GREEN)
            break
        await asyncio.sleep(1.0)

    if frame is None:
        log("Frame spribegaming.com non trouve !", RED)
        for i, f in enumerate(page.frames):
            log(f"  {i}: {f.url[:90]}", YELLOW)
        return None, []

    log("Attente de la liste des payouts ...", YELLOW)
    while asyncio.get_event_loop().time() - debut < timeout_s:
        liste = await lire_liste_payouts(frame)
        if liste:
            log(f"Liste initiale ({len(liste)} elements) : {liste[:4]} ...", GREEN)
            return frame, liste
        await asyncio.sleep(0.8)

    log("Liste vide apres timeout.", RED)
    return frame, []


# ──────────────────────────────────────────────────────────
# Reconnexion automatique si la session expire
# ──────────────────────────────────────────────────────────
async def verifier_session_active(page):
    """Retourne True si la page semble connectee (pas de formulaire login)."""
    try:
        url = page.url
        # Si redirige vers login → session expirée
        if "login" in url or "signin" in url:
            return False
        # Vérifier qu'un element connecte est present
        logged_in = await page.evaluate("""
            () => {
                // Cherche un element typique de l'interface connectee
                return !!(
                    document.querySelector('[class*="balance"]') ||
                    document.querySelector('[class*="user"]') ||
                    document.querySelector('[class*="account"]') ||
                    document.querySelector('[class*="logout"]')
                );
            }
        """)
        return logged_in
    except Exception:
        return True  # On suppose connecté si on ne peut pas vérifier


# ──────────────────────────────────────────────────────────
# CSV
# ──────────────────────────────────────────────────────────
class ResultatCSV:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.count = 0
        if not self.filepath.exists():
            with open(self.filepath, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["#", "timestamp", "cote", "cote_numerique"])
            log(f"Fichier cree : {self.filepath}", CYAN)
        else:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self.count = sum(1 for _ in f) - 1
            log(f"Reprise : {self.count} tours existants", YELLOW)

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


# ──────────────────────────────────────────────────────────
# Scraper principal
# ──────────────────────────────────────────────────────────
async def scraper(output, duree, headless):
    log(f"{BOLD}=== Scraper BetPawa Aviator (VPS mode) ==={RESET}", CYAN)
    log(f"Fichier : {output} | Headless : {headless}", CYAN)
    log("─" * 55, CYAN)

    # Charger la session
    session = charger_session()
    if session:
        log(f"Session chargee depuis {SESSION_FILE} ({len(session['storage_state'].get('cookies', []))} cookies)", GREEN)
    else:
        log(f"Aucun {SESSION_FILE} trouve → mode login manuel (fenetre visible)", YELLOW)
        headless = False  # Force visible si pas de session

    csv_writer = ResultatCSV(output)
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, lambda: stop_event.set())
    loop.add_signal_handler(signal.SIGTERM, lambda: stop_event.set())

    if duree:
        async def auto_stop():
            await asyncio.sleep(duree)
            log(f"Duree max atteinte ({duree}s = {duree//3600}h).", YELLOW)
            stop_event.set()
        asyncio.create_task(auto_stop())

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",       # important sur VPS (peu de RAM)
                "--disable-blink-features=AutomationControlled",
            ]
        )

        # Créer le contexte avec ou sans session sauvegardée
        if session:
            context = await browser.new_context(
                storage_state=session["storage_state"],
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="fr-FR",
            )
        else:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="fr-FR",
            )

        page = await context.new_page()

        # Injecter le localStorage si disponible
        if session and session.get("local_storage"):
            await page.add_init_script(f"""
                const data = {json.dumps(session['local_storage'])};
                for (const [k, v] of Object.entries(data)) {{
                    try {{ localStorage.setItem(k, v); }} catch(e) {{}}
                }}
            """)

        log(f"Ouverture : {URL_BETPAWA}", YELLOW)
        try:
            await page.goto(URL_BETPAWA, wait_until="domcontentloaded", timeout=60_000)
        except PlaywrightTimeout:
            log("Timeout chargement (normal).", YELLOW)

        # Si pas de session → attendre login manuel
        if not session:
            log("─" * 55, YELLOW)
            log("Connectez-vous dans la fenetre puis appuyez ENTREE", YELLOW)
            input()

        # Vérifier que la session est active
        actif = await verifier_session_active(page)
        if not actif:
            log("Session expirée ou non connecté !", RED)
            log("Relancez save_session.py sur votre PC pour regenerer session.json", RED)
            await browser.close()
            return

        log("Session active ✓", GREEN)

        # Attendre le frame + liste
        frame, liste_actuelle = await attendre_frame_et_liste(page, timeout_s=120)

        if not liste_actuelle:
            log("Abandon. Verifiez connexion + que le jeu est ouvert.", RED)
            await browser.close()
            return

        log("Surveillance demarre ! Ctrl+C / SIGTERM pour arreter.", GREEN)
        log(f"Tete de liste initiale : {liste_actuelle[0]}", CYAN)
        log("─" * 55, CYAN)

        erreurs = 0
        derniere_reconnexion = asyncio.get_event_loop().time()

        while not stop_event.is_set():
            # Re-trouver le frame si rechargement
            if frame not in page.frames:
                frame = trouver_frame_spribe(page)
                if frame is None:
                    await asyncio.sleep(2)
                    continue

            try:
                nouvelle_liste = await lire_liste_payouts(frame)
                erreurs = 0
            except Exception as e:
                erreurs += 1
                if erreurs >= 5:
                    log(f"Erreurs repetees: {e}", RED)
                    # Tentative de rechargement
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=30_000)
                        frame, nouvelle_liste = await attendre_frame_et_liste(page, timeout_s=60)
                        if nouvelle_liste:
                            liste_actuelle = nouvelle_liste
                        erreurs = 0
                        log("Page rechargee avec succes.", GREEN)
                    except Exception:
                        pass
                await asyncio.sleep(2)
                continue

            # Vérification session toutes les 30 min
            now = asyncio.get_event_loop().time()
            if now - derniere_reconnexion > 1800:
                actif = await verifier_session_active(page)
                if not actif:
                    log("Session expirée, rechargement...", YELLOW)
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=30_000)
                        frame, nouvelle_liste = await attendre_frame_et_liste(page, 60)
                        if nouvelle_liste:
                            liste_actuelle = nouvelle_liste
                    except Exception as e:
                        log(f"Echec rechargement: {e}", RED)
                derniere_reconnexion = now

            if not nouvelle_liste:
                # Tour en cours (avion vole) → attendre
                await asyncio.sleep(POLL_MS / 1000)
                continue

            # ── Détecter les nouveaux éléments en tête de liste ──
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
                    if val is not None:
                        couleur = GREEN if val >= 2.0 else RED
                        bar = "█" * min(int(val), 20)
                        log(f"Tour #{num:>4}  |  {cote:<10}  {bar}", couleur)
                    else:
                        log(f"Tour #{num:>4}  |  {cote}", YELLOW)

                liste_actuelle = nouvelle_liste

            await asyncio.sleep(POLL_MS / 1000)

        log("─" * 55, CYAN)
        log(f"Termine. {csv_writer.count} tours -> {csv_writer.filepath.resolve()}", GREEN)
        await browser.close()


# ──────────────────────────────────────────────────────────
# Stats
# ──────────────────────────────────────────────────────────
def afficher_stats(filepath):
    path = Path(filepath)
    if not path.exists():
        print("Fichier introuvable.")
        return
    cotes = []
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                cotes.append(float(row["cote_numerique"]))
            except (ValueError, KeyError):
                pass
    if not cotes:
        print("Aucune donnee.")
        return
    print(f"\n{'─'*48}")
    print(f"  STATISTIQUES  ({len(cotes)} tours)")
    print(f"{'─'*48}")
    print(f"  Minimum  : {min(cotes):.2f}x")
    print(f"  Maximum  : {max(cotes):.2f}x")
    print(f"  Moyenne  : {sum(cotes)/len(cotes):.2f}x")
    print(f"  Mediane  : {sorted(cotes)[len(cotes)//2]:.2f}x")
    print(f"\n  Frequences cote >= seuil :")
    for s in [1.2, 1.5, 2.0, 3.0, 5.0, 10.0, 20.0]:
        n = sum(1 for c in cotes if c >= s)
        pct = 100 * n / len(cotes)
        bar = "▓" * int(pct / 2)
        print(f"    >={s:5.1f}x : {n:>5}/{len(cotes)} ({pct:5.1f}%) {bar}")
    print(f"{'─'*48}\n")


def main():
    parser = argparse.ArgumentParser(description="Scraper BetPawa Aviator - VPS")
    parser.add_argument("--output", "-o", default="resultats_betpawa.csv")
    parser.add_argument("--duree", "-d", type=int, default=None,
                        help="Duree en secondes (ex: 604800 = 7 jours)")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Mode headless (defaut: True sur VPS)")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.stats:
        afficher_stats(args.output)
    else:
        asyncio.run(scraper(output=args.output, duree=args.duree, headless=args.headless))

if __name__ == "__main__":
    main()
