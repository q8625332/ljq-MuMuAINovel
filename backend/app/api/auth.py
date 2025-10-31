"""
认证 API - LinuxDO OAuth2 登录 + 本地账户登录 + JWT支持
"""
from fastapi import APIRouter, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional
import hashlib
from app.services.oauth_service import LinuxDOOAuthService
from app.user_manager import user_manager
from app.database import init_db
from app.logger import get_logger
from app.config import settings
from app.utils.jwt_handler import create_access_token

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["认证"])

# OAuth2 服务实例
oauth_service = LinuxDOOAuthService()

# State 临时存储（生产环境应使用 Redis）
_state_storage = {}


class AuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class LocalLoginRequest(BaseModel):
    """本地登录请求"""
    username: str
    password: str


class LocalLoginResponse(BaseModel):
    """本地登录响应"""
    success: bool
    message: str
    user: Optional[dict] = None
    access_token: str
    token_type: str = "bearer"


@router.get("/config")
async def get_auth_config():
    """获取认证配置信息"""
    return {
        "local_auth_enabled": settings.LOCAL_AUTH_ENABLED,
        "linuxdo_enabled": bool(settings.LINUXDO_CLIENT_ID and settings.LINUXDO_CLIENT_SECRET)
    }


@router.post("/local/login", response_model=LocalLoginResponse)
async def local_login(request: LocalLoginRequest, response: Response):
    """本地账户登录"""
    # 检查是否启用本地登录
    if not settings.LOCAL_AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="本地账户登录未启用")
    
    # 检查是否配置了本地账户
    if not settings.LOCAL_AUTH_USERNAME or not settings.LOCAL_AUTH_PASSWORD:
        raise HTTPException(status_code=500, detail="本地账户未配置")
    
    # 验证用户名和密码
    if request.username != settings.LOCAL_AUTH_USERNAME or request.password != settings.LOCAL_AUTH_PASSWORD:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # 生成本地用户ID（使用用户名的hash）
    user_id = f"local_{hashlib.md5(request.username.encode()).hexdigest()[:16]}"
    
    # 创建或更新本地用户
    user = await user_manager.create_or_update_from_linuxdo(
        linuxdo_id=user_id,
        username=request.username,
        display_name=settings.LOCAL_AUTH_DISPLAY_NAME,
        avatar_url=None,
        trust_level=9  # 本地用户给予高信任级别
    )
    
    # 初始化用户数据库
    try:
        await init_db(user.user_id)
        logger.info(f"本地用户 {user.user_id} 数据库初始化成功")
    except Exception as e:
        logger.error(f"本地用户 {user.user_id} 数据库初始化失败: {e}")
    
    # 生成JWT令牌
    access_token = create_access_token(user.user_id)
    
    # 同时设置Cookie（向后兼容）
    response.set_cookie(
        key="user_id",
        value=user.user_id,
        path="/",
        max_age=7 * 24 * 60 * 60,  # 7天
        httponly=True,
        secure=False,
        samesite="lax",
        domain=None
    )
    
    logger.info(f"本地用户 {user.user_id} 登录成功，已生成JWT令牌")
    
    return LocalLoginResponse(
        success=True,
        message="登录成功",
        user=user.dict(),
        access_token=access_token,
        token_type="bearer"
    )


@router.get("/linuxdo/url", response_model=AuthUrlResponse)
async def get_linuxdo_auth_url():
    """获取 LinuxDO 授权 URL"""
    state = oauth_service.generate_state()
    auth_url = oauth_service.get_authorization_url(state)
    
    # 临时存储 state（5分钟有效）
    _state_storage[state] = True
    
    return AuthUrlResponse(auth_url=auth_url, state=state)


async def _handle_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    response: Response = None
):
    """
    LinuxDO OAuth2 回调处理
    
    成功后重定向到前端首页，并设置 user_id Cookie
    """
    # 检查是否有错误
    if error:
        raise HTTPException(status_code=400, detail=f"授权失败: {error}")
    
    # 检查必需参数
    if not code or not state:
        raise HTTPException(status_code=400, detail="缺少 code 或 state 参数")
    
    # 验证 state（防止 CSRF）
    if state not in _state_storage:
        raise HTTPException(status_code=400, detail="无效的 state 参数")
    
    # 删除已使用的 state
    del _state_storage[state]
    
    # 1. 使用 code 获取 access_token
    token_data = await oauth_service.get_access_token(code)
    if not token_data or "access_token" not in token_data:
        raise HTTPException(status_code=400, detail="获取访问令牌失败")
    
    access_token = token_data["access_token"]
    
    # 2. 使用 access_token 获取用户信息
    user_info = await oauth_service.get_user_info(access_token)
    if not user_info:
        raise HTTPException(status_code=400, detail="获取用户信息失败")
    
    # 3. 创建或更新用户
    linuxdo_id = str(user_info.get("id"))
    username = user_info.get("username", "")
    display_name = user_info.get("name", username)
    avatar_url = user_info.get("avatar_url")
    trust_level = user_info.get("trust_level", 0)
    
    user = await user_manager.create_or_update_from_linuxdo(
        linuxdo_id=linuxdo_id,
        username=username,
        display_name=display_name,
        avatar_url=avatar_url,
        trust_level=trust_level
    )
    
    # 3.5. 初始化用户数据库（如果是新用户）
    try:
        await init_db(user.user_id)
        logger.info(f"用户 {user.user_id} 数据库初始化成功")
    except Exception as e:
        logger.error(f"用户 {user.user_id} 数据库初始化失败: {e}")
        # 继续执行，不影响登录流程（可能是已存在的用户）
    
    # 4. 设置 Cookie 并重定向到前端回调页面
    # 使用配置的前端URL，支持不同的部署环境
    frontend_url = settings.FRONTEND_URL.rstrip('/')
    redirect_url = f"{frontend_url}/auth/callback"
    logger.info(f"OAuth回调成功，重定向到前端: {redirect_url}")
    redirect_response = RedirectResponse(url=redirect_url)
    
    # 设置 httponly Cookie（7天有效）
    # 注意：在生产环境中，如果使用 HTTP（非 HTTPS），必须设置 secure=False
    # 如果使用反向代理或多 IP 环境，应该设置 domain 参数
    redirect_response.set_cookie(
        key="user_id",
        value=user.user_id,
        path="/",  # 确保 Cookie 在整个应用中有效
        max_age=7 * 24 * 60 * 60,  # 7天
        httponly=True,
        secure=False,  # 🔧 修复：HTTP 环境下必须为 False
        samesite="lax",
        domain=None  # 🔧 修复：设置为 None 自动适配当前域名
    )
    
    return redirect_response


@router.get("/linuxdo/callback")
async def linuxdo_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    response: Response = None
):
    """LinuxDO OAuth2 回调处理（标准路径）"""
    return await _handle_callback(code, state, error, response)


@router.get("/callback")
async def callback_alias(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    response: Response = None
):
    """LinuxDO OAuth2 回调处理（兼容路径）"""
    return await _handle_callback(code, state, error, response)


@router.post("/logout")
async def logout(response: Response):
    """退出登录"""
    response.delete_cookie("user_id", path="/")  # 删除时也要指定 path
    return {"message": "退出登录成功"}


@router.get("/user")
async def get_current_user(request: Request):
    """获取当前登录用户信息"""
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="未登录")
    
    return request.state.user.dict()