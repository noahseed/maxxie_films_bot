# Maxxie Films Bot

Catalogue privé pour **@maxxie_films_bot**, en Python 3.11+, sans dépendances externes.
Les administrateurs envoient au bot des vidéos ou documents vidéo avec leur titre
en légende. Les utilisateurs autorisés recherchent les films et les reçoivent en privé.
Les fichiers restent chez Telegram ; le VPS conserve leurs références dans SQLite.

## Utilisation

- `/start`, `/aide` : accueil et commandes.
- `/id` : obtenir son identifiant numérique, même sans accès au catalogue.
- `/catalogue` : parcourir les films, dix par page.
- `/recherche titre` : recherche insensible aux accents et à la casse.
- `/film numéro` : recevoir un film.
- Administrateurs : envoyer une vidéo avec un titre en légende ; renvoyer le même fichier met à jour son entrée sans doublon.
- `/supprimer numéro` : retirer une entrée (administrateurs uniquement).

Seuls `ADMIN_USER_IDS` et `ALLOWED_USER_IDS` accèdent aux films. Les groupes et les
canaux sont ignorés. Cette version ne publie pas vers un canal et n’indexe pas
les anciens messages automatiquement.

## Hébergement sur le VPS existant

VPS : `debian@maxxie432.rondeau-cameira.fr` (Debian, Python 3.13).
Le service musical `maxxie-bot` et le service films sont indépendants :

| Ressource | Films |
| --- | --- |
| Service et compte système | `maxxie-films-bot` |
| Code | `/opt/maxxie-films-bot` |
| Configuration secrète | `/etc/maxxie-films-bot.env` (root, mode 600) |
| Catalogue | `/var/lib/maxxie-films-bot/catalogue.sqlite3` |

Depuis votre ordinateur, copier le code :

```bash
ssh debian@maxxie432.rondeau-cameira.fr 'mkdir -p ~/maxxie-films-bot/deploy'
scp bot.py catalogue.py telegram_api.py debian@maxxie432.rondeau-cameira.fr:~/maxxie-films-bot/
scp deploy/* debian@maxxie432.rondeau-cameira.fr:~/maxxie-films-bot/deploy/
```

Puis sur le VPS :

```bash
sudo sh ~/maxxie-films-bot/deploy/install.sh
sudo python3 /opt/maxxie-films-bot/configure.py
sudo systemctl enable --now maxxie-films-bot
sudo systemctl status maxxie-films-bot
sudo journalctl -u maxxie-films-bot -n 30 --no-pager
```

L’assistant demande le jeton en saisie masquée et les identifiants numériques des
utilisateurs. Il vérifie l’identité de @maxxie_films_bot et refuse un webhook
existant. Aucun jeton ne doit être ajouté au dépôt ou au chat. Le script conserve
une configuration existante et ne démarre ni ne redémarre les services.

Le long polling n’exige aucun port entrant. Un seul processus doit utiliser le
jeton. Le service se relance après une panne et reprend la réception à son curseur
SQLite. Les demandes sont marquées avant traitement pour éviter de répéter un
envoi incertain : un arrêt à cet instant peut perdre une demande. L’utilisateur
peut alors la renouveler. Les erreurs d’envoi ne sont pas rejouées automatiquement.

Les limites d’envoi de Telegram s’appliquent. Les références de fichiers sont
propres au bot : ajouter les films au nouveau bot. Voir la
[documentation Telegram](https://core.telegram.org/bots/api#sending-files).

Pour changer les accès : modifier `/etc/maxxie-films-bot.env`, puis redémarrer
uniquement `maxxie-films-bot`. Pour sauvegarder, utiliser l’API de sauvegarde SQLite
ou copier la base après arrêt du service ; conserver aussi la configuration secrète
dans un stockage protégé. Ne jamais versionner ces fichiers.

## Vérification locale

```bash
python3 -m unittest discover -s tests -v
```

Les tests utilisent des réponses simulées et n’envoient aucun message Telegram.
