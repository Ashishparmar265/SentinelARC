import secrets
from src.database import SessionLocal, UserSession

def create_session(user_id: int) -> str:
    db = SessionLocal()
    token = secrets.token_hex(32)
    session = UserSession(user_id=user_id, token=token)
    db.add(session)
    db.commit()
    db.close()
    return token

def verify_session(token: str):
    db = SessionLocal()
    session = db.query(UserSession).filter(UserSession.token == token).first()
    if session:
        user_info = {"id": session.user.id, "username": session.user.username}
        db.close()
        return user_info
    db.close()
    return None

def delete_session(token: str):
    db = SessionLocal()
    session = db.query(UserSession).filter(UserSession.token == token).first()
    if session:
        db.delete(session)
        db.commit()
    db.close()
