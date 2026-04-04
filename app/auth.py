import os
from dataclasses import dataclass
from typing import Literal, Optional
import logging

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))


Role = Literal["user", "admin", "partner", "affiliate", "sales","guest"]


_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    tenant_id: str
    role: Role

    @property
    def namespace(self) -> str:
        return f"{self.role}"



def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.error(f"Missing env var: {name}")
        raise HTTPException(
            status_code=500,
            detail="Authentication configuration error"
        )
    return value




def _get_claim(payload: dict, claim_name: str) -> Optional[str]:
    try:
        value = payload.get(claim_name)
        print(f"Extracted claim {claim_name}: {value}")
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)

    except Exception:
        logger.warning(f"Failed reading claim: {claim_name}")
        return None






def _decode_jwt(token: str) -> dict:

    secret = os.getenv("JWT_SECRET", "dev-secret-change-me").strip()
    
    algorithms = [os.getenv("JWT_ALGORITHM", "HS256")]
    options = {"verify_signature": True}
    issuer = os.getenv("JWT_ISSUER") or None
    audience = os.getenv("JWT_AUDIENCE") or None

    try:
        logger.info(f"🔑 Attempting to decode JWT token with algorithm: {algorithms[0]}")
        return jwt.decode(
            token,
            secret,
            algorithms=algorithms,
            issuer=issuer,
            audience=audience,
            options=options,
        )

    except jwt.ExpiredSignatureError:
        logger.warning("⏰ JWT token expired")
        raise HTTPException(status_code=401, detail="Token expired - please login again")

    except jwt.InvalidTokenError as e:
        logger.warning(f"❌ Invalid JWT token: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"🔴 JWT decode failed: {str(e)}")
        logger.error(f"   Token starts with: {token[:20]}...")
        logger.error(f"   Secret length: {len(secret)}")
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )


def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthContext:
    # Development mode: bypass all auth checks
    if os.getenv("DEV_AUTH_BYPASS", "false").lower() == "true":
        logger.warning("⚠️  DEV AUTH BYPASS ENABLED - DISABLE IN PRODUCTION!")
        return AuthContext(
            user_id=os.getenv("DEV_USER_ID", "dev_user"),
            tenant_id=os.getenv("DEV_TENANT_ID", "dev_tenant"),
            role=os.getenv("DEV_ROLE", "admin"),  # type: ignore
        )

    # Allow guest access if no credentials provided
    if credentials is None or not (credentials.credentials or "").strip():
        logger.info("👤 No credentials provided - using guest access")
        return AuthContext(
            user_id="guest",
            tenant_id=os.getenv("GUEST_TENANT_ID", "public"),
            role="guest",  # type: ignore
        )

    # Validate bearer scheme
    if (credentials.scheme or "").lower() != "bearer":
        logger.error(f"❌ Invalid scheme: {credentials.scheme} (expected 'Bearer')")
        raise HTTPException(status_code=401, detail="Invalid Authorization scheme - use 'Bearer TOKEN'")

    try:
        token = credentials.credentials.strip()
        logger.info(f"🔐 Received token, length: {len(token)}")
        payload = _decode_jwt(token)

        user_claim = os.getenv("JWT_USER_CLAIM", "user_id")
        tenant_claim = os.getenv("JWT_TENANT_CLAIM", "tenant_id")
        role_claim = os.getenv("JWT_ROLE_CLAIM", "role")

        user_id = _get_claim(payload, user_claim)
        tenant_id = _get_claim(payload, tenant_claim)
        role_raw = _get_claim(payload, role_claim)

        logger.info(f"📋 Decoded JWT claims: user_id={user_id}, tenant_id={tenant_id}, role={role_raw}")

        if not user_id:
            logger.warning(f"⚠️  Missing claim: {user_claim}")
            # Fallback to guest if claim missing
            if os.getenv("DEV_MODE", "false").lower() == "true":
                return AuthContext(
                    user_id="guest",
                    tenant_id=os.getenv("GUEST_TENANT_ID", "public"),
                    role="guest",  # type: ignore
                )
            raise HTTPException(status_code=401, detail=f"Missing claim: {user_claim}")
            
        if not tenant_id:
            logger.warning(f"⚠️  Missing claim: {tenant_claim}")
            tenant_id = os.getenv("GUEST_TENANT_ID", "public")
            
        if not role_raw:
            logger.warning(f"⚠️  Missing claim: {role_claim}")
            role_raw = "guest"

        role_raw = role_raw.lower()
        allowed_roles: set[str] = {"user", "admin", "partner", "affiliate", "sales", "guest"}
        if role_raw not in allowed_roles:
            logger.warning(f"⚠️  Role not allowed: {role_raw}")
            role_raw = "guest"  # Fallback to guest role

        logger.info(f"✅ User authenticated successfully: user_id={user_id}, role={role_raw}")
        return AuthContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role_raw,  # type: ignore[arg-type]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🔴 Authentication error: {str(e)}")
        # Fallback to guest access on any error in dev mode
        if os.getenv("DEV_MODE", "false").lower() == "true":
            logger.info("⚠️  Falling back to guest access due to auth error")
            return AuthContext(
                user_id="guest",
                tenant_id=os.getenv("GUEST_TENANT_ID", "public"),
                role="guest",  # type: ignore
            )
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")



