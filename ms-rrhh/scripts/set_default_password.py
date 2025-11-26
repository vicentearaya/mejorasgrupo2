import sys
import os
# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import Employee
from app.routers.auth import get_password_hash

def set_default_password():
    db = SessionLocal()
    try:
        # Get user by email
        email = "carlos.lopez@logistica.cl"
        user = db.query(Employee).filter(Employee.email == email).first()
        if not user:
            print(f"User {email} not found.")
            return

        print(f"Found user: {user.nombre} ({user.email})")
        
        # Set password to '123456'
        hashed_password = get_password_hash("123456")
        user.password = hashed_password
        db.commit()
        
        print(f"✅ Password for '{user.email}' set to '123456'")
        print(f"Credentials:\nEmail: {user.email}\nPassword: 123456")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    set_default_password()
