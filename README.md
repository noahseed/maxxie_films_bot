# Maxxie Films Bot

Catalogue privé pour **@maxxie_films_bot**, en Python 3.11+, sans dépendances externes.
Les administrateurs envoient au bot des vidéos ou documents vidéo ; le bot les publie
automatiquement dans le canal, avec leur nom de fichier sans le suffixe `.mp4`
(également reconnu en majuscules). Exemple : `Mon Film.mp4` → `Mon Film`.
Le nom de fichier prime sur une légende existante. Si Telegram ne fournit pas le nom,
la légende sert de titre ; sans les deux, le bot demande de renvoyer le fichier.
Les utilisateurs autorisés recherchent les films et ouvrent leur publication dans le canal.
Les fichiers restent chez Telegram ; le VPS conserve leurs références dans SQLite.

## Utilisation

Le menu propose **Rechercher un film** et **Lire les règles** sur la première ligne,
**Rejoindre le canal** seul sur la deuxième, puis **Contact** et **Aide**
sur la troisième. Le règlement s’affiche en privé avec un retour au menu.
L’option Catalogue a été retirée ; les anciens boutons de
catalogue et de pagination reviennent au menu. Cliquer sur un titre ouvre
son message dans le canal. Seuls les films indexés dans ce canal sont proposés. La recherche demande simplement de saisir un titre, sans commande.
Les résultats permettent de revenir au menu.

La recherche accepte les mots dans un ordre différent, les accents et les fautes
courantes (exemple : `poter harry`). Les correspondances exactes passent avant les
titres proches. Ajouter une année et une langue filtre les résultats :
`Matrix 1999 VF`, `Matrix VOSTFR` ou `2019 MULTI`. Les années et langues sont lues
dans les titres enregistrés, sans inventer de métadonnées absentes. Les mentions
VF/VFF/VFI/FR/français sont regroupées ; VO, VOSTFR et MULTI restent distinctes.
Un film dont la langue n’est pas renseignée ne correspond pas à un filtre de langue.

Les options **Publier** et **Retirer** sont supprimées pour tous, y compris les
administrateurs. Les anciens boutons et commandes correspondants reviennent au
menu sans publier ni retirer d’entrée.
L’envoi d’une vidéo par un administrateur conserve la publication automatique.
Un fichier déjà connu affiche un bouton vers sa publication d’origine.

Les textes affichés ne présentent plus de commandes slash. Les commandes
historiques restent compatibles, notamment `/start` pour ouvrir le menu initial
et `/id` pour obtenir son identifiant. La commande `/film numéro` est supprimée
et ne déclenche plus d’action. Au démarrage, les listes de commandes
Telegram par défaut et pour les conversations privées sont supprimées pour la
langue par défaut et le français.

## Contact privé

Le bouton **Contact** invite à écrire un message ou à envoyer une pièce jointe.
Le bot transmet au compte `NOTIFY_CHAT_ID` un en-tête avec le nom, le pseudo
éventuel et l’identifiant de l’expéditeur, puis copie son message en privé avec
`copyMessage`. Une confirmation est affichée seulement si Telegram accepte l’envoi.
Les types de messages non copiables par Telegram peuvent échouer ; le bot indique
alors que la transmission n’est pas confirmée, sans nouvel essai automatique.

Les messages suivants restent en mode contact jusqu’à un retour au **Menu**, une
autre action de navigation, une commande ou 15 minutes d’inactivité. Ce mode est
conservé après redémarrage dans SQLite (identifiant et expiration uniquement).
Le texte et les fichiers ne sont pas stockés sur le VPS. Les vidéos envoyées par
un administrateur en mode contact sont transmises en privé, sans publication dans
le canal. L’abonnement et les autorisations habituelles sont vérifiés avant chaque
message.

Chaque notification Contact comporte un bouton **Répondre**, réservé au compte
`NOTIFY_CHAT_ID`. Clique dessus puis envoie ta réponse (texte ou pièce jointe) :
le bot la transmet au destinataire et confirme l’envoi. Les messages suivants
restent dans cette conversation jusqu’au **Menu**, une autre action ou l’expiration
de la session de 15 minutes. Les vidéos envoyées dans ce mode ne sont pas publiées
dans le canal. Le destinataire doit toujours être autorisé et abonné au canal.

