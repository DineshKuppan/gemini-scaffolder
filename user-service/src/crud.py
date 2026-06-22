from sqlalchemy.orm import Session
from typing import List, Optional
from . import models, schemas
from passlib.context import CryptContext

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_user(db: Session, user_id: int, tenant_id: str) -> Optional[models.User]:
    return db.query(models.User).filter(
        models.User.id == user_id, 
        models.User.tenant_id == tenant_id
    ).first()

def get_user_by_email(db: Session, email: str, tenant_id: str) -> Optional[models.User]:
    return db.query(models.User).filter(
        models.User.email == email, 
        models.User.tenant_id == tenant_id
    ).first()

def get_users(db: Session, tenant_id: str, skip: int = 0, limit: int = 100) -> List[models.User]:
    return db.query(models.User).filter(
        models.User.tenant_id == tenant_id
    ).offset(skip).limit(limit).all()

def create_user(db: Session, user: schemas.UserCreate, tenant_id: str) -> models.User:
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        tenant_id=tenant_id,
        is_active=True,
        is_superuser=False
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate, tenant_id: str) -> Optional[models.User]:
    db_user = get_user(db, user_id=user_id, tenant_id=tenant_id)
    if not db_user:
        return None
    
    update_data = user_update.dict(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    
    for key, value in update_data.items():
        setattr(db_user, key, value)
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int, tenant_id: str) -> bool:
    db_user = get_user(db, user_id=user_id, tenant_id=tenant_id)
    if not db_user:
        return False
    db.delete(db_user)
    db.commit()
    return True

def get_user_context(db: Session, user_id: int, tenant_id: str) -> dict:
    """
    Specialized helper for FastMCP tool integration to provide rich context 
    about a user for LLM consumption.
    """
    user = get_user(db, user_id, tenant_id)
    if not user:
        return {"error": "User not found"}
    
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "tenant_id": user.tenant_id,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None
    }