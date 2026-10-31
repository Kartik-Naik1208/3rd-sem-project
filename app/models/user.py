import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    """User account model for authentication and history tracking."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Scans performed by this user
    scans = db.relationship('Scan', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    # Password reset tokens for this user
    reset_tokens = db.relationship(
        'PasswordResetToken',
        backref='user',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='PasswordResetToken.created_at.desc()'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class PasswordResetToken(db.Model):
    """
    Cryptographically secure database-backed password reset token.
    Stores SHA-256 hash of raw token; enforces single use, 30-minute expiration,
    and automatic invalidation of older tokens.
    """
    __tablename__ = 'password_reset_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used = db.Column(db.Boolean, default=False, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Computes SHA-256 hash for raw token string."""
        return hashlib.sha256(raw_token.strip().encode('utf-8')).hexdigest()

    @property
    def is_expired(self) -> bool:
        """Checks if current time is past expiration timestamp."""
        if self.expires_at is None:
            return True
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp

    @property
    def is_valid(self) -> bool:
        """Returns True if token has not been used and has not expired."""
        return (not self.used) and (not self.is_expired)

    def mark_used(self):
        """Marks token as consumed and records timestamp."""
        self.used = True
        self.used_at = datetime.now(timezone.utc)

    @classmethod
    def create_for_user(cls, user, expires_in_minutes: int = 30):
        """
        Invalidates any prior active tokens for this user, generates a new
        cryptographically secure token, stores only its SHA-256 hash, and
        returns (token_record, raw_token).
        """
        now = datetime.now(timezone.utc)
        # Invalidate any existing unused reset tokens for this user
        cls.query.filter_by(user_id=user.id, used=False).update(
            {'used': True, 'used_at': now}
        )

        raw_token = secrets.token_urlsafe(32)
        token_hash = cls.hash_token(raw_token)
        expires_at = now + timedelta(minutes=expires_in_minutes)

        token_record = cls(
            user_id=user.id,
            token_hash=token_hash,
            created_at=now,
            expires_at=expires_at,
            used=False
        )
        db.session.add(token_record)
        return token_record, raw_token

    @classmethod
    def verify_token(cls, raw_token: str):
        """
        Verifies raw token against database hash, expiry, and used status.
        Returns (token_record, user) if completely valid; otherwise (None, None).
        """
        if not raw_token or not isinstance(raw_token, str):
            return None, None

        token_hash = cls.hash_token(raw_token)
        record = cls.query.filter_by(token_hash=token_hash).first()
        if not record or not record.is_valid:
            return None, None

        return record, record.user

    def __repr__(self):
        return f'<PasswordResetToken user_id={self.user_id} used={self.used}>'

