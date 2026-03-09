import hmac
import hashlib
import json
from urllib.parse import parse_qs, unquote
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.user import User


class AuthService:
    """Service for Telegram authentication and JWT management."""
    
    @staticmethod
    def validate_telegram_init_data(init_data: str) -> Optional[Dict[str, Any]]:
        """
        Validate Telegram WebApp initData signature.
        Returns parsed user data if valid, None otherwise.
        """
        try:
            parsed = parse_qs(init_data)
            
            # Extract hash
            received_hash = parsed.get("hash", [None])[0]
            if not received_hash:
                return None
            
            # Build data-check-string (sorted alphabetically, excluding hash)
            data_check_parts = []
            for key in sorted(parsed.keys()):
                if key != "hash":
                    value = parsed[key][0]
                    data_check_parts.append(f"{key}={value}")
            
            data_check_string = "\n".join(data_check_parts)
            
            # Create secret key
            secret_key = hmac.new(
                b"WebAppData",
                settings.TELEGRAM_BOT_TOKEN.encode(),
                hashlib.sha256
            ).digest()
            
            # Calculate hash
            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Compare hashes
            if not hmac.compare_digest(calculated_hash, received_hash):
                return None
            
            # Parse user data
            user_data_str = parsed.get("user", [None])[0]
            if not user_data_str:
                return None
            
            user_data = json.loads(unquote(user_data_str))
            return user_data
            
        except Exception:
            return None
    
    @staticmethod
    def create_access_token(user_id: int, telegram_user_id: int) -> str:
        """Create JWT access token."""
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        payload = {
            "sub": str(user_id),
            "telegram_user_id": telegram_user_id,
            "exp": expire,
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    @staticmethod
    def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate JWT token."""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            return payload
        except Exception:
            return None
    
    async def get_or_create_user(self, db: AsyncSession, telegram_user_id: int) -> User:
        """Get existing user or create new one."""
        result = await db.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(telegram_user_id=telegram_user_id)
            db.add(user)
            await db.commit()
            await db.refresh(user)
        
        return user
    
    async def complete_onboarding(self, db: AsyncSession, user_id: int) -> User:
        """Mark user onboarding as completed."""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user:
            user.onboarding_completed = True
            await db.commit()
            await db.refresh(user)
        
        return user


auth_service = AuthService()
