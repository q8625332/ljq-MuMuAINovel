from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class ApiConfigBase(BaseModel):
    """API配置基础模型"""
    model_config = ConfigDict(protected_namespaces=())
    
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    api_provider: str = Field(..., description="API提供商: openai, anthropic, azure, custom")
    api_key: str = Field(..., min_length=1, description="API密钥")
    api_base_url: str = Field(..., min_length=1, description="API基础URL")
    model_name: str = Field(..., min_length=1, description="模型名称")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int = Field(default=2000, ge=1, le=100000, description="最大token数")
    is_default: bool = Field(default=False, description="是否为默认配置")


class ApiConfigCreate(ApiConfigBase):
    """创建API配置"""
    pass


class ApiConfigUpdate(BaseModel):
    """更新API配置"""
    model_config = ConfigDict(protected_namespaces=())
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    api_provider: Optional[str] = None
    api_key: Optional[str] = Field(None, min_length=1)
    api_base_url: Optional[str] = Field(None, min_length=1)
    model_name: Optional[str] = Field(None, min_length=1)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=100000)
    is_default: Optional[bool] = None


class ApiConfigResponse(ApiConfigBase):
    """API配置响应模型"""
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    
    id: str
    user_id: str


class RefreshModelsRequest(BaseModel):
    """刷新模型列表请求"""
    api_provider: str = Field(..., description="API提供商")
    api_key: str = Field(..., description="API密钥")
    api_base_url: str = Field(..., description="API基础URL")


class RefreshModelsResponse(BaseModel):
    """刷新模型列表响应"""
    models: list[str] = Field(..., description="可用模型列表")
    count: int = Field(..., description="模型数量")