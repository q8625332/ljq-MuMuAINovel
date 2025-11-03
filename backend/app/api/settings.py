"""
设置管理 API
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, List
from pathlib import Path
import httpx

from app.database import get_db
from app.models.settings import Settings
from app.schemas.settings import SettingsCreate, SettingsUpdate, SettingsResponse
from app.user_manager import User
from app.logger import get_logger
from app.config import settings as app_settings, PROJECT_ROOT
from app.services.ai_service import AIService, create_user_ai_service

logger = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["设置管理"])


def read_env_defaults() -> Dict[str, Any]:
    """从.env文件读取默认配置（仅读取，不修改）- 优先使用有效的API密钥"""
    # 优先查找有效的API密钥和对应的配置
    api_provider = app_settings.default_ai_provider
    api_key = ""
    api_base_url = ""
    
    # 按优先级查找有效的API配置
    if app_settings.openai_api_key and app_settings.openai_api_key != "your_openai_api_key_here":
        api_provider = "openai"
        api_key = app_settings.openai_api_key
        api_base_url = app_settings.openai_base_url or ""
    elif app_settings.gemini_api_key and app_settings.gemini_api_key != "your_gemini_api_key_here":
        api_provider = "openai"  # Gemini使用OpenAI兼容接口
        api_key = app_settings.gemini_api_key
        api_base_url = app_settings.gemini_base_url or ""
    elif app_settings.anthropic_api_key and app_settings.anthropic_api_key != "your_anthropic_api_key_here":
        api_provider = "anthropic"
        api_key = app_settings.anthropic_api_key
        api_base_url = app_settings.anthropic_base_url or ""
    
    return {
        "api_provider": api_provider,
        "api_key": api_key,
        "api_base_url": api_base_url,
        "model_name": app_settings.default_model,
        "temperature": app_settings.default_temperature,
        "max_tokens": app_settings.default_max_tokens,
    }


def require_login(request: Request):
    """依赖：要求用户已登录"""
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="需要登录")
    return request.state.user


async def get_user_ai_service(
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
) -> AIService:
    """
    依赖：获取当前用户的AI服务实例
    优先级：api_configs默认配置 > settings配置 > .env配置
    """
    from app.models.api_config import ApiConfig
    
    # 1. 优先查找 api_configs 中的默认配置
    api_config_result = await db.execute(
        select(ApiConfig).where(
            ApiConfig.user_id == user.user_id,
            ApiConfig.is_default == True
        )
    )
    api_config = api_config_result.scalar_one_or_none()
    
    if api_config:
        # 验证API密钥是否有效
        if not api_config.api_key or api_config.api_key.startswith("your_"):
            logger.error(f"用户 {user.user_id} 的默认API配置 '{api_config.name}' 包含无效的API密钥")
            raise HTTPException(
                status_code=400,
                detail=f"API配置 '{api_config.name}' 的密钥无效，请在设置中配置有效的API密钥"
            )
        
        logger.info(f"✅ 用户 {user.user_id} 使用API配置: {api_config.name} ({api_config.api_provider})")
        return create_user_ai_service(
            api_provider=api_config.api_provider,
            api_key=api_config.api_key,
            api_base_url=api_config.api_base_url or "",
            model_name=api_config.model_name,
            temperature=api_config.temperature,
            max_tokens=api_config.max_tokens
        )
    
    # 2. 如果没有API配置，查找 settings 配置
    settings_result = await db.execute(
        select(Settings).where(Settings.user_id == user.user_id)
    )
    settings = settings_result.scalar_one_or_none()
    
    if settings:
        # 验证API密钥是否有效
        if not settings.api_key or settings.api_key.startswith("your_"):
            logger.error(f"用户 {user.user_id} 的Settings配置包含无效的API密钥")
            raise HTTPException(
                status_code=400,
                detail="Settings中的API密钥无效，请在设置中配置有效的API密钥"
            )
        
        logger.info(f"✅ 用户 {user.user_id} 使用Settings配置 ({settings.api_provider})")
        return create_user_ai_service(
            api_provider=settings.api_provider,
            api_key=settings.api_key,
            api_base_url=settings.api_base_url or "",
            model_name=settings.model_name,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens
        )
    
    # 3. 如果都没有，从.env读取
    logger.info(f"用户 {user.user_id} 首次使用，从.env读取配置")
    env_defaults = read_env_defaults()
    
    # 验证.env中的配置是否有效
    if not env_defaults.get("api_key") or env_defaults["api_key"].startswith("your_"):
        logger.error(f"用户 {user.user_id} 没有有效的API配置")
        raise HTTPException(
            status_code=400,
            detail="未找到有效的API配置。请在前端「API配置」页面添加并设置默认配置，或在.env文件中配置有效的API密钥"
        )
    
    # 保存到settings
    settings = Settings(
        user_id=user.user_id,
        **env_defaults
    )
    db.add(settings)
    await db.commit()
    await db.refresh(settings)
    
    logger.info(f"✅ 用户 {user.user_id} 使用.env配置 ({settings.api_provider})")
    return create_user_ai_service(
        api_provider=settings.api_provider,
        api_key=settings.api_key,
        api_base_url=settings.api_base_url or "",
        model_name=settings.model_name,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens
    )


@router.get("", response_model=SettingsResponse)
async def get_settings(
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户的设置
    如果用户没有保存过设置，自动从.env创建并保存到数据库
    """
    result = await db.execute(
        select(Settings).where(Settings.user_id == user.user_id)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        # 如果用户没有保存过设置，从.env读取默认配置并保存到数据库
        env_defaults = read_env_defaults()
        logger.info(f"用户 {user.user_id} 首次获取设置，自动从.env同步到数据库")
        
        # 创建新设置并保存到数据库
        settings = Settings(
            user_id=user.user_id,
            **env_defaults
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        logger.info(f"用户 {user.user_id} 的设置已从.env同步到数据库")
    
    logger.info(f"用户 {user.user_id} 获取已保存的设置")
    return settings


@router.post("", response_model=SettingsResponse)
async def save_settings(
    data: SettingsCreate,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    创建或更新当前用户的设置（Upsert）
    如果设置已存在则更新，否则创建新设置
    仅保存到数据库
    """
    # 查找现有设置
    result = await db.execute(
        select(Settings).where(Settings.user_id == user.user_id)
    )
    settings = result.scalar_one_or_none()
    
    # 准备数据
    settings_dict = data.model_dump(exclude_unset=True)
    
    if settings:
        # 更新现有设置
        for key, value in settings_dict.items():
            setattr(settings, key, value)
        
        await db.commit()
        await db.refresh(settings)
        logger.info(f"用户 {user.user_id} 更新设置")
    else:
        # 创建新设置
        settings = Settings(
            user_id=user.user_id,
            **settings_dict
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        logger.info(f"用户 {user.user_id} 创建设置")
    
    return settings


@router.put("", response_model=SettingsResponse)
async def update_settings(
    data: SettingsUpdate,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    更新当前用户的设置
    仅保存到数据库
    """
    result = await db.execute(
        select(Settings).where(Settings.user_id == user.user_id)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        raise HTTPException(status_code=404, detail="设置不存在，请先创建设置")
    
    # 更新设置
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(settings, key, value)
    
    await db.commit()
    await db.refresh(settings)
    logger.info(f"用户 {user.user_id} 更新设置")
    
    return settings


@router.delete("")
async def delete_settings(
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    删除当前用户的设置
    """
    result = await db.execute(
        select(Settings).where(Settings.user_id == user.user_id)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        raise HTTPException(status_code=404, detail="设置不存在")
    
    await db.delete(settings)
    await db.commit()
    logger.info(f"用户 {user.user_id} 删除设置")
    
    return {"message": "设置已删除", "user_id": user.user_id}


@router.get("/models")
async def get_available_models(
    api_key: str,
    api_base_url: str,
    provider: str = "openai"
):
    """
    从配置的 API 获取可用的模型列表
    
    Args:
        api_key: API 密钥
        api_base_url: API 基础 URL
        provider: API 提供商 (openai, anthropic, azure, custom)
    
    Returns:
        模型列表
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "openai" or provider == "azure" or provider == "custom":
                # OpenAI 兼容接口获取模型列表
                url = f"{api_base_url.rstrip('/')}/models"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                logger.info(f"正在从 {url} 获取模型列表")
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                models = []
                
                if "data" in data and isinstance(data["data"], list):
                    for model in data["data"]:
                        model_id = model.get("id", "")
                        # 过滤出常用的文本生成模型
                        if any(keyword in model_id.lower() for keyword in [
                            "gpt", "gemini", "claude", "llama", "mistral", "qwen", "deepseek"
                        ]):
                            models.append({
                                "value": model_id,
                                "label": model_id,
                                "description": model.get("description", "") or f"Created: {model.get('created', 'N/A')}"
                            })
                
                if not models:
                    raise HTTPException(
                        status_code=404,
                        detail="未能从 API 获取到可用的模型列表"
                    )
                
                logger.info(f"成功获取 {len(models)} 个模型")
                return {
                    "provider": provider,
                    "models": models,
                    "count": len(models)
                }
                
            elif provider == "anthropic":
                # Anthropic 没有公开的模型列表API
                raise HTTPException(
                    status_code=400,
                    detail="Anthropic 不支持自动获取模型列表，请手动输入模型名称"
                )
            
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的提供商: {provider}"
                )
            
    except httpx.HTTPStatusError as e:
        logger.error(f"获取模型列表失败 (HTTP {e.response.status_code}): {e.response.text}")
        raise HTTPException(
            status_code=400,
            detail=f"无法从 API 获取模型列表 (HTTP {e.response.status_code})"
        )
    except httpx.RequestError as e:
        logger.error(f"请求模型列表失败: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"无法连接到 API: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型列表时发生错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取模型列表失败: {str(e)}"
        )