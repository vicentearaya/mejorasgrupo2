import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.models import Employee
from app.routers.auth import get_password_hash
from app.db import get_db

class TestLogin(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.mock_session = MagicMock()
        
        # Create a mock user
        self.test_user = Employee(
            id=1,
            email="test@example.com",
            password=get_password_hash("password123"),
            nombre="Test User",
            role_id=1,
            activo=True
        )

    def override_get_db(self):
        try:
            yield self.mock_session
        finally:
            pass

    def test_login_success(self):
        """Test successful login with valid credentials"""
        # Setup mock to return the user
        self.mock_session.query.return_value.filter.return_value.first.return_value = self.test_user
        
        # Override dependency
        app.dependency_overrides[get_db] = self.override_get_db
        
        response = self.client.post(
            "/auth/login", 
            data={"username": "test@example.com", "password": "password123"}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")

    def test_login_invalid_password(self):
        """Test login failure with incorrect password"""
        # Setup mock to return the user
        self.mock_session.query.return_value.filter.return_value.first.return_value = self.test_user
        
        # Override dependency
        app.dependency_overrides[get_db] = self.override_get_db
        
        response = self.client.post(
            "/auth/login", 
            data={"username": "test@example.com", "password": "wrongpassword"}
        )
        
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Incorrect email or password")

    def test_login_user_not_found(self):
        """Test login failure when user does not exist"""
        # Setup mock to return None
        self.mock_session.query.return_value.filter.return_value.first.return_value = None
        
        # Override dependency
        app.dependency_overrides[get_db] = self.override_get_db
        
        response = self.client.post(
            "/auth/login", 
            data={"username": "nonexistent@example.com", "password": "password123"}
        )
        
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Incorrect email or password")

    def tearDown(self):
        app.dependency_overrides = {}

if __name__ == '__main__':
    unittest.main()
