import os
try:
    import passlib.hash
    HAS_PASSLIB = True
except ImportError:
    HAS_PASSLIB = False
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///output/sentinelarc.db")

# Ensure the output directory exists so SQLite doesn't throw OperationalError
os.makedirs("output", exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    reports = relationship("Report", back_populates="owner", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")

    def verify_password(self, password: str) -> bool:
        # Pre-hash with SHA256 and Base64 encode to stay under bcrypt's 72-byte limit
        import hashlib, base64
        pwd_hash = hashlib.sha256(password.encode("utf-8")).digest()
        b64_pwd = base64.b64encode(pwd_hash).decode("utf-8")
        if HAS_PASSLIB:
            return passlib.hash.bcrypt.verify(b64_pwd, self.password_hash)
        return False

    @staticmethod
    def hash_password(password: str) -> str:
        # Pre-hash with SHA256 and Base64 encode to stay under bcrypt's 72-byte limit
        import hashlib, base64
        pwd_hash = hashlib.sha256(password.encode("utf-8")).digest()
        b64_pwd = base64.b64encode(pwd_hash).decode("utf-8")
        if HAS_PASSLIB:
            return passlib.hash.bcrypt.hash(b64_pwd)
        return f"mock_{b64_pwd}"

class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="sessions")

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_path = Column(String(500), nullable=False)
    query = Column(Text, nullable=False)
    file_size = Column(Integer, nullable=True, default=0)
    checksum = Column(String(64), nullable=True)
    meta_file_path = Column(String(500), nullable=True)
    format = Column(String(20), nullable=True, default="markdown")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    owner = relationship("User", back_populates="reports")

def init_db():
    Base.metadata.create_all(bind=engine)
    # Automatic migration: ensure newly added columns exist in older SQLite DB files
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(reports)"))
            cols = {row[1] for row in res.fetchall()}
            if "file_size" not in cols:
                conn.execute(text("ALTER TABLE reports ADD COLUMN file_size INTEGER DEFAULT 0"))
            if "checksum" not in cols:
                conn.execute(text("ALTER TABLE reports ADD COLUMN checksum VARCHAR(64)"))
            if "meta_file_path" not in cols:
                conn.execute(text("ALTER TABLE reports ADD COLUMN meta_file_path VARCHAR(500)"))
            if "format" not in cols:
                conn.execute(text("ALTER TABLE reports ADD COLUMN format VARCHAR(20) DEFAULT 'markdown'"))
            conn.commit()
    except Exception as e:
        print(f"[Database] Migration check: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
