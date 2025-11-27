import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app import crud

class TestStockAdjustments(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.mock_session = MagicMock()

    def override_get_db(self):
        try:
            yield self.mock_session
        finally:
            pass

    @patch('app.crud.upsert_stock')
    @patch('app.crud.insert_movimiento')
    @patch('app.crud.check_and_create_alert')
    def test_add_units_success(self, mock_alert, mock_mov, mock_upsert):
        """Test adding units (IN) successfully"""
        # Setup mocks
        mock_upsert.return_value = MagicMock(cantidad=100)
        mock_mov.return_value = MagicMock(id=1)
        mock_alert.return_value = None
        
        # Override dependency
        app.dependency_overrides[get_db] = self.override_get_db
        
        payload = {
            "producto_id": 1,
            "bodega_id": 1,
            "tipo": "IN",
            "cantidad": 10,
            "motivo": "Restock"
        }
        
        response = self.client.post("/movements", json=payload)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['stock'], 100)
        
        # Verify crud calls
        mock_upsert.assert_called_once()
        # Check that delta was positive
        args, _ = mock_upsert.call_args
        self.assertEqual(args[3], 10) # delta

    @patch('app.crud.upsert_stock')
    @patch('app.crud.insert_movimiento')
    @patch('app.crud.check_and_create_alert')
    def test_remove_units_success(self, mock_alert, mock_mov, mock_upsert):
        """Test removing units (OUT) successfully"""
        # Setup mocks
        mock_upsert.return_value = MagicMock(cantidad=90)
        mock_mov.return_value = MagicMock(id=2)
        mock_alert.return_value = None
        
        # Override dependency
        app.dependency_overrides[get_db] = self.override_get_db
        
        payload = {
            "producto_id": 1,
            "bodega_id": 1,
            "tipo": "OUT",
            "cantidad": 5,
            "motivo": "Sale"
        }
        
        response = self.client.post("/movements", json=payload)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['stock'], 90)
        
        # Verify crud calls
        mock_upsert.assert_called_once()
        # Check that delta was negative
        args, _ = mock_upsert.call_args
        self.assertEqual(args[3], -5) # delta

    def test_invalid_type(self):
        """Test invalid movement type"""
        app.dependency_overrides[get_db] = self.override_get_db
        
        payload = {
            "producto_id": 1,
            "bodega_id": 1,
            "tipo": "INVALID",
            "cantidad": 10
        }
        
        response = self.client.post("/movements", json=payload)
        
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'tipo must be IN|OUT|TRANSFER')

    def tearDown(self):
        app.dependency_overrides = {}

if __name__ == '__main__':
    unittest.main()
