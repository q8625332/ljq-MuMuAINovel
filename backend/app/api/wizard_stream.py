"""项目创建向导流式API - 使用SSE避免超时"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, AsyncGenerator
import json
import re

from app.database import get_db
from app.models.project import Project
from app.models.character import Character
from app.models.outline import Outline
from app.models.chapter import Chapter
from app.models.relationship import CharacterRelationship, Organization, OrganizationMember, RelationshipType
from app.services.ai_service import AIService
from app.services.prompt_service import prompt_service
from app.logger import get_logger
from app.utils.sse_response import SSEResponse, create_sse_response
from app.api.settings import get_user_ai_service

router = APIRouter(prefix="/wizard-stream", tags=["项目创建向导(流式)"])
logger = get_logger(__name__)


async def world_building_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """世界构建流式生成器"""
    # 标记数据库会话是否已提交
    db_committed = False
    try:
        # 发送开始消息
        yield await SSEResponse.send_progress("开始生成世界观...", 10)
        
        # 提取参数
        title = data.get("title")
        description = data.get("description")
        theme = data.get("theme")
        genre = data.get("genre")
        narrative_perspective = data.get("narrative_perspective")
        target_words = data.get("target_words")
        chapter_count = data.get("chapter_count")
        character_count = data.get("character_count")
        provider = data.get("provider")
        model = data.get("model")
        
        if not title or not description or not theme or not genre:
            yield await SSEResponse.send_error("title、description、theme 和 genre 是必需的参数", 400)
            return
        
        # 获取提示词
        yield await SSEResponse.send_progress("准备AI提示词...", 20)
        prompt = prompt_service.get_world_building_prompt(
            title=title,
            theme=theme,
            genre=genre
        )
        
        # 流式调用AI
        yield await SSEResponse.send_progress("正在调用AI生成...", 30)
        
        accumulated_text = ""
        chunk_count = 0
        
        async for chunk in user_ai_service.generate_text_stream(
            prompt=prompt,
            provider=provider,
            model=model
        ):
            chunk_count += 1
            accumulated_text += chunk
            
            # 发送内容块
            yield await SSEResponse.send_chunk(chunk)
            
            # 定期更新进度
            if chunk_count % 5 == 0:
                progress = min(30 + (chunk_count // 5), 70)
                yield await SSEResponse.send_progress(f"生成中... ({len(accumulated_text)}字符)", progress)
            
            # 每20个块发送心跳
            if chunk_count % 20 == 0:
                yield await SSEResponse.send_heartbeat()
        
        # 解析结果
        yield await SSEResponse.send_progress("解析AI返回结果...", 80)
        
        world_data = {}
        try:
            cleaned_text = accumulated_text.strip()
            
            # 移除markdown代码块标记
            if cleaned_text.startswith('```json'):
                cleaned_text = cleaned_text[7:].lstrip('\n\r')
            elif cleaned_text.startswith('```'):
                cleaned_text = cleaned_text[3:].lstrip('\n\r')
            if cleaned_text.endswith('```'):
                cleaned_text = cleaned_text[:-3].rstrip('\n\r')
            cleaned_text = cleaned_text.strip()
            
            world_data = json.loads(cleaned_text)
                    
        except json.JSONDecodeError as e:
            logger.error(f"世界构建JSON解析失败: {e}")
            world_data = {
                "time_period": "AI返回格式错误，请重试",
                "location": "AI返回格式错误，请重试",
                "atmosphere": "AI返回格式错误，请重试",
                "rules": "AI返回格式错误，请重试"
            }
        # 保存到数据库
        yield await SSEResponse.send_progress("保存到数据库...", 90)
        
        project = Project(
            title=title,
            description=description,
            theme=theme,
            genre=genre,
            world_time_period=world_data.get("time_period"),
            world_location=world_data.get("location"),
            world_atmosphere=world_data.get("atmosphere"),
            world_rules=world_data.get("rules"),
            narrative_perspective=narrative_perspective,
            target_words=target_words,
            chapter_count=chapter_count,
            character_count=character_count,
            wizard_status="incomplete",
            wizard_step=1,
            status="planning"
        )
        db.add(project)
        await db.commit()
        db_committed = True
        await db.refresh(project)
        
        # 发送最终结果
        yield await SSEResponse.send_result({
            "project_id": project.id,
            "time_period": world_data.get("time_period"),
            "location": world_data.get("location"),
            "atmosphere": world_data.get("atmosphere"),
            "rules": world_data.get("rules")
        })
        
        yield await SSEResponse.send_progress("完成!", 100, "success")
        yield await SSEResponse.send_done()
        
    except GeneratorExit:
        # SSE连接断开，回滚未提交的事务
        logger.warning("世界构建生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("世界构建事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"世界构建流式生成失败: {str(e)}")
        # 异常时回滚事务
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("世界构建事务已回滚（异常）")
        yield await SSEResponse.send_error(f"生成失败: {str(e)}")


@router.post("/world-building", summary="流式生成世界构建")
async def generate_world_building_stream(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式生成世界构建，避免超时
    前端使用EventSource接收实时进度和结果
    """
    return create_sse_response(world_building_generator(data, db, user_ai_service))


