import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "karavali-secret-key-default-2026")
    
    # Retrieve DATABASE_URL
    database_url = os.getenv("DATABASE_URL", "").strip()
    
    # SQLAlchemy requires 'postgresql://' instead of 'postgres://'
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        
    # Fallback to local SQLite if DATABASE_URL is not configured
    if not database_url:
        basedir = os.path.abspath(os.path.dirname(__file__))
        database_url = f"sqlite:///{os.path.join(basedir, 'karavali_complex.db')}"
        
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