Les boutons de réponse utilisent des références aléatoires conservées sept jours,
liées à l’administrateur et au destinataire ; un autre utilisateur ne peut pas
s’en servir. Les sessions et leurs références survivent aux redémarrages. Aucun
contenu de conversation n’est enregistré sur le VPS. Un envoi non confirmé n’est
pas retenté automatiquement.

## Notifications de nouveaux utilisateurs

À la première interaction privée d’un utilisateur, le bot envoie un message privé
à `NOTIFY_CHAT_ID`, avec le nom affiché, le pseudo si disponible et l’identifiant
Telegram. Les tentatives d’accès d’utilisateurs non autorisés sont aussi signalées.
Les messages du canal ne déclenchent pas de notification. Le destinataire ne reçoit
pas de notification pour ses propres interactions.

Les identifiants déjà vus sont conservés dans la table SQLite `visitors`, sans
stocker les noms ni les pseudos. Les visites suivantes et les redémarrages ne
produisent pas de nouvelle alerte. Le suivi commence à l’installation de cette
fonction : une ancienne personne peut donc être signalée lors de son prochain
passage si elle n’avait jamais été enregistrée.

`NOTIFY_CHAT_ID` doit être l’identifiant positif d’un administrateur. Avec un seul
administrateur, son identifiant est utilisé par défaut. Avec plusieurs, préciser
le destinataire. Ce compte doit avoir démarré le bot et ne pas l’avoir bloqué.
Une erreur de notification est journalisée sans empêcher l’utilisateur de
continuer. Les notifications ne sont pas rejouées automatiquement, car un échec
réseau peut survenir après un envoi accepté par Telegram.

## Abonnement obligatoire pour utiliser le bot

Avant toute interaction privée (accueil, aide, recherche, anciens boutons,
commandes et envoi de vidéos), le bot interroge Telegram pour vérifier l’abonnement
au canal. Membres, administrateurs et propriétaire sont acceptés ; le statut
restreint exige `is_member=true`. Une erreur de vérification bloque l’accès et
propose de réessayer. Aucun rôle administrateur n’exempte de cette vérification.

Sans abonnement, seuls **Rejoindre le canal** et **J’ai rejoint le canal** sont
proposés. Ce dernier bouton vérifie à nouveau l’abonnement avant d’afficher le
menu. Quitter le canal bloque les interactions suivantes.

Les résultats de recherche sont des liens vers les messages du canal. Aucun film
n’est envoyé en privé aux utilisateurs. Les anciens boutons de téléchargement
renvoient aussi vers la publication, après vérification d’abonnement.
Les notifications de première visite sont enregistrées avant le contrôle d’accès.

Les listes `ADMIN_USER_IDS` et `ALLOWED_USER_IDS` continuent de limiter l’accès au
catalogue privé : l’abonnement est une condition supplémentaire. Le bot doit rester
administrateur du canal pour vérifier les abonnements des autres utilisateurs.

La détection des doublons utilise l’identifiant unique de fichier Telegram, même
si le fichier est renommé ou envoyé comme document vidéo. Elle s’applique aux
messages connus du bot dans le canal configuré. Deux fichiers différents portant
le même titre ne sont pas bloqués : il peut s’agir de versions distinctes. Un
fichier réencodé peut donc ne pas être reconnu. Si le message a été supprimé de
Telegram, le lien peut être périmé. Les suppressions ne sont pas synchronisées
automatiquement et nécessitent une maintenance du catalogue sur le serveur.

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
le canal. Pour indexer un ancien
film sans le republier, un administrateur peut transférer son message du canal
au bot en privé, avec son titre en légende. Si Telegram masque l’origine, ajouter
la référence du fichier reste possible, mais le bot ne sait pas qu’il est déjà
publié. L’API ne permet pas de parcourir automatiquement tout l’historique.

