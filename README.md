# Maxxie Films Bot

Catalogue privé pour **@maxxie_films_bot**, en Python 3.11+, avec PostgreSQL et le pilote psycopg.
Les administrateurs envoient au bot des vidéos ou documents vidéo ; le bot les publie
automatiquement dans le canal, avec leur nom de fichier sans le suffixe `.mp4`
(également reconnu en majuscules). Exemple : `Mon Film.mp4` → `Mon Film`.
Le nom de fichier prime sur une légende existante. Si Telegram ne fournit pas le nom,
la légende sert de titre ; sans les deux, le bot demande de renvoyer le fichier.
Les abonnés du canal recherchent les films et ouvrent leur publication dans le canal.
Les fichiers restent chez Telegram ; le VPS conserve leurs références dans PostgreSQL.

## Utilisation

Le menu propose **Rechercher un film** et **Lire les règles** sur la première ligne,
**Rejoindre le canal** et **Hasard** sur la deuxième, **Visiter le site web** sur la troisième, puis **Contact**,
**Accueil** et **Aide** sur la quatrième. Le règlement s’affiche en privé avec un retour au menu.
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

Les messages suivants restent en mode contact jusqu’à un retour au **Aide**, une
autre action de navigation, une commande ou 15 minutes d’inactivité. Ce mode est
conservé après redémarrage dans SQLite (identifiant et expiration uniquement).
Le texte et les fichiers ne sont pas stockés sur le VPS. Les vidéos envoyées par
un administrateur en mode contact sont transmises en privé, sans publication dans
le canal. L’abonnement et les autorisations habituelles sont vérifiés avant chaque
message.

Chaque notification Contact comporte un bouton **Répondre**, réservé au compte
`NOTIFY_CHAT_ID`. Clique dessus puis envoie ta réponse (texte ou pièce jointe) :
le bot la transmet au destinataire et confirme l’envoi. Les messages suivants
restent dans cette conversation jusqu’au **Aide**, une autre action ou l’expiration
de la session de 15 minutes. Les vidéos envoyées dans ce mode ne sont pas publiées
dans le canal. Le destinataire doit toujours être abonné au canal.

Les boutons de réponse utilisent des références aléatoires conservées sept jours,
liées à l’administrateur et au destinataire ; un autre utilisateur ne peut pas
s’en servir. Les sessions et leurs références survivent aux redémarrages. Aucun
contenu de conversation n’est enregistré sur le VPS. Un envoi non confirmé n’est
pas retenté automatiquement.

## Jaquettes automatiques

Après configuration TMDB, le bot récupère les affiches des films indexés dans le
canal, y compris les anciens films déjà connus. Le bot modifie le **post vidéo existant** pour ajouter la jaquette comme
**couverture**, en réutilisant la même vidéo Telegram. Aucune photo séparée et
aucun nouveau commentaire ne sont créés. Le lien du message est conservé. Les nouveaux films sont pris en charge automatiquement, qu’ils soient
publiés via le bot ou directement dans le canal. Les vidéos sont publiées même si la jaquette est introuvable. Les fichiers envoyés
comme documents restent des documents : ils ne sont pas convertis en vidéo.

Pour les nouveaux posts, la légende complète et ses entités de mise en forme sont
mémorisées et conservées lors de la modification. Pour les anciennes vidéos dont
le bot ne disposait pas de la légende complète, le titre enregistré est utilisé
comme légende, conformément au choix de l’administrateur. Le 7 novembre 2026, les 108 anciennes photos de jaquettes ont été identifiées
dans Telegram puis supprimées par le bot, en excluant tous les identifiants des
vidéos. Le reçu privé de cette opération est conservé sur le VPS dans
`/var/backups/maxxie-films-bot/legacy-poster-cleanup-20261107.json`. Le bot doit avoir le droit de modifier les messages
du canal. Telegram choisit l’affichage de la couverture, sans placement gauche/droite imposable.

La recherche utilise le titre et l’année lorsqu’elle est présente ; les mentions
techniques courantes (1080p, VF, VOSTFR, etc.) sont retirées. Un titre ambigu ou une
correspondance insuffisante est ignoré plutôt que d’envoyer une affiche au hasard.
Les titres traduits sont recherchés en français auprès de TMDB.

### Activer les jaquettes

