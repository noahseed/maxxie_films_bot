"""Client Telegram minimal, sans dépendances externes ni jetons dans les erreurs."""
import http.client
import json
import re


class TelegramError(Exception):
    def __init__(self, code, retry_after=None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(f"Telegram : erreur {code}")


class Telegram:
    def __init__(self, token):
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
            raise ValueError("Format du jeton Telegram invalide")
        self._path = f"/bot{token}/"

    def call(self, method, **params):
        # Aucun nouvel essai implicite : un envoi peut avoir été accepté
        # avant une coupure réseau.
        connection = http.client.HTTPSConnection(
            "api.telegram.org", timeout=params.get("timeout", 0) + 15)
        try:
            connection.request("POST", self._path + method,
                               json.dumps(params).encode("utf-8"),
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            result = json.loads(response.read())
        except (OSError, http.client.HTTPException, ValueError):
            raise TelegramError(0) from None
        finally:
            connection.close()
        if not isinstance(result, dict):
            raise TelegramError(0)
        if not result.get("ok"):
            raise TelegramError(result.get("error_code", response.status),
                                result.get("parameters", {}).get("retry_after"))
        if "result" not in result:
            raise TelegramError(0)
        return result["result"]
