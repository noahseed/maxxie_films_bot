import unittest
import socket
from unittest.mock import patch, MagicMock

from telegram_api import Telegram, TelegramError, connect_ipv4


class TelegramTests(unittest.TestCase):
    def test_rejects_malformed_token_without_echoing_it(self):
        with self.assertRaises(ValueError) as caught:
            Telegram("secret\ninvalid")
        self.assertNotIn("secret", str(caught.exception))

    @patch("telegram_api.http.client.HTTPSConnection")
    def test_uncertain_send_is_not_retried_and_token_is_hidden(self, factory):
        connection = factory.return_value
        connection.request.side_effect = OSError("123:secret")
        with self.assertLogs('maxxie-films', level='WARNING') as logs:
            with self.assertRaises(TelegramError) as caught:
                Telegram("123:secret").call("sendMessage", chat_id=1, text="Bonjour")
        self.assertEqual(connection.request.call_count, 1)
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn('secret', str(logs.output))
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

    @patch('telegram_api.http.client.HTTPSConnection')
    def test_successive_calls_reuse_tls_connection_and_change_read_timeout(self, factory):
        response = factory.return_value.getresponse.return_value
        response.will_close = False
        response.read.return_value = b'{"ok":true,"result":[]}'
        api = Telegram('123:secret')
        api.call('getUpdates', timeout=30)
        factory.return_value.sock.settimeout.assert_called_with(35)
        api.call('getChatMember', chat_id=-100123, user_id=1)
        factory.return_value.sock.settimeout.assert_called_with(8)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(factory.return_value.request.call_count, 2)
        self.assertIs(factory.return_value._create_connection, connect_ipv4)
        factory.assert_called_with('api.telegram.org', timeout=3)

    @patch('telegram_api.http.client.HTTPSConnection')
    def test_stale_connection_is_replaced_for_safe_read(self, factory):
        first, second = MagicMock(), MagicMock()
        first.request.side_effect = OSError('connection closed')
        second.getresponse.return_value.read.return_value = b'{"ok":true,"result":{"id":1}}'
        second.getresponse.return_value.will_close = False
        factory.side_effect = [first, second]
        result = Telegram('123:secret').call('getMe')
        self.assertEqual(result, {'id': 1})
        self.assertEqual(factory.call_count, 2)
        first.close.assert_called_once()

    @patch('telegram_api.socket.socket')
    @patch('telegram_api.socket.getaddrinfo')
    def test_connection_uses_ipv4_without_attempting_ipv6(self, addresses, factory):
        addresses.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', 443))]
        connection = connect_ipv4(('api.telegram.org', 443), 3)
        addresses.assert_called_with('api.telegram.org', 443, socket.AF_INET, socket.SOCK_STREAM)
        factory.return_value.connect.assert_called_with(('192.0.2.1', 443))
        self.assertIs(connection, factory.return_value)


if __name__ == "__main__":
    unittest.main()
