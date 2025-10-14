from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
import hashlib

SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Use more compatible bcrypt settings for Python 3.13
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__rounds=12
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Truncate password to 72 bytes if necessary
    if len(plain_password.encode('utf-8')) > 72:
        # Use SHA256 for longer passwords to fit bcrypt limit
        plain_password = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    # Truncate password to 72 bytes if necessary
    if len(password.encode('utf-8')) > 72:
        # Use SHA256 for longer passwords to fit bcrypt limit
        password = hashlib.sha256(password.encode('utf-8')).hexdigest()
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[str]:
    try:
        print(f"[DEBUG] verify_token called with token: {token[:20]}...")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"[DEBUG] JWT payload decoded successfully: {payload}")
        username: str = payload.get("sub")
        if username is None:
            print("[DEBUG] No 'sub' field in JWT payload")
            return None
        print(f"[DEBUG] Username extracted from token: {username}")
        return username
    except JWTError as e:
        print(f"[DEBUG] JWT verification failed: {str(e)}")
        return None