from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..main import get_db, User

router = APIRouter(prefix="/api/users", tags=["users"])


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: Optional[bool] = True


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int

    class Config:
        orm_mode = True


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    db_user = User(email=user_in.email, full_name=user_in.full_name, is_active=user_in.is_active)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/", response_model=List[UserResponse])
def list_users(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    rows = db.query(User).limit(limit).offset(offset).all()
    return rows
