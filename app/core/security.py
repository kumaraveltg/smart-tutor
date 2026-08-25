from shutil import move

from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
new_hash = pwd_context.hash("admin@123")
print(new_hash)

def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)

#TODO: move SECRET_KEY to an environment variable before deploying —
# never leave a real secret hardcoded in source.
SECRET_KEY = "smarttutor-secret-key"  # TODO: move to env var
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
 
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") 
 
 
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
 
 
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
 
 
def decode_access_token(token: str) -> dict:
    # Raises jose.JWTError if invalid/expired — caught by the caller (deps.py)
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
 