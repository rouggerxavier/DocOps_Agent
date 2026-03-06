"""Rotas de autenticação: /api/auth/register, /api/auth/login, /api/auth/me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from docops.api.schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
)
from docops.auth.dependencies import get_current_user
from docops.auth.security import (
    create_access_token,
    hash_password,
    normalize_email,
    verify_password,
)
from docops.db.crud import create_user, get_user_by_email
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger

logger = get_logger("docops.api.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """Cadastra novo usuário. E-mail deve ser único."""
    email = normalize_email(str(body.email))

    if get_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail já cadastrado.",
        )

    user = create_user(
        db,
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
    )
    logger.info(f"Novo usuário cadastrado: id={user.id} email={email!r}")
    return RegisterResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        created_at=user.created_at,
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Autentica usuário e retorna access token JWT."""
    email = normalize_email(str(body.email))
    user = get_user_by_email(db, email)

    # Erro genérico — não revela se o e-mail existe
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
        )

    token = create_access_token(user.id)
    return LoginResponse(access_token=token, token_type="bearer")


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    """Retorna dados do usuário autenticado."""
    return MeResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        created_at=current_user.created_at,
    )
