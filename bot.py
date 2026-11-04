"""Bot Maxxie Films — Python 3.11+, bibliothèque standard."""
import logging
import os
from pathlib import Path
import signal
import threading

from catalogue import Catalogue
from telegram_api import Telegram, TelegramError

LOG = logging.getLogger("maxxie-films")
HELP = ("🎬 Maxxie Films\n\n"
        "Bienvenue dans notre coin cinéma ! 🍿\n"
        "Choisis un film dans le catalogue ou recherche son titre.\n"
        "Rejoins le canal pour recevoir les films ici. Bonne séance !")
ADMIN_HELP = ("\n\nAdministration : envoie une vidéo pour la publier dans le canal "
              "avec son nom de fichier sans .mp4. Les boutons du catalogue "
              "permettent aussi de publier ou retirer une entrée.")
MENU_BUTTON = {"text": "🏠 Menu", "callback_data": "menu"}


def video_media(message):
    if message.get("video"):
        return message["video"], "video"
    document = message.get("document", {})
    if document.get("mime_type", "").startswith("video/"):
        return document, "document"
    return None, None


def film_title(message, media):
    title = (media.get("file_name") or "").strip()
    if title:
        title = title.replace("\\", "/").rsplit("/", 1)[-1]
    else:
        title = message.get("caption", "").strip()
    if title.lower().endswith(".mp4"):
        title = title[:-4].strip()
    return title[:200]


def verify_channel(api, bot_id, reference):
    channel = api.call("getChat", chat_id=reference)
    if channel.get("type") != "channel":
        raise ValueError("CHANNEL_ID doit désigner un canal Telegram.")
    member = api.call("getChatMember", chat_id=channel["id"], user_id=bot_id)
    if member.get("status") != "administrator" or not member.get("can_post_messages"):
        raise ValueError("Ajoute le bot comme administrateur du canal avec le droit de publier.")
    return channel["id"]


def clear_commands(api):
    for scope in ("default", "all_private_chats"):
        for language in ("", "fr"):
            api.call("deleteMyCommands", scope={"type": scope}, language_code=language)


