"""AI服务封装 - 统一的OpenAI和Claude接口"""
from typing import Optional, AsyncGenerator, List, Dict, Any
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from app.config import settings as app_settings
from app.logger import get_logger
import httpx

logger = get_logger(__name__)


class AIService:
    """AI服务统一接口 - 支持从用户设置或全局配置初始化"""
    
    def __init__(
        self,
        api_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        default_temperature: Optional[float] = None,
        default_max_tokens: Optional[int] = None
    ):
        """
        初始化AI客户端（优化并发性能）
        
        Args:
            api_provider: API提供商 (openai/anthropic)，为None时使用全局配置
            api_key: API密钥，为None时使用全局配置
            api_base_url: API基础URL，为None时使用全局配置
            default_model: 默认模型，为None时使用全局配置
            default_temperature: 默认温度，为None时使用全局配置
            default_max_tokens: 默认最大tokens，为None时使用全局配置
        """
        # 保存用户设置或使用全局配置
        self.api_provider = api_provider or app_settings.default_ai_provider
        self.default_model = default_model or app_settings.default_model
        self.default_temperature = default_temperature or app_settings.default_temperature
        self.default_max_tokens = default_max_tokens or app_settings.default_max_tokens
        
        # 初始化OpenAI客户端
        openai_key = api_key if api_provider == "openai" else app_settings.openai_api_key
        if openai_key:
            # 创建自定义的httpx客户端来避免proxies参数问题
            try:
                # 配置连接池限制，支持高并发
                # max_keepalive_connections: 保持活跃的连接数（提高复用率）
                # max_connections: 最大并发连接数（防止资源耗尽）
                limits = httpx.Limits(
                    max_keepalive_connections=50,  # 保持50个活跃连接
                    max_connections=100,            # 最多100个并发连接
                    keepalive_expiry=30.0          # 30秒后过期未使用的连接
                )
                
                # 使用httpx.AsyncClient并设置超时和连接池
                # connect: 连接超时10秒
                # read: 读取超时180秒（3分钟，适合长文本生成）
                # write: 写入超时10秒
                # pool: 连接池超时10秒
                http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=10.0,
                        read=180.0,
                        write=10.0,
                        pool=10.0
                    ),
                    limits=limits
                )
                
                client_kwargs = {
                    "api_key": openai_key,
                    "http_client": http_client
                }
                
                # 优先使用用户提供的base_url，否则使用全局配置
                base_url = api_base_url if api_provider == "openai" else app_settings.openai_base_url
                if base_url:
                    client_kwargs["base_url"] = base_url
                
                self.openai_client = AsyncOpenAI(**client_kwargs)
                logger.info("✅ OpenAI客户端初始化成功")
                logger.info("   - 超时设置：连接10s，读取180s")
                logger.info("   - 连接池：50个保活连接，最大100个并发")
            except Exception as e:
                logger.error(f"OpenAI客户端初始化失败: {e}")
                self.openai_client = None
        else:
            self.openai_client = None
            logger.warning("OpenAI API key未配置")
        
        # 初始化Anthropic客户端
        anthropic_key = api_key if api_provider == "anthropic" else app_settings.anthropic_api_key
        if anthropic_key:
            try:
                # 为Anthropic设置相同的超时和连接池配置
                limits = httpx.Limits(
                    max_keepalive_connections=50,
                    max_connections=100,
                    keepalive_expiry=30.0
                )
                
                http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=10.0,
                        read=180.0,
                        write=10.0,
                        pool=10.0
                    ),
                    limits=limits
                )
                
                client_kwargs = {
                    "api_key": anthropic_key,
                    "http_client": http_client
                }
                
                # 优先使用用户提供的base_url，否则使用全局配置
                base_url = api_base_url if api_provider == "anthropic" else app_settings.anthropic_base_url
                if base_url:
                    client_kwargs["base_url"] = base_url
                
                self.anthropic_client = AsyncAnthropic(**client_kwargs)
                logger.info("✅ Anthropic客户端初始化成功")
                logger.info("   - 超时设置：连接10s，读取180s")
                logger.info("   - 连接池：50个保活连接，最大100个并发")
            except Exception as e:
                logger.error(f"Anthropic客户端初始化失败: {e}")
                self.anthropic_client = None
        else:
            self.anthropic_client = None
            logger.warning("Anthropic API key未配置")
    
    async def generate_text(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        生成文本
        
        Args:
            prompt: 用户提示词
            provider: AI提供商 (openai/anthropic)
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            system_prompt: 系统提示词
            
        Returns:
            生成的文本
        """
        provider = provider or self.api_provider
        model = model or self.default_model
        temperature = temperature or self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens
        
        if provider == "openai":
            return await self._generate_openai(
                prompt, model, temperature, max_tokens, system_prompt
            )
        elif provider == "anthropic":
            return await self._generate_anthropic(
                prompt, model, temperature, max_tokens, system_prompt
            )
        else:
            raise ValueError(f"不支持的AI提供商: {provider}")
    
    async def generate_text_stream(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式生成文本
        
        Args:
            prompt: 用户提示词
            provider: AI提供商
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            system_prompt: 系统提示词
            
        Yields:
            生成的文本片段
        """
        provider = provider or self.api_provider
        model = model or self.default_model
        temperature = temperature or self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens
        
        if provider == "openai":
            async for chunk in self._generate_openai_stream(
                prompt, model, temperature, max_tokens, system_prompt
            ):
                yield chunk
        elif provider == "anthropic":
            async for chunk in self._generate_anthropic_stream(
                prompt, model, temperature, max_tokens, system_prompt
            ):
                yield chunk
        else:
            raise ValueError(f"不支持的AI提供商: {provider}")
    
    async def _generate_openai(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str]
    ) -> str:
        """使用OpenAI生成文本"""
        if not self.openai_client:
            raise ValueError("OpenAI客户端未初始化，请检查API key配置")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            logger.info(f"🔵 开始调用OpenAI API")
            logger.info(f"  - 模型: {model}")
            logger.info(f"  - 温度: {temperature}")
            logger.info(f"  - 最大tokens: {max_tokens}")
            logger.info(f"  - Prompt长度: {len(prompt)} 字符")
            logger.info(f"  - 消息数量: {len(messages)}")
            
            response = await self.openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            logger.info(f"✅ OpenAI API调用成功")
            logger.info(f"  - 响应ID: {response.id if hasattr(response, 'id') else 'N/A'}")
            logger.info(f"  - 选项数量: {len(response.choices)}")
            
            if not response.choices:
                logger.error("❌ OpenAI返回的choices为空")
                return ""
            
            content = response.choices[0].message.content
            logger.info(f"  - 返回内容长度: {len(content) if content else 0} 字符")
            
            if content:
                logger.info(f"  - 返回内容预览（前200字符）: {content[:200]}")
                return content
            else:
                logger.error("❌ OpenAI返回了空内容")
                logger.error(f"  - 完整响应: {response}")
                raise ValueError("AI返回了空内容，请检查API配置或稍后重试")
            
        except Exception as e:
            logger.error(f"❌ OpenAI API调用失败")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            logger.error(f"  - 错误信息: {str(e)}")
            logger.error(f"  - 模型: {model}")
            raise
    
    async def _generate_openai_stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str]
    ) -> AsyncGenerator[str, None]:
        """使用OpenAI流式生成文本"""
        if not self.openai_client:
            raise ValueError("OpenAI客户端未初始化，请检查API key配置")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            logger.info(f"🔵 开始调用OpenAI流式API")
            logger.info(f"  - 模型: {model}")
            logger.info(f"  - Prompt长度: {len(prompt)} 字符")
            logger.info(f"  - 最大tokens: {max_tokens}")
            
            stream = await self.openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            logger.info(f"✅ OpenAI流式API连接成功，开始接收数据...")
            
            chunk_count = 0
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    if chunk.choices[0].delta.content:
                        chunk_count += 1
                        yield chunk.choices[0].delta.content
            
            logger.info(f"✅ OpenAI流式生成完成，共接收 {chunk_count} 个chunk")
            
        except httpx.TimeoutException as e:
            logger.error(f"❌ OpenAI流式API超时")
            logger.error(f"  - 错误: {str(e)}")
            logger.error(f"  - 提示: 请检查网络连接或考虑缩短prompt长度")
            raise TimeoutError(f"AI服务超时（180秒），请稍后重试或减少上下文长度") from e
        except Exception as e:
            logger.error(f"❌ OpenAI流式API调用失败: {str(e)}")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            raise
    
    async def _generate_anthropic(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str]
    ) -> str:
        """使用Anthropic生成文本"""
        if not self.anthropic_client:
            raise ValueError("Anthropic客户端未初始化，请检查API key配置")
        
        try:
            response = await self.anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API调用失败: {str(e)}")
            raise
    
    async def _generate_anthropic_stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str]
    ) -> AsyncGenerator[str, None]:
        """使用Anthropic流式生成文本"""
        if not self.anthropic_client:
            raise ValueError("Anthropic客户端未初始化，请检查API key配置")
        
        try:
            logger.info(f"🔵 开始调用Anthropic流式API")
            logger.info(f"  - 模型: {model}")
            logger.info(f"  - Prompt长度: {len(prompt)} 字符")
            logger.info(f"  - 最大tokens: {max_tokens}")
            
            async with self.anthropic_client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                logger.info(f"✅ Anthropic流式API连接成功，开始接收数据...")
                
                chunk_count = 0
                async for text in stream.text_stream:
                    chunk_count += 1
                    yield text
                
                logger.info(f"✅ Anthropic流式生成完成，共接收 {chunk_count} 个chunk")
                
        except httpx.TimeoutException as e:
            logger.error(f"❌ Anthropic流式API超时")
            logger.error(f"  - 错误: {str(e)}")
            raise TimeoutError(f"AI服务超时（180秒），请稍后重试或减少上下文长度") from e
        except Exception as e:
            logger.error(f"❌ Anthropic流式API调用失败: {str(e)}")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            raise


# 创建全局AI服务实例（使用环境变量配置，用于向后兼容）
ai_service = AIService()


def create_user_ai_service(
    api_provider: str,
    api_key: str,
    api_base_url: str,
    model_name: str,
    temperature: float,
    max_tokens: int
) -> AIService:
    """
    根据用户设置创建AI服务实例
    
    Args:
        api_provider: API提供商
        api_key: API密钥
        api_base_url: API基础URL
        model_name: 模型名称
        temperature: 温度参数
        max_tokens: 最大tokens
        
    Returns:
        AIService实例
    """
    return AIService(
        api_provider=api_provider,
        api_key=api_key,
        api_base_url=api_base_url,
        default_model=model_name,
        default_temperature=temperature,
        default_max_tokens=max_tokens
    )