Créer un compte TMDB et obtenir le **API Read Access Token** depuis les
[paramètres API TMDB](https://www.themoviedb.org/settings/api). Sur le VPS :

```bash
sudo python3 /opt/maxxie-films-bot/configure_posters.py
sudo systemctl restart maxxie-films-bot
```

Le jeton est saisi sans affichage, vérifié et enregistré dans
`/etc/maxxie-films-tmdb.env`, root 600, sans réutiliser une clé OpenAI. Ce fichier
est inclus dans les sauvegardes dès qu’il existe. Sans ce jeton, le bot garde son
fonctionnement actuel et ne cherche pas de jaquette.

Un téléchargement à la fois est effectué en arrière-plan, sans bloquer la
recherche ni Contact. Les images JPEG (5 Mo maximum) sont conservées dans
`/var/lib/maxxie-films-bot/posters`, avec un cache limité à 500 fichiers. Les
connexions utilisent uniquement les domaines API et images de TMDB, sans suivre
les redirections. Aucun jeton n’est transmis au serveur d’images.

La file PostgreSQL reprend les téléchargements en attente après un redémarrage. Les
couvertures appliquées (`covered`) et les modifications au résultat incertain
(`cover_uncertain`) ne sont pas répétées automatiquement. Les anciennes tâches de
photos séparées sont reprises pour appliquer une couverture. Un changement de
titre permet une nouvelle recherche si aucune couverture n’avait été appliquée.
Les tâches sans correspondance ou en erreur ne sont pas retentées sans changement
de titre. Si Telegram refuse temporairement une modification avec un code 429,
la tâche est conservée et reprend après le délai demandé par le serveur. Les erreurs sont visibles dans le journal du service. Les sauvegardes
incluent la file et la configuration ; le cache d’images, reproductible, n’est pas
archivé.

This product uses the TMDB API but is not endorsed or certified by TMDB.
Sources : [authentification TMDB](https://developer.themoviedb.org/docs/authentication-application),
[images TMDB](https://developer.themoviedb.org/docs/image-basics).

## Assistant IA OpenAI

L’assistant cinéma répond par défaut aux messages texte libres, sans bouton
d’activation. Le menu indique que cette discussion utilise OpenAI. Aucun appel
ne part à l’affichage du menu ou pour une commande. Le bouton **Rechercher un film**
ouvre la recherche classique sans IA ; **Contact** transmet les messages à
l’administrateur sans IA. **Aide** quitte ces modes et rétablit la discussion par
défaut. La recherche classique expire après 15 minutes d’inactivité. Les vidéos,
les règles et la gestion des jaquettes ne déclenchent aucun appel OpenAI.

Les messages saisis dans ce mode ainsi que les titres et identifiants internes du
catalogue du canal sont envoyés à OpenAI ; les conversations Contact, la recherche
classique, les vidéos et leurs identifiants Telegram ne le sont pas. L’IA sélectionne
jusqu’à cinq films du catalogue ; le bot vérifie leur présence et ajoute des boutons
ouvrant leurs publications dans le canal. Les liens sont construits par le bot.
Le contexte contient au plus 500 titres ; au-delà, il privilégie les correspondances
avec la question et les ajouts récents, et signale cette sélection partielle à l’IA.
L’IA peut aussi discuter de films hors catalogue sans proposer de lien pour eux.
L’IA ne peut ni publier, ni retirer un film,
ni exécuter des commandes. Le bouton **Aide** efface la mémoire de la discussion.

La mémoire des deux derniers échanges reste uniquement en RAM et expire après
15 minutes d’inactivité (nettoyage au passage suivant de la boucle). Les requêtes
utilisent la Responses API avec `store=false`, sans identifiant ni pseudo Telegram.
Les questions et réponses ne sont pas enregistrées dans PostgreSQL. Les quotas le sont,
sans contenu : **20 requêtes par utilisateur et 100 pour le bot par jour UTC**, avec
600 tokens de sortie maximum et 2 000 caractères par question. Les tentatives en
erreur consomment aussi une unité de quota. Ce sont des limites d’appels, pas une
garantie de plafond de facturation OpenAI.

Deux générations au maximum sont exécutées en arrière-plan, une par utilisateur.
Le reste du bot reste utilisable pendant la génération. L’abonnement est vérifié
avant la question et à nouveau avant l’envoi de la réponse.

### Clé dédiée au bot films

Aucune clé du bot musical n’est réutilisée. Créer une clé de projet dédiée dans
[OpenAI Platform](https://platform.openai.com/api-keys), puis sur le VPS :

```bash
sudo python3 /opt/maxxie-films-bot/configure_openai.py
sudo systemctl restart maxxie-films-bot
```

Le script demande la clé en saisie masquée et vérifie l’accès au modèle sans
générer de réponse. Il crée `/etc/maxxie-films-openai.env`, réservé à root (600).
Le modèle proposé est `gpt-4.1-mini`. Les limites sont réglables dans ce même
fichier avec `OPENAI_DAILY_USER_LIMIT` et `OPENAI_DAILY_TOTAL_LIMIT`. La clé reste
sur le serveur ; ne pas la coller dans Telegram, dans le chat ou dans Git.
Sans cette configuration, le bot reste fonctionnel et l’assistant indique qu’il
attend sa configuration. L’API peut refuser la génération si le projet ne dispose
pas de crédit ou de droits suffisants.

Le fichier dédié est inclus dans les sauvegardes dès qu’il existe. Les archives
qui le contiennent sont donc également secrètes. Documentation de référence :
[Responses et authentification](https://developers.openai.com/api/reference/overview),
[sorties structurées](https://developers.openai.com/api/docs/guides/structured-outputs).

## Notifications de nouveaux utilisateurs

À la première interaction privée d’un utilisateur, le bot envoie un message privé
à `NOTIFY_CHAT_ID`, avec le nom affiché, le pseudo si disponible et l’identifiant
Telegram. Les premières visites d’utilisateurs pas encore abonnés sont aussi signalées.
Les messages du canal ne déclenchent pas de notification. Le destinataire ne reçoit
pas de notification pour ses propres interactions.

Les identifiants déjà vus sont conservés dans la table PostgreSQL `visitors`, sans
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

L’abonnement au canal suffit pour accéder aux fonctionnalités utilisateur, y
compris Assistant IA et Contact. Aucune inscription dans une liste d’accès n’est
nécessaire. L’ancienne variable `ALLOWED_USER_IDS` est ignorée. `ADMIN_USER_IDS`
réserve uniquement les fonctions administrateur aux comptes configurés. Le bot
doit rester administrateur du canal pour vérifier les abonnements.

La détection des doublons utilise l’identifiant unique de fichier Telegram, même
si le fichier est renommé ou envoyé comme document vidéo. Elle s’applique aux
messages connus du bot dans le canal configuré. Deux fichiers différents portant
le même titre ne sont pas bloqués : il peut s’agir de versions distinctes. Un
fichier réencodé peut donc ne pas être reconnu. Si le message a été supprimé de
Telegram, le lien peut être périmé. Les suppressions ne sont pas synchronisées
automatiquement et nécessitent une maintenance du catalogue sur le serveur.

Tous les abonnés du canal peuvent utiliser le bot. Le canal public reste
accessible selon ses propres règles Telegram.

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
| Catalogue | `maxxie_films` (PostgreSQL local, rôle `maxxie-films-bot`) |

Depuis votre ordinateur, copier le code :

```bash
ssh debian@maxxie432.rondeau-cameira.fr 'mkdir -p ~/maxxie-films-bot/deploy'
scp database.py migrate_postgres.py bot.py catalogue.py search.py telegram_api.py openai_api.py posters.py backups.py debian@maxxie432.rondeau-cameira.fr:~/maxxie-films-bot/
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
PostgreSQL. Les demandes sont marquées avant traitement pour éviter de répéter un
envoi incertain : un arrêt à cet instant peut perdre une demande. L’utilisateur
peut alors la renouveler. Les erreurs d’envoi ne sont pas rejouées automatiquement.

Les appels Telegram utilisent IPv4 pour éviter les délais intermittents observés
avec le choix automatique IPv6/IPv4 du VPS. La connexion HTTPS est réutilisée ;
une connexion inactive depuis plus de 20 secondes est remplacée. Le délai de
connexion est limité à 3 secondes et celui de lecture à 8 secondes (30 secondes pour les médias, 35 secondes
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

Chaque archive contient un export PostgreSQL cohérent (`pg_dump --format=custom`),
les configurations secrètes, le code et les unités systemd. Les références des
films, les synopsis, visiteurs, quotas et sessions Contact sont sauvegardés.
Les vidéos restent chez Telegram. Le catalogue de l’export (`pg_restore --list`)
et les empreintes SHA-256 des fichiers archivés sont vérifiés avant publication
et purge des archives anciennes. Un échec conserve les sauvegardes précédentes.

```bash
sudo systemctl start maxxie-films-backup.service
sudo journalctl -u maxxie-films-backup.service -n 10 --no-pager
systemctl list-timers maxxie-films-backup.timer
sudo ls -lh /var/backups/maxxie-films-bot/
```

Ces sauvegardes sont **locales au VPS** : conserver une copie externe dans un
stockage protégé pour couvrir la perte du serveur. Les archives contiennent le
jeton Telegram et ne doivent jamais être publiées ni ajoutées à Git.

Pour restaurer, arrêter le bot, extraire l’archive dans un dossier privé et vérifier
`manifest.json`. Restaurer `data/catalogue.dump` avec `pg_restore --no-owner --no-acl`
dans une base PostgreSQL vide appartenant à `maxxie-films-bot`, puis configurer
`DATABASE_URL` vers cette base et redémarrer le bot. Exécuter la restauration sous
le compte système `maxxie-films-bot` pour l’authentification locale. Les configurations
restent root 600. Une restauration revient à l’état de la sauvegarde, y compris
les visiteurs, quotas et le curseur Telegram.

## Migration SQLite vers PostgreSQL

Installer `postgresql` et `python3-psycopg`, puis exécuter
`sudo python3 /opt/maxxie-films-bot/setup_postgres.py`. Le rôle dédié n’est ni
superutilisateur, ni créateur de bases ou de rôles. L’accès utilise le socket local
et l’authentification peer, sans nouveau mot de passe ni port public.

Arrêter le bot, effectuer une sauvegarde, puis exécuter sous `maxxie-films-bot` :

```bash
python3 /opt/maxxie-films-bot/migrate_postgres.py \
  /var/lib/maxxie-films-bot/catalogue.sqlite3 \
  'postgresql:///maxxie_films?host=/var/run/postgresql'
```

Le script exige une destination vide, copie les tables du catalogue et des fonctionnalités dans une transaction,
compare chaque ligne et recale la séquence des identifiants de films. Ajouter
`DATABASE_URL=postgresql:///maxxie_films?host=/var/run/postgresql` dans la
configuration, puis redémarrer. Le fichier SQLite reste conservé comme copie
antérieure ; il n’est plus mis à jour. SQLite est encore supporté pour les tests
et l’import des anciennes sauvegardes. Les jaquettes restent dans le répertoire
de cache existant, indépendant du moteur de base.

Tests PostgreSQL (dans une base réservée aux tests) :

```bash
TEST_POSTGRES_DSN='postgresql:///maxxie_films_test?host=/var/run/postgresql' \
  python3 tests/run_postgres.py
```

## Vérification locale

```bash
python3 -m unittest discover -s tests -v
```

Les tests utilisent des réponses simulées et n’envoient aucun message Telegram.

## Synopsis sous les titres

Le bot ajoute automatiquement les synopsis français de TMDB sous le titre des
publications existantes et nouvelles. Il modifie uniquement la légende : les vidéos,
leurs liens et leurs couvertures restent en place. Les légendes affichent uniquement
le titre et le synopsis, sans mention de source.
Les résumés longs sont tronqués pour respecter les 1 024 caractères UTF-16 de
Telegram. Une correspondance ambiguë ou sans résumé français laisse le post intact.
Le suivi persistant `synopsis_jobs` évite de rééditer les publications déjà traitées ;
les limitations Telegram suspendent les modifications pendant le délai demandé.
Aucun appel OpenAI n’est utilisé pour les synopsis.

Le bouton **Aide**, à droite de Contact, affiche les commandes `/start`, `/aide`
(alias `/help`), `/recherche titre` et `/id`. Les commandes `/catalogue`,
`/publier` et `/supprimer` sont supprimées : elles ne déclenchent aucune action.
Les boutons Aide et les commandes `/aide` et `/help` quittent le mode en cours.

Le bouton **Hasard** propose un film choisi dans le catalogue du canal, avec un lien
vers sa publication et un bouton pour en tirer un autre, sans appel OpenAI.

Le résultat **Hasard** affiche le synopsis enregistré sous le titre du film.
Sans résumé confirmé, il indique « Synopsis indisponible pour ce film. ».

**Hasard** envoie aussi la jaquette disponible avec le titre et le synopsis en
légende, et conserve les boutons de lecture et de nouveau tirage. Telegram choisit
la disposition de la photo. Sans jaquette identifiée, le résultat reste textuel.
La récupération de la jaquette se fait en arrière-plan, sans appel OpenAI.

Le bouton **Accueil**, entre Contact et Aide, affiche le même accueil que `/start`
et quitte la recherche ou le contact en cours.

## Fiches, correspondances et administration

Les métadonnées sont conservées dans `film_metadata` : identifiants IMDb/TMDB,
année, genres, chemin de jaquette et identifiant photo Telegram. Une correspondance
confirmée utilise directement sa fiche externe pour les recherches suivantes.
Les corrections manuelles de synopsis restent celles du catalogue. Les jaquettes
manuelles restent prioritaires lors de l’enrichissement. Les photos envoyées en
privé sont réutilisées via leur identifiant Telegram, sans nouveau téléchargement.
Un cache absent peut être recréé en arrière-plan. Aucun appel OpenAI n’est effectué
pour ces opérations.

Une recherche avec un seul résultat affiche sa fiche complète. Plusieurs résultats
conservent leurs liens de canal et proposent chacun un bouton **Fiche**. Une fiche
présente la jaquette disponible, le titre, le synopsis, le lien du film et les boutons
Contact, Accueil, Aide et **Signaler un problème**. Les signalements sont envoyés en
privé à l’administrateur avec la publication concernée. Un signalement par minute
et par utilisateur est autorisé. Seuls sa référence, son motif et son statut sont
conservés pendant 30 jours ; le texte explicatif n’est pas stocké dans la base.

Le bouton **Administration**, visible uniquement pour `ADMIN_USER_IDS`, permet de
rechercher ou parcourir les films puis de corriger un titre, un synopsis, fournir
un lien IMDb/TMDB, remplacer une jaquette par une photo Telegram, ou supprimer un
film. L’association externe affiche le titre et l’année à confirmer avant toute
modification. Une suppression exige aussi une confirmation liée au film, au compte
et valable 15 minutes. Elle supprime la publication, puis ses références et données
associées de la base. Les photos doivent être envoyées comme photos, pas fichiers.
Le retour à Accueil, Aide ou une autre fonction annule la saisie en cours. Aucun
rôle utilisateur ne permet de contourner l’abonnement obligatoire au canal.

## Hasard et filtres

**Hasard** exclut les dix derniers films tirés au cours des dernières 24 heures.
Quand tous les films possibles ont été proposés, un nouveau cycle commence en
évitant le dernier film si plusieurs choix existent. Les filtres **Genre** et
**Année** se cumulent, s’appliquent seulement aux métadonnées identifiées, et peuvent
être effacés avec **Tous les films**. Les préférences de filtres restent en mémoire
jusqu’au redémarrage ; l’historique de tirages est conservé dans PostgreSQL.

Les films existants peuvent être enrichis sans modifier les publications :

```bash
python3 /opt/maxxie-films-bot/enrich_catalogue.py
```

Ce programme s’exécute sous le compte du bot, avec `DATABASE_URL`, `CHANNEL_ID` et
`TMDB_READ_TOKEN` dans son environnement. L’option `--confirmed fichier.json`
importe des correspondances déjà vérifiées, sous la forme `{ "message_id": tmdb_id }`.
Le bot prépare aussi automatiquement les métadonnées des nouveaux films en arrière-plan.
Les titres ambigus ne sont pas associés arbitrairement.

## Surveillance technique

`maxxie-films-monitor.timer` contrôle toutes les cinq minutes le service du bot,
PostgreSQL, le résultat de la dernière sauvegarde et l’existence d’une archive de
moins de 27 heures. Une anomalie déclenche un message à `NOTIFY_CHAT_ID` ; une même
anomalie ne déclenche au plus qu’un message par heure. Les erreurs Telegram et
OpenAI rencontrées par le bot sont aussi signalées sans contenu des conversations
ni secrets. Une panne de l’API Telegram ou du réseau peut empêcher l’alerte elle-même ;
les journaux systemd restent disponibles. Cette surveillance s’exécute sur le même
VPS et ne détecte donc pas son arrêt complet depuis l’extérieur.

```bash
systemctl status maxxie-films-monitor.timer
sudo systemctl start maxxie-films-monitor.service
```

## Tests sur GitHub Actions

Le workflow **Tests du bot** s’exécute à chaque push et pull request, et peut être
lancé manuellement dans l’onglet Actions. Il exécute les tests unitaires avec
Python 3.11, 3.13 et 3.14, puis la suite PostgreSQL et les tests de migration avec
Python 3.13 et un conteneur PostgreSQL 17 isolé. Il n’utilise aucun secret Telegram,
OpenAI ou TMDB et ne déploie rien sur le VPS.
