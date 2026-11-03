#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Score de sommeil /100 pour Garmin Forerunner 55 (qui n'a pas le score natif).

Principe : la FR55 mesure les stades de sommeil mais ne calcule pas de score.
Ce script récupère les données de la nuit via l'API Garmin Connect (non
officielle, bibliothèque `garminconnect`), calcule un score sur 100 avec des
coefficients issus de la littérature scientifique, puis le publie
(fichier local + GitHub Pages pour le widget montre + notification ntfy).

=== Modèle de score (100 points) ===================================================
Composante      Poids  Cible optimale          Source principale
-----------------------------------------------------------------------------------
Durée totale     30    7 à 9 h                 Hirshkowitz et al. 2015, Sleep Health
                                               (recommandations NSF, adultes 18-64) ;
                                               Watson et al. 2015, Sleep (consensus
                                               AASM/SRS : >= 7 h)
Efficacité       20    >= 85 % (temps dormi /  Ohayon et al. 2017, Sleep Health
                       temps au lit)           (indicateurs de qualité NSF)
Sommeil profond  15    ~13-23 % du sommeil     Ohayon et al. 2004, Sleep
(N3)                   (jeune adulte)          (méta-analyse normative)
Sommeil REM      15    ~20-25 % du sommeil     Ohayon et al. 2004, Sleep
Continuité       10    WASO <= 20 min,         Ohayon et al. 2017, Sleep Health
(WASO/réveils)         <= 1 réveil > 5 min
FC nocturne      10    FC moy. sommeil proche  Trinder et al. 2001, J Sleep Res
                       de la FC repos          (baisse parasympathique nocturne)
-----------------------------------------------------------------------------------
Pourquoi les stades ne pèsent "que" 30 pts au total : la classification des
stades au poignet (accéléro + FC) reste approximative comparée à la
polysomnographie (Chinoy et al. 2021, Sleep). La durée et l'efficacité, elles,
sont mesurées de façon fiable — d'où leur poids dominant (50 pts).

Si une donnée manque (ex. REM non détecté), le score est renormalisé sur les
composantes disponibles pour rester sur 100.

=== Usage ==========================================================================
  python sleep_score.py                 # nuit dernière
  python sleep_score.py --date 2026-07-07
  python sleep_score.py --debug         # affiche le JSON brut Garmin (à faire
                                        # la 1re fois pour vérifier les champs)
  python sleep_score.py --no-publish    # calcul seul, sans publication

Identifiants : variables d'environnement GARMIN_EMAIL / GARMIN_PASSWORD,
sinon saisie interactive. Les tokens sont mis en cache (~/.garmin_tokens),
donc le mot de passe n'est demandé qu'une fois.

