import unittest
from unittest.mock import patch
from src.api_client import APIClient

class TestAPIClient(unittest.TestCase):
    @patch('requests.post')
    def test_login(self, mock_post):
        mock_post.return_value.json.return_value = {
            "resp": {"status": "success", "respCode": 200},
            "login": {"token": "abcdef12345", "expires": 3600}
        }
        client = APIClient("https://10.18.254.100:8443/api/v1", "admin", "pass")
        token = client.login()
        self.assertEqual(token, "abcdef12345")

if __name__ == '__main__':
    unittest.main()
