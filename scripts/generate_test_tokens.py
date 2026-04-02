import os
import jwt
from dotenv import load_dotenv

load_dotenv()

def generate_test_token(role: str, user_id: str = "test_user_id", tenant_id: str = "test_tenant_id"):
    secret = os.getenv("JWT_SECRET", "dev-secret-change-me").strip()
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    user_claim = os.getenv("JWT_USER_CLAIM", "user_id")
    tenant_claim = os.getenv("JWT_TENANT_CLAIM", "tenant_id")
    role_claim = os.getenv("JWT_ROLE_CLAIM", "role")

    payload = {
        user_claim: user_id,
        tenant_claim: tenant_id,
        role_claim: role,
        "exp": 1742031230 + (3600 * 24 * 365) # Valid for 1 year
    }

    token = jwt.encode(payload, secret, algorithm=algorithm)
    return token

if __name__ == "__main__":
    print(generate_test_token("partner"))