class Bot:
    def __init__(self, api, catalogue, admins, allowed_users, channel_id=None):
        self.api, self.catalogue = api, catalogue
        self.admins, self.allowed_users = set(admins), set(allowed_users)
        self.channel_id = channel_id

    def send(self, chat_id, text, **params):
        return self.api.call("sendMessage", chat_id=chat_id, text=text, **params)

    def handle(self, update):
        post = update.get("channel_post") or update.get("edited_channel_post")
        if post:
            if post.get("chat", {}).get("type") == "channel" and post["chat"]["id"] == self.channel_id:
                media, kind = video_media(post)
                if media:
                    title = post.get("caption", "").strip() or media.get("file_name") or f"Film {post['message_id']}"
                    film_id = self.catalogue.add(media, kind, title)
                    self.catalogue.link_channel(self.channel_id, film_id, post["message_id"])
            return
        callback = update.get("callback_query")
        message = update.get("message") or (callback or {}).get("message", {})
        if message.get("chat", {}).get("type") != "private":
            return
        user_id = (callback or message).get("from", {}).get("id")
        chat_id = message["chat"]["id"]
        if not isinstance(user_id, int) or user_id != chat_id:
            return
        if callback:
            try:
                self.api.call("answerCallbackQuery", callback_query_id=callback["id"])
            except TelegramError:
                pass
        text = message.get("text", "").strip()
        command, _, argument = text.partition(" ")
        command = command.split("@", 1)[0].lower()
        if not callback and command == "/id":
            self.send(chat_id, f"Ton identifiant Telegram : {user_id}")
            return
        if user_id not in self.allowed_users | self.admins:
            self.send(chat_id, "Ce catalogue est privé. Demande l’accès à son administrateur. "
                      f"Ton identifiant : {user_id}")
            return
        if callback:
            data = callback.get("data", "")
            if data == "catalogue":
                self.list_films(chat_id)
            elif data in ("aide", "menu"):
                self.show_menu(chat_id, user_id)
            elif data == "recherche":
                self.send(chat_id, "🔎 Envoie le titre du film que tu recherches.",
                          reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            elif data.startswith("rejoindre:"):
                self.deliver(chat_id, data.split(":", 1)[1])
            elif data.startswith("publier:") and user_id in self.admins:
                self.publish(chat_id, data.split(":", 1)[1])
            elif data.startswith("retirer:") and user_id in self.admins:
                identifier = data.split(":", 1)[1]
                if identifier.isdigit() and len(identifier) < 16:
                    self.send(chat_id, "Retirer ce film du catalogue ? Le message du canal sera conservé.",
                              reply_markup={"inline_keyboard": [[
                                  {"text": "Confirmer le retrait", "callback_data": f"confirmer_retrait:{identifier}"},
                                  MENU_BUTTON]]})
            elif data.startswith("confirmer_retrait:") and user_id in self.admins:
                identifier = data.split(":", 1)[1]
                if identifier.isdigit() and len(identifier) < 16:
                    removed = self.catalogue.remove(int(identifier))
                    self.send(chat_id, "Film retiré." if removed else "Film introuvable.",
                              reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            elif data.startswith("film:"):
                self.deliver(chat_id, data[5:])
            elif data.startswith("page:") and data[5:].isdigit():
                self.list_films(chat_id, page=min(int(data[5:]), 100000))
            return
        media, kind = video_media(message)
        if media:
            if user_id not in self.admins:
                self.send(chat_id, "Seuls les administrateurs peuvent ajouter des films.")
                return
            existing = self.catalogue.published_file(self.channel_id, media["file_unique_id"])
            if existing:
                film_id, title, message_id = existing
                self.show_duplicate(chat_id, film_id, title, message_id)
                return
            title = film_title(message, media)
            if not title:
                self.send(chat_id, "Telegram n’a pas fourni le nom du fichier. "
                          "Renvoie la vidéo en tant que fichier, ou indique son titre en légende.")
                return
            film_id = self.catalogue.add(media, kind, title)
            origin = message.get("forward_origin", {})
            if (self.channel_id and origin.get("type") == "channel" and
                    origin.get("chat", {}).get("id") == self.channel_id and
                    isinstance(origin.get("message_id"), int)):
                self.catalogue.link_channel(self.channel_id, film_id, origin["message_id"])
                self.send(chat_id, f"Film indexé : {title}\nNuméro : {film_id}")
            elif self.channel_id:
                self.publish(chat_id, str(film_id))
            else:
                self.send(chat_id, f"Film enregistré : {title}\nNuméro : {film_id}")
        elif command in ("/start", "/aide", "/help"):
            self.show_menu(chat_id, user_id)
        elif command == "/catalogue":
            self.list_films(chat_id)
        elif command == "/recherche":
            if argument.strip():
                self.list_films(chat_id, argument.strip()[:200])
            else:
                self.send(chat_id, "🔎 Envoie le titre du film que tu recherches.")
        elif command == "/film":
            self.deliver(chat_id, argument.strip())
        elif command == "/publier" and user_id in self.admins:
            self.publish(chat_id, argument.strip())
        elif command == "/supprimer" and user_id in self.admins:
            if argument.strip().isdigit() and len(argument.strip()) < 16:
                removed = self.catalogue.remove(int(argument.strip()))
                self.send(chat_id, "Film retiré." if removed else "Film introuvable.")
            else:
                self.send(chat_id, "Choisis un film dans le catalogue pour le retirer.")
        elif text and not text.startswith("/"):
            self.list_films(chat_id, text[:200])

    def show_menu(self, chat_id, user_id):
        self.send(chat_id, HELP + (ADMIN_HELP if user_id in self.admins else ""),
                  reply_markup={"inline_keyboard": [
                      [{"text": "🎬 Catalogue", "callback_data": "catalogue"},
                       {"text": "❓ Aide", "callback_data": "aide"}],
                      [{"text": "🔎 Rechercher un film", "callback_data": "recherche"}],
                      [{"text": "🎬 Rejoindre le canal", "url": "https://t.me/maxxie_films"}]]})

    def publish(self, chat_id, identifier):
        if not self.channel_id:
            self.send(chat_id, "Le canal n’est pas configuré.")
            return
        if not identifier.isdigit() or len(identifier) > 15:
            self.send(chat_id, "Choisis un film dans le catalogue pour le publier.")
            return
        film_id = int(identifier)
        film = self.catalogue.get(film_id)
        if not film:
            self.send(chat_id, "Film introuvable.")
            return
        member = self.api.call("getChatMember", chat_id=self.channel_id, user_id=chat_id)
        if member.get("status") != "creator" and not (
                member.get("status") == "administrator" and member.get("can_post_messages")):
            self.send(chat_id, "Tu dois aussi avoir le droit de publier dans le canal.")
            return
        message_id = self.catalogue.channel_message(self.channel_id, film_id)
        if message_id:
            self.show_duplicate(chat_id, film_id, film[2], message_id)
            return
        file_id, kind, title = film
        sent = self.api.call("sendVideo" if kind == "video" else "sendDocument",
                             chat_id=self.channel_id, caption=title, **{kind: file_id})
        self.catalogue.link_channel(self.channel_id, film_id, sent["message_id"])
        self.send(chat_id, "Film publié dans le canal.")

    def show_duplicate(self, chat_id, film_id, title, message_id):
        channel = str(self.channel_id)
        # Les liens t.me/c utilisent l’identifiant sans le préfixe Bot API -100.
        url = f"https://t.me/c/{channel[4:]}/{message_id}"
        self.send(chat_id, f"♻️ Ce film est déjà disponible dans le canal.\n\n"
                  f"🎬 {title}\nNuméro : {film_id}\n\nIl n’a pas été republié.",
                  reply_markup={"inline_keyboard": [[
                      {"text": "🎬 Voir le film dans le canal", "url": url}]]})

    def list_films(self, chat_id, query="", page=0):
        rows = self.catalogue.search(query, page)
        if not rows:
            self.send(chat_id, "Aucun film trouvé.", reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            return
        keyboard = [[{"text": f"🎬 {title}"[:64], "callback_data": f"film:{film_id}"}]
                    for film_id, title in rows[:10]]
        if chat_id in self.admins:
            keyboard = []
            for film_id, title in rows[:10]:
                keyboard.append([{"text": f"🎬 {title}"[:64], "callback_data": f"film:{film_id}"}])
                keyboard.append([{"text": "📢 Publier", "callback_data": f"publier:{film_id}"},
                                 {"text": "🗑 Retirer", "callback_data": f"retirer:{film_id}"}])
        navigation = []
        if not query:
            if page:
                navigation.append({"text": "← Précédents", "callback_data": f"page:{page-1}"})
            if len(rows) > 10:
                navigation.append({"text": "Suivants →", "callback_data": f"page:{page+1}"})
        if navigation:
            keyboard.append(navigation)
        keyboard.append([MENU_BUTTON])
        text = "Choisis un film :"
        if query and len(rows) > 10:
            text += "\nPlus de 10 résultats : précise ta recherche."
        self.send(chat_id, text, reply_markup={"inline_keyboard": keyboard})

    def deliver(self, chat_id, identifier):
        if not identifier.isdigit() or len(identifier) > 15:
            self.send(chat_id, "Choisis un film dans le catalogue.")
            return
        film = self.catalogue.get(int(identifier))
        if not film:
            self.send(chat_id, "Film introuvable.")
            return
        if not self.check_membership(chat_id, identifier):
            return
        file_id, kind, title = film
        self.api.call("sendVideo" if kind == "video" else "sendDocument",
                      chat_id=chat_id, caption=title, **{kind: file_id})

    def check_membership(self, chat_id, identifier):
        try:
            if not self.channel_id:
                raise TelegramError(0)
            member = self.api.call("getChatMember", chat_id=self.channel_id, user_id=chat_id)
        except TelegramError:
            self.send(chat_id, "La vérification de ton abonnement est momentanément indisponible. Réessaie dans un instant.",
                      reply_markup={"inline_keyboard": [[
                          {"text": "🔄 Réessayer", "callback_data": f"rejoindre:{identifier}"}], [MENU_BUTTON]]})
            return False
        if member.get("status") in ("creator", "administrator", "member") or (
                member.get("status") == "restricted" and member.get("is_member") is True):
            return True
        self.send(chat_id, "🔒 Rejoins le canal Maxxie Films pour télécharger ce film, puis vérifie ton abonnement.",
                  reply_markup={"inline_keyboard": [
                      [{"text": "🎬 Rejoindre le canal", "url": "https://t.me/maxxie_films"}],
                      [{"text": "✅ J’ai rejoint le canal", "callback_data": f"rejoindre:{identifier}"}],
                      [MENU_BUTTON]]})
        return False


def user_ids(value):
    ids = {int(item.strip()) for item in value.split(",") if item.strip()}
    if any(item <= 0 for item in ids):
        raise ValueError("Les identifiants utilisateurs doivent être positifs")
    return ids


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    admins = user_ids(os.environ.get("ADMIN_USER_IDS", ""))
    if not admins:
        raise SystemExit("ADMIN_USER_IDS doit contenir au moins un administrateur.")
    allowed = user_ids(os.environ.get("ALLOWED_USER_IDS", ""))
    api = Telegram(os.environ["BOT_TOKEN"])
    expected = os.environ["BOT_USERNAME"].lstrip("@").lower()
    path = Path(os.environ.get("DATABASE_PATH", "/var/lib/maxxie-films-bot/catalogue.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    store = Catalogue(path)
    bot = Bot(api, store, admins, allowed)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    ready = False
    backoff = 2
    while not stop.is_set():
        try:
            if not ready:
                identity = api.call("getMe")
                if identity.get("username", "").lower() != expected:
                    raise SystemExit("Le jeton ne correspond pas au BOT_USERNAME attendu.")
                if api.call("getWebhookInfo").get("url"):
                    raise SystemExit("Un webhook existe : retire-le avant de démarrer ce service.")
                try:
                    bot.channel_id = verify_channel(api, identity["id"], os.environ.get("CHANNEL_ID", "@maxxie_films"))
                except ValueError as error:
                    raise SystemExit(str(error)) from None
                clear_commands(api)
                ready = True
                LOG.info("Bot vérifié ; réception des messages.")
            updates = api.call("getUpdates", offset=store.offset(), timeout=30,
                               allowed_updates=["message", "callback_query", "channel_post", "edited_channel_post"])
            for update in updates:
                if stop.is_set():
                    break
                # Enregistrer avant tout effet externe pour éviter un nouvel envoi
                # après un arrêt incertain. Un crash peut donc perdre une demande.
                store.acknowledge(update["update_id"])
                try:
                    bot.handle(update)
                except TelegramError as error:
                    LOG.warning("Traitement non rejoué, résultat potentiellement incertain (code %s).", error.code)
                    if error.code == 429:
                        stop.wait(min(error.retry_after or 5, 300))
            backoff = 2
        except TelegramError as error:
            if error.code in (401, 404, 409):
                raise SystemExit(f"Telegram refuse la réception (code {error.code}).") from None
            LOG.warning("Réception indisponible (code %s).", error.code)
            stop.wait(min(error.retry_after or backoff, 300))
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    main()
