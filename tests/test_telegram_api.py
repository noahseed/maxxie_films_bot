import unittest
from unittest.mock import patch, MagicMock

from telegram_api import Telegram, TelegramError


class TelegramTests(unittest.TestCase):
    def test_rejects_malformed_token_without_echoing_it(self):
        with self.assertRaises(ValueError) as caught:
            Telegram("secret\ninvalid")
        self.assertNotIn("secret", str(caught.exception))

    @patch("telegram_api.http.client.HTTPSConnection")
    def test_uncertain_send_is_not_retried_and_token_is_hidden(self, factory):
        connection = factory.return_value
        connection.request.side_effect = OSError("123:secret")
        with self.assertRaises(TelegramError) as caught:
            Telegram("123:secret").call("sendMessage", chat_id=1, text="Bonjour")
        self.assertEqual(connection.request.call_count, 1)
        self.assertNotIn("secret", str(caught.exception))
        connection.close.assert_called_once()

    @patch("telegram_api.http.client.HTTPSConnection")
    def test_rate_limit_is_exposed_without_response_description(self, factory):
        response = MagicMock(status=429)
        response.read.return_value = b'{"ok":false,"error_code":429,"description":"secret","parameters":{"retry_after":10}}'
        factory.return_value.getresponse.return_value = response
        with self.assertRaises(TelegramError) as caught:
            Telegram("123:secret").call("sendMessage", chat_id=1, text="Bonjour")
        self.assertEqual(caught.exception.retry_after, 10)
        self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
