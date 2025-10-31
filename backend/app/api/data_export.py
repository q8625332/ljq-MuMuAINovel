"""用户数据导出导入API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime
import json
from typing import Dict, Any, List
import logging

from app.database import get_db, get_engine
from app.api.users import require_login
from app.models import (
    Project, Outline, Character, Chapter, GenerationHistory, Settings,
    RelationshipType, CharacterRelationship, Organization, OrganizationMember
)

router = APIRouter()
logger = logging.getLogger(__name__)

# 数据导出格式版本
EXPORT_VERSION = "1.0.0"


def serialize_model(obj: Any) -> Dict[str, Any]:
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


async def export_table_data(db: AsyncSession, model_class) -> List[Dict[str, Any]]:
    """导出指定表的所有数据"""
    try:
        result = await db.execute(select(model_class))
        items = result.scalars().all()
        return [serialize_model(item) for item in items]
    except Exception as e:
        logger.error(f"导出表 {model_class.__tablename__} 失败: {str(e)}")
        return []


@router.get("/export-data")
async def export_user_data(
    request,
    current_user=Depends(require_login)
):
    """
    导出用户全部数据
    
    返回包含所有项目、角色、章节、大纲、关系、组织等数据的JSON文件
    """
    user_id = current_user["user_id"]
    
    try:
        # 获取用户数据库引擎和会话
        engine = await get_engine(user_id)
        async with AsyncSession(engine) as db:
            # 导出所有表的数据（按依赖顺序）
            logger.info(f"开始导出用户 {user_id} 的数据")
            
            # 1. 无依赖的基础表
            projects = await export_table_data(db, Project)
            relationship_types = await export_table_data(db, RelationshipType)
            
            # 2. 依赖Project的表
            characters = await export_table_data(db, Character)
            chapters = await export_table_data(db, Chapter)
            outlines = await export_table_data(db, Outline)
            generation_history = await export_table_data(db, GenerationHistory)
            
            # 3. 依赖Character的表
            organizations = await export_table_data(db, Organization)
            character_relationships = await export_table_data(db, CharacterRelationship)
            organization_members = await export_table_data(db, OrganizationMember)
            
            # 4. Settings表（独立的用户设置）
            settings = await export_table_data(db, Settings)
            
            # 构建导出数据结构
            export_data = {
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
                    # 基础表
                    "projects": projects,
                    "relationship_types": relationship_types,
                    
                    # 内容表
                    "characters": characters,
                    "chapters": chapters,
                    "outlines": outlines,
                    "generation_history": generation_history,
                    
                    # 关系表
                    "character_relationships": character_relationships,
                    "organizations": organizations,
                    "organization_members": organization_members,
                    
                    # 设置
                    "settings": settings,
                }
            }
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"mumuai_backup_user{user_id}_{timestamp}.json"
            
            logger.info(f"用户 {user_id} 数据导出成功，共 {len(projects)} 个项目")
            
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
    """
    导入用户数据
    
    参数:
    - file: JSON格式的备份文件
    - replace: 是否替换现有数据（默认为False，追加模式）
    
    注意:
    - 如果replace=True，将清空现有数据后导入
    - 如果replace=False，将保留现有数据并追加导入（可能导致ID冲突）
    """
    user_id = current_user["user_id"]
    
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
                detail=f"不支持的数据版本: {import_data['version']}，当前支持版本: {EXPORT_VERSION}"
            )
        
        logger.info(f"开始导入用户 {user_id} 的数据，替换模式: {replace}")
        
        # 获取用户数据库引擎和会话
        engine = await get_engine(user_id)
        async with AsyncSession(engine) as db:
            async with db.begin():  # 使用事务确保数据一致性
                
                # 如果是替换模式，先清空所有表（按依赖顺序反向删除）
                if replace:
                    logger.info(f"清空用户 {user_id} 的现有数据")
                    await db.execute(delete(OrganizationMember))
                    await db.execute(delete(CharacterRelationship))
                    await db.execute(delete(Organization))
                    await db.execute(delete(GenerationHistory))
                    await db.execute(delete(Outline))
                    await db.execute(delete(Chapter))
                    await db.execute(delete(Character))
                    await db.execute(delete(Project))
                    # RelationshipType 是预置数据，不删除
                    await db.execute(delete(Settings))
                    await db.flush()
                
                data = import_data["data"]
                
                # 导入数据（按依赖顺序）
                # 1. 导入Projects
                if "projects" in data and data["projects"]:
                    for item in data["projects"]:
                        project = Project(**item)
                        db.add(project)
                    logger.info(f"导入 {len(data['projects'])} 个项目")
                
                # 2. 导入RelationshipTypes（跳过已存在的预置数据）
                if "relationship_types" in data and data["relationship_types"]:
                    existing_types = await db.execute(select(RelationshipType))
                    existing_ids = {t.id for t in existing_types.scalars().all()}
                    
                    new_count = 0
                    for item in data["relationship_types"]:
                        if item["id"] not in existing_ids:
                            rel_type = RelationshipType(**item)
                            db.add(rel_type)
                            new_count += 1
                    if new_count > 0:
                        logger.info(f"导入 {new_count} 个新关系类型")
                
                await db.flush()  # 确保Projects和RelationshipTypes已插入
                
                # 3. 导入Characters
                if "characters" in data and data["characters"]:
                    for item in data["characters"]:
                        character = Character(**item)
                        db.add(character)
                    logger.info(f"导入 {len(data['characters'])} 个角色")
                
                # 4. 导入Chapters
                if "chapters" in data and data["chapters"]:
                    for item in data["chapters"]:
                        chapter = Chapter(**item)
                        db.add(chapter)
                    logger.info(f"导入 {len(data['chapters'])} 个章节")
                
                # 5. 导入Outlines
                if "outlines" in data and data["outlines"]:
                    for item in data["outlines"]:
                        outline = Outline(**item)
                        db.add(outline)
                    logger.info(f"导入 {len(data['outlines'])} 个大纲")
                
                # 6. 导入GenerationHistory
                if "generation_history" in data and data["generation_history"]:
                    for item in data["generation_history"]:
                        history = GenerationHistory(**item)
                        db.add(history)
                    logger.info(f"导入 {len(data['generation_history'])} 条生成历史")
                
                await db.flush()  # 确保Characters已插入
                
                # 7. 导入Organizations
                if "organizations" in data and data["organizations"]:
                    for item in data["organizations"]:
                        org = Organization(**item)
                        db.add(org)
                    logger.info(f"导入 {len(data['organizations'])} 个组织")
                
                # 8. 导入CharacterRelationships
                if "character_relationships" in data and data["character_relationships"]:
                    for item in data["character_relationships"]:
                        rel = CharacterRelationship(**item)
                        db.add(rel)
                    logger.info(f"导入 {len(data['character_relationships'])} 个角色关系")
                
                # 9. 导入OrganizationMembers
                if "organization_members" in data and data["organization_members"]:
                    for item in data["organization_members"]:
                        member = OrganizationMember(**item)
                        db.add(member)
                    logger.info(f"导入 {len(data['organization_members'])} 个组织成员")
                
                # 10. 导入Settings
                if "settings" in data and data["settings"]:
                    for item in data["settings"]:
                        settings = Settings(**item)
                        db.add(settings)
                    logger.info(f"导入 {len(data['settings'])} 条设置")
                
                # 提交事务
                await db.commit()
        
        logger.info(f"用户 {user_id} 数据导入成功")
        
        return {
            "message": "数据导入成功",
            "mode": "替换模式" if replace else "追加模式",
            "metadata": import_data.get("metadata", {}),
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
    current_user=Depends(require_login)
):
    """
    获取当前用户可导出的数据统计信息
    
    用于在导出前预览数据量
    """
    user_id = current_user["user_id"]
    
    try:
        engine = await get_engine(user_id)
        async with AsyncSession(engine) as db:
            # 统计各表数据量
            projects_count = (await db.execute(select(Project))).scalars().all()
            characters_count = (await db.execute(select(Character))).scalars().all()
            chapters_count = (await db.execute(select(Chapter))).scalars().all()
            outlines_count = (await db.execute(select(Outline))).scalars().all()
            relationships_count = (await db.execute(select(CharacterRelationship))).scalars().all()
            organizations_count = (await db.execute(select(Organization))).scalars().all()
            members_count = (await db.execute(select(OrganizationMember))).scalars().all()
            history_count = (await db.execute(select(GenerationHistory))).scalars().all()
            
            return {
                "user_id": user_id,
                "data_summary": {
                    "projects": len(projects_count),
                    "characters": len(characters_count),
                    "chapters": len(chapters_count),
                    "outlines": len(outlines_count),
                    "relationships": len(relationships_count),
                    "organizations": len(organizations_count),
                    "organization_members": len(members_count),
                    "generation_history": len(history_count),
                },
                "total_records": (
                    len(projects_count) + len(characters_count) + len(chapters_count) +
                    len(outlines_count) + len(relationships_count) + len(organizations_count) +
                    len(members_count) + len(history_count)
                )
            }
            
    except Exception as e:
        logger.error(f"获取用户 {user_id} 导出信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取导出信息失败: {str(e)}")