Les suppressions de messages dans Telegram ne sont pas synchronisées. En cas de
remplacement du fichier d’un message, le nouveau fichier est indexé et l’ancienne
référence au message est retirée. Les albums sont traités fichier par fichier.
La prévention des doublons de publication ne garantit pas une livraison exactement
une fois après une coupure pendant l’envoi.

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
scp bot.py catalogue.py search.py telegram_api.py backups.py debian@maxxie432.rondeau-cameira.fr:~/maxxie-films-bot/
scp deploy/* debian@maxxie432.rondeau-cameira.fr:~/maxxie-films-bot/deploy/
```

Puis sur le VPS :

```bash
sudo sh ~/maxxie-films-bot/deploy/install.sh
sudo python3 /opt/maxxie-films-bot/configure.py
sudo systemctl enable --now maxxie-films-bot
sudo systemctl status maxxie-films-bot
sudo systemctl start maxxie-films-backup.service
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

Les appels Telegram utilisent IPv4 pour éviter les délais intermittents observés
avec le choix automatique IPv6/IPv4 du VPS. La connexion HTTPS est réutilisée ;
une connexion inactive depuis plus de 20 secondes est remplacée. Le délai de
connexion est limité à 3 secondes et celui de lecture à 8 secondes (35 secondes
pour une réception longue de 30 secondes). Seuls les appels de lecture peuvent
être retentés une fois après une erreur réseau. Un envoi incertain n’est jamais
répété automatiquement. Les appels hors long polling dépassant une seconde sont
journalisés avec la méthode et la durée, sans jeton ni contenu privé.

Les limites d’envoi de Telegram s’appliquent. Les références de fichiers sont
propres au bot : ajouter les films au nouveau bot. Voir la
[documentation Telegram](https://core.telegram.org/bots/api#sending-files).

Pour changer les accès : modifier `/etc/maxxie-films-bot.env`, puis redémarrer
uniquement `maxxie-films-bot`.

## Sauvegardes automatiques

L’installation active `maxxie-films-backup.timer`. Une sauvegarde est prévue chaque
jour à **04 h 00, heure de Paris**, avec jusqu’à cinq minutes de décalage. Si le VPS
est éteint à cette heure, systemd exécute la sauvegarde manquée à son retour.
Les **14 dernières archives** sont conservées dans `/var/backups/maxxie-films-bot`
(dossier root 700, archives 600).

Chaque archive contient une copie cohérente SQLite créée avec l’API de sauvegarde,
le fichier secret de configuration, le code et les unités systemd. Les références
des films, visiteurs et sessions Contact sont donc sauvegardées. Les fichiers
vidéo restent chez Telegram. L’intégrité SQLite et les empreintes SHA-256 des
fichiers archivés sont vérifiées avant de publier l’archive et de purger les plus
anciennes. Un échec conserve les précédentes sauvegardes.

```bash
sudo systemctl start maxxie-films-backup.service
sudo journalctl -u maxxie-films-backup.service -n 10 --no-pager
systemctl list-timers maxxie-films-backup.timer
sudo ls -lh /var/backups/maxxie-films-bot/
```

Ces sauvegardes sont **locales au VPS** : conserver une copie externe dans un
stockage protégé pour couvrir la perte du serveur. Les archives contiennent le
jeton Telegram et ne doivent jamais être publiées ni ajoutées à Git.

Pour restaurer, arrêter le bot, extraire une archive choisie dans un dossier privé,
vérifier ses fichiers avec `manifest.json`, puis restaurer la base via l’API SQLite
`backup` (source `data/catalogue.sqlite3`, destination de production). Remettre la
configuration en mode 600 root, le code dans `/opt/maxxie-films-bot`, et la base
sous le compte `maxxie-films-bot`, mode 600, avant de redémarrer. Les tests valident
une restauration depuis une base active en mode WAL. Une restauration revient à
l’état de la sauvegarde choisie, y compris les visiteurs et le curseur Telegram.

## Vérification locale

```bash
python3 -m unittest discover -s tests -v
```

Les tests utilisent des réponses simulées et n’envoient aucun message Telegram.
