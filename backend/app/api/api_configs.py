from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List
from app.database import get_db
from app.models.api_config import ApiConfig
from app.schemas.api_config import (
    ApiConfigCreate,
    ApiConfigUpdate,
    ApiConfigResponse,
    RefreshModelsRequest,
    RefreshModelsResponse
)
from app.logger import get_logger
import httpx

logger = get_logger(__name__)

router = APIRouter(prefix="/api-configs", tags=["API配置管理"])


@router.get("", response_model=List[ApiConfigResponse])
async def list_api_configs(
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的所有API配置"""
    user_id = "default_user"
    result = await db.execute(
        select(ApiConfig).where(ApiConfig.user_id == user_id)
    )
    configs = result.scalars().all()
    return configs


@router.get("/{config_id}", response_model=ApiConfigResponse)
async def get_api_config(
    config_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取指定API配置"""
    user_id = "default_user"
    result = await db.execute(
        select(ApiConfig).where(
            and_(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API配置不存在"
        )
    return config


@router.post("", response_model=ApiConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_api_config(
    config_data: ApiConfigCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新的API配置"""
    user_id = "default_user"
    
    # 检查配置名称是否已存在
    result = await db.execute(
        select(ApiConfig).where(
            and_(ApiConfig.user_id == user_id, ApiConfig.name == config_data.name)
        )
    )
    existing_config = result.scalar_one_or_none()
    if existing_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="配置名称已存在"
        )
    
    # 如果设置为默认配置，需要取消其他配置的默认状态
    if config_data.is_default:
        default_configs = (await db.execute(
            select(ApiConfig).where(
                and_(ApiConfig.user_id == user_id, ApiConfig.is_default == True)
            )
        )).scalars().all()
        
        for dc in default_configs:
            dc.is_default = False
    
    # 创建新配置
    new_config = ApiConfig(
        user_id=user_id,
        **config_data.model_dump()
    )
    db.add(new_config)
    await db.commit()
    await db.refresh(new_config)
    return new_config


@router.put("/{config_id}", response_model=ApiConfigResponse)
async def update_api_config(
    config_id: str,
    config_data: ApiConfigUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新API配置"""
    user_id = "default_user"
    
    # 获取配置
    result = await db.execute(
        select(ApiConfig).where(
            and_(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API配置不存在"
        )
    
    # 检查名称是否与其他配置冲突
    if config_data.name and config_data.name != config.name:
        result = await db.execute(
            select(ApiConfig).where(
                and_(
                    ApiConfig.user_id == user_id,
                    ApiConfig.name == config_data.name,
                    ApiConfig.id != config_id
                )
            )
        )
        existing_config = result.scalar_one_or_none()
        if existing_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="配置名称已存在"
            )
    
    # 如果设置为默认配置，需要取消其他配置的默认状态
    if config_data.is_default:
        default_configs = (await db.execute(
            select(ApiConfig).where(
                and_(
                    ApiConfig.user_id == user_id,
                    ApiConfig.is_default == True,
                    ApiConfig.id != config_id
                )
            )
        )).scalars().all()
        
        for dc in default_configs:
            dc.is_default = False
    
    # 更新配置
    update_data = config_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
    
    await db.commit()
    await db.refresh(config)
    return config


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_config(
    config_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除API配置"""
    user_id = "default_user"
    
    result = await db.execute(
        select(ApiConfig).where(
            and_(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API配置不存在"
        )
    
    await db.delete(config)
    await db.commit()


@router.post("/{config_id}/set-default", response_model=ApiConfigResponse)
async def set_default_config(
    config_id: str,
    db: AsyncSession = Depends(get_db)
):
    """设置默认API配置"""
    user_id = "default_user"
    
    # 获取配置
    result = await db.execute(
        select(ApiConfig).where(
            and_(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API配置不存在"
        )
    
    # 取消其他配置的默认状态
    default_configs = (await db.execute(
        select(ApiConfig).where(
            and_(ApiConfig.user_id == user_id, ApiConfig.is_default == True)
        )
    )).scalars().all()
    
    for dc in default_configs:
        dc.is_default = False
    
    # 设置当前配置为默认
    config.is_default = True
    await db.commit()
    await db.refresh(config)
    return config


@router.get("/default/config", response_model=ApiConfigResponse)
async def get_default_config(
    db: AsyncSession = Depends(get_db)
):
    """获取默认API配置"""
    user_id = "default_user"
    
    result = await db.execute(
        select(ApiConfig).where(
            and_(ApiConfig.user_id == user_id, ApiConfig.is_default == True)
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到默认API配置"
        )
    return config


@router.post("/refresh-models", response_model=RefreshModelsResponse)
async def refresh_models(request: RefreshModelsRequest):
    """刷新可用模型列表"""
    try:
        provider = request.api_provider.lower()
        
        if provider in ["openai", "azure", "custom"]:
            # OpenAI 兼容接口获取模型列表
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{request.api_base_url.rstrip('/')}/models"
                headers = {
                    "Authorization": f"Bearer {request.api_key}",
                    "Content-Type": "application/json"
                }
                
                logger.info(f"正在从 {url} 获取模型列表")
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                all_models = []
                filtered_models = []
                
                if "data" in data and isinstance(data["data"], list):
                    for model in data["data"]:
                        model_id = model.get("id", "")
                        if model_id:
                            all_models.append(model_id)
                            # 尝试过滤出常用的文本生成模型
                            if any(keyword in model_id.lower() for keyword in [
                                "gpt", "gemini", "claude", "llama", "mistral", "qwen", "deepseek", "glm"
                            ]):
                                filtered_models.append(model_id)
                
                # 如果过滤后有模型,使用过滤后的;否则返回所有模型
                model_list = sorted(filtered_models) if filtered_models else sorted(all_models)
                
                if not model_list:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="未能从 API 获取到可用的模型列表"
                    )
                
                logger.info(f"成功获取 {len(model_list)} 个模型")
                
        elif provider == "anthropic":
            # Anthropic 不提供列表API，返回已知的可用模型
            model_list = [
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307",
                "claude-2.1",
                "claude-2.0",
                "claude-instant-1.2"
            ]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的API提供商: {provider}"
            )
        
        return RefreshModelsResponse(models=model_list, count=len(model_list))
        
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法从 API 获取模型列表 (HTTP {e.response.status_code})"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法连接到 API: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"刷新模型列表时发生错误: {str(e)}"
        )