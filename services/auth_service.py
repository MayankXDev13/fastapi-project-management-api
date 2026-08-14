from datetime import datetime, timedelta, timezone
import sys

from fastapi import HTTPException, status
from sqlmodel import Session, select

from models import User, VerificationToken, VerificationTokenType
from persistence import (
    first_or_raise,
    flush_add,
    get_or_404,
    save,
    transaction,
)
from services.emailer import Mailer, resend_mailer
from utils.auth import (
    create_access_token,
    generate_raw_token,
    hash_token,
    hash_password,
    verify_password,
)


def _create_verification_token(
    user_id: str,
    token_type: VerificationTokenType,
    db: Session,
    expires_in: timedelta | None = None,
) -> str:
    if expires_in is None:
        if token_type == VerificationTokenType.email_verification:
            expires_in = timedelta(hours=24)
        elif token_type == VerificationTokenType.password_reset:
            expires_in = timedelta(hours=1)
        elif token_type == VerificationTokenType.refresh_token:
            expires_in = timedelta(days=7)

    raw_token = generate_raw_token()
    token = VerificationToken(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        type=token_type,
        expires_at=datetime.now(timezone.utc) + expires_in,
    )
    db.add(token)
    return raw_token


def _deliver_mail(
    mailer: Mailer, to: str, token_type: VerificationTokenType, raw_token: str
) -> None:
    """Email is best-effort: the user and their token are already committed
    before this runs, so a delivery failure must not 500 the request."""
    try:
        mailer(to=to, token_type=token_type, raw_token=raw_token)
    except Exception as exc:  # noqa: BLE001 - delivery must never break the request
        print(f"[EMAIL ERROR] to={to}, type={token_type.value}: {exc}", file=sys.stderr)


def register_user(
    email: str,
    password: str,
    db: Session,
    *,
    mailer: Mailer = resend_mailer,
) -> User:
    existing = db.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    with transaction(db):
        user = flush_add(db, User(email=email, hash_password=hash_password(password)))
        raw_token = _create_verification_token(
            user.id, VerificationTokenType.email_verification, db
        )

    _deliver_mail(
        mailer,
        to=email,
        token_type=VerificationTokenType.email_verification,
        raw_token=raw_token,
    )

    return user


def login_user(email: str, password: str, db: Session) -> dict:
    user = db.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(password, user.hash_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token({"sub": user.id})
    with transaction(db):
        refresh_token_str = _create_verification_token(
            user.id, VerificationTokenType.refresh_token, db
        )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_str,
        "token_type": "bearer",
    }


def refresh_token(refresh_token_str: str, db: Session) -> dict:
    stored_token = first_or_raise(
        db,
        select(VerificationToken).where(
            VerificationToken.token_hash == hash_token(refresh_token_str),
            VerificationToken.type == VerificationTokenType.refresh_token,
            VerificationToken.used_at.is_(None),
            VerificationToken.expires_at > datetime.now(timezone.utc),
        ),
        HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ),
    )

    user = first_or_raise(
        db,
        select(User).where(User.id == stored_token.user_id),
        HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        ),
    )

    with transaction(db):
        stored_token.used_at = datetime.now(timezone.utc)
        new_access_token = create_access_token({"sub": user.id})
        new_refresh_token_str = _create_verification_token(
            user.id, VerificationTokenType.refresh_token, db
        )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token_str,
        "token_type": "bearer",
    }


def logout_user(refresh_token_str: str, db: Session) -> None:
    stored_token = db.exec(
        select(VerificationToken).where(
            VerificationToken.token_hash == hash_token(refresh_token_str),
            VerificationToken.type == VerificationTokenType.refresh_token,
            VerificationToken.used_at.is_(None),
        )
    ).first()

    if stored_token:
        stored_token.used_at = datetime.now(timezone.utc)
        db.commit()


def verify_email(token_str: str, db: Session) -> None:
    stored_token = first_or_raise(
        db,
        select(VerificationToken).where(
            VerificationToken.token_hash == hash_token(token_str),
            VerificationToken.type == VerificationTokenType.email_verification,
            VerificationToken.used_at.is_(None),
            VerificationToken.expires_at > datetime.now(timezone.utc),
        ),
        HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        ),
    )

    user = get_or_404(db, User, stored_token.user_id)
    with transaction(db):
        user.is_email_verified = True
        stored_token.used_at = datetime.now(timezone.utc)


def forgot_password(
    email: str,
    db: Session,
    *,
    mailer: Mailer = resend_mailer,
) -> None:
    user = db.exec(select(User).where(User.email == email)).first()
    if not user:
        return

    with transaction(db):
        raw_token = _create_verification_token(
            user.id, VerificationTokenType.password_reset, db
        )

    _deliver_mail(
        mailer,
        to=email,
        token_type=VerificationTokenType.password_reset,
        raw_token=raw_token,
    )


def reset_password(token_str: str, new_password: str, db: Session) -> None:
    stored_token = first_or_raise(
        db,
        select(VerificationToken).where(
            VerificationToken.token_hash == hash_token(token_str),
            VerificationToken.type == VerificationTokenType.password_reset,
            VerificationToken.used_at.is_(None),
            VerificationToken.expires_at > datetime.now(timezone.utc),
        ),
        HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        ),
    )

    user = get_or_404(db, User, stored_token.user_id)
    with transaction(db):
        user.hash_password = hash_password(new_password)
        stored_token.used_at = datetime.now(timezone.utc)


def update_user_profile(user_id: str, update_data: dict, db: Session) -> User:
    user = get_or_404(db, User, user_id)

    allowed_fields = {"email"}
    for field, value in update_data.items():
        if field in allowed_fields:
            setattr(user, field, value)

    return save(db, user)


def change_password(
    user_id: str, old_password: str, new_password: str, db: Session
) -> None:
    user = get_or_404(db, User, user_id)

    if not verify_password(old_password, user.hash_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )

    user.hash_password = hash_password(new_password)
    save(db, user)