# Score de sommeil /100 pour Garmin Forerunner 55

La FR55 enregistre les stades de sommeil et la fréquence cardiaque nocturne,
mais ne calcule pas de score de sommeil : la fonction Firstbeat est réservée aux
modèles supérieurs. L'API Connect IQ embarquée n'expose pas les stades aux
applications tierces, le score est donc calculé hors montre à partir des données
Garmin Connect, puis renvoyé sur la montre.

```
FR55  →  Garmin Connect  →  sleep_score.py  →  score.json (GitHub Pages)  →  widget FR55
```

Le script peut aussi envoyer une notification ntfy que la montre affiche en
miroir du téléphone. C'est la variante la plus rapide, sans rien compiler.

## Le score

| Composante | Poids | Cible |
|---|---|---|
| Durée totale | 30 | 7–9 h |
| Efficacité | 20 | ≥ 85 % |
| Sommeil profond | 15 | 13–23 % |
| Sommeil REM | 15 | 20–25 % |
| Continuité (WASO, réveils) | 10 | WASO ≤ 20 min, ≤ 1 réveil |
| FC nocturne vs FC repos | 10 | écart ≤ 3 bpm |

Durée et efficacité pèsent la moitié du score parce que ce sont les deux mesures
fiables. Les stades ne valent que 30 points à eux deux : leur classification au
poignet reste approximative face à la polysomnographie. Si une composante manque
(REM non détecté par exemple), le score est renormalisé sur 100.

Les cibles viennent de Hirshkowitz et al. 2015 (*Sleep Health*) et Watson et al.
2015 (*Sleep*) pour la durée, Ohayon et al. 2017 (*Sleep Health*) pour
l'efficacité et la continuité, Ohayon et al. 2004 (*Sleep*) pour les stades, et
Trinder et al. 2001 (*J Sleep Res*) pour la fréquence cardiaque nocturne. La
réserve sur la mesure au poignet vient de Chinoy et al. 2021 (*Sleep*).

## Le script

Python 3.10 ou plus récent, puis :

```bash
pip install garminconnect requests
```

Au premier lancement, vérifier que les champs renvoyés par l'API correspondent
bien à ce que le script lit :

```bash
python sleep_score.py --debug --no-publish
```

L'email et le mot de passe Garmin ne sont demandés qu'une fois, les tokens sont
ensuite mis en cache dans `~/.garmin_tokens`. Si un champ du JSON brut ne
correspond pas, c'est `extraire_mesures()` qu'il faut adapter : tous les accès y
sont défensifs.

Ensuite, en usage normal :

```bash
python sleep_score.py
```

La montre doit avoir synchronisé avec le téléphone avant. Ouvrir l'app Garmin
Connect au réveil suffit. Sinon le script sort en « pas de données » et il faut
le relancer plus tard.

## Notification sur la montre

Le chemin le plus court, sans toucher à Monkey C :

1. Créer un topic ntfy avec un nom difficile à deviner, par exemple `sommeil-x7Kp2q`
2. Installer l'app ntfy sur le téléphone et s'abonner au topic
3. Définir la variable d'environnement `NTFY_TOPIC`, puis lancer le script

La notification arrive sur le téléphone et la FR55 l'affiche en miroir.

Un topic ntfy n'a pas de mot de passe : son nom *est* le secret, et quiconque
le connaît peut lire les notifications. D'où le nom aléatoire, gardé dans
`ntfy_topic.txt` qui n'est pas suivi par git. C'est aussi pourquoi la
notification peut contenir le détail des mesures alors que le fichier publié
sur GitHub, lui, n'en contient pas.

## Lancement automatique

Sur Windows, par le Planificateur de tâches : nouvelle tâche, déclencheur
quotidien à 8h30, action `python C:\chemin\sleep_score.py`. J'en ai ajouté une
seconde à 10h au cas où la synchro du matin n'ait pas eu lieu.

Sur Linux ou macOS, `crontab -e` :

```
30 8 * * * cd /chemin && python3 sleep_score.py
```

Pour que ça tourne sans garder le PC allumé, GitHub Actions avec un
`schedule: cron` et les identifiants en secrets fonctionne également. À savoir :
la connexion Garmin depuis une IP de datacenter peut déclencher des
vérifications supplémentaires, et conserver le cache de tokens en artefact
limite le problème.

## Publication du score

Le widget lit le score sur GitHub Pages, qui sert le `Content-Type`
`application/json` exigé par Connect IQ.

1. Un dépôt public, avec un `score.json` à la racine
2. Settings → Pages → Deploy from branch `main`. Le fichier devient accessible à
   `https://TON-PSEUDO.github.io/TON-DEPOT/score.json`
3. Créer un token fine-grained limité à ce dépôt, permission *Contents:
   Read and write*
4. Définir `GITHUB_TOKEN` et `GITHUB_REPO` (au format `pseudo/depot`)

Le script pousse alors le score à chaque exécution. Pages met le fichier en
cache dix minutes sur son réseau de diffusion : le widget peut donc afficher un
score légèrement en retard juste après une publication.

Seuls les trois champs lus par la montre sont publiés — `date`, `score` et
`qualite`. Le détail des mesures (fréquence cardiaque, stades, horaires) reste
dans `score_detail.json`, qui n'est pas suivi par git : le dépôt est public et
chaque publication crée un commit conservé indéfiniment.

## Le widget

1. VS Code avec l'extension Monkey C
2. Lancer *Verify Installation* depuis l'extension : elle installe le Connect IQ
   SDK et guide la création de la clé développeur
3. `Ctrl+Shift+P` → *Monkey C: New Project*, type Widget, cocher fr55. Passer par
   là garantit un manifest valide
4. Remplacer les dossiers `source/` et `resources/` du projet généré par ceux de
   `sommeilfr55/`
5. Dans le fichier de la vue, remplacer `SCORE_URL` par ton URL GitHub Pages
6. *Monkey C: Run* pour tester dans le simulateur, puis *Build for Device* pour
   produire le `.prg`
7. Brancher la FR55 en USB, copier le `.prg` dans `GARMIN/APPS/`, éjecter
8. Sur la montre : maintenir UP → Paramètres → Widgets, ajouter « Score Sommeil »

Depuis le cadran, DOWN fait défiler jusqu'au widget. Il récupère le score à
l'ouverture, ce qui suppose le téléphone connecté en Bluetooth, et garde le
dernier score en cache pour l'afficher hors connexion.

## Limites

L'API Garmin Connect utilisée ici n'est pas officielle. Usage personnel à faible
volume, et elle peut casser du jour au lendemain si Garmin change quelque chose,
d'où l'option `--debug` pour diagnostiquer.

Le widget se rafraîchit à l'ouverture et non en push. C'est une limite des
widgets Connect IQ, pas du code.

Le score reste une estimation. La classification des stades au poignet est
approximative comparée à la polysomnographie : c'est un indicateur de tendance,
pas un diagnostic.
