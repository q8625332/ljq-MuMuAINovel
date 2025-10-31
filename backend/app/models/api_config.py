from sqlalchemy import Column, String, Float, Integer, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class ApiConfig(Base):
    """API配置模型"""
    __tablename__ = "api_configs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)  # 配置名称
    api_provider = Column(String, nullable=False)  # openai, anthropic, azure, custom
    api_key = Column(String, nullable=False)
    api_base_url = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    is_default = Column(Boolean, default=False)  # 是否为默认配置

    # 创建复合唯一索引：同一用户不能有重复的配置名称
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uix_user_config_name'),
        Index('ix_api_configs_user_default', 'user_id', 'is_default'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'api_provider': self.api_provider,
            'api_key': self.api_key,
            'api_base_url': self.api_base_url,
            'model_name': self.model_name,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'is_default': self.is_default,
        }