Publication (optionnelle, via variables d'environnement) :
  GITHUB_TOKEN + GITHUB_REPO ("pseudo/repo") [+ GITHUB_FILE, défaut score.json]
      -> pousse score.json sur le repo (à coupler avec GitHub Pages pour le widget)
  NTFY_TOPIC ("un-nom-unique-difficile-a-deviner")
      -> notification push ntfy.sh (s'affiche sur la montre via le téléphone)
"""

import argparse
import base64
import datetime
import getpass
import json
import os
import sys

import requests
from garminconnect import Garmin

TOKEN_DIR = os.path.expanduser("~/.garmin_tokens")
# Detail complet des mesures, garde en local uniquement (fichier gitignore).
# Separe de score.json, qui est suivi par git et publie : y ecrire le detail
# exposerait les donnees de sante au premier "git add".
# Chemin absolu car la tache planifiee s'execute depuis C:\Windows\System32.
FICHIER_SORTIE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "score_detail.json"
)

POIDS = {
    "duree": 30,
    "efficacite": 20,
    "profond": 15,
    "rem": 15,
    "continuite": 10,
    "fc": 10,
}

# ------------------------------------------------------------------ utilitaires


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ------------------------------------------------------- fonctions de scoring


def pts_duree(heures):
    """30 pts. Optimal : 7-9 h (Hirshkowitz 2015 ; Watson 2015 : >= 7 h).
    En dessous : -10 pts par heure manquante (6 h -> 20, 5 h -> 10, 4 h -> 0).
    Au-dessus de 9 h : légère pénalité (plancher 20), le sommeil très long
    étant associé à une moins bonne qualité sans être "dangereux" ponctuellement."""
    if heures is None:
        return None
    if 7 <= heures <= 9:
        return 30.0
    if heures < 7:
        return clamp(30 - (7 - heures) * 10, 0, 30)
    return clamp(30 - (heures - 9) * 5, 20, 30)


def pts_efficacite(eff):
    """20 pts. Efficacité = temps dormi / (temps dormi + temps éveillé au lit).
    >= 85 % = bon indicateur de qualité (Ohayon 2017) ; < 75 % = médiocre."""
    if eff is None:
        return None
    e = eff * 100
    if e >= 92:
        return 20.0
    if e >= 85:
        return 14 + (e - 85) * (6 / 7)      # 85 % -> 14, 92 % -> 20
    if e >= 75:
        return 7 + (e - 75) * (7 / 10)      # 75 % -> 7, 85 % -> 14
    return clamp(7 * (e - 60) / 15, 0, 7)   # 60 % -> 0


def pts_profond(pct):
    """15 pts. N3 (profond) ~13-23 % du temps de sommeil chez le jeune adulte
    (Ohayon 2004). Excès de profond peu pénalisé : souvent signe de dette de
    sommeil ou de récupération après effort, pas un problème en soi."""
    if pct is None:
        return None
    if 13 <= pct <= 23:
        return 15.0
    if pct < 13:
        return clamp(15 * (pct - 5) / 8, 0, 15)   # 5 % -> 0, 13 % -> 15
    return clamp(15 - (pct - 23) * 0.5, 10, 15)


def pts_rem(pct):
    """15 pts. REM ~20-25 % du temps de sommeil (Ohayon 2004)."""
    if pct is None:
        return None
    if 20 <= pct <= 25:
        return 15.0
    if pct < 20:
        return clamp(15 * (pct - 8) / 12, 0, 15)  # 8 % -> 0, 20 % -> 15
    return clamp(15 - (pct - 25) * 0.6, 8, 15)


def pts_continuite(waso_min, nb_reveils):
    """10 pts. WASO (éveil après endormissement) <= 20 min = bon,
    > 40-50 min = mauvais ; <= 1 réveil > 5 min = bon (Ohayon 2017)."""
    if waso_min is None:
        return None
    if waso_min <= 20:
        p = 10.0
    elif waso_min <= 50:
        p = 10 - (waso_min - 20) * (8 / 30)       # 20 min -> 10, 50 min -> 2
    else:
        p = clamp(2 - (waso_min - 50) * 0.1, 0, 2)
    if nb_reveils is not None and nb_reveils > 1:
        p -= min(2, (nb_reveils - 1) * 0.5)
    return clamp(p, 0, 10)


def pts_fc(fc_sommeil, fc_repos):
    """10 pts. Une FC nocturne basse relativement à la FC de repos reflète la
    dominance parasympathique et une bonne récupération (Trinder 2001).
    NB : la "FC repos" Garmin est déjà ~le minimum de la journée (souvent
    atteint pendant le sommeil), d'où des seuils exprimés en delta serré."""
    if fc_sommeil is None or fc_repos is None:
        return None
    d = fc_sommeil - fc_repos
    if d <= 3:
        return 10.0
    if d <= 12:
        return 10 - (d - 3) * (7 / 9)             # +3 -> 10, +12 -> 3
    return clamp(3 - (d - 12) * (3 / 8), 0, 3)    # +20 -> 0


# ----------------------------------------------------------- accès aux données


def obtenir_client():
    """Connexion Garmin avec cache de tokens (mot de passe demandé 1 seule fois)."""
    try:
        client = Garmin()
        client.login(TOKEN_DIR)
        return client
    except Exception:
        pass
    email = os.environ.get("GARMIN_EMAIL") or input("Email Garmin : ")
    mdp = os.environ.get("GARMIN_PASSWORD") or getpass.getpass("Mot de passe : ")
    client = Garmin(
        email=email,
        password=mdp,
        prompt_mfa=lambda: input("Code de validation Garmin : "),
    )
    # Passer TOKEN_DIR ici est ce qui declenche la sauvegarde des tokens :
    # sans lui, le mot de passe serait redemande a chaque execution et la
    # tache planifiee echouerait.
    client.login(TOKEN_DIR)
    return client


def moyenne_liste_fc(liste):
    """Moyenne des relevés FC pendant le sommeil ([{'value': x, ...}, ...])."""
    if not liste:
        return None
    valeurs = [p.get("value") for p in liste if isinstance(p, dict) and p.get("value")]
    return round(sum(valeurs) / len(valeurs), 1) if valeurs else None


def extraire_mesures(client, date_str, debug=False):
    """Récupère et normalise les mesures de la nuit. Tous les accès sont
    défensifs (.get) car les noms de champs Garmin peuvent évoluer :
    lancer une fois avec --debug pour vérifier sur TES données."""
    brut = client.get_sleep_data(date_str)
    if debug:
        print(json.dumps(brut, indent=2, ensure_ascii=False))

    dto = (brut or {}).get("dailySleepDTO") or {}
    tst_s = dto.get("sleepTimeSeconds")
    if not tst_s:
        return None  # nuit pas encore synchronisée (ou pas de données)

    profond_s = dto.get("deepSleepSeconds") or 0
    leger_s = dto.get("lightSleepSeconds") or 0
    rem_s = dto.get("remSleepSeconds")          # peut être None/0 selon détection
    eveil_s = dto.get("awakeSleepSeconds") or 0
    non_mesure_s = dto.get("unmeasurableSleepSeconds") or 0

    temps_au_lit_s = tst_s + eveil_s + non_mesure_s
    efficacite = tst_s / temps_au_lit_s if temps_au_lit_s else None

    fc_sommeil = moyenne_liste_fc(brut.get("sleepHeartRate"))
    fc_repos = brut.get("restingHeartRate")
    if fc_repos is None:
        try:
            rhr = client.get_rhr_day(date_str)
            fc_repos = (
                rhr.get("allMetrics", {})
                .get("metricsMap", {})
                .get("WELLNESS_RESTING_HEART_RATE", [{}])[0]
                .get("value")
            )
        except Exception:
            fc_repos = None

    return {
        "tst_h": round(tst_s / 3600, 2),
        "profond_pct": round(100 * profond_s / tst_s, 1) if tst_s else None,
        "rem_pct": round(100 * rem_s / tst_s, 1) if (rem_s and tst_s) else None,
        "leger_pct": round(100 * leger_s / tst_s, 1) if tst_s else None,
        "efficacite_pct": round(100 * efficacite, 1) if efficacite else None,
        "waso_min": round(eveil_s / 60, 1),
        "reveils": dto.get("awakeCount"),
        "agitation": brut.get("restlessMomentsCount"),
        "fc_sommeil": fc_sommeil,
        "fc_repos": fc_repos,
        "stress_sommeil": dto.get("avgSleepStress"),
    }


# --------------------------------------------------------------- score global


def calculer_score(m):
    sous = {
        "duree": pts_duree(m["tst_h"]),
        "efficacite": pts_efficacite(
            m["efficacite_pct"] / 100 if m["efficacite_pct"] else None
        ),
        "profond": pts_profond(m["profond_pct"]),
        "rem": pts_rem(m["rem_pct"]),
        "continuite": pts_continuite(m["waso_min"], m["reveils"]),
        "fc": pts_fc(m["fc_sommeil"], m["fc_repos"]),
    }
    dispo = {k: v for k, v in sous.items() if v is not None}
    if not dispo:
        return None, sous
    # Renormalisation sur 100 si des composantes manquent
    score = 100 * sum(dispo.values()) / sum(POIDS[k] for k in dispo)
    return round(clamp(score, 0, 100)), {
        k: (round(v, 1) if v is not None else None) for k, v in sous.items()
    }


def libelle(score):
    if score >= 90: return "Excellent"
    if score >= 80: return "Bon"
    if score >= 60: return "Correct"
    if score >= 40: return "Médiocre"
    return "Mauvais"


# ---------------------------------------------------------------- publication


def publier_github(payload):
    """Publie le score sur GitHub Pages pour le widget.

    Ne publie que les trois champs lus par la montre. Le detail des mesures
    (frequence cardiaque, stades, horaires) reste dans le fichier local : le
    depot est public et chaque publication cree un commit conserve a vie.
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    chemin = os.environ.get("GITHUB_FILE", "score.json")
    if not token or not repo:
        print("-> publication GitHub ignoree : GITHUB_TOKEN ou GITHUB_REPO absent "
              "(variable definie mais terminal pas relance ?)")
        return False

    public = {
        "date": payload["date"],
        "score": payload["score"],
        "qualite": payload["qualite"],
    }

    api = f"https://api.github.com/repos/{repo}/contents/{chemin}"
    entetes = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json"}
    r = requests.get(api, headers=entetes, timeout=20)
    sha = r.json().get("sha") if r.status_code == 200 else None
    corps = {
        "message": f"score sommeil {payload['date']}",
        "content": base64.b64encode(
            json.dumps(public, ensure_ascii=False).encode()
        ).decode(),
    }
    if sha:
        corps["sha"] = sha
    r = requests.put(api, headers=entetes, json=corps, timeout=20)
    if not r.ok:
        print(f"-> echec de la publication GitHub : HTTP {r.status_code} "
              f"{r.json().get('message', '')}")
    return r.ok


def publier_ntfy(payload):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    m = payload["mesures"]

    def val(x, unite):
        # Une mesure absente (REM non detecte par exemple) afficherait "None"
        return f"{x} {unite}" if x is not None else "—"

    msg = (f"{payload['score']}/100 ({payload['qualite']})\n"
           f"Durée {val(m['tst_h'], 'h')} · Profond {val(m['profond_pct'], '%')} · "
           f"REM {val(m['rem_pct'], '%')} · Efficacité {val(m['efficacite_pct'], '%')}")
    r = requests.post(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
                      headers={"Title": f"Sommeil {payload['date']}"}, timeout=20)
    if not r.ok:
        print(f"-> echec de la notification ntfy : HTTP {r.status_code}")
    return r.ok


# ----------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="Score de sommeil Garmin FR55")
    ap.add_argument("--date", help="AAAA-MM-JJ (défaut : aujourd'hui)")
    ap.add_argument("--debug", action="store_true", help="affiche le JSON brut")
    ap.add_argument("--no-publish", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="recalcule meme si le score du jour existe deja")
    args = ap.parse_args()

    date_str = args.date or datetime.date.today().isoformat()

    # La tache se declenche aussi a l'ouverture de session, donc plusieurs fois
    # par jour. Sans ce garde-fou, chaque lancement referait un appel a Garmin
    # et un commit identique sur le depot.
    if not args.force and os.path.exists(FICHIER_SORTIE):
        try:
            with open(FICHIER_SORTIE, encoding="utf-8") as f:
                if json.load(f).get("date") == date_str:
                    print(f"Score du {date_str} deja calcule. --force pour refaire.")
                    return
        except (ValueError, OSError):
            pass  # fichier illisible : on recalcule

    client = obtenir_client()
    mesures = extraire_mesures(client, date_str, debug=args.debug)

    if mesures is None:
        print(f"Pas de données de sommeil pour {date_str}.")
        print("La montre a-t-elle synchronisé avec le téléphone ce matin ?")
        sys.exit(2)

    score, sous_scores = calculer_score(mesures)
    payload = {
        "date": date_str,
        "score": score,
        "qualite": libelle(score),
        "sous_scores": sous_scores,
        "mesures": mesures,
    }

    print(f"\n=== Nuit du {date_str} : {score}/100 ({payload['qualite']}) ===")
    for k, v in sous_scores.items():
        print(f"  {k:<11} {v if v is not None else '—':>5} / {POIDS[k]}")
    print(f"  Durée {mesures['tst_h']} h | Profond {mesures['profond_pct']} % | "
          f"REM {mesures['rem_pct']} % | Effic. {mesures['efficacite_pct']} % | "
          f"WASO {mesures['waso_min']} min | "
          f"FC nuit {mesures['fc_sommeil']} vs repos {mesures['fc_repos']}")

    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if not args.no_publish:
        if publier_github(payload):
            print("-> publié sur GitHub")
        if publier_ntfy(payload):
            print("-> notification ntfy envoyée")


if __name__ == "__main__":
    main()
