from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg2://lux:luxpass@localhost:5432/erp')

# Configurar engine con UTF-8 garantizado
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    connect_args={
        'connect_timeout': 10,
        'options': '-c client_encoding=utf8'
    },
    echo=False
)

# Event listener para garantizar encoding en cada conexión
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("SET client_encoding to UTF8")
        cursor.close()
    except Exception as e:
        # Fallar silenciosamente - la opción de conexión ya debería garantizar UTF8
        pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
