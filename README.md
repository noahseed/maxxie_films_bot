# Maxxie Films Bot

Catalogue privé pour **@maxxie_films_bot**, en Python 3.11+, sans dépendances externes.
Les administrateurs envoient au bot des vidéos ou documents vidéo ; le bot les publie
automatiquement dans le canal, avec leur nom de fichier sans le suffixe `.mp4`
(également reconnu en majuscules). Exemple : `Mon Film.mp4` → `Mon Film`.
Le nom de fichier prime sur une légende existante. Si Telegram ne fournit pas le nom,
la légende sert de titre ; sans les deux, le bot demande de renvoyer le fichier.
Les utilisateurs autorisés recherchent les films et les reçoivent en privé.
Les fichiers restent chez Telegram ; le VPS conserve leurs références dans SQLite.

## Utilisation

- `/start`, `/aide` : accueil et commandes.
- `/id` : obtenir son identifiant numérique, même sans accès au catalogue.
- `/catalogue` : parcourir les films, dix par page.
- `/recherche titre` : recherche insensible aux accents et à la casse.
- `/film numéro` : recevoir un film.
- Administrateurs : envoyer une vidéo pour la publier automatiquement ; renvoyer un
  fichier déjà indexé dans le canal affiche son titre et un bouton **Voir le film
  dans le canal**, sans le republier ni modifier son titre enregistré.
- `/supprimer numéro` : retirer une entrée (administrateurs uniquement).
- `/publier numéro` : publier un film dans `@maxxie_films` (administrateur du bot
  disposant aussi du droit de publier dans le canal). Un film déjà indexé dans le
  canal n’est pas republié.

La détection des doublons utilise l’identifiant unique de fichier Telegram, même
si le fichier est renommé ou envoyé comme document vidéo. Elle s’applique aux
messages connus du bot dans le canal configuré. Deux fichiers différents portant
le même titre ne sont pas bloqués : il peut s’agir de versions distinctes. Un
fichier réencodé peut donc ne pas être reconnu. Si le message a été supprimé de
Telegram, le lien peut être périmé ; retirer l’entrée avec `/supprimer` pour
permettre une nouvelle publication.

Seuls `ADMIN_USER_IDS` et `ALLOWED_USER_IDS` accèdent au catalogue privé du bot.
Le canal public reste accessible selon ses propres règles Telegram.

## Canal Maxxie Films

Le bot gère [@maxxie_films](https://t.me/maxxie_films). Il doit être administrateur
avec le droit **Publier des messages**. Au démarrage, il vérifie le type de
destination et ses droits, puis résout `CHANNEL_ID` (par défaut `@maxxie_films`)
en identifiant numérique.

Les nouvelles vidéos et documents vidéo publiés directement dans ce canal sont
indexés sans réponse dans le canal. Les modifications de légende mettent à jour
le titre. Sans légende, le nom du fichier ou le numéro du message sert de titre.
Les autres canaux et les groupes sont ignorés. Le menu privé propose un bouton
pour ouvrir le canal.

L’envoi d’un fichier au bot en privé l’ajoute au catalogue et le publie dans le canal
si l’expéditeur est administrateur du bot et dispose du droit de publication dans
le canal. `/publier numéro` permet aussi de publier une entrée existante. Pour indexer un ancien
film sans le republier, un administrateur peut transférer son message du canal
au bot en privé, avec son titre en légende. Si Telegram masque l’origine, ajouter
la référence du fichier reste possible, mais le bot ne sait pas qu’il est déjà
publié. L’API ne permet pas de parcourir automatiquement tout l’historique.

`/supprimer` retire l’entrée du catalogue, sans supprimer le message du canal.
Les suppressions de messages dans Telegram ne sont pas synchronisées. En cas de
remplacement du fichier d’un message, le nouveau fichier est indexé ; retirer
l’ancienne entrée avec `/supprimer` si elle n’est plus souhaitée. Les albums sont
traités fichier par fichier. La prévention des doublons de publication ne garantit
pas une livraison exactement une fois après une coupure pendant l’envoi.

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
utilisateurs. Il vérifie l’identité de @maxxie_films_bot, ses droits dans le canal et refuse un webhook
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
