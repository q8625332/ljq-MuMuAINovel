"""用户数据导出导入API - 重构版本"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.database import get_db, get_engine
from app.api.users import require_login
from app.models import (
    Project, Outline, Character, Chapter, GenerationHistory, Settings,
    RelationshipType, CharacterRelationship, Organization, OrganizationMember
)

router = APIRouter()
logger = logging.getLogger(__name__)

# 数据导出格式版本
EXPORT_VERSION = "2.0.0"


class DataExporter:
    """数据导出器"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def serialize_model(self, obj: Any) -> Dict[str, Any]:
        """将SQLAlchemy模型对象序列化为字典"""
        if obj is None:
            return None
        
        result = {}
        for column in obj.__table__.columns:
            value = getattr(obj, column.name)
            # 处理datetime对象
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result
    
    async def export_table_data(self, model_class) -> List[Dict[str, Any]]:
        """导出指定表的所有数据"""
        try:
            result = await self.db.execute(select(model_class))
            items = result.scalars().all()
            return [self.serialize_model(item) for item in items]
        except Exception as e:
            logger.error(f"导出表 {model_class.__tablename__} 失败: {str(e)}")
            return []
    
    async def export_all_data(self, user_id: str) -> Dict[str, Any]:
        """导出所有数据"""
        # 按依赖顺序导出数据
        # 1. 基础表
        projects = await self.export_table_data(Project)
        relationship_types = await self.export_table_data(RelationshipType)
        
        # 2. 依赖Project的表
        characters = await self.export_table_data(Character)
        chapters = await self.export_table_data(Chapter)
        outlines = await self.export_table_data(Outline)
        generation_history = await self.export_table_data(GenerationHistory)
        
        # 3. 依赖Character的表
        organizations = await self.export_table_data(Organization)
        character_relationships = await self.export_table_data(CharacterRelationship)
        organization_members = await self.export_table_data(OrganizationMember)
        
        # 4. 设置表
        settings = await self.export_table_data(Settings)
        
        return {
            "version": EXPORT_VERSION,
            "export_time": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "metadata": {
                "total_projects": len(projects),
                "total_characters": len(characters),
                "total_chapters": len(chapters),
                "total_outlines": len(outlines),
                "total_relationships": len(character_relationships),
                "total_organizations": len(organizations),
                "total_members": len(organization_members),
                "total_history": len(generation_history),
            },
            "data": {
                "projects": projects,
                "relationship_types": relationship_types,
                "characters": characters,
                "chapters": chapters,
                "outlines": outlines,
                "generation_history": generation_history,
                "character_relationships": character_relationships,
                "organizations": organizations,
                "organization_members": organization_members,
                "settings": settings,
            }
        }


