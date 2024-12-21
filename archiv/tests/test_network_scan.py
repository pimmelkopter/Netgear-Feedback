import unittest
from unittest.mock import patch
from src.network_scan import find_first_switch

class TestNetworkScan(unittest.TestCase):
    @patch('requests.head')
    def test_find_switch(self, mock_head):
        mock_head.return_value.status_code = 200
        ip = find_first_switch("10.18.254", 10, 11)
        self.assertTrue(ip.startswith("10.18.254"))

if __name__ == '__main__':
    unittest.main()
