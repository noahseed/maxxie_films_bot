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
        "Recherche un film par son titre.\n"
        "Les résultats ouvrent les films directement dans le canal. Bonne séance !")
ADMIN_HELP = ("\n\nAdministration : envoie une vidéo pour la publier dans le canal "
              "avec son nom de fichier sans .mp4.")
MENU_BUTTON = {"text": "🏠 Menu", "callback_data": "menu"}
RULES = ("📜 Règles de Maxxie Films\n\n"
         "• Respecte les autres membres et les administrateurs.\n"
         "• Évite le spam, la publicité et les messages répétitifs.\n"
         "• Recherche les films par leur titre et ouvre-les dans le canal.\n"
         "• Pour signaler un problème ou poser une question, utilise le bouton Contact.")


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
    def __init__(self, api, catalogue, admins, allowed_users, channel_id=None, notify_chat_id=None):
        self.api, self.catalogue = api, catalogue
        self.admins, self.allowed_users = set(admins), set(allowed_users)
        self.channel_id = channel_id
        self.notify_chat_id = notify_chat_id

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
        self.notify_new_visitor((callback or message).get("from", {}))
        if callback:
            try:
                self.api.call("answerCallbackQuery", callback_query_id=callback["id"])
            except TelegramError:
                pass
        text = message.get("text", "").strip()
        command, _, argument = text.partition(" ")
        command = command.split("@", 1)[0].lower()
        if not self.check_membership(chat_id):
            self.catalogue.clear_contact(user_id)
            self.catalogue.clear_reply(user_id)
            return
        if not callback and command == "/id":
            self.send(chat_id, f"Ton identifiant Telegram : {user_id}")
            return
        if user_id not in self.allowed_users | self.admins:
            self.send(chat_id, "Ce catalogue est privé. Demande l’accès à son administrateur. "
                      f"Ton identifiant : {user_id}")
            return
        if callback:
            data = callback.get("data", "")
            self.catalogue.clear_contact(user_id)
            self.catalogue.clear_reply(user_id)
            if data.startswith("repondre:"):
                target = (self.catalogue.begin_reply(user_id, data.split(":", 1)[1])
                          if user_id == self.notify_chat_id and user_id in self.admins else None)
                if not target:
                    self.send(chat_id, "Cette réponse n’est pas disponible ou a expiré.")
                    return
                self.send(chat_id, f"💬 Ta réponse sera transmise à l’utilisateur {target}. "
                          "Envoie ton texte ou une pièce jointe. Reviens au menu pour terminer "
                          "(session valable 15 minutes).",
                          reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            elif data == "contact":
                if not self.notify_chat_id:
                    self.send(chat_id, "Le contact est momentanément indisponible.")
                    return
                self.catalogue.request_contact(user_id)
                self.send(chat_id, "✉️ Envoie ton message : il sera transmis en privé à l’administrateur. "
                          "Tu peux aussi joindre une photo, une vidéo ou un fichier. "
                          "Reviens au menu pour terminer (expiration après 15 minutes d’inactivité).",
                          reply_markup={"inline_keyboard": [[{"text": "Annuler", "callback_data": "menu"}]]})
            elif data == "catalogue":
                self.show_menu(chat_id, user_id)
            elif data in ("aide", "menu", "abonnement"):
                self.show_menu(chat_id, user_id)
            elif data == "regles":
                self.send(chat_id, RULES, reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            elif data == "recherche":
                self.send(chat_id, "🔎 Envoie un titre, même approximatif. Tu peux préciser "
                          "une année et une langue : par exemple « Matrix 1999 VF ».",
                          reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            elif data.startswith("rejoindre:"):
                self.deliver(chat_id, data.split(":", 1)[1])
            elif data.startswith(("publier:", "retirer:", "confirmer_retrait:")):
                self.show_menu(chat_id, user_id)
            elif data.startswith("film:"):
                self.deliver(chat_id, data[5:])
            elif data.startswith("page:") and data[5:].isdigit():
                self.show_menu(chat_id, user_id)
            return
        if text.startswith("/"):
            self.catalogue.clear_contact(user_id)
            self.catalogue.clear_reply(user_id)
        elif self.catalogue.reply_target(user_id):
            self.send_reply(user_id, message)
            return
        elif self.catalogue.contact_pending(user_id):
            self.send_contact(chat_id, message)
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
            self.show_menu(chat_id, user_id)
        elif command == "/recherche":
            if argument.strip():
                self.list_films(chat_id, argument.strip()[:200])
            else:
                self.send(chat_id, "🔎 Envoie le titre du film que tu recherches.")
        elif command in ("/publier", "/supprimer"):
            self.show_menu(chat_id, user_id)
        elif text and not text.startswith("/"):
            self.list_films(chat_id, text[:200])

    def show_menu(self, chat_id, user_id):
        self.send(chat_id, HELP + (ADMIN_HELP if user_id in self.admins else ""),
                  reply_markup={"inline_keyboard": [
                      [{"text": "🔎 Rechercher un film", "callback_data": "recherche"},
                       {"text": "📜 Lire les règles", "callback_data": "regles"}],
                      [{"text": "🎬 Rejoindre le canal", "url": "https://t.me/maxxie_films"}],
                      [{"text": "✉️ Contact", "callback_data": "contact"},
                       {"text": "❓ Aide", "callback_data": "aide"}]]})

    def send_contact(self, chat_id, message):
        # Garder le mode contact pour les messages suivants, y compris un album.
        # Le curseur des mises à jour est enregistré avant tout envoi.
        self.catalogue.request_contact(chat_id)
        user = message.get("from", {})
        name = " ".join(str(user.get(key, "")) for key in ("first_name", "last_name")).strip()
        username = user.get("username")
        try:
            if not self.notify_chat_id:
                raise TelegramError(0)
            token = self.catalogue.create_contact_thread(self.notify_chat_id, chat_id)
            self.send(self.notify_chat_id,
                      f"✉️ Message de contact Maxxie Films\n\nNom : {name[:200] or 'Non renseigné'}\n"
                      f"Pseudo : {'@' + username if username else 'Non renseigné'}\nIdentifiant : {chat_id}",
                      reply_markup={"inline_keyboard": [[
                          {"text": "💬 Répondre", "callback_data": f"repondre:{token}"}]]})
            self.api.call("copyMessage", chat_id=self.notify_chat_id,
                          from_chat_id=chat_id, message_id=message["message_id"])
        except TelegramError as error:
            LOG.warning("Message de contact non confirmé (code %s).", error.code)
            self.send(chat_id, "La transmission de ton message n’a pas pu être confirmée. "
                      "Tu peux réessayer avec le bouton Contact.",
                      reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            return
        self.send(chat_id, "✅ Ton message a été transmis à l’administrateur. "
                  "Tu peux écrire un autre message ou revenir au menu.",
                  reply_markup={"inline_keyboard": [[MENU_BUTTON]]})

    def send_reply(self, owner_id, message):
        target = self.catalogue.reply_target(owner_id)
        if owner_id != self.notify_chat_id or owner_id not in self.admins or not target:
            self.catalogue.clear_reply(owner_id)
            self.send(owner_id, "La session de réponse a expiré.")
            return
        if target not in self.allowed_users | self.admins:
            self.send(owner_id, "Cet utilisateur n’a plus accès au bot.")
            return
        try:
            member = self.api.call("getChatMember", chat_id=self.channel_id, user_id=target)
            if not (member.get("status") in ("creator", "administrator", "member") or
                    (member.get("status") == "restricted" and member.get("is_member") is True)):
                self.send(owner_id, "Cet utilisateur doit rejoindre le canal avant de recevoir ta réponse.")
                return
            self.send(target, "💬 Réponse de l’administrateur Maxxie Films")
            self.api.call("copyMessage", chat_id=target, from_chat_id=owner_id,
                          message_id=message["message_id"])
        except TelegramError as error:
            LOG.warning("Réponse de contact non confirmée (code %s).", error.code)
            self.send(owner_id, "La transmission de ta réponse n’a pas pu être confirmée.",
                      reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            return
        self.send(owner_id, "✅ Réponse transmise. Tu peux continuer ou revenir au menu.",
                  reply_markup={"inline_keyboard": [[MENU_BUTTON]]})

    def notify_new_visitor(self, user):
        user_id = user["id"]
        if not self.catalogue.remember_visitor(user_id):
            return
        if not self.notify_chat_id or user_id == self.notify_chat_id:
            return
        name = " ".join(str(user.get(key, "")) for key in ("first_name", "last_name")).strip()
        username = user.get("username")
        text = (f"👋 Nouvel utilisateur de Maxxie Films\n\n"
                f"Nom : {name[:200] or 'Non renseigné'}\n"
                f"Pseudo : {'@' + username if username else 'Non renseigné'}\n"
                f"Identifiant : {user_id}")
        try:
            self.send(self.notify_chat_id, text)
        except TelegramError as error:
            # Ne pas interrompre l’utilisateur ou répéter un envoi incertain.
            LOG.warning("Notification de nouveau visiteur non confirmée (code %s).", error.code)

    def publish(self, chat_id, identifier):
        if not self.channel_id:
            self.send(chat_id, "Le canal n’est pas configuré.")
            return
        if not identifier.isdigit() or len(identifier) > 15:
            self.send(chat_id, "Recherche un film pour le publier.")
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
        url = self.film_link(message_id)
        self.send(chat_id, f"♻️ Ce film est déjà disponible dans le canal.\n\n"
                  f"🎬 {title}\nNuméro : {film_id}\n\nIl n’a pas été republié.",
                  reply_markup={"inline_keyboard": [[
                      {"text": "🎬 Voir le film dans le canal", "url": url}]]})

    def film_link(self, message_id):
        channel = str(self.channel_id)
        return f"https://t.me/c/{channel[4:]}/{message_id}"

    def list_films(self, chat_id, query="", page=0):
        if not query.strip():
            self.send(chat_id, "🔎 Envoie le titre du film que tu recherches.",
                      reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            return
        rows = self.catalogue.search_channel(self.channel_id, query)
        if not rows:
            self.send(chat_id, "Aucun film trouvé dans le canal.",
                      reply_markup={"inline_keyboard": [[MENU_BUTTON]]})
            return
        keyboard = [[{"text": f"🎬 {title}"[:64], "url": self.film_link(message_id)}]
                    for _, title, message_id in rows[:10]]
        keyboard.append([MENU_BUTTON])
        text = "🎬 Titres trouvés ou proches de ta recherche — ouvre le film dans le canal :"
        if len(rows) > 10:
            text += "\nPlus de 10 résultats : précise ta recherche."
        self.send(chat_id, text, reply_markup={"inline_keyboard": keyboard})

    def deliver(self, chat_id, identifier):
        # Les anciens boutons de téléchargement ouvrent désormais le canal.
        if not identifier.isdigit() or len(identifier) > 15:
            self.send(chat_id, "Recherche un film puis sélectionne son titre.")
            return
        film = self.catalogue.get(int(identifier))
        message_id = self.catalogue.channel_message(self.channel_id, int(identifier))
        if not film or not message_id:
            self.send(chat_id, "Ce film n’est pas disponible dans le canal.")
            return
        self.send(chat_id, f"🎬 {film[2]}", reply_markup={"inline_keyboard": [[
            {"text": "🎬 Voir le film dans le canal", "url": self.film_link(message_id)}], [MENU_BUTTON]]})

    def check_membership(self, chat_id):
        try:
            if not self.channel_id:
                raise TelegramError(0)
            member = self.api.call("getChatMember", chat_id=self.channel_id, user_id=chat_id)
        except TelegramError:
            self.send(chat_id, "La vérification de ton abonnement est momentanément indisponible. Réessaie dans un instant.",
                      reply_markup={"inline_keyboard": [[
                          {"text": "🔄 Réessayer", "callback_data": "abonnement"}]]})
            return False
        if member.get("status") in ("creator", "administrator", "member") or (
                member.get("status") == "restricted" and member.get("is_member") is True):
            return True
        self.send(chat_id, "🔒 Rejoins le canal Maxxie Films pour utiliser le bot, puis vérifie ton abonnement.",
                  reply_markup={"inline_keyboard": [
                      [{"text": "🎬 Rejoindre le canal", "url": "https://t.me/maxxie_films"}],
                      [{"text": "✅ J’ai rejoint le canal", "callback_data": "abonnement"}]]})
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
    notify_id = os.environ.get("NOTIFY_CHAT_ID", "").strip()
    if not notify_id and len(admins) == 1:
        notify_id = str(next(iter(admins)))
    if not notify_id or not notify_id.isdigit() or int(notify_id) not in admins:
        raise SystemExit("NOTIFY_CHAT_ID doit désigner un administrateur en privé.")
    bot = Bot(api, store, admins, allowed, notify_chat_id=int(notify_id))
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
