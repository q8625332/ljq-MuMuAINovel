"""
认证中间件 - 支持JWT和Cookie两种认证方式
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.user_manager import user_manager
from app.utils.jwt_handler import verify_token
from app.logger import get_logger

logger = get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件 - 支持JWT和Cookie"""
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求，支持从Authorization头（JWT）或Cookie中提取用户信息
        优先使用JWT，如果没有JWT则尝试Cookie
        """
        user_id = None
        
        # 1. 优先尝试从Authorization头获取JWT令牌
        auth_header = request.headers.get("Authorization")
        if auth_header:
            logger.info(f"收到Authorization头: {auth_header[:20]}...")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")
                user_id = verify_token(token)
                if user_id:
                    logger.info(f"✅ 通过JWT验证用户: {user_id}")
                else:
                    logger.warning(f"❌ JWT令牌验证失败")
            else:
                logger.warning(f"❌ Authorization头格式错误，不是Bearer令牌")
        else:
            logger.debug(f"请求 {request.url.path} 没有Authorization头")
        
        # 2. 如果JWT验证失败，尝试从Cookie获取
        if not user_id:
            user_id = request.cookies.get("user_id")
            if user_id:
                logger.info(f"✅ 通过Cookie验证用户: {user_id}")
        
        # 3. 注入用户信息到 request.state
        if user_id:
            user = await user_manager.get_user(user_id)
            if user:
                request.state.user_id = user_id
                request.state.user = user
                request.state.is_admin = user.is_admin
            else:
                # 用户不存在，清除状态
                request.state.user_id = None
                request.state.user = None
                request.state.is_admin = False
        else:
            # 未登录
            request.state.user_id = None
            request.state.user = None
            request.state.is_admin = False
        
        # 继续处理请求
        response = await call_next(request)
        return response