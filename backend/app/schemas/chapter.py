"""章节相关的Pydantic模型"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ChapterBase(BaseModel):
    """章节基础模型"""
    title: str = Field(..., description="章节标题")
    chapter_number: int = Field(..., description="章节序号")
    content: Optional[str] = Field(None, description="章节内容")
    summary: Optional[str] = Field(None, description="章节摘要")
    word_count: Optional[int] = Field(0, description="字数")
    status: Optional[str] = Field("draft", description="章节状态")


class ChapterCreate(BaseModel):
    """创建章节的请求模型"""
    project_id: str = Field(..., description="所属项目ID")
    title: str = Field(..., description="章节标题")
    chapter_number: int = Field(..., description="章节序号")
    content: Optional[str] = Field(None, description="章节内容")
    summary: Optional[str] = Field(None, description="章节摘要")
    status: Optional[str] = Field("draft", description="章节状态")


class ChapterUpdate(BaseModel):
    """更新章节的请求模型"""
    title: Optional[str] = None
    content: Optional[str] = None
    # chapter_number 不允许修改，只能通过大纲的重排序来调整
    summary: Optional[str] = None
    # word_count 自动计算，不允许手动修改
    status: Optional[str] = None


class ChapterResponse(BaseModel):
    """章节响应模型"""
    id: str
    project_id: str
    title: str
    chapter_number: int
    content: Optional[str] = None
    summary: Optional[str] = None
    word_count: int = 0
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ChapterListResponse(BaseModel):
    """章节列表响应模型"""
    total: int
    items: list[ChapterResponse]