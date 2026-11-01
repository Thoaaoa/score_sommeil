# Score de sommeil /100 sur Garmin Forerunner 55

La FR55 mesure le sommeil (stades, FC) mais ne calcule pas le score natif de
Garmin (fonction Firstbeat réservée aux modèles supérieurs). L'API Connect IQ
embarquée n'exposant pas les stades de sommeil aux apps tierces, le score est
calculé **hors montre** à partir des données Garmin Connect, puis renvoyé sur
la montre.

## Architecture

```
FR55 --(sync BLE matin)--> app Garmin Connect --(cloud)--> Garmin Connect Web
                                                                |
                                              sleep_score.py (ton PC, planifié)
                                                |                    |
                                     score.json sur GitHub     notification ntfy
                                                |                    |
                              widget Connect IQ sur la FR55    notif miroir montre
                                        (v2)                        (v1)
```

## Modèle de score (sources)

| Composante | Poids | Cible | Source |
|---|---|---|---|
| Durée totale | 30 | 7–9 h | Hirshkowitz et al. 2015, *Sleep Health* (NSF) ; Watson et al. 2015, *Sleep* (AASM/SRS) |
| Efficacité | 20 | ≥ 85 % | Ohayon et al. 2017, *Sleep Health* (NSF) |
| Sommeil profond | 15 | 13–23 % | Ohayon et al. 2004, *Sleep* (méta-analyse) |
| Sommeil REM | 15 | 20–25 % | Ohayon et al. 2004, *Sleep* |
| Continuité (WASO, réveils) | 10 | WASO ≤ 20 min, ≤ 1 réveil | Ohayon et al. 2017 |
| FC nocturne vs FC repos | 10 | delta ≤ 3 bpm | Trinder et al. 2001, *J Sleep Res* |

Les stades pèsent 30 pts au total car leur mesure au poignet est approximative
(Chinoy et al. 2021, *Sleep*, comparaison trackers vs polysomnographie).
Composante manquante → score renormalisé sur 100.

## Étape 1 — Le script (15 min)

1. Python 3.10+ puis : `pip install garminconnect requests`
2. Premier lancement pour vérifier les champs sur TES données :
   `python sleep_score.py --debug --no-publish`
   (email + mot de passe Garmin demandés une fois, tokens mis en cache ensuite ;
   si un champ du JSON brut diffère de ce que lit le script, adapter
   `extraire_mesures()` — tout est en `.get()` défensif)
3. Lancement normal : `python sleep_score.py` → affiche le score + écrit `score.json`

Important : la montre doit avoir synchronisé avec le téléphone avant (ouvrir
l'app Garmin Connect au réveil suffit). Sinon le script sort en "pas de données",
il suffit de le relancer plus tard.

## Étape 2 — v1 rapide : notification sur la montre (10 min, zéro Monkey C)

1. Créer un topic ntfy (un nom unique difficile à deviner, ex. `sommeil-x7Kp2q`)
2. Installer l'app ntfy sur l'iPhone et s'abonner au topic
3. `export NTFY_TOPIC=sommeil-x7Kp2q` (ou variable d'env. Windows) puis lancer le script
4. La notification push arrive sur le téléphone → la FR55 l'affiche en miroir

## Étape 3 — Planification automatique

- **Windows** : Planificateur de tâches → nouvelle tâche → déclencheur
  quotidien 8h30 (+ une 2e à 10h en secours) → action
  `python C:\chemin\sleep_score.py`
- **Linux/Mac** : `crontab -e` → `30 8 * * * cd /chemin && python3 sleep_score.py`
- **Variante sans PC allumé** : GitHub Actions avec un `schedule: cron` et les
  identifiants en *secrets*. Attention : la connexion Garmin depuis une IP de
  datacenter peut déclencher des vérifications ; garder le cache de tokens en
  artefact aide.

## Étape 4 — Publication pour le widget (GitHub Pages)

1. Créer un repo **public** (ex. `sommeil`), y mettre un `score.json` vide
2. Settings → Pages → Deploy from branch `main` → le fichier devient accessible à
   `https://TON-PSEUDO.github.io/sommeil/score.json` (Content-Type
   `application/json`, requis par Connect IQ)
3. Créer un token fine-grained (Settings → Developer settings) limité à ce repo,
   permission *Contents: Read and write*
4. Variables d'environnement : `GITHUB_TOKEN=...` et `GITHUB_REPO=TON-PSEUDO/sommeil`
5. Le script pousse le score à chaque exécution (délai Pages : ~1 min)

## Étape 5 — v2 : le widget sur la FR55

1. Installer **VS Code** + extension **Monkey C** (Garmin)
2. Via l'extension : *Verify Installation* → elle installe le **Connect IQ SDK**
   et te fait créer une **clé développeur ** (guidé)
3. `Ctrl+Shift+P` → *Monkey C: New Project* → type **Widget**, cocher **fr55**
   (chemin le plus sûr : le manifest généré est garanti valide)
4. Remplacer `source/` et `resources/` du projet par ceux du dossier
   `widget-fr55/` fourni
5. Dans `SommeilView.mc`, remplacer `SCORE_URL` par ta vraie URL GitHub Pages
6. Tester : `Ctrl+Shift+P` → *Monkey C: Run* (simulateur, choisir fr55)
7. Compiler : *Monkey C: Build for Device* → cible fr55 → produit un `.prg`
8. Brancher la FR55 en USB → copier le `.prg` dans `GARMIN/APPS/` → éjecter
9. Sur la montre : maintenir UP → Paramètres → Widgets (ou depuis l'app Garmin
   Connect IQ) → ajouter "Score Sommeil" à la boucle de widgets
10. Depuis le cadran, DOWN pour scroller jusqu'au widget : il va chercher le
    score (téléphone connecté en Bluetooth nécessaire) et garde en cache le
    dernier score connu pour l'afficher hors connexion

## Limites à connaître

- API Garmin Connect **non officielle** : usage personnel à faible volume,
  peut casser lors d'un changement côté Garmin (d'où `--debug`)
- Le widget se rafraîchit à l'ouverture, pas en push (limite BLE des widgets)
- Le score est **estimatif** : la classification des stades au poignet reste
  approximative face à la polysomnographie ; c'est un outil de tendance,
  pas un diagnostic
