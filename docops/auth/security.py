"""Hashing de senhas, criação/decodificação de JWT e normalização de e-mail."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

import bcrypt
import jwt

from docops.config import config


def hash_password(password: str) -> str:
    """Gera hash seguro da senha.

    bcrypt tem limite efetivo de 72 bytes. Para suportar senhas longas sem
    truncamento silencioso, aplicamos SHA-256 antes de usar bcrypt.
    """
    prehashed = hashlib.sha256(password.encode("utf-8")).digest()
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(prehashed, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    prehashed = hashlib.sha256(plain.encode("utf-8")).digest()
    return bcrypt.checkpw(prehashed, hashed.encode("utf-8"))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=config.jwt_expires_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, config.jwt_secret_key, algorithm=config.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Decodifica o token e retorna o user_id. Lança jwt.InvalidTokenError em caso de falha."""
    payload = jwt.decode(token, config.jwt_secret_key, algorithms=[config.jwt_algorithm])
    return int(payload["sub"])
