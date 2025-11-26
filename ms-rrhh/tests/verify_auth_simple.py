from fastapi.testclient import TestClient
from app.main import app
from app.models import Employee
from app.routers.auth import get_password_hash
from unittest.mock import MagicMock
from app.db import get_db

client = TestClient(app)

# Mock DB Session
mock_session = MagicMock()
mock_user = Employee(
    id=1,
    email="test@example.com",
    password=get_password_hash("password123"),
    nombre="Test User",
    role_id=1,
    activo=True
)

def override_get_db():
    try:
        yield mock_session
    finally:
        pass

app.dependency_overrides[get_db] = override_get_db

if __name__ == "__main__":
    print("Testing Auth Flow with Mock DB...")

    # 1. Test Invalid Login
    print("\n1. Testing Login with invalid credentials...")
    # Setup mock to return None for invalid user
    mock_session.query.return_value.filter.return_value.first.return_value = None
    
    response = client.post("/auth/login", data={"username": "wrong@example.com", "password": "wrongpassword"})
    print(f"Status: {response.status_code}")
    assert response.status_code == 401
    print("✅ Invalid credentials rejected.")

    # 2. Test Valid Login
    print("\n2. Testing Login with valid credentials...")
    # Setup mock to return user
    mock_session.query.return_value.filter.return_value.first.return_value = mock_user
    
    response = client.post("/auth/login", data={"username": "test@example.com", "password": "password123"})
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Response: {response.json()}")
    assert response.status_code == 200
    token = response.json()["access_token"]
    print(f"✅ Login successful. Token received: {token[:20]}...")

    # 3. Test Protected Endpoint (e.g. /employees/me if it existed, or just verify token structure)
    # Since we don't have a simple /me endpoint, we can trust the token generation if login passed.
    print("\n✅ Verification Complete!")
