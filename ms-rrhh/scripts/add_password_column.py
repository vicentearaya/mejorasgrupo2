import sys
import os
from sqlalchemy import text
# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal

def add_password_column():
    db = SessionLocal()
    try:
        print("Attempting to add 'password' column to 'employees' table...")
        # Check if column exists first to avoid error
        # Postgres specific check
        check_sql = text("SELECT column_name FROM information_schema.columns WHERE table_name='employees' AND column_name='password';")
        result = db.execute(check_sql).fetchone()
        
        if result:
            print("Column 'password' already exists.")
        else:
            alter_sql = text("ALTER TABLE employees ADD COLUMN password VARCHAR(255);")
            db.execute(alter_sql)
            db.commit()
            print("✅ Column 'password' added successfully.")
            
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_password_column()