class DataImporter:
    """数据导入器"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.import_stats = {
            "projects": 0,
            "characters": 0,
            "chapters": 0,
            "outlines": 0,
            "generation_history": 0,
            "character_relationships": 0,
            "organizations": 0,
            "organization_members": 0,
            "settings": 0
        }
    
    def deserialize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """将字典中的日期时间字符串转换为datetime对象"""
        result = item.copy()
        for key, value in result.items():
            if isinstance(value, str) and key in ('created_at', 'updated_at'):
                try:
                    # 处理ISO格式的日期时间字符串
                    result[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
        return result
    
    async def import_data(self, import_data: Dict[str, Any], replace: bool = False) -> Dict[str, Any]:
        """导入数据"""
        try:
            async with self.db.begin():
                # 如果是替换模式，先清空所有表（按依赖顺序反向删除）
                if replace:
                    await self.clear_all_data()
                
                data = import_data["data"]
                
                # 导入Projects
                if "projects" in data and data["projects"]:
                    for item in data["projects"]:
                        project = Project(**self.deserialize_item(item))
                        self.db.add(project)
                        self.import_stats["projects"] += 1
                
                await self.db.flush()
                
                # 导入RelationshipTypes（跳过已存在的）
                if "relationship_types" in data and data["relationship_types"]:
                    existing_types = await self.db.execute(select(RelationshipType))
                    existing_ids = {t.id for t in existing_types.scalars().all()}
                    
                    for item in data["relationship_types"]:
                        if item["id"] not in existing_ids:
                            rel_type = RelationshipType(**self.deserialize_item(item))
                            self.db.add(rel_type)
                
                # 导入Characters
                if "characters" in data and data["characters"]:
                    for item in data["characters"]:
                        character = Character(**self.deserialize_item(item))
                        self.db.add(character)
                        self.import_stats["characters"] += 1
                
                await self.db.flush()
                
                # 导入其他表
                tables_to_import = [
                    ("chapters", Chapter),
                    ("outlines", Outline),
                    ("generation_history", GenerationHistory),
                    ("organizations", Organization),
                    ("character_relationships", CharacterRelationship),
                    ("organization_members", OrganizationMember),
                    ("settings", Settings),
                ]
                
                for table_name, model_class in tables_to_import:
                    if table_name in data and data[table_name]:
                        for item in data[table_name]:
                            obj = model_class(**self.deserialize_item(item))
                            self.db.add(obj)
                        self.import_stats[table_name] += len(data[table_name])
                
            return self.import_stats
        except Exception as e:
            logger.error(f"导入数据失败: {str(e)}")
            raise
    
    async def clear_all_data(self):
        """清空所有数据"""
        tables_to_clear = [
            OrganizationMember,
            CharacterRelationship,
            Organization,
            GenerationHistory,
            Outline,
            Chapter,
            Character,
            Project,
            Settings,
        ]
        
        for model_class in tables_to_clear:
            await self.db.execute(delete(model_class))
        
        logger.info("所有现有数据已清空")


@router.get("/export-data")
async def export_user_data(
    request: Request,
    current_user=Depends(require_login)
):
    """导出用户全部数据"""
    user_id = current_user.user_id
    
    try:
        engine = await get_engine(user_id)
        async with AsyncSession(engine) as db:
            logger.info(f"开始导出用户 {user_id} 的数据")
            
            exporter = DataExporter(db)
            export_data = await exporter.export_all_data(user_id)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"mumuai_backup_user{user_id}_{timestamp}.json"
            
            logger.info(f"用户 {user_id} 数据导出成功，共 {len(export_data['data']['projects'])} 个项目")
            
            # 返回JSON响应，触发下载
            return JSONResponse(
                content=export_data,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/json; charset=utf-8"
                }
            )
            
    except Exception as e:
        logger.error(f"导出用户 {user_id} 数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"数据导出失败: {str(e)}")


@router.post("/import-data")
async def import_user_data(
    file: UploadFile = File(..., description="导入的JSON备份文件"),
    replace: bool = Query(False, description="是否替换现有数据（清空后导入）"),
    current_user=Depends(require_login)
):
    """导入用户数据"""
    user_id = current_user.user_id
    
    try:
        # 读取上传的文件
        content = await file.read()
        import_data = json.loads(content.decode('utf-8'))
        
        # 验证数据格式
        if "version" not in import_data or "data" not in import_data:
            raise HTTPException(status_code=400, detail="无效的备份文件格式")
        
        # 检查版本兼容性
        if import_data["version"] != EXPORT_VERSION:
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的数据版本: {import_data['version']}，当前支持版本: {EXPORT_VERSION}")
        
        logger.info(f"开始导入用户 {user_id} 的数据，替换模式: {replace}")
        
        # 获取用户数据库引擎和会话
        engine = await get_engine(user_id)
        async with AsyncSession(engine) as db:
            importer = DataImporter(db)
            import_stats = await importer.import_data(import_data, replace)
        
        logger.info(f"用户 {user_id} 数据导入成功")
        
        return {
            "message": "数据导入成功",
            "mode": "替换模式" if replace else "追加模式",
            "import_stats": import_stats,
            "import_time": datetime.utcnow().isoformat() + "Z"
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的JSON文件格式")
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"缺少必要的数据字段: {str(e)}")
    except Exception as e:
        logger.error(f"导入用户 {user_id} 数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"数据导入失败: {str(e)}")


@router.get("/export-info")
async def get_export_info(
    request: Request,
    current_user=Depends(require_login)
):
    """获取当前用户可导出的数据统计信息"""
    user_id = current_user.user_id
    
    try:
        engine = await get_engine(user_id)
        async with AsyncSession(engine) as db:
            # 统计各表数据量
            projects = await db.execute(select(Project))
            characters = await db.execute(select(Character))
            chapters = await db.execute(select(Chapter))
            outlines = await db.execute(select(Outline))
            relationships = await db.execute(select(CharacterRelationship))
            organizations = await db.execute(select(Organization))
            members = await db.execute(select(OrganizationMember))
            history = await db.execute(select(GenerationHistory))
            
            projects_count = len(projects.scalars().all())
            characters_count = len(characters.scalars().all())
            chapters_count = len(chapters.scalars().all())
            outlines_count = len(outlines.scalars().all())
            relationships_count = len(relationships.scalars().all())
            organizations_count = len(organizations.scalars().all())
            members_count = len(members.scalars().all())
            history_count = len(history.scalars().all())
        
        total_records = (
            projects_count + characters_count + chapters_count +
            outlines_count + relationships_count + organizations_count + members_count + history_count
        )
        
        return {
            "user_id": user_id,
            "data_summary": {
                "projects": projects_count,
                "characters": characters_count,
                "chapters": chapters_count,
                "outlines": outlines_count,
                "relationships": relationships_count,
                "organizations": organizations_count,
                "organization_members": members_count,
                "generation_history": history_count,
            },
            "total_records": total_records,
        }
        
    except Exception as e:
        logger.error(f"获取用户 {user_id} 导出信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取导出信息失败: {str(e)}")