import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app.models import Alerta

class TestAlerts(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.mock_session = MagicMock()

    def override_get_db(self):
        try:
            yield self.mock_session
        finally:
            pass

    def test_list_alerts(self):
        """Test listing unread alerts"""
        # Setup mock
        mock_alert = MagicMock(spec=Alerta)
        mock_alert.id = 1
        mock_alert.tipo = "CRITICO"
        mock_alert.mensaje = "Stock bajo"
        mock_alert.leida = False
        
        self.mock_session.query.return_value.filter.return_value.all.return_value = [mock_alert]
        
        # Override dependency
        app.dependency_overrides[get_db] = self.override_get_db
        
        response = self.client.get("/alerts")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['tipo'], "CRITICO")

    def test_ack_alert_success(self):
        """Test acknowledging an alert successfully"""
        # Setup mock
        mock_alert = MagicMock(spec=Alerta)
        mock_alert.id = 1
        mock_alert.leida = False
        
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_alert
        
        # Override dependency
        app.dependency_overrides[get_db] = self.override_get_db
        
        response = self.client.patch("/alerts/1/ack")
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        
        # Verify db commit was called
        self.mock_session.commit.assert_called_once()
        # Verify alert status changed (mock object)
        self.assertTrue(mock_alert.leida)

    def test_ack_alert_not_found(self):
        """Test acknowledging a non-existent alert"""
        # Setup mock to return None
        self.mock_session.query.return_value.filter.return_value.first.return_value = None
        
        # Override dependency
        app.dependency_overrides[get_db] = self.override_get_db
        
        response = self.client.patch("/alerts/999/ack")
        
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail'], 'alert not found')

    def tearDown(self):
        app.dependency_overrides = {}

if __name__ == '__main__':
    unittest.main()
