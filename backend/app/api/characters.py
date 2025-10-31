"""角色管理API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import json

from app.database import get_db
from app.models.character import Character
from app.models.project import Project
from app.models.generation_history import GenerationHistory
from app.models.relationship import CharacterRelationship, Organization, OrganizationMember, RelationshipType
from app.schemas.character import (
    CharacterUpdate,
    CharacterResponse,
    CharacterListResponse,
    CharacterGenerateRequest
)
from app.services.ai_service import AIService
from app.services.prompt_service import prompt_service
from app.logger import get_logger
from app.api.settings import get_user_ai_service

router = APIRouter(prefix="/characters", tags=["角色管理"])
logger = get_logger(__name__)


@router.get("", response_model=CharacterListResponse, summary="获取角色列表")
async def get_characters(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有角色（query参数版本）"""
    # 获取总数
    count_result = await db.execute(
        select(func.count(Character.id)).where(Character.project_id == project_id)
    )
    total = count_result.scalar_one()
    
    # 获取角色列表
    result = await db.execute(
        select(Character)
        .where(Character.project_id == project_id)
        .order_by(Character.created_at.desc())
    )
    characters = result.scalars().all()
    
    return CharacterListResponse(total=total, items=characters)


@router.get("/project/{project_id}", response_model=CharacterListResponse, summary="获取项目的所有角色")
async def get_project_characters(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有角色（路径参数版本）"""
    # 获取总数
    count_result = await db.execute(
        select(func.count(Character.id)).where(Character.project_id == project_id)
    )
    total = count_result.scalar_one()
    
    # 获取角色列表
    result = await db.execute(
        select(Character)
        .where(Character.project_id == project_id)
        .order_by(Character.created_at.desc())
    )
    characters = result.scalars().all()
    
    return CharacterListResponse(total=total, items=characters)


@router.get("/{character_id}", response_model=CharacterResponse, summary="获取角色详情")
async def get_character(
    character_id: str,
    db: AsyncSession = Depends(get_db)
):
    """根据ID获取角色详情"""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()
    
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    return character


@router.put("/{character_id}", response_model=CharacterResponse, summary="更新角色")
async def update_character(
    character_id: str,
    character_update: CharacterUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新角色信息"""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()
    
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 更新字段
    update_data = character_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(character, field, value)
    
    await db.commit()
    await db.refresh(character)
    return character


@router.delete("/{character_id}", summary="删除角色")
async def delete_character(
    character_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除角色"""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()
    
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    await db.delete(character)
    await db.commit()
    
    return {"message": "角色删除成功"}


@router.post("/generate", response_model=CharacterResponse, summary="AI生成角色")
async def generate_character(
    request: CharacterGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用AI生成角色卡
    
    根据用户输入的信息，结合项目的世界观、主题等背景，
    AI会生成一个完整、详细的角色设定卡片。
    
    生成内容包括：姓名、年龄、性别、性格、外貌、背景故事、人际关系等
    """
    # 验证项目是否存在并获取项目信息
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    try:
        # 获取已存在的角色列表，用于关系网络
        existing_chars_result = await db.execute(
            select(Character)
            .where(Character.project_id == request.project_id)
            .order_by(Character.created_at.desc())
        )
        existing_characters = existing_chars_result.scalars().all()
        
        # 构建现有角色信息摘要（包含组织）
        existing_chars_info = ""
        character_list = []
        organization_list = []
        
        if existing_characters:
            for c in existing_characters[:10]:  # 最多显示10个
                if c.is_organization:
                    organization_list.append(f"- {c.name} [{c.organization_type or '组织'}]")
                else:
                    character_list.append(f"- {c.name}（{c.role_type or '未知'}）")
            
            if character_list:
                existing_chars_info += "\n已有角色：\n" + "\n".join(character_list)
            if organization_list:
                existing_chars_info += "\n\n已有组织：\n" + "\n".join(organization_list)
        
        # 构建项目上下文信息
        project_context = f"""
项目信息：
- 书名：{project.title}
- 主题：{project.theme or '未设定'}
- 类型：{project.genre or '未设定'}
- 时间背景：{project.world_time_period or '未设定'}
- 地理位置：{project.world_location or '未设定'}
- 氛围基调：{project.world_atmosphere or '未设定'}
- 世界规则：{project.world_rules or '未设定'}
{existing_chars_info}
"""
        
        # 构建用户输入信息
        user_input = f"""
用户要求：
- 角色名称：{request.name or '请AI生成'}
- 角色定位：{request.role_type or 'supporting'}（protagonist=主角, supporting=配角, antagonist=反派）
- 背景设定：{request.background or '无特殊要求'}
- 其他要求：{request.requirements or '无'}
"""
        
        # 使用统一的提示词服务
        prompt = prompt_service.get_single_character_prompt(
            project_context=project_context,
            user_input=user_input
        )
        
        # 调用AI生成角色
        logger.info(f"🎯 开始为项目 {request.project_id} 生成角色")
        logger.info(f"  - 角色名：{request.name or 'AI生成'}")
        logger.info(f"  - 角色定位：{request.role_type}")
        logger.info(f"  - 背景设定：{request.background or '无'}")
        logger.info(f"  - AI提供商：{request.provider or 'default'}")
        logger.info(f"  - AI模型：{request.model or 'default'}")
        logger.info(f"  - Prompt长度：{len(prompt)} 字符")
        
        try:
            ai_response = await user_ai_service.generate_text(
                prompt=prompt,
                provider=request.provider,
                model=request.model
            )
            logger.info(f"✅ AI响应接收完成，长度：{len(ai_response) if ai_response else 0} 字符")
        except Exception as ai_error:
            logger.error(f"❌ AI服务调用异常：{str(ai_error)}")
            raise HTTPException(
                status_code=500,
                detail=f"AI服务调用失败：{str(ai_error)}"
            )
        
        # 检查AI响应
        if not ai_response or not ai_response.strip():
            logger.error("❌ AI返回了空响应")
            raise HTTPException(
                status_code=500,
                detail="AI服务返回空响应。可能原因：1) API配置错误 2) 模型不支持 3) 网络问题。请检查后端日志。"
            )
        
        logger.info(f"📝 开始清理AI响应")
        # 清理AI响应，移除可能的markdown标记
        cleaned_response = ai_response.strip()
        original_length = len(cleaned_response)
        
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]
            logger.info("  - 移除了 ```json 标记")
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]
            logger.info("  - 移除了 ``` 标记")
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
            logger.info("  - 移除了末尾 ``` 标记")
        cleaned_response = cleaned_response.strip()
        
        logger.info(f"  - 清理前长度：{original_length}，清理后长度：{len(cleaned_response)}")
        logger.info(f"  - 清理后内容预览（前300字符）：{cleaned_response[:300]}")
        
        # 解析AI响应
        logger.info(f"🔍 开始解析JSON")
        try:
            character_data = json.loads(cleaned_response)
            logger.info(f"✅ JSON解析成功")
            logger.info(f"  - 解析后的字段：{list(character_data.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON解析失败")
            logger.error(f"  - 错误位置：line {e.lineno}, column {e.colno}")
            logger.error(f"  - 错误信息：{str(e)}")
            logger.error(f"  - 完整响应内容（前1000字符）：{cleaned_response[:1000]}")
            
            raise HTTPException(
                status_code=500,
                detail=f"AI返回的内容无法解析为JSON。错误：{str(e)}。响应内容已记录到日志，请查看后端日志排查。"
            )
        
        # 转换traits为JSON字符串
        traits_json = json.dumps(character_data.get("traits", []), ensure_ascii=False) if character_data.get("traits") else None
        
        # 判断是否为组织
        is_organization = character_data.get("is_organization", False)
        
        # 创建角色
        character = Character(
            project_id=request.project_id,
            name=character_data.get("name", request.name or "未命名角色"),
            age=str(character_data.get("age", "")),
            gender=character_data.get("gender"),
            is_organization=is_organization,
            role_type=request.role_type or "supporting",
            personality=character_data.get("personality", ""),
            background=character_data.get("background", ""),
            appearance=character_data.get("appearance", ""),
            relationships=character_data.get("relationships_text", character_data.get("relationships", "")),  # 优先使用文本描述
            organization_type=character_data.get("organization_type") if is_organization else None,
            organization_purpose=character_data.get("organization_purpose") if is_organization else None,
            organization_members=json.dumps(character_data.get("organization_members", []), ensure_ascii=False) if is_organization else None,
            traits=traits_json
        )
        db.add(character)
        await db.flush()  # 获取character.id
        
        logger.info(f"✅ 角色创建成功：{character.name} (ID: {character.id}, 是否组织: {is_organization})")
        
        # 如果是组织，自动创建Organization详情记录
        if is_organization:
            org_check = await db.execute(
                select(Organization).where(Organization.character_id == character.id)
            )
            existing_org = org_check.scalar_one_or_none()
            
            if not existing_org:
                organization = Organization(
                    character_id=character.id,
                    project_id=request.project_id,
                    member_count=0,
                    power_level=character_data.get("power_level", 50),
                    location=character_data.get("location"),
                    motto=character_data.get("motto")
                )
                db.add(organization)
                await db.flush()
                logger.info(f"✅ 自动创建组织详情：{character.name} (Org ID: {organization.id})")
            else:
                logger.info(f"ℹ️  组织详情已存在：{character.name}")
        
        # 处理结构化关系数据（仅针对非组织角色）
        if not is_organization:
            relationships_data = character_data.get("relationships", [])
            if relationships_data and isinstance(relationships_data, list):
                logger.info(f"📊 开始处理 {len(relationships_data)} 条关系数据")
                created_rels = 0
                
                for rel in relationships_data:
                    try:
                        target_name = rel.get("target_character_name")
                        if not target_name:
                            logger.debug(f"  ⚠️  关系缺少target_character_name，跳过")
                            continue
                        
                        target_result = await db.execute(
                            select(Character).where(
                                Character.project_id == request.project_id,
                                Character.name == target_name
                            )
                        )
                        target_char = target_result.scalar_one_or_none()
                        
                        if target_char:
                            # 检查是否已存在相同关系
                            existing_rel = await db.execute(
                                select(CharacterRelationship).where(
                                    CharacterRelationship.project_id == request.project_id,
                                    CharacterRelationship.character_from_id == character.id,
                                    CharacterRelationship.character_to_id == target_char.id
                                )
                            )
                            if existing_rel.scalar_one_or_none():
                                logger.debug(f"  ℹ️  关系已存在：{character.name} -> {target_name}")
                                continue
                            
                            relationship = CharacterRelationship(
                                project_id=request.project_id,
                                character_from_id=character.id,
                                character_to_id=target_char.id,
                                relationship_name=rel.get("relationship_type", "未知关系"),
                                intimacy_level=rel.get("intimacy_level", 50),
                                description=rel.get("description", ""),
                                started_at=rel.get("started_at"),
                                source="ai"
                            )
                            
                            # 匹配预定义关系类型
                            rel_type_result = await db.execute(
                                select(RelationshipType).where(
                                    RelationshipType.name == rel.get("relationship_type")
                                )
                            )
                            rel_type = rel_type_result.scalar_one_or_none()
                            if rel_type:
                                relationship.relationship_type_id = rel_type.id
                            
                            db.add(relationship)
                            created_rels += 1
                            logger.info(f"  ✅ 创建关系：{character.name} -> {target_name} ({rel.get('relationship_type')})")
                        else:
                            logger.warning(f"  ⚠️  目标角色不存在：{target_name}")
                            
                    except Exception as rel_error:
                        logger.warning(f"  ❌ 创建关系失败：{str(rel_error)}")
                        continue
                
                logger.info(f"✅ 成功创建 {created_rels} 条关系记录")
        
        # 处理组织成员关系（仅针对非组织角色）
        if not is_organization:
            org_memberships = character_data.get("organization_memberships", [])
            if org_memberships and isinstance(org_memberships, list):
                logger.info(f"🏢 开始处理 {len(org_memberships)} 条组织成员关系")
                created_members = 0
                
                for membership in org_memberships:
                    try:
                        org_name = membership.get("organization_name")
                        if not org_name:
                            logger.debug(f"  ⚠️  组织成员关系缺少organization_name，跳过")
                            continue
                        
                        org_char_result = await db.execute(
                            select(Character).where(
                                Character.project_id == request.project_id,
                                Character.name == org_name,
                                Character.is_organization == True
                            )
                        )
                        org_char = org_char_result.scalar_one_or_none()
                        
                        if org_char:
                            # 获取或创建Organization记录
                            org_result = await db.execute(
                                select(Organization).where(Organization.character_id == org_char.id)
                            )
                            org = org_result.scalar_one_or_none()
                            
                            if not org:
                                # 如果组织Character存在但Organization不存在，自动创建
                                org = Organization(
                                    character_id=org_char.id,
                                    project_id=request.project_id,
                                    member_count=0
                                )
                                db.add(org)
                                await db.flush()
                                logger.info(f"  ℹ️  自动创建缺失的组织详情：{org_name}")
                            
                            # 检查是否已存在成员关系
                            existing_member = await db.execute(
                                select(OrganizationMember).where(
                                    OrganizationMember.organization_id == org.id,
                                    OrganizationMember.character_id == character.id
                                )
                            )
                            if existing_member.scalar_one_or_none():
                                logger.debug(f"  ℹ️  成员关系已存在：{character.name} -> {org_name}")
                                continue
                            
                            # 创建成员关系
                            member = OrganizationMember(
                                organization_id=org.id,
                                character_id=character.id,
                                position=membership.get("position", "成员"),
                                rank=membership.get("rank", 0),
                                loyalty=membership.get("loyalty", 50),
                                joined_at=membership.get("joined_at"),
                                status=membership.get("status", "active"),
                                source="ai"
                            )
                            db.add(member)
                            
                            # 更新组织成员计数
                            org.member_count += 1
                            
                            created_members += 1
                            logger.info(f"  ✅ 添加成员：{character.name} -> {org_name} ({membership.get('position')})")
                        else:
                            logger.warning(f"  ⚠️  组织不存在：{org_name}")
                            
                    except Exception as org_error:
                        logger.warning(f"  ❌ 添加组织成员失败：{str(org_error)}")
                        continue
                
                logger.info(f"✅ 成功创建 {created_members} 条组织成员记录")
        
        # 记录生成历史
        history = GenerationHistory(
            project_id=request.project_id,
            prompt=prompt,
            generated_content=ai_response,
            model=request.model or "default"
        )
        db.add(history)
        
        await db.commit()
        await db.refresh(character)
        
        logger.info(f"🎉 成功为项目 {request.project_id} 生成角色: {character.name}")
        
        return character
        
    except Exception as e:
        logger.error(f"生成角色失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成角色失败: {str(e)}")