async def characters_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """角色批量生成流式生成器 - 优化版:分批+重试"""
    db_committed = False
    try:
        yield await SSEResponse.send_progress("开始生成角色...", 5)
        
        project_id = data.get("project_id")
        count = data.get("count", 5)
        world_context = data.get("world_context")
        theme = data.get("theme", "")
        genre = data.get("genre", "")
        requirements = data.get("requirements", "")
        provider = data.get("provider")
        model = data.get("model")
        
        # 验证项目
        yield await SSEResponse.send_progress("验证项目...", 10)
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await SSEResponse.send_error("项目不存在", 404)
            return
        
        project.wizard_step = 2
        
        world_context = world_context or {
            "time_period": project.world_time_period or "未设定",
            "location": project.world_location or "未设定",
            "atmosphere": project.world_atmosphere or "未设定",
            "rules": project.world_rules or "未设定"
        }
        
        # 优化的分批策略:每批生成3个,平衡效率和成功率
        BATCH_SIZE = 3  # 每批生成3个角色
        MAX_RETRIES = 3  # 每批最多重试3次
        all_characters = []
        total_batches = (count + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_idx in range(total_batches):
            # 精确计算当前批次应该生成的数量
            remaining = count - len(all_characters)
            current_batch_size = min(BATCH_SIZE, remaining)
            
            # 如果已经达到目标数量,直接退出
            if current_batch_size <= 0:
                logger.info(f"已生成{len(all_characters)}个角色,达到目标数量{count}")
                break
            
            batch_progress = 15 + (batch_idx * 60 // total_batches)
            
            # 重试逻辑
            retry_count = 0
            batch_success = False
            
            while retry_count < MAX_RETRIES and not batch_success:
                try:
                    retry_suffix = f" (重试{retry_count}/{MAX_RETRIES})" if retry_count > 0 else ""
                    yield await SSEResponse.send_progress(
                        f"生成第{batch_idx+1}/{total_batches}批角色 ({current_batch_size}个){retry_suffix}...",
                        batch_progress
                    )
                    
                    # 构建批次要求 - 包含已生成角色信息保持连贯
                    existing_chars_context = ""
                    if all_characters:
                        existing_chars_context = "\n\n【已生成的角色】:\n"
                        for char in all_characters:
                            existing_chars_context += f"- {char.get('name')}: {char.get('role_type', '未知')}, {char.get('personality', '暂无')[:50]}...\n"
                        existing_chars_context += "\n请确保新角色与已有角色形成合理的关系网络和互动。\n"
                    
                    # 构建精确的批次要求,明确告诉AI要生成的数量
                    if batch_idx == 0:
                        if current_batch_size == 1:
                            batch_requirements = f"{requirements}\n请生成1个主角(protagonist)"
                        else:
                            batch_requirements = f"{requirements}\n请精确生成{current_batch_size}个角色:1个主角(protagonist)和{current_batch_size-1}个核心配角(supporting)"
                    else:
                        batch_requirements = f"{requirements}\n请精确生成{current_batch_size}个角色{existing_chars_context}"
                        if batch_idx == total_batches - 1:
                            batch_requirements += "\n可以包含组织或反派(antagonist)"
                        else:
                            batch_requirements += "\n主要是配角(supporting)和反派(antagonist)"
                    
                    prompt = prompt_service.get_characters_batch_prompt(
                        count=current_batch_size,  # 传递精确数量
                        time_period=world_context.get("time_period", ""),
                        location=world_context.get("location", ""),
                        atmosphere=world_context.get("atmosphere", ""),
                        rules=world_context.get("rules", ""),
                        theme=theme or project.theme or "",
                        genre=genre or project.genre or "",
                        requirements=batch_requirements
                    )
                    
                    # 流式生成
                    accumulated_text = ""
                    async for chunk in user_ai_service.generate_text_stream(
                        prompt=prompt,
                        provider=provider,
                        model=model
                    ):
                        accumulated_text += chunk
                        yield await SSEResponse.send_chunk(chunk)
                    
                    # 解析批次结果
                    cleaned_text = accumulated_text.strip()
                    # 移除markdown代码块标记
                    if cleaned_text.startswith('```json'):
                        cleaned_text = cleaned_text[7:].lstrip('\n\r')
                    elif cleaned_text.startswith('```'):
                        cleaned_text = cleaned_text[3:].lstrip('\n\r')
                    if cleaned_text.endswith('```'):
                        cleaned_text = cleaned_text[:-3].rstrip('\n\r')
                    cleaned_text = cleaned_text.strip()
                    
                    characters_data = json.loads(cleaned_text)
                    if not isinstance(characters_data, list):
                        characters_data = [characters_data]
                    
                    # 验证生成数量是否精确
                    if len(characters_data) != current_batch_size:
                        logger.warning(f"批次{batch_idx+1}生成数量不匹配: 期望{current_batch_size}, 实际{len(characters_data)}")
                        
                        # 如果数量不足,重试
                        if len(characters_data) < current_batch_size:
                            if retry_count < MAX_RETRIES - 1:
                                retry_count += 1
                                yield await SSEResponse.send_progress(
                                    f"⚠️ 生成数量不足(期望{current_batch_size},实际{len(characters_data)}),准备重试...",
                                    batch_progress,
                                    "warning"
                                )
                                continue
                            else:
                                # 最后一次重试仍不足，记录但继续使用
                                logger.warning(f"批次{batch_idx+1}多次重试后仍数量不足，使用当前结果")
                                yield await SSEResponse.send_progress(
                                    f"⚠️ 批次{batch_idx+1}生成{len(characters_data)}个（期望{current_batch_size}），继续处理",
                                    batch_progress,
                                    "warning"
                                )
                        # 如果数量过多,只取需要的数量并发出警告
                        else:
                            logger.warning(f"批次{batch_idx+1}生成过多角色({len(characters_data)}>{current_batch_size}),将只取前{current_batch_size}个")
                            yield await SSEResponse.send_progress(
                                f"⚠️ AI生成过多，截取前{current_batch_size}个角色",
                                batch_progress,
                                "warning"
                            )
                            characters_data = characters_data[:current_batch_size]
                    
                    all_characters.extend(characters_data)
                    batch_success = True
                    logger.info(f"批次{batch_idx+1}成功添加{len(characters_data)}个角色,当前总数{len(all_characters)}/{count}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"批次{batch_idx+1}解析失败(尝试{retry_count+1}/{MAX_RETRIES}): {e}")
                    retry_count += 1
                    if retry_count < MAX_RETRIES:
                        yield await SSEResponse.send_progress(
                            f"解析失败，准备重试...",
                            batch_progress,
                            "warning"
                        )
                    else:
                        yield await SSEResponse.send_progress(
                            f"批次{batch_idx+1}多次重试失败，跳过",
                            batch_progress,
                            "warning"
                        )
                except Exception as e:
                    logger.error(f"批次{batch_idx+1}生成异常(尝试{retry_count+1}/{MAX_RETRIES}): {e}")
                    retry_count += 1
                    if retry_count < MAX_RETRIES:
                        yield await SSEResponse.send_progress(
                            f"生成异常，准备重试...",
                            batch_progress,
                            "warning"
                        )
                    else:
                        yield await SSEResponse.send_progress(
                            f"批次{batch_idx+1}多次重试失败，跳过",
                            batch_progress,
                            "warning"
                        )
        
        if not all_characters:
            yield await SSEResponse.send_error("所有批次都生成失败，请重试")
            return
        
        # 保存到数据库 - 分阶段处理以保证一致性
        yield await SSEResponse.send_progress("验证角色数据...", 82)
        
        # 预处理：构建本批次所有实体的名称集合
        valid_entity_names = set()
        valid_organization_names = set()
        
        for char_data in all_characters:
            entity_name = char_data.get("name", "")
            if entity_name:
                valid_entity_names.add(entity_name)
                if char_data.get("is_organization", False):
                    valid_organization_names.add(entity_name)
        
        # 清理幻觉引用
        cleaned_count = 0
        for char_data in all_characters:
            # 清理关系数组中的无效引用
            if "relationships_array" in char_data and isinstance(char_data["relationships_array"], list):
                original_rels = char_data["relationships_array"]
                valid_rels = []
                for rel in original_rels:
                    target_name = rel.get("target_character_name", "")
                    if target_name in valid_entity_names:
                        valid_rels.append(rel)
                    else:
                        cleaned_count += 1
                        logger.debug(f"  🧹 清理无效关系引用：{char_data.get('name')} -> {target_name}")
                char_data["relationships_array"] = valid_rels
            
            # 清理组织成员关系中的无效引用
            if "organization_memberships" in char_data and isinstance(char_data["organization_memberships"], list):
                original_orgs = char_data["organization_memberships"]
                valid_orgs = []
                for org_mem in original_orgs:
                    org_name = org_mem.get("organization_name", "")
                    if org_name in valid_organization_names:
                        valid_orgs.append(org_mem)
                    else:
                        cleaned_count += 1
                        logger.debug(f"  🧹 清理无效组织引用：{char_data.get('name')} -> {org_name}")
                char_data["organization_memberships"] = valid_orgs
        
        if cleaned_count > 0:
            logger.info(f"✨ 清理了{cleaned_count}个AI幻觉引用")
            yield await SSEResponse.send_progress(f"已清理{cleaned_count}个无效引用", 84)
        
        yield await SSEResponse.send_progress("保存角色到数据库...", 85)
        
        # 第一阶段：创建所有Character记录
        created_characters = []
        character_name_to_obj = {}  # 名称到对象的映射，用于后续关系创建
        
        for char_data in all_characters:
            # 从relationships_array提取文本描述以保持向后兼容
            relationships_text = ""
            relationships_array = char_data.get("relationships_array", [])
            if relationships_array and isinstance(relationships_array, list):
                # 将关系数组转换为可读文本
                rel_descriptions = []
                for rel in relationships_array:
                    target = rel.get("target_character_name", "未知")
                    rel_type = rel.get("relationship_type", "关系")
                    desc = rel.get("description", "")
                    rel_descriptions.append(f"{target}({rel_type}): {desc}")
                relationships_text = "; ".join(rel_descriptions)
            # 兼容旧格式
            elif isinstance(char_data.get("relationships"), dict):
                relationships_text = json.dumps(char_data.get("relationships"), ensure_ascii=False)
            elif isinstance(char_data.get("relationships"), str):
                relationships_text = char_data.get("relationships")
            
            character = Character(
                project_id=project_id,
                name=char_data.get("name", "未命名角色"),
                age=char_data.get("age"),
                gender=char_data.get("gender"),
                is_organization=char_data.get("is_organization", False),
                role_type=char_data.get("role_type", "supporting"),
                personality=char_data.get("personality", ""),
                background=char_data.get("background", ""),
                appearance=char_data.get("appearance", ""),
                relationships=relationships_text,
                organization_type=char_data.get("organization_type"),
                organization_purpose=char_data.get("organization_purpose"),
                organization_members=json.dumps(char_data.get("organization_members", []), ensure_ascii=False),
                traits=json.dumps(char_data.get("traits", []), ensure_ascii=False)
            )
            db.add(character)
            created_characters.append((character, char_data))
        
        await db.flush()  # 获取所有角色的ID
        
        # 刷新并建立名称映射
        for character, _ in created_characters:
            await db.refresh(character)
            character_name_to_obj[character.name] = character
            logger.info(f"向导创建角色：{character.name} (ID: {character.id}, 是否组织: {character.is_organization})")
        
        # 为is_organization=True的角色创建Organization记录
        yield await SSEResponse.send_progress("创建组织记录...", 87)
        organization_name_to_obj = {}  # 组织名称到Organization对象的映射
        
        for character, char_data in created_characters:
            if character.is_organization:
                # 检查是否已存在Organization记录
                org_check = await db.execute(
                    select(Organization).where(Organization.character_id == character.id)
                )
                existing_org = org_check.scalar_one_or_none()
                
                if not existing_org:
                    # 创建Organization记录
                    org = Organization(
                        character_id=character.id,
                        project_id=project_id,
                        member_count=0,  # 初始为0，后续添加成员时会更新
                        power_level=char_data.get("power_level", 5),
                        location=char_data.get("location"),
                        motto=char_data.get("motto")
                    )
                    db.add(org)
                    logger.info(f"向导创建组织记录：{character.name}")
                else:
                    org = existing_org
                
                # 建立组织名称映射（无论是新建还是已存在）
                organization_name_to_obj[character.name] = org
        
        await db.flush()  # 确保Organization记录有ID
        
        # 刷新角色以获取ID
        for character, _ in created_characters:
            await db.refresh(character)
        
        # 第三阶段：创建角色间的关系
        yield await SSEResponse.send_progress("创建角色关系...", 90)
        relationships_created = 0
        
        for character, char_data in created_characters:
            # 跳过组织实体的角色关系处理（组织通过成员关系关联）
            if character.is_organization:
                continue
            
            # 处理relationships数组
            relationships_data = char_data.get("relationships_array", [])
            if not relationships_data and isinstance(char_data.get("relationships"), list):
                relationships_data = char_data.get("relationships")
            
            if relationships_data and isinstance(relationships_data, list):
                for rel in relationships_data:
                    try:
                        target_name = rel.get("target_character_name")
                        if not target_name:
                            logger.debug(f"  ⚠️  {character.name}的关系缺少target_character_name，跳过")
                            continue
                        
                        # 使用名称映射快速查找
                        target_char = character_name_to_obj.get(target_name)
                        
                        if target_char:
                            # 避免创建重复关系
                            existing_rel = await db.execute(
                                select(CharacterRelationship).where(
                                    CharacterRelationship.project_id == project_id,
                                    CharacterRelationship.character_from_id == character.id,
                                    CharacterRelationship.character_to_id == target_char.id
                                )
                            )
                            if existing_rel.scalar_one_or_none():
                                logger.debug(f"  ℹ️  关系已存在：{character.name} -> {target_name}")
                                continue
                            
                            relationship = CharacterRelationship(
                                project_id=project_id,
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
                            relationships_created += 1
                            logger.info(f"  ✅ 向导创建关系：{character.name} -> {target_name} ({rel.get('relationship_type')})")
                        else:
                            logger.warning(f"  ⚠️  目标角色不存在：{character.name} -> {target_name}（可能是AI幻觉）")
                    except Exception as e:
                        logger.warning(f"  ❌ 向导创建关系失败：{character.name} - {str(e)}")
                        continue
            
        # 第四阶段：创建组织成员关系
        yield await SSEResponse.send_progress("创建组织成员关系...", 93)
        members_created = 0
        
        for character, char_data in created_characters:
            # 跳过组织实体本身
            if character.is_organization:
                continue
            
            # 处理组织成员关系
            org_memberships = char_data.get("organization_memberships", [])
            if org_memberships and isinstance(org_memberships, list):
                for membership in org_memberships:
                    try:
                        org_name = membership.get("organization_name")
                        if not org_name:
                            logger.debug(f"  ⚠️  {character.name}的组织成员关系缺少organization_name，跳过")
                            continue
                        
                        # 使用映射快速查找组织
                        org = organization_name_to_obj.get(org_name)
                        
                        if org:
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
                            
                            members_created += 1
                            logger.info(f"  ✅ 向导添加成员：{character.name} -> {org_name} ({membership.get('position')})")
                        else:
                            # 这种情况理论上已经被预处理清理了，但保留日志以防万一
                            logger.debug(f"  ℹ️  组织引用已被清理：{character.name} -> {org_name}")
                    except Exception as e:
                        logger.warning(f"  ❌ 向导添加组织成员失败：{character.name} - {str(e)}")
                        continue
        
        logger.info(f"📊 向导数据统计：")
        logger.info(f"  - 创建角色/组织：{len(created_characters)} 个")
        logger.info(f"  - 创建组织详情：{len(organization_name_to_obj)} 个")
        logger.info(f"  - 创建角色关系：{relationships_created} 条")
        logger.info(f"  - 创建组织成员：{members_created} 条")
        
        await db.commit()
        db_committed = True
        
        # 重新提取character对象
        created_characters = [char for char, _ in created_characters]
        
        # 发送结果
        yield await SSEResponse.send_result({
            "message": f"成功生成{len(created_characters)}个角色/组织（分{total_batches}批完成）",
            "count": len(created_characters),
            "batches": total_batches,
            "characters": [
                {
                    "id": char.id,
                    "project_id": char.project_id,
                    "name": char.name,
                    "age": char.age,
                    "gender": char.gender,
                    "is_organization": char.is_organization,
                    "role_type": char.role_type,
                    "personality": char.personality,
                    "background": char.background,
                    "appearance": char.appearance,
                    "relationships": char.relationships,
                    "organization_type": char.organization_type,
                    "organization_purpose": char.organization_purpose,
                    "organization_members": char.organization_members,
                    "traits": char.traits,
                    "created_at": char.created_at.isoformat() if char.created_at else None,
                    "updated_at": char.updated_at.isoformat() if char.updated_at else None
                } for char in created_characters
            ]
        })
        
        yield await SSEResponse.send_progress("完成!", 100, "success")
        yield await SSEResponse.send_done()
        
    except GeneratorExit:
        logger.warning("角色生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("角色生成事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"角色生成失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("角色生成事务已回滚（异常）")
        yield await SSEResponse.send_error(f"生成失败: {str(e)}")


@router.post("/characters", summary="流式批量生成角色")
async def generate_characters_stream(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式批量生成角色，避免超时
    """
    return create_sse_response(characters_generator(data, db, user_ai_service))


async def outline_generator(
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """大纲生成流式生成器 - 向导固定生成前8章作为开局"""
    db_committed = False
    try:
        yield await SSEResponse.send_progress("开始生成大纲...", 5)
        
        project_id = data.get("project_id")
        # 向导固定生成8章，忽略传入的chapter_count
        chapter_count = 8
        narrative_perspective = data.get("narrative_perspective")
        target_words = data.get("target_words", 100000)
        requirements = data.get("requirements", "")
        provider = data.get("provider")
        model = data.get("model")
        
        # 8章一次性生成，不需要分批
        BATCH_SIZE = 8
        MAX_RETRIES = 3
        
        # 获取项目信息
        yield await SSEResponse.send_progress("加载项目信息...", 10)
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await SSEResponse.send_error("项目不存在", 404)
            return
        
        # 获取角色信息
        yield await SSEResponse.send_progress("加载角色信息...", 15)
        result = await db.execute(
            select(Character).where(Character.project_id == project_id)
        )
        characters = result.scalars().all()
        
        characters_info = "\n".join([
            f"- {char.name} ({'组织' if char.is_organization else '角色'}, {char.role_type}): {char.personality[:100] if char.personality else '暂无描述'}"
            for char in characters
        ])
        
        # 分批生成大纲
        yield await SSEResponse.send_progress("准备分批生成大纲...", 20)
        
        all_outlines = []
        total_batches = (chapter_count + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_idx in range(total_batches):
            start_chapter = batch_idx * BATCH_SIZE + 1
            end_chapter = min((batch_idx + 1) * BATCH_SIZE, chapter_count)
            current_batch_size = end_chapter - start_chapter + 1
            
            batch_progress = 20 + (batch_idx * 55 // total_batches)
            
            # 重试逻辑
            retry_count = 0
            batch_success = False
            
            while retry_count < MAX_RETRIES and not batch_success:
                try:
                    retry_suffix = f" (重试{retry_count}/{MAX_RETRIES})" if retry_count > 0 else ""
                    yield await SSEResponse.send_progress(
                        f"生成第{start_chapter}-{end_chapter}章大纲{retry_suffix}...",
                        batch_progress
                    )
                    
                    # 构建批次提示词 - 包含前文摘要保持故事连贯
                    previous_context = ""
                    if all_outlines:
                        previous_context = "\n\n【前文情节摘要】:\n"
                        for outline in all_outlines[-3:]:  # 只包含最近3章,避免过长
                            ch_num = outline.get("chapter_number", "?")
                            ch_title = outline.get("title", "未命名")
                            ch_summary = outline.get("summary", "")[:100]
                            previous_context += f"第{ch_num}章《{ch_title}》: {ch_summary}...\n"
                        previous_context += f"\n请确保第{start_chapter}-{end_chapter}章与前文情节自然衔接,保持故事连贯性。\n"
                    
                    # 向导专用的开局大纲要求
                    batch_requirements = f"{requirements}\n\n【重要说明】这是小说的开局部分，请生成前8章大纲，重点关注：\n"
                    batch_requirements += "1. 引入主要角色和世界观设定\n"
                    batch_requirements += "2. 建立主线冲突和故事钩子\n"
                    batch_requirements += "3. 展开初期情节，为后续发展埋下伏笔\n"
                    batch_requirements += "4. 不要试图完结故事，这只是开始部分\n"
                    batch_requirements += "5. 不要在JSON字符串值中使用中文引号（""''），请使用【】或《》标记\n"
                    
                    batch_prompt = prompt_service.get_complete_outline_prompt(
                        title=project.title,
                        theme=project.theme or "未设定",
                        genre=project.genre or "通用",
                        chapter_count=8,  # 固定8章
                        narrative_perspective=narrative_perspective,
                        target_words=target_words // 10,  # 开局约占总字数的1/10
                        time_period=project.world_time_period or "未设定",
                        location=project.world_location or "未设定",
                        atmosphere=project.world_atmosphere or "未设定",
                        rules=project.world_rules or "未设定",
                        characters_info=characters_info or "暂无角色信息",
                        requirements=batch_requirements
                    )
                    
                    # 流式生成
                    accumulated_text = ""
                    async for chunk in user_ai_service.generate_text_stream(
                        prompt=batch_prompt,
                        provider=provider,
                        model=model
                    ):
                        accumulated_text += chunk
                        yield await SSEResponse.send_chunk(chunk)
                    
                    # 解析结果
                    cleaned_text = accumulated_text.strip()
                    
                    # 移除markdown代码块标记
                    if cleaned_text.startswith('```json'):
                        cleaned_text = cleaned_text[7:].lstrip('\n\r')
                    elif cleaned_text.startswith('```'):
                        cleaned_text = cleaned_text[3:].lstrip('\n\r')
                    if cleaned_text.endswith('```'):
                        cleaned_text = cleaned_text[:-3].rstrip('\n\r')
                    cleaned_text = cleaned_text.strip()
                    
                    batch_outline_data = json.loads(cleaned_text)
                    if not isinstance(batch_outline_data, list):
                        batch_outline_data = [batch_outline_data]
                    
                    # 验证生成数量
                    if len(batch_outline_data) < current_batch_size:
                        logger.warning(f"批次{batch_idx+1}生成数量不足: 期望{current_batch_size}, 实际{len(batch_outline_data)}")
                        if retry_count < MAX_RETRIES - 1:
                            retry_count += 1
                            yield await SSEResponse.send_progress(
                                f"生成数量不足，准备重试...",
                                batch_progress,
                                "warning"
                            )
                            continue
                    
                    # 修正章节编号
                    for i, chapter_data in enumerate(batch_outline_data):
                        chapter_data["chapter_number"] = start_chapter + i
                    
                    all_outlines.extend(batch_outline_data)
                    batch_success = True
                    logger.info(f"批次{batch_idx+1}成功生成{len(batch_outline_data)}章大纲")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"大纲生成批次{batch_idx+1} JSON解析失败(尝试{retry_count+1}/{MAX_RETRIES}): {e}")
                    retry_count += 1
                    if retry_count < MAX_RETRIES:
                        yield await SSEResponse.send_progress(
                            f"解析失败，准备重试...",
                            batch_progress,
                            "warning"
                        )
                    else:
                        yield await SSEResponse.send_progress(
                            f"批次{batch_idx+1}多次重试失败，跳过",
                            batch_progress,
                            "warning"
                        )
                except Exception as e:
                    logger.error(f"批次{batch_idx+1}生成异常(尝试{retry_count+1}/{MAX_RETRIES}): {e}")
                    retry_count += 1
                    if retry_count < MAX_RETRIES:
                        yield await SSEResponse.send_progress(
                            f"生成异常，准备重试...",
                            batch_progress,
                            "warning"
                        )
                    else:
                        yield await SSEResponse.send_progress(
                            f"批次{batch_idx+1}多次重试失败，跳过",
                            batch_progress,
                            "warning"
                        )
        
        if not all_outlines:
            yield await SSEResponse.send_error("所有批次都生成失败，请重试")
            return
        
        outline_data = all_outlines
        
        # 保存到数据库
        yield await SSEResponse.send_progress("保存大纲到数据库...", 90)
        
        created_outlines = []
        for index, chapter_data in enumerate(outline_data[:chapter_count], 1):
            chapter_num = chapter_data.get("chapter_number", index)
            
            outline = Outline(
                project_id=project_id,
                title=chapter_data.get("title", f"第{chapter_num}章"),
                content=chapter_data.get("summary", chapter_data.get("content", "")),
                structure=json.dumps(chapter_data, ensure_ascii=False),
                order_index=chapter_num
            )
            db.add(outline)
            created_outlines.append(outline)
            
            chapter = Chapter(
                project_id=project_id,
                chapter_number=chapter_num,
                title=chapter_data.get("title", f"第{chapter_num}章"),
                summary=chapter_data.get("summary", chapter_data.get("content", ""))[:500] if chapter_data.get("summary") or chapter_data.get("content") else "",
                status="draft"
            )
            db.add(chapter)
        
        # 更新项目（向导固定生成8章作为开局）
        project.chapter_count = 8
        project.narrative_perspective = narrative_perspective
        project.target_words = target_words
        project.status = "writing"
        project.wizard_status = "completed"
        
        project.wizard_step = 4
        
        await db.commit()
        db_committed = True
        
        # 发送结果
        yield await SSEResponse.send_result({
            "message": f"成功生成{len(created_outlines)}章大纲",
            "count": len(created_outlines),
            "outlines": [
                {
                    "order_index": outline.order_index,
                    "title": outline.title,
                    "content": outline.content[:100] + "..." if len(outline.content) > 100 else outline.content
                } for outline in created_outlines
            ]
        })
        
        yield await SSEResponse.send_progress("完成!", 100, "success")
        yield await SSEResponse.send_done()
        
    except GeneratorExit:
        logger.warning("大纲生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("大纲生成事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"大纲生成失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("大纲生成事务已回滚（异常）")
        yield await SSEResponse.send_error(f"生成失败: {str(e)}")


@router.post("/outline", summary="流式生成完整大纲")
async def generate_outline_stream(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式生成完整大纲，避免超时
    """
    return create_sse_response(outline_generator(data, db, user_ai_service))


async def update_world_building_generator(
    project_id: str,
    data: Dict[str, Any],
    db: AsyncSession
) -> AsyncGenerator[str, None]:
    """更新世界观流式生成器"""
    db_committed = False
    try:
        yield await SSEResponse.send_progress("开始更新世界观...", 10)
        
        # 获取项目
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await SSEResponse.send_error("项目不存在", 404)
            return
        
        yield await SSEResponse.send_progress("验证数据...", 30)
        
        # 更新世界观字段
        if "time_period" in data:
            project.world_time_period = data["time_period"]
        if "location" in data:
            project.world_location = data["location"]
        if "atmosphere" in data:
            project.world_atmosphere = data["atmosphere"]
        if "rules" in data:
            project.world_rules = data["rules"]
        
        yield await SSEResponse.send_progress("保存到数据库...", 70)
        
        await db.commit()
        db_committed = True
        await db.refresh(project)
        
        # 发送结果
        yield await SSEResponse.send_result({
            "project_id": project.id,
            "time_period": project.world_time_period,
            "location": project.world_location,
            "atmosphere": project.world_atmosphere,
            "rules": project.world_rules
        })
        
        yield await SSEResponse.send_progress("完成!", 100, "success")
        yield await SSEResponse.send_done()
        
    except GeneratorExit:
        logger.warning("更新世界观生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("更新世界观事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"更新世界观失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("更新世界观事务已回滚（异常）")
        yield await SSEResponse.send_error(f"更新失败: {str(e)}")


@router.post("/world-building/{project_id}", summary="流式更新世界观")
async def update_world_building_stream(
    project_id: str,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """
    使用SSE流式更新项目的世界观信息
    请求体格式：
    {
        "time_period": "时间背景",
        "location": "地理位置",
        "atmosphere": "氛围基调",
        "rules": "世界规则"
    }
    """
    return create_sse_response(update_world_building_generator(project_id, data, db))


async def regenerate_world_building_generator(
    project_id: str,
    data: Dict[str, Any],
    db: AsyncSession,
    user_ai_service: AIService
) -> AsyncGenerator[str, None]:
    """重新生成世界观流式生成器"""
    db_committed = False
    try:
        yield await SSEResponse.send_progress("开始重新生成世界观...", 10)
        
        # 获取项目
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await SSEResponse.send_error("项目不存在", 404)
            return
        
        provider = data.get("provider")
        model = data.get("model")
        
        # 获取世界构建提示词
        yield await SSEResponse.send_progress("准备AI提示词...", 20)
        prompt = prompt_service.get_world_building_prompt(
            title=project.title,
            theme=project.theme or "",
            genre=project.genre or ""
        )
        
        # 流式调用AI
        yield await SSEResponse.send_progress("正在调用AI生成...", 30)
        
        accumulated_text = ""
        chunk_count = 0
        
        async for chunk in user_ai_service.generate_text_stream(
            prompt=prompt,
            provider=provider,
            model=model
        ):
            chunk_count += 1
            accumulated_text += chunk
            
            # 发送内容块
            yield await SSEResponse.send_chunk(chunk)
            
            # 定期更新进度
            if chunk_count % 5 == 0:
                progress = min(30 + (chunk_count // 5), 70)
                yield await SSEResponse.send_progress(f"生成中... ({len(accumulated_text)}字符)", progress)
            
            # 每20个块发送心跳
            if chunk_count % 20 == 0:
                yield await SSEResponse.send_heartbeat()
        
        # 解析结果
        yield await SSEResponse.send_progress("解析AI返回结果...", 80)
        
        world_data = {}
        try:
            cleaned_text = accumulated_text.strip()
            # 移除markdown代码块标记
            if cleaned_text.startswith('```json'):
                cleaned_text = cleaned_text[7:].lstrip('\n\r')
            elif cleaned_text.startswith('```'):
                cleaned_text = cleaned_text[3:].lstrip('\n\r')
            if cleaned_text.endswith('```'):
                cleaned_text = cleaned_text[:-3].rstrip('\n\r')
            cleaned_text = cleaned_text.strip()
            
            world_data = json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            logger.error(f"AI返回非JSON格式: {e}")
            logger.info(world_data)
            world_data = {
                "time_period": "AI返回格式错误，请重试",
                "location": "AI返回格式错误，请重试",
                "atmosphere": "AI返回格式错误，请重试",
                "rules": "AI返回格式错误，请重试"
            }
        
        # 更新项目世界观
        yield await SSEResponse.send_progress("保存到数据库...", 90)
        
        project.world_time_period = world_data.get("time_period")
        project.world_location = world_data.get("location")
        project.world_atmosphere = world_data.get("atmosphere")
        project.world_rules = world_data.get("rules")
        
        await db.commit()
        db_committed = True
        await db.refresh(project)
        
        # 发送结果
        yield await SSEResponse.send_result({
            "project_id": project.id,
            "time_period": project.world_time_period,
            "location": project.world_location,
            "atmosphere": project.world_atmosphere,
            "rules": project.world_rules
        })
        
        yield await SSEResponse.send_progress("完成!", 100, "success")
        yield await SSEResponse.send_done()
        
    except GeneratorExit:
        logger.warning("重新生成世界观生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("重新生成世界观事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"重新生成世界观失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("重新生成世界观事务已回滚（异常）")
        yield await SSEResponse.send_error(f"重新生成失败: {str(e)}")


@router.post("/world-building/{project_id}/regenerate", summary="流式重新生成世界观")
async def regenerate_world_building_stream(
    project_id: str,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用SSE流式重新生成项目的世界观
    请求体格式：
    {
        "provider": "AI提供商（可选）",
        "model": "模型名称（可选）"
    }
    """
    return create_sse_response(regenerate_world_building_generator(project_id, data, db, user_ai_service))


async def cleanup_wizard_data_generator(
    project_id: str,
    db: AsyncSession
) -> AsyncGenerator[str, None]:
    """清理向导数据流式生成器"""
    db_committed = False
    try:
        yield await SSEResponse.send_progress("开始清理向导数据...", 10)
        
        # 获取项目
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            yield await SSEResponse.send_error("项目不存在", 404)
            return
        
        # 删除相关的角色
        yield await SSEResponse.send_progress("删除角色数据...", 30)
        characters = await db.execute(
            select(Character).where(Character.project_id == project_id)
        )
        char_count = 0
        for character in characters.scalars():
            await db.delete(character)
            char_count += 1
        
        # 删除相关的大纲
        yield await SSEResponse.send_progress("删除大纲数据...", 50)
        outlines = await db.execute(
            select(Outline).where(Outline.project_id == project_id)
        )
        outline_count = 0
        for outline in outlines.scalars():
            await db.delete(outline)
            outline_count += 1
        
        # 删除相关的章节
        yield await SSEResponse.send_progress("删除章节数据...", 70)
        chapters = await db.execute(
            select(Chapter).where(Chapter.project_id == project_id)
        )
        chapter_count = 0
        for chapter in chapters.scalars():
            await db.delete(chapter)
            chapter_count += 1
        
        # 删除项目
        yield await SSEResponse.send_progress("删除项目...", 85)
        await db.delete(project)
        
        yield await SSEResponse.send_progress("提交数据库更改...", 95)
        await db.commit()
        db_committed = True
        
        # 发送结果
        yield await SSEResponse.send_result({
            "message": "项目及相关数据已清理",
            "deleted": {
                "characters": char_count,
                "outlines": outline_count,
                "chapters": chapter_count
            }
        })
        
        yield await SSEResponse.send_progress("完成!", 100, "success")
        yield await SSEResponse.send_done()
        
    except GeneratorExit:
        logger.warning("清理向导数据生成器被提前关闭")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("清理向导数据事务已回滚（GeneratorExit）")
    except Exception as e:
        logger.error(f"清理数据失败: {str(e)}")
        if not db_committed and db.in_transaction():
            await db.rollback()
            logger.info("清理向导数据事务已回滚（异常）")
        yield await SSEResponse.send_error(f"清理失败: {str(e)}")


@router.post("/cleanup/{project_id}", summary="流式清理向导数据")
async def cleanup_wizard_data_stream(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    使用SSE流式清理向导过程中创建的项目及相关数据
    用于返回上一步时清理已生成的内容
    """
    return create_sse_response(cleanup_wizard_data_generator(project_id, db))