"""
用户管理 API
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.user_manager import user_manager, User
from app.logger import get_logger

router = APIRouter(prefix="/users", tags=["用户管理"])
logger = get_logger(__name__)


def require_login(request: Request):
    """依赖：要求用户已登录"""
    # 详细日志记录
    logger.info(f"🔍 require_login 检查 - URL: {request.url.path}")
    logger.info(f"  - hasattr(request.state, 'user'): {hasattr(request.state, 'user')}")
    if hasattr(request.state, "user"):
        logger.info(f"  - request.state.user: {request.state.user}")
    if hasattr(request.state, "user_id"):
        logger.info(f"  - request.state.user_id: {request.state.user_id if hasattr(request.state, 'user_id') else 'None'}")
    
    # 检查请求头
    auth_header = request.headers.get("Authorization")
    logger.info(f"  - Authorization header: {auth_header[:30] if auth_header else 'None'}...")
    
    # 检查Cookie
    user_id_cookie = request.cookies.get("user_id")
    logger.info(f"  - user_id cookie: {user_id_cookie}")
    
    if not hasattr(request.state, "user") or not request.state.user:
        logger.warning(f"❌ 认证失败: request.state.user 不存在或为空")
        raise HTTPException(status_code=401, detail="需要登录")
    
    logger.info(f"✅ 认证成功: {request.state.user}")
    return request.state.user


def require_admin(request: Request):
    """依赖：要求用户为管理员"""
    user = require_login(request)
    if not request.state.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


class SetAdminRequest(BaseModel):
    user_id: str
    is_admin: bool


@router.get("/current")
async def get_current_user(user: User = Depends(require_login)):
    """获取当前登录用户信息"""
    return user.dict()


@router.get("", response_model=List[dict])
async def list_users(admin_user: User = Depends(require_admin)):
    """
    获取所有用户列表（仅管理员）
    """
    users = await user_manager.get_all_users()
    return [user.dict() for user in users]


@router.post("/set-admin")
async def set_admin(
    data: SetAdminRequest,
    request: Request,
    admin_user: User = Depends(require_admin)
):
    """
    设置用户的管理员权限（仅管理员）
    
    限制：
    - 不能撤销自己的管理员权限
    - 至少保留一个管理员
    """
    # 检查是否尝试撤销自己的权限
    if data.user_id == admin_user.user_id and not data.is_admin:
        raise HTTPException(
            status_code=400,
            detail="不能撤销自己的管理员权限"
        )
    
    # 尝试设置管理员权限
    success = await user_manager.set_admin(data.user_id, data.is_admin)
    
    if not success:
        if not data.is_admin:
            raise HTTPException(
                status_code=400,
                detail="无法撤销管理员权限，至少需要保留一个管理员"
            )
        else:
            raise HTTPException(
                status_code=404,
                detail="用户不存在"
            )
    
    return {
        "message": f"已{'授予' if data.is_admin else '撤销'}管理员权限",
        "user_id": data.user_id,
        "is_admin": data.is_admin
    }


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    admin_user: User = Depends(require_admin)
):
    """
    删除用户（仅管理员）
    
    限制：
    - 不能删除管理员用户
    """
    success = await user_manager.delete_user(user_id)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="无法删除该用户（用户不存在或为管理员）"
        )
    
    return {
        "message": "用户已删除",
        "user_id": user_id
    }


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    admin_user: User = Depends(require_admin)
):
    """获取指定用户信息（仅管理员）"""
    user = await user_manager.get_user(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return user.dict()