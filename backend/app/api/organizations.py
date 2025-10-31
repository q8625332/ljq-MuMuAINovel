"""组织管理API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List

from app.database import get_db
from app.models.relationship import Organization, OrganizationMember
from app.models.character import Character
from app.schemas.relationship import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationDetailResponse,
    OrganizationMemberCreate,
    OrganizationMemberUpdate,
    OrganizationMemberResponse,
    OrganizationMemberDetailResponse
)
from app.logger import get_logger

router = APIRouter(prefix="/organizations", tags=["组织管理"])
logger = get_logger(__name__)


@router.get("/project/{project_id}", response_model=List[OrganizationDetailResponse], summary="获取项目的所有组织")
async def get_project_organizations(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取项目中的所有组织及其详情
    
    返回组织的基本信息和统计数据
    """
    result = await db.execute(
        select(Organization).where(Organization.project_id == project_id)
    )
    organizations = result.scalars().all()
    
    # 获取每个组织的角色信息
    org_list = []
    for org in organizations:
        char_result = await db.execute(
            select(Character).where(Character.id == org.character_id)
        )
        char = char_result.scalar_one_or_none()
        
        if char:
            org_list.append(OrganizationDetailResponse(
                id=org.id,
                character_id=org.character_id,
                name=char.name,
                type=char.organization_type,
                purpose=char.organization_purpose,
                member_count=org.member_count,
                power_level=org.power_level,
                location=org.location,
                motto=org.motto,
                color=org.color
            ))
    
    logger.info(f"获取项目 {project_id} 的组织列表，共 {len(org_list)} 个")
    return org_list


@router.get("/{org_id}", response_model=OrganizationResponse, summary="获取组织详情")
async def get_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取组织的详细信息"""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    return org


@router.post("/", response_model=OrganizationResponse, summary="创建组织")
async def create_organization(
    organization: OrganizationCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    创建新组织
    
    - 需要关联到一个已存在的角色记录（is_organization=True）
    - 可以设置父组织、势力等级等属性
    """
    # 验证角色是否存在且是组织
    char_result = await db.execute(
        select(Character).where(Character.id == organization.character_id)
    )
    char = char_result.scalar_one_or_none()
    
    if not char:
        raise HTTPException(status_code=404, detail="关联的角色不存在")
    if not char.is_organization:
        raise HTTPException(status_code=400, detail="关联的角色不是组织类型")
    
    # 检查是否已存在
    existing = await db.execute(
        select(Organization).where(Organization.character_id == organization.character_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该角色已有组织详情记录")
    
    # 创建组织
    db_org = Organization(**organization.model_dump())
    db.add(db_org)
    await db.commit()
    await db.refresh(db_org)
    
    logger.info(f"创建组织成功：{db_org.id} - {char.name}")
    return db_org


@router.put("/{org_id}", response_model=OrganizationResponse, summary="更新组织")
async def update_organization(
    org_id: str,
    organization: OrganizationUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新组织的属性"""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    db_org = result.scalar_one_or_none()
    
    if not db_org:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    # 更新字段
    update_data = organization.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_org, field, value)
    
    await db.commit()
    await db.refresh(db_org)
    
    logger.info(f"更新组织成功：{org_id}")
    return db_org


@router.delete("/{org_id}", summary="删除组织")
async def delete_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除组织（会级联删除所有成员关系）"""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    db_org = result.scalar_one_or_none()
    
    if not db_org:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    await db.delete(db_org)
    await db.commit()
    
    logger.info(f"删除组织成功：{org_id}")
    return {"message": "组织删除成功", "id": org_id}


# ============ 组织成员管理 ============

@router.get("/{org_id}/members", response_model=List[OrganizationMemberDetailResponse], summary="获取组织成员")
async def get_organization_members(
    org_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取组织的所有成员
    
    按职位等级（rank）降序排列
    """
    # 验证组织存在
    org_result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    if not org_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="组织不存在")
    
    # 获取成员列表
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == org_id)
        .order_by(OrganizationMember.rank.desc(), OrganizationMember.created_at)
    )
    members = result.scalars().all()
    
    # 获取成员角色信息
    member_list = []
    for member in members:
        char_result = await db.execute(
            select(Character).where(Character.id == member.character_id)
        )
        char = char_result.scalar_one_or_none()
        
        if char:
            member_list.append(OrganizationMemberDetailResponse(
                id=member.id,
                character_id=member.character_id,
                character_name=char.name,
                position=member.position,
                rank=member.rank,
                loyalty=member.loyalty,
                contribution=member.contribution,
                status=member.status,
                joined_at=member.joined_at,
                left_at=member.left_at,
                notes=member.notes
            ))
    
    logger.info(f"获取组织 {org_id} 的成员列表，共 {len(member_list)} 人")
    return member_list


@router.post("/{org_id}/members", response_model=OrganizationMemberResponse, summary="添加组织成员")
async def add_organization_member(
    org_id: str,
    member: OrganizationMemberCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    添加角色到组织
    
    - 一个角色在同一组织中只能有一个职位
    - 会自动更新组织的成员计数
    """
    # 验证组织存在
    org_result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    # 验证角色存在
    char_result = await db.execute(
        select(Character).where(Character.id == member.character_id)
    )
    char = char_result.scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="角色不存在")
    if char.is_organization:
        raise HTTPException(status_code=400, detail="不能将组织添加为成员")
    
    # 检查是否已存在
    existing = await db.execute(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.character_id == member.character_id
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该角色已在组织中")
    
    # 创建成员关系
    db_member = OrganizationMember(
        organization_id=org_id,
        **member.model_dump(),
        source="manual"
    )
    db.add(db_member)
    
    # 更新组织成员计数
    org.member_count += 1
    
    await db.commit()
    await db.refresh(db_member)
    
    logger.info(f"添加成员成功：{char.name} 加入组织 {org_id}")
    return db_member


@router.put("/members/{member_id}", response_model=OrganizationMemberResponse, summary="更新成员信息")
async def update_organization_member(
    member_id: str,
    member: OrganizationMemberUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新组织成员的职位、忠诚度等信息"""
    result = await db.execute(
        select(OrganizationMember).where(OrganizationMember.id == member_id)
    )
    db_member = result.scalar_one_or_none()
    
    if not db_member:
        raise HTTPException(status_code=404, detail="成员记录不存在")
    
    # 更新字段
    update_data = member.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_member, field, value)
    
    await db.commit()
    await db.refresh(db_member)
    
    logger.info(f"更新成员信息成功：{member_id}")
    return db_member


@router.delete("/members/{member_id}", summary="移除组织成员")
async def remove_organization_member(
    member_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    从组织中移除成员
    
    会自动更新组织的成员计数
    """
    result = await db.execute(
        select(OrganizationMember).where(OrganizationMember.id == member_id)
    )
    db_member = result.scalar_one_or_none()
    
    if not db_member:
        raise HTTPException(status_code=404, detail="成员记录不存在")
    
    # 更新组织成员计数
    org_result = await db.execute(
        select(Organization).where(Organization.id == db_member.organization_id)
    )
    org = org_result.scalar_one()
    org.member_count = max(0, org.member_count - 1)
    
    await db.delete(db_member)
    await db.commit()
    
    logger.info(f"移除成员成功：{member_id}")
    return {"message": "成员移除成功", "id": member_id}