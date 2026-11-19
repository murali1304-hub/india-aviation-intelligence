from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserOut
from app.services.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    taken = db.query(User).filter(
        or_(User.username == data.username, User.email == data.email.lower())
    ).first()
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already registered")
    user = User(
        username=data.username,
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Username or email + password (form-encoded, works with Swagger 'Authorize')."""
    user = db.query(User).filter(
        or_(User.username == form.username, User.email == form.username.lower())
    ).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return Token(access_token=create_access_token(user.username))


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current
