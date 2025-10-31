"""章节管理API"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import json
import asyncio

from app.database import get_db
from app.models.chapter import Chapter
from app.models.project import Project
from app.models.outline import Outline
from app.models.character import Character
from app.models.generation_history import GenerationHistory
from app.schemas.chapter import (
    ChapterCreate,
    ChapterUpdate,
    ChapterResponse,
    ChapterListResponse
)
from app.services.ai_service import AIService
from app.services.prompt_service import prompt_service
from app.logger import get_logger
from app.api.settings import get_user_ai_service

router = APIRouter(prefix="/chapters", tags=["章节管理"])
logger = get_logger(__name__)


@router.post("", response_model=ChapterResponse, summary="创建章节")
async def create_chapter(
    chapter: ChapterCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新的章节"""
    # 验证项目是否存在
    result = await db.execute(
        select(Project).where(Project.id == chapter.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 计算字数
    word_count = len(chapter.content)
    
    db_chapter = Chapter(
        **chapter.model_dump(),
        word_count=word_count
    )
    db.add(db_chapter)
    
    # 更新项目的当前字数
    project.current_words = project.current_words + word_count
    
    await db.commit()
    await db.refresh(db_chapter)
    return db_chapter


@router.get("/project/{project_id}", response_model=ChapterListResponse, summary="获取项目的所有章节")
async def get_project_chapters(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有章节（路径参数版本）"""
    # 获取总数
    count_result = await db.execute(
        select(func.count(Chapter.id)).where(Chapter.project_id == project_id)
    )
    total = count_result.scalar_one()
    
    # 获取章节列表
    result = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.chapter_number)
    )
    chapters = result.scalars().all()
    
    return ChapterListResponse(total=total, items=chapters)


@router.get("/{chapter_id}", response_model=ChapterResponse, summary="获取章节详情")
async def get_chapter(
    chapter_id: str,
    db: AsyncSession = Depends(get_db)
):
    """根据ID获取章节详情"""
    result = await db.execute(
        select(Chapter).where(Chapter.id == chapter_id)
    )
    chapter = result.scalar_one_or_none()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    return chapter


@router.put("/{chapter_id}", response_model=ChapterResponse, summary="更新章节")
async def update_chapter(
    chapter_id: str,
    chapter_update: ChapterUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新章节信息"""
    result = await db.execute(
        select(Chapter).where(Chapter.id == chapter_id)
    )
    chapter = result.scalar_one_or_none()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    # 记录旧字数
    old_word_count = chapter.word_count or 0
    
    # 更新字段
    update_data = chapter_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(chapter, field, value)
    
    # 如果内容更新了，重新计算字数
    if "content" in update_data and chapter.content:
        new_word_count = len(chapter.content)
        chapter.word_count = new_word_count
        
        # 更新项目字数
        result = await db.execute(
            select(Project).where(Project.id == chapter.project_id)
        )
        project = result.scalar_one_or_none()
        if project:
            project.current_words = project.current_words - old_word_count + new_word_count
    
    await db.commit()
    await db.refresh(chapter)
    return chapter


@router.delete("/{chapter_id}", summary="删除章节")
async def delete_chapter(
    chapter_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除章节"""
    result = await db.execute(
        select(Chapter).where(Chapter.id == chapter_id)
    )
    chapter = result.scalar_one_or_none()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    # 更新项目字数
    result = await db.execute(
        select(Project).where(Project.id == chapter.project_id)
    )
    project = result.scalar_one_or_none()
    if project:
        project.current_words = max(0, project.current_words - chapter.word_count)
    
    await db.delete(chapter)
    await db.commit()
    
    return {"message": "章节删除成功"}


async def check_prerequisites(db: AsyncSession, chapter: Chapter) -> tuple[bool, str, list[Chapter]]:
    """
    检查章节前置条件
    
    Args:
        db: 数据库会话
        chapter: 当前章节
        
    Returns:
        (可否生成, 错误信息, 前置章节列表)
    """
    # 如果是第一章，无需检查前置
    if chapter.chapter_number == 1:
        return True, "", []
    
    # 查询所有前置章节（序号小于当前章节的）
    result = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == chapter.project_id)
        .where(Chapter.chapter_number < chapter.chapter_number)
        .order_by(Chapter.chapter_number)
    )
    previous_chapters = result.scalars().all()
    
    # 检查是否所有前置章节都有内容
    incomplete_chapters = [
        ch for ch in previous_chapters
        if not ch.content or ch.content.strip() == ""
    ]
    
    if incomplete_chapters:
        missing_numbers = [str(ch.chapter_number) for ch in incomplete_chapters]
        error_msg = f"需要先完成前置章节：第 {', '.join(missing_numbers)} 章"
        return False, error_msg, previous_chapters
    
    return True, "", previous_chapters


@router.get("/{chapter_id}/can-generate", summary="检查章节是否可以生成")
async def check_can_generate(
    chapter_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    检查章节是否满足生成条件
    返回可生成状态和前置章节信息
    """
    # 获取章节
    result = await db.execute(
        select(Chapter).where(Chapter.id == chapter_id)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    # 检查前置条件
    can_generate, error_msg, previous_chapters = await check_prerequisites(db, chapter)
    
    # 构建前置章节信息
    previous_info = [
        {
            "id": ch.id,
            "chapter_number": ch.chapter_number,
            "title": ch.title,
            "has_content": bool(ch.content and ch.content.strip()),
            "word_count": ch.word_count or 0
        }
        for ch in previous_chapters
    ]
    
    return {
        "can_generate": can_generate,
        "reason": error_msg if not can_generate else "",
        "previous_chapters": previous_info,
        "chapter_number": chapter.chapter_number
    }


@router.post("/{chapter_id}/generate", summary="AI创作章节内容")
async def generate_chapter_content(
    chapter_id: str,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    根据大纲、前置章节内容和项目信息AI创作章节完整内容
    要求：必须按顺序生成，确保前置章节都已完成
    """
    # 获取章节
    result = await db.execute(
        select(Chapter).where(Chapter.id == chapter_id)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    # 检查前置条件
    can_generate, error_msg, previous_chapters = await check_prerequisites(db, chapter)
    if not can_generate:
        raise HTTPException(status_code=400, detail=error_msg)
    
    try:
        # 获取项目信息
        project_result = await db.execute(
            select(Project).where(Project.id == chapter.project_id)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
        
        # 获取对应的大纲（使用新的查询确保获取最新数据）
        outline_result = await db.execute(
            select(Outline)
            .where(Outline.project_id == chapter.project_id)
            .where(Outline.order_index == chapter.chapter_number)
            .execution_options(populate_existing=True)
        )
        outline = outline_result.scalar_one_or_none()
        
        # 获取所有大纲用于上下文（使用新的查询确保获取最新数据）
        all_outlines_result = await db.execute(
            select(Outline)
            .where(Outline.project_id == chapter.project_id)
            .order_by(Outline.order_index)
            .execution_options(populate_existing=True)
        )
        all_outlines = all_outlines_result.scalars().all()
        outlines_context = "\n".join([
            f"第{o.order_index}章 {o.title}: {o.content[:100]}..."
            for o in all_outlines
        ])
        
        # 获取角色信息
        characters_result = await db.execute(
            select(Character).where(Character.project_id == chapter.project_id)
        )
        characters = characters_result.scalars().all()
        characters_info = "\n".join([
            f"- {c.name}({'组织' if c.is_organization else '角色'}, {c.role_type}): {c.personality[:100] if c.personality else ''}"
            for c in characters
        ])
        
        # 构建前置章节内容上下文（如果有前置章节）
        previous_content = ""
        if previous_chapters:
            # Token控制：保留最近3章的完整内容，早期章节使用摘要
            recent_chapters = previous_chapters[-3:] if len(previous_chapters) > 3 else previous_chapters
            early_chapters = previous_chapters[:-3] if len(previous_chapters) > 3 else []
            
            # 早期章节摘要
            if early_chapters:
                early_summary = "【前期剧情概要】\n" + "\n".join([
                    f"第{ch.chapter_number}章《{ch.title}》：{ch.content[:200] if ch.content else ''}..."
                    for ch in early_chapters
                ])
                previous_content += early_summary + "\n\n"
            
            # 最近章节完整内容
            if recent_chapters:
                recent_content = "【最近章节完整内容】\n" + "\n\n".join([
                    f"=== 第{ch.chapter_number}章：{ch.title} ===\n{ch.content}"
                    for ch in recent_chapters
                ])
                previous_content += recent_content
            
            logger.info(f"构建前置上下文：{len(early_chapters)}章摘要 + {len(recent_chapters)}章完整内容")
        
        # 根据是否有前置内容选择不同的提示词
        if previous_content:
            # 使用带上下文的提示词
            prompt = prompt_service.get_chapter_generation_with_context_prompt(
                title=project.title,
                theme=project.theme or '',
                genre=project.genre or '',
                narrative_perspective=project.narrative_perspective or '第三人称',
                time_period=project.world_time_period or '未设定',
                location=project.world_location or '未设定',
                atmosphere=project.world_atmosphere or '未设定',
                rules=project.world_rules or '未设定',
                characters_info=characters_info or '暂无角色信息',
                outlines_context=outlines_context,
                previous_content=previous_content,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.title,
                chapter_outline=outline.content if outline else chapter.summary or '暂无大纲'
            )
        else:
            # 第一章，使用原有提示词
            prompt = prompt_service.get_chapter_generation_prompt(
                title=project.title,
                theme=project.theme or '',
                genre=project.genre or '',
                narrative_perspective=project.narrative_perspective or '第三人称',
                time_period=project.world_time_period or '未设定',
                location=project.world_location or '未设定',
                atmosphere=project.world_atmosphere or '未设定',
                rules=project.world_rules or '未设定',
                characters_info=characters_info or '暂无角色信息',
                outlines_context=outlines_context,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.title,
                chapter_outline=outline.content if outline else chapter.summary or '暂无大纲'
            )
        
        logger.info(f"开始AI创作章节 {chapter_id}")
        
        # 调用AI生成
        ai_content = await user_ai_service.generate_text(
            prompt=prompt
        )
        
        # 更新章节内容
        old_word_count = chapter.word_count or 0
        chapter.content = ai_content
        new_word_count = len(ai_content)
        chapter.word_count = new_word_count
        chapter.status = "completed"
        
        # 更新项目字数
        project.current_words = project.current_words - old_word_count + new_word_count
        
        # 记录生成历史
        history = GenerationHistory(
            project_id=chapter.project_id,
            chapter_id=chapter.id,
            prompt=f"创作章节: 第{chapter.chapter_number}章 {chapter.title}",
            generated_content=ai_content[:500] if len(ai_content) > 500 else ai_content,
            model="default"
        )
        db.add(history)
        
        await db.commit()
        await db.refresh(chapter)
        
        logger.info(f"成功创作章节 {chapter_id}，共 {new_word_count} 字")
        
        return {"content": ai_content}
        
    except Exception as e:
        logger.error(f"创作章节失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创作章节失败: {str(e)}")

@router.post("/{chapter_id}/generate-stream", summary="AI创作章节内容（流式）")
async def generate_chapter_content_stream(
    chapter_id: str,
    request: Request,
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    根据大纲、前置章节内容和项目信息AI创作章节完整内容（流式返回）
    要求：必须按顺序生成，确保前置章节都已完成
    
    注意：此函数不使用依赖注入的db，而是在生成器内部创建独立的数据库会话
    以避免流式响应期间的连接泄漏问题
    """
    # 预先验证章节存在性（使用临时会话）
    async for temp_db in get_db(request):
        try:
            result = await temp_db.execute(
                select(Chapter).where(Chapter.id == chapter_id)
            )
            chapter = result.scalar_one_or_none()
            if not chapter:
                raise HTTPException(status_code=404, detail="章节不存在")
            
            # 检查前置条件
            can_generate, error_msg, previous_chapters = await check_prerequisites(temp_db, chapter)
            if not can_generate:
                raise HTTPException(status_code=400, detail=error_msg)
            
            # 保存前置章节数据供生成器使用
            previous_chapters_data = [
                {
                    'id': ch.id,
                    'chapter_number': ch.chapter_number,
                    'title': ch.title,
                    'content': ch.content
                }
                for ch in previous_chapters
            ]
        finally:
            await temp_db.close()
        break
    
    async def event_generator():
        # 在生成器内部创建独立的数据库会话
        db_session = None
        db_committed = False
        try:
            # 创建新的数据库会话
            async for db_session in get_db(request):
                # 重新获取章节信息
                chapter_result = await db_session.execute(
                    select(Chapter).where(Chapter.id == chapter_id)
                )
                current_chapter = chapter_result.scalar_one_or_none()
                if not current_chapter:
                    yield f"data: {json.dumps({'type': 'error', 'error': '章节不存在'}, ensure_ascii=False)}\n\n"
                    return
            
                # 获取项目信息
                project_result = await db_session.execute(
                    select(Project).where(Project.id == current_chapter.project_id)
                )
                project = project_result.scalar_one_or_none()
                if not project:
                    yield f"data: {json.dumps({'type': 'error', 'error': '项目不存在'}, ensure_ascii=False)}\n\n"
                    return
                
                # 获取对应的大纲
                outline_result = await db_session.execute(
                    select(Outline)
                    .where(Outline.project_id == current_chapter.project_id)
                    .where(Outline.order_index == current_chapter.chapter_number)
                    .execution_options(populate_existing=True)
                )
                outline = outline_result.scalar_one_or_none()
                
                # 获取所有大纲用于上下文
                all_outlines_result = await db_session.execute(
                    select(Outline)
                    .where(Outline.project_id == current_chapter.project_id)
                    .order_by(Outline.order_index)
                    .execution_options(populate_existing=True)
                )
                all_outlines = all_outlines_result.scalars().all()
                outlines_context = "\n".join([
                    f"第{o.order_index}章 {o.title}: {o.content[:100]}..."
                    for o in all_outlines
                ])
                
                # 获取角色信息
                characters_result = await db_session.execute(
                    select(Character).where(Character.project_id == current_chapter.project_id)
                )
                characters = characters_result.scalars().all()
                characters_info = "\n".join([
                    f"- {c.name}({'组织' if c.is_organization else '角色'}, {c.role_type}): {c.personality[:100] if c.personality else ''}"
                    for c in characters
                ])
                
                # 构建前置章节内容上下文（使用之前保存的数据）
                previous_content = ""
                if previous_chapters_data:
                    recent_chapters = previous_chapters_data[-3:] if len(previous_chapters_data) > 3 else previous_chapters_data
                    early_chapters = previous_chapters_data[:-3] if len(previous_chapters_data) > 3 else []
                    
                    if early_chapters:
                        early_summary = "【前期剧情概要】\n" + "\n".join([
                            f"第{ch['chapter_number']}章《{ch['title']}》：{ch['content'][:200] if ch['content'] else ''}..."
                            for ch in early_chapters
                        ])
                        previous_content += early_summary + "\n\n"
                    
                    if recent_chapters:
                        recent_content = "【最近章节完整内容】\n" + "\n\n".join([
                            f"=== 第{ch['chapter_number']}章：{ch['title']} ===\n{ch['content']}"
                            for ch in recent_chapters
                        ])
                        previous_content += recent_content
                    
                    logger.info(f"构建前置上下文：{len(early_chapters)}章摘要 + {len(recent_chapters)}章完整内容")
            
                # 发送开始事件
                yield f"data: {json.dumps({'type': 'start', 'message': '开始AI创作...'}, ensure_ascii=False)}\n\n"
                
                # 根据是否有前置内容选择不同的提示词
                if previous_content:
                    prompt = prompt_service.get_chapter_generation_with_context_prompt(
                        title=project.title,
                        theme=project.theme or '',
                        genre=project.genre or '',
                        narrative_perspective=project.narrative_perspective or '第三人称',
                        time_period=project.world_time_period or '未设定',
                        location=project.world_location or '未设定',
                        atmosphere=project.world_atmosphere or '未设定',
                        rules=project.world_rules or '未设定',
                        characters_info=characters_info or '暂无角色信息',
                        outlines_context=outlines_context,
                        previous_content=previous_content,
                        chapter_number=current_chapter.chapter_number,
                        chapter_title=current_chapter.title,
                        chapter_outline=outline.content if outline else current_chapter.summary or '暂无大纲'
                    )
                else:
                    prompt = prompt_service.get_chapter_generation_prompt(
                        title=project.title,
                        theme=project.theme or '',
                        genre=project.genre or '',
                        narrative_perspective=project.narrative_perspective or '第三人称',
                        time_period=project.world_time_period or '未设定',
                        location=project.world_location or '未设定',
                        atmosphere=project.world_atmosphere or '未设定',
                        rules=project.world_rules or '未设定',
                        characters_info=characters_info or '暂无角色信息',
                        outlines_context=outlines_context,
                        chapter_number=current_chapter.chapter_number,
                        chapter_title=current_chapter.title,
                        chapter_outline=outline.content if outline else current_chapter.summary or '暂无大纲'
                    )
                
                logger.info(f"开始AI流式创作章节 {chapter_id}")
                
                # 流式生成内容
                full_content = ""
                async for chunk in user_ai_service.generate_text_stream(prompt=prompt):
                    full_content += chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)  # 让出控制权
                
                # 更新章节内容到数据库
                old_word_count = current_chapter.word_count or 0
                current_chapter.content = full_content
                new_word_count = len(full_content)
                current_chapter.word_count = new_word_count
                current_chapter.status = "completed"
                
                # 更新项目字数
                project.current_words = project.current_words - old_word_count + new_word_count
                
                # 记录生成历史
                history = GenerationHistory(
                    project_id=current_chapter.project_id,
                    chapter_id=current_chapter.id,
                    prompt=f"创作章节: 第{current_chapter.chapter_number}章 {current_chapter.title}",
                    generated_content=full_content[:500] if len(full_content) > 500 else full_content,
                    model="default"
                )
                db_session.add(history)
                
                await db_session.commit()
                db_committed = True
                await db_session.refresh(current_chapter)
                
                logger.info(f"成功创作章节 {chapter_id}，共 {new_word_count} 字")
                
                # 发送完成事件
                yield f"data: {json.dumps({'type': 'done', 'message': '创作完成', 'word_count': new_word_count}, ensure_ascii=False)}\n\n"
                
                break  # 退出async for db_session循环
        
        except GeneratorExit:
            # SSE连接断开
            logger.warning("章节生成器被提前关闭（SSE断开）")
            if db_session and not db_committed:
                try:
                    if db_session.in_transaction():
                        await db_session.rollback()
                        logger.info("章节生成事务已回滚（GeneratorExit）")
                except Exception as e:
                    logger.error(f"GeneratorExit回滚失败: {str(e)}")
        except Exception as e:
            logger.error(f"流式创作章节失败: {str(e)}")
            if db_session and not db_committed:
                try:
                    if db_session.in_transaction():
                        await db_session.rollback()
                        logger.info("章节生成事务已回滚（异常）")
                except Exception as rollback_error:
                    logger.error(f"回滚失败: {str(rollback_error)}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            # 确保数据库会话被正确关闭
            if db_session:
                try:
                    # 最后检查：确保没有未提交的事务
                    if not db_committed and db_session.in_transaction():
                        await db_session.rollback()
                        logger.warning("在finally中发现未提交事务，已回滚")
                    
                    await db_session.close()
                    logger.info("数据库会话已关闭")
                except Exception as close_error:
                    logger.error(f"关闭数据库会话失败: {str(close_error)}")
                    # 强制关闭
                    try:
                        await db_session.close()
                    except:
                        pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
