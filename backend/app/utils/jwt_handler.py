"""
JWT认证工具类
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# JWT配置
SECRET_KEY = settings.LOCAL_AUTH_PASSWORD or "your-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建JWT访问令牌
    
    Args:
        user_id: 用户ID
        expires_delta: 过期时间增量，默认7天
        
    Returns:
        JWT令牌字符串
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    
    to_encode = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"创建JWT令牌，用户: {user_id}, 过期时间: {expire}")
    return encoded_jwt


def verify_token(token: str) -> Optional[str]:
    """
    验证JWT令牌并返回用户ID
    
    Args:
        token: JWT令牌字符串
        
    Returns:
        用户ID，如果令牌无效则返回None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            logger.warning("JWT令牌中没有用户ID")
            return None
        return user_id
    except JWTError as e:
        logger.warning(f"JWT令牌验证失败: {e}")
        return None