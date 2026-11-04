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
        "/catalogue — derniers films\n"
        "/recherche titre — rechercher un film\n"
        "/film numéro — recevoir un film\n"
        "/id — ton identifiant Telegram\n"
        "/aide — afficher ce menu")
ADMIN_HELP = ("\n\nAdministration : envoie une vidéo ou un fichier vidéo "
              "avec son titre en légende pour l’ajouter.\n"
              "/supprimer numéro — retirer un film du catalogue")


class Bot:
    def __init__(self, api, catalogue, admins, allowed_users):
        self.api, self.catalogue = api, catalogue
        self.admins, self.allowed_users = set(admins), set(allowed_users)

    def send(self, chat_id, text, **params):
        return self.api.call("sendMessage", chat_id=chat_id, text=text, **params)

    def handle(self, update):
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
            if data.startswith("film:"):
                self.deliver(chat_id, data[5:])
            elif data.startswith("page:") and data[5:].isdigit():
                self.list_films(chat_id, page=min(int(data[5:]), 100000))
            return
        media = message.get("video")
        kind = "video"
        document = message.get("document", {})
        if not media and document.get("mime_type", "").startswith("video/"):
            media, kind = document, "document"
        if media:
            if user_id not in self.admins:
                self.send(chat_id, "Seuls les administrateurs peuvent ajouter des films.")
                return
            title = message.get("caption", "").strip()
            if not title:
                self.send(chat_id, "Renvoie le film avec son titre en légende.")
                return
            film_id = self.catalogue.add(media, kind, title)
            self.send(chat_id, f"Film enregistré : {title[:200]}\nNuméro : {film_id}")
        elif command in ("/start", "/aide", "/help"):
            self.send(chat_id, HELP + (ADMIN_HELP if user_id in self.admins else ""))
        elif command == "/catalogue":
            self.list_films(chat_id)
        elif command == "/recherche":
            if argument.strip():
                self.list_films(chat_id, argument.strip()[:200])
            else:
                self.send(chat_id, "Utilise /recherche titre")
        elif command == "/film":
            self.deliver(chat_id, argument.strip())
        elif command == "/supprimer" and user_id in self.admins:
            if argument.strip().isdigit() and len(argument.strip()) < 16:
                removed = self.catalogue.remove(int(argument.strip()))
                self.send(chat_id, "Film retiré." if removed else "Film introuvable.")
            else:
                self.send(chat_id, "Utilise /supprimer numéro")

    def list_films(self, chat_id, query="", page=0):
        rows = self.catalogue.search(query, page)
        if not rows:
            self.send(chat_id, "Aucun film trouvé.")
            return
        keyboard = [[{"text": f"🎬 {title}"[:64], "callback_data": f"film:{film_id}"}]
                    for film_id, title in rows[:10]]
        navigation = []
        if not query:
            if page:
                navigation.append({"text": "← Précédents", "callback_data": f"page:{page-1}"})
            if len(rows) > 10:
                navigation.append({"text": "Suivants →", "callback_data": f"page:{page+1}"})
        if navigation:
            keyboard.append(navigation)
        text = "Choisis un film :"
        if query and len(rows) > 10:
            text += "\nPlus de 10 résultats : précise ta recherche."
        self.send(chat_id, text, reply_markup={"inline_keyboard": keyboard})

    def deliver(self, chat_id, identifier):
        if not identifier.isdigit() or len(identifier) > 15:
            self.send(chat_id, "Utilise /film numéro")
            return
        film = self.catalogue.get(int(identifier))
        if not film:
            self.send(chat_id, "Film introuvable.")
            return
        file_id, kind, title = film
        self.api.call("sendVideo" if kind == "video" else "sendDocument",
                      chat_id=chat_id, caption=title, **{kind: file_id})


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
                ready = True
                LOG.info("Bot vérifié ; réception des messages.")
            updates = api.call("getUpdates", offset=store.offset(), timeout=30,
                               allowed_updates=["message", "callback_query"])
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
