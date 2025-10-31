"""大纲管理API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List
import json

from app.database import get_db
from app.models.outline import Outline
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.generation_history import GenerationHistory
from app.schemas.outline import (
    OutlineCreate,
    OutlineUpdate,
    OutlineResponse,
    OutlineListResponse,
    OutlineGenerateRequest,
    OutlineReorderRequest
)
from app.services.ai_service import AIService
from app.services.prompt_service import prompt_service
from app.logger import get_logger
from app.api.settings import get_user_ai_service

router = APIRouter(prefix="/outlines", tags=["大纲管理"])
logger = get_logger(__name__)


@router.post("", response_model=OutlineResponse, summary="创建大纲")
async def create_outline(
    outline: OutlineCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新的章节大纲，同时创建对应的章节记录"""
    # 验证项目是否存在
    result = await db.execute(
        select(Project).where(Project.id == outline.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 创建大纲
    db_outline = Outline(**outline.model_dump())
    db.add(db_outline)
    
    # 同步创建对应的章节记录
    chapter = Chapter(
        project_id=outline.project_id,
        chapter_number=outline.order_index,
        title=outline.title,
        summary=outline.content[:500] if len(outline.content) > 500 else outline.content,
        status="draft"
    )
    db.add(chapter)
    
    await db.commit()
    await db.refresh(db_outline)
    return db_outline


@router.get("", response_model=OutlineListResponse, summary="获取大纲列表")
async def get_outlines(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有大纲"""
    # 获取总数
    count_result = await db.execute(
        select(func.count(Outline.id)).where(Outline.project_id == project_id)
    )
    total = count_result.scalar_one()
    
    # 获取大纲列表
    result = await db.execute(
        select(Outline)
        .where(Outline.project_id == project_id)
        .order_by(Outline.order_index)
    )
    outlines = result.scalars().all()
    
    return OutlineListResponse(total=total, items=outlines)


@router.get("/project/{project_id}", response_model=OutlineListResponse, summary="获取项目的所有大纲")
async def get_project_outlines(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有大纲（路径参数版本）"""
    # 获取总数
    count_result = await db.execute(
        select(func.count(Outline.id)).where(Outline.project_id == project_id)
    )
    total = count_result.scalar_one()
    
    # 获取大纲列表
    result = await db.execute(
        select(Outline)
        .where(Outline.project_id == project_id)
        .order_by(Outline.order_index)
    )
    outlines = result.scalars().all()
    
    return OutlineListResponse(total=total, items=outlines)


@router.get("/{outline_id}", response_model=OutlineResponse, summary="获取大纲详情")
async def get_outline(
    outline_id: str,
    db: AsyncSession = Depends(get_db)
):
    """根据ID获取大纲详情"""
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    return outline


@router.put("/{outline_id}", response_model=OutlineResponse, summary="更新大纲")
async def update_outline(
    outline_id: str,
    outline_update: OutlineUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新大纲信息，同步更新对应章节和structure字段"""
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    # 更新字段
    update_data = outline_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(outline, field, value)
    
    # 如果修改了content或title，同步更新structure字段
    if 'content' in update_data or 'title' in update_data:
        try:
            # 尝试解析现有的structure
            if outline.structure:
                structure_data = json.loads(outline.structure)
            else:
                structure_data = {}
            
            # 更新structure中的对应字段
            if 'title' in update_data:
                structure_data['title'] = outline.title
            if 'content' in update_data:
                structure_data['summary'] = outline.content
                structure_data['content'] = outline.content
            
            # 保存更新后的structure
            outline.structure = json.dumps(structure_data, ensure_ascii=False)
            logger.info(f"同步更新大纲 {outline_id} 的structure字段")
        except json.JSONDecodeError:
            logger.warning(f"大纲 {outline_id} 的structure字段格式错误，跳过更新")
    
    # 同步更新对应的章节标题和摘要
    if 'title' in update_data or 'content' in update_data:
        chapter_result = await db.execute(
            select(Chapter).where(
                Chapter.project_id == outline.project_id,
                Chapter.chapter_number == outline.order_index
            )
        )
        chapter = chapter_result.scalar_one_or_none()
        
        if chapter:
            if 'title' in update_data:
                chapter.title = outline.title
            if 'content' in update_data:
                # 更新章节摘要（取content前500字符）
                chapter.summary = outline.content[:500] if len(outline.content) > 500 else outline.content
            logger.info(f"同步更新章节 {chapter.id} 的标题和摘要")
        else:
            logger.warning(f"未找到对应的章节记录 (order_index={outline.order_index})")
    
    await db.commit()
    await db.refresh(outline)
    return outline


@router.delete("/{outline_id}", summary="删除大纲")
async def delete_outline(
    outline_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除大纲，同步删除章节，并重新排序后续项"""
    result = await db.execute(
        select(Outline).where(Outline.id == outline_id)
    )
    outline = result.scalar_one_or_none()
    
    if not outline:
        raise HTTPException(status_code=404, detail="大纲不存在")
    
    project_id = outline.project_id
    deleted_order = outline.order_index
    
    # 删除对应的章节
    await db.execute(
        delete(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == deleted_order
        )
    )
    
    # 删除大纲
    await db.delete(outline)
    
    # 重新排序后续的大纲和章节（序号-1）
    result = await db.execute(
        select(Outline).where(
            Outline.project_id == project_id,
            Outline.order_index > deleted_order
        )
    )
    subsequent_outlines = result.scalars().all()
    
    for o in subsequent_outlines:
        old_order = o.order_index
        o.order_index -= 1
        
        # 同步更新对应的章节
        chapter_result = await db.execute(
            select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == old_order
            )
        )
        chapter = chapter_result.scalar_one_or_none()
        if chapter:
            chapter.chapter_number = old_order - 1
    
    await db.commit()
    
    return {"message": "大纲删除成功"}


@router.post("/reorder", summary="批量重排序大纲")
async def reorder_outlines(
    request: OutlineReorderRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    批量调整大纲顺序，同步更新章节序号
    
    策略：先收集所有变更，最后一次性提交，避免临时冲突
    """
    try:
        # 第一步：收集所有大纲和对应的章节
        outline_chapter_map = {}  # {outline_id: (outline, chapter, old_order, new_order)}
        
        for item in request.orders:
            outline_id = item.id
            new_order = item.order_index
            
            # 获取大纲
            result = await db.execute(
                select(Outline).where(Outline.id == outline_id)
            )
            outline = result.scalar_one_or_none()
            
            if not outline:
                logger.warning(f"大纲 {outline_id} 不存在，跳过")
                continue
            
            old_order = outline.order_index
            
            # 获取对应的章节（通过旧的chapter_number匹配）
            chapter_result = await db.execute(
                select(Chapter).where(
                    Chapter.project_id == outline.project_id,
                    Chapter.chapter_number == old_order
                )
            )
            chapter = chapter_result.first()
            chapter_obj = chapter[0] if chapter else None
            
            outline_chapter_map[outline_id] = (outline, chapter_obj, old_order, new_order)
        
        # 第二步：批量更新所有大纲和章节
        updated_outlines = 0
        updated_chapters = 0
        
        for outline_id, (outline, chapter, old_order, new_order) in outline_chapter_map.items():
            # 更新大纲
            outline.order_index = new_order
            updated_outlines += 1
            
            # 更新章节
            if chapter:
                chapter.chapter_number = new_order
                chapter.title = outline.title  # 同步更新标题
                updated_chapters += 1
            else:
                logger.warning(f"章节 {old_order} 不存在，跳过")
        
        # 第三步：一次性提交所有更改
        await db.commit()
        
        logger.info(f"重排序成功：更新了 {updated_outlines} 个大纲，{updated_chapters} 个章节")
        
        return {
            "message": "重排序成功",
            "updated_outlines": updated_outlines,
            "updated_chapters": updated_chapters
        }
        
    except Exception as e:
        await db.rollback()
        logger.error(f"重排序失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重排序失败: {str(e)}")


@router.post("/generate", response_model=OutlineListResponse, summary="AI生成/续写大纲")
async def generate_outline(
    request: OutlineGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用AI生成或续写小说大纲 - 智能模式
    
    支持三种模式：
    - auto: 自动判断（无大纲→新建，有大纲→续写）
    - new: 强制全新生成
    - continue: 强制续写模式
    """
    # 验证项目是否存在
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    try:
        # 获取现有大纲（强制从数据库获取最新数据，包括用户手动修改的内容）
        existing_result = await db.execute(
            select(Outline)
            .where(Outline.project_id == request.project_id)
            .order_by(Outline.order_index)
            .execution_options(populate_existing=True)
        )
        existing_outlines = existing_result.scalars().all()
        
        # 判断实际执行模式
        actual_mode = request.mode
        if actual_mode == "auto":
            actual_mode = "continue" if existing_outlines else "new"
            logger.info(f"自动判断模式：{'续写' if existing_outlines else '新建'}")
        
        # 模式：全新生成
        if actual_mode == "new":
            return await _generate_new_outline(
                request, project, db, user_ai_service
            )
        
        # 模式：续写
        elif actual_mode == "continue":
            if not existing_outlines:
                raise HTTPException(
                    status_code=400,
                    detail="续写模式需要已有大纲，当前项目没有大纲"
                )
            
            return await _continue_outline(
                request, project, existing_outlines, db, user_ai_service
            )
        
        else:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的模式: {request.mode}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成大纲失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成大纲失败: {str(e)}")


async def _generate_new_outline(
    request: OutlineGenerateRequest,
    project: Project,
    db: AsyncSession,
    user_ai_service: AIService
) -> OutlineListResponse:
    """全新生成大纲"""
    logger.info(f"全新生成大纲 - 项目: {project.id}, keep_existing: {request.keep_existing}")
    
    # 获取角色信息
    characters_result = await db.execute(
        select(Character).where(Character.project_id == project.id)
    )
    characters = characters_result.scalars().all()
    characters_info = "\n".join([
        f"- {char.name} ({'组织' if char.is_organization else '角色'}, {char.role_type}): "
        f"{char.personality[:100] if char.personality else '暂无描述'}"
        for char in characters
    ])
    
    # 使用完整提示词
    prompt = prompt_service.get_complete_outline_prompt(
        title=project.title,
        theme=request.theme or project.theme or "未设定",
        genre=request.genre or project.genre or "通用",
        chapter_count=request.chapter_count,
        narrative_perspective=request.narrative_perspective,
        target_words=request.target_words,
        time_period=project.world_time_period or "未设定",
        location=project.world_location or "未设定",
        atmosphere=project.world_atmosphere or "未设定",
        rules=project.world_rules or "未设定",
        characters_info=characters_info or "暂无角色信息",
        requirements=request.requirements or ""
    )
    
    # 调用AI
    ai_response = await user_ai_service.generate_text(
        prompt=prompt,
        provider=request.provider,
        model=request.model
    )
    
    # 解析响应
    outline_data = _parse_ai_response(ai_response)
    
    # 全新生成模式：必须删除旧大纲和章节
    # 注意：这是"new"模式的核心逻辑，应该始终删除旧数据
    logger.info(f"删除项目 {project.id} 的旧大纲和章节")
    await db.execute(
        delete(Outline).where(Outline.project_id == project.id)
    )
    await db.execute(
        delete(Chapter).where(Chapter.project_id == project.id)
    )
    
    # 保存新大纲
    outlines = await _save_outlines(
        project.id, outline_data, db, start_index=1
    )
    
    # 记录历史
    history = GenerationHistory(
        project_id=project.id,
        prompt=prompt,
        generated_content=ai_response,
        model=request.model or "default"
    )
    db.add(history)
    
    await db.commit()
    
    for outline in outlines:
        await db.refresh(outline)
    
    logger.info(f"全新生成完成 - {len(outlines)} 章")
    return OutlineListResponse(total=len(outlines), items=outlines)


async def _continue_outline(
    request: OutlineGenerateRequest,
    project: Project,
    existing_outlines: List[Outline],
    db: AsyncSession,
    user_ai_service: AIService
) -> OutlineListResponse:
    """续写大纲"""
    logger.info(f"续写大纲 - 项目: {project.id}, 已有: {len(existing_outlines)} 章")
    
    # 分析已有大纲
    current_chapter_count = len(existing_outlines)
    last_chapter_number = existing_outlines[-1].order_index
    
    # 获取最近2章的剧情
    recent_outlines = existing_outlines[-2:] if len(existing_outlines) >= 2 else existing_outlines
    recent_plot = "\n".join([
        f"第{o.order_index}章《{o.title}》: {o.content}"
        for o in recent_outlines
    ])
    # logger.debug(f"最近三章内容：{recent_plot}")
    # 全部章节概览
    all_chapters_brief = "\n".join([
        f"第{o.order_index}章: {o.title}"
        for o in existing_outlines
    ])
    
    # 获取角色信息
    characters_result = await db.execute(
        select(Character).where(Character.project_id == project.id)
    )
    characters = characters_result.scalars().all()
    characters_info = "\n".join([
        f"- {char.name} ({'组织' if char.is_organization else '角色'}, {char.role_type}): "
        f"{char.personality[:100] if char.personality else '暂无描述'}"
        for char in characters
    ])
    
    # 情节阶段指导
    stage_instructions = {
        "development": "继续展开情节，深化角色关系，推进主线冲突",
        "climax": "进入故事高潮，矛盾激化，关键冲突爆发",
        "ending": "解决主要冲突，收束伏笔，给出结局"
    }
    stage_instruction = stage_instructions.get(request.plot_stage, "")
    
    # 使用标准续写提示词模板
    prompt = prompt_service.get_outline_continue_prompt(
        title=project.title,
        theme=request.theme or project.theme or "未设定",
        genre=request.genre or project.genre or "通用",
        narrative_perspective=request.narrative_perspective,
        chapter_count=request.chapter_count,
        time_period=project.world_time_period or "未设定",
        location=project.world_location or "未设定",
        atmosphere=project.world_atmosphere or "未设定",
        rules=project.world_rules or "未设定",
        characters_info=characters_info or "暂无角色信息",
        current_chapter_count=current_chapter_count,
        all_chapters_brief=all_chapters_brief,
        recent_plot=recent_plot,
        plot_stage_instruction=stage_instruction,
        start_chapter=last_chapter_number + 1,
        story_direction=request.story_direction or "自然延续",
        requirements=request.requirements or ""
    )
    
    # 调用AI
    ai_response = await user_ai_service.generate_text(
        prompt=prompt,
        provider=request.provider,
        model=request.model
    )
    
    # 解析响应
    outline_data = _parse_ai_response(ai_response)
    
    # 保存续写的大纲
    new_outlines = await _save_outlines(
        project.id, outline_data, db, start_index=last_chapter_number + 1
    )
    
    # 记录历史
    history = GenerationHistory(
        project_id=project.id,
        prompt=prompt,
        generated_content=ai_response,
        model=request.model or "default"
    )
    db.add(history)
    
    await db.commit()
    
    for outline in new_outlines:
        await db.refresh(outline)
    
    # 返回所有大纲（包括旧的和新的）
    all_result = await db.execute(
        select(Outline)
        .where(Outline.project_id == project.id)
        .order_by(Outline.order_index)
    )
    all_outlines = all_result.scalars().all()
    
    logger.info(f"续写完成 - 新增 {len(new_outlines)} 章，总计 {len(all_outlines)} 章")
    return OutlineListResponse(total=len(all_outlines), items=all_outlines)


def _parse_ai_response(ai_response: str) -> list:
    """解析AI响应为章节数据列表"""
    try:
        # 清理响应文本
        cleaned_text = ai_response.strip()
        if cleaned_text.startswith('```json'):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith('```'):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
        
        outline_data = json.loads(cleaned_text)
        
        # 确保是列表格式
        if not isinstance(outline_data, list):
            # 如果是对象，尝试提取chapters字段
            if isinstance(outline_data, dict):
                outline_data = outline_data.get("chapters", [outline_data])
            else:
                outline_data = [outline_data]
        
        return outline_data
        
    except json.JSONDecodeError as e:
        logger.error(f"AI响应解析失败: {e}")
        # 返回一个包含原始内容的章节
        return [{
            "title": "AI生成的大纲",
            "content": ai_response[:1000],
            "summary": ai_response[:1000]
        }]


async def _save_outlines(
    project_id: str,
    outline_data: list,
    db: AsyncSession,
    start_index: int = 1
) -> List[Outline]:
    """保存大纲到数据库"""
    outlines = []
    
    for idx, chapter_data in enumerate(outline_data):
        order_idx = chapter_data.get("chapter_number", start_index + idx)
        title = chapter_data.get("title", f"第{order_idx}章")
        
        # 优先使用summary，其次content
        content = chapter_data.get("summary") or chapter_data.get("content", "")
        
        # 如果有额外信息，添加到内容中
        if "key_events" in chapter_data:
            content += f"\n\n关键事件：" + "、".join(chapter_data["key_events"])
        if "characters_involved" in chapter_data:
            content += f"\n涉及角色：" + "、".join(chapter_data["characters_involved"])
        
        # 创建大纲
        outline = Outline(
            project_id=project_id,
            title=title,
            content=content,
            structure=json.dumps(chapter_data, ensure_ascii=False),
            order_index=order_idx
        )
        db.add(outline)
        outlines.append(outline)
        
        # 同步创建章节记录
        chapter = Chapter(
            project_id=project_id,
            chapter_number=order_idx,
            title=title,
            summary=content[:500] if len(content) > 500 else content,
            status="draft"
        )
        db.add(chapter)
    
    return outlines