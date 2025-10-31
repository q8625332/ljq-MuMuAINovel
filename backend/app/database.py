"""数据库连接和会话管理 - 支持多用户数据隔离"""
import asyncio
from typing import Dict, Any
from datetime import datetime
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool
from fastapi import Request, HTTPException
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# 创建基类
Base = declarative_base()

# 引擎缓存：每个用户一个引擎
_engine_cache: Dict[str, Any] = {}

# 锁管理：用于保护引擎创建过程
_engine_locks: Dict[str, asyncio.Lock] = {}
_cache_lock = asyncio.Lock()

# 会话统计（用于监控连接泄漏）
_session_stats = {
    "created": 0,
    "closed": 0,
    "active": 0,
    "errors": 0,
    "generator_exits": 0,
    "last_check": None
}


async def get_engine(user_id: str):
    """获取或创建用户专属的数据库引擎（线程安全）
    
    Args:
        user_id: 用户ID
        
    Returns:
        用户专属的异步引擎
    """
    if user_id in _engine_cache:
        return _engine_cache[user_id]
    
    async with _cache_lock:
        if user_id not in _engine_locks:
            _engine_locks[user_id] = asyncio.Lock()
        user_lock = _engine_locks[user_id]
    
    async with user_lock:
        if user_id not in _engine_cache:
            db_url = f"sqlite+aiosqlite:///data/ai_story_user_{user_id}.db"
            engine = create_async_engine(
                db_url,
                echo=False,
                future=True,
                poolclass=StaticPool,
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={
                    "timeout": 30,
                    "check_same_thread": False
                }
            )
            
            try:
                async with engine.begin() as conn:
                    await conn.execute(text("PRAGMA journal_mode=WAL"))
                    await conn.execute(text("PRAGMA synchronous=NORMAL"))
                    await conn.execute(text("PRAGMA cache_size=-64000"))
                    await conn.execute(text("PRAGMA temp_store=MEMORY"))
                    await conn.execute(text("PRAGMA busy_timeout=5000"))
                    
                    logger.info(f"✅ 用户 {user_id} 的数据库已优化（WAL模式 + 64MB缓存）")
            except Exception as e:
                logger.warning(f"⚠️ 用户 {user_id} 数据库优化失败: {str(e)}")
            _engine_cache[user_id] = engine
            logger.info(f"为用户 {user_id} 创建数据库引擎")
        
        return _engine_cache[user_id]


async def get_db(request: Request):
    """获取数据库会话的依赖函数
    
    从 request.state.user_id 获取用户ID，然后返回该用户的数据库会话
    """
    user_id = getattr(request.state, "user_id", None)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录或用户ID缺失")
    
    engine = await get_engine(user_id)
    
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    session = AsyncSessionLocal()
    session_id = id(session)
    
    global _session_stats
    _session_stats["created"] += 1
    _session_stats["active"] += 1
    
    logger.debug(f"📊 会话创建 [User:{user_id}][ID:{session_id}] - 活跃:{_session_stats['active']}, 总创建:{_session_stats['created']}, 总关闭:{_session_stats['closed']}")
    
    try:
        yield session
        if session.in_transaction():
            await session.rollback()
    except GeneratorExit:
        _session_stats["generator_exits"] += 1
        logger.warning(f"⚠️ GeneratorExit [User:{user_id}][ID:{session_id}] - SSE连接断开（总计:{_session_stats['generator_exits']}次）")
        try:
            if session.in_transaction():
                await session.rollback()
                logger.info(f"✅ 事务已回滚 [User:{user_id}][ID:{session_id}]（GeneratorExit）")
        except Exception as rollback_error:
            _session_stats["errors"] += 1
            logger.error(f"❌ GeneratorExit回滚失败 [User:{user_id}][ID:{session_id}]: {str(rollback_error)}")
    except Exception as e:
        _session_stats["errors"] += 1
        logger.error(f"❌ 会话异常 [User:{user_id}][ID:{session_id}]: {str(e)}")
        try:
            if session.in_transaction():
                await session.rollback()
                logger.info(f"✅ 事务已回滚 [User:{user_id}][ID:{session_id}]（异常）")
        except Exception as rollback_error:
            logger.error(f"❌ 异常回滚失败 [User:{user_id}][ID:{session_id}]: {str(rollback_error)}")
        raise
    finally:
        try:
            if session.in_transaction():
                await session.rollback()
                logger.warning(f"⚠️ finally中发现未提交事务 [User:{user_id}][ID:{session_id}]，已回滚")
            
            await session.close()
            
            _session_stats["closed"] += 1
            _session_stats["active"] -= 1
            _session_stats["last_check"] = datetime.now().isoformat()
            
            logger.debug(f"📊 会话关闭 [User:{user_id}][ID:{session_id}] - 活跃:{_session_stats['active']}, 总创建:{_session_stats['created']}, 总关闭:{_session_stats['closed']}, 错误:{_session_stats['errors']}")
            
            if _session_stats["active"] > 10:
                logger.warning(f"🚨 活跃会话数过多: {_session_stats['active']}，可能存在连接泄漏！")
            elif _session_stats["active"] < 0:
                logger.error(f"🚨 活跃会话数异常: {_session_stats['active']}，统计可能不准确！")
                
        except Exception as e:
            _session_stats["errors"] += 1
            logger.error(f"❌ 关闭会话时出错 [User:{user_id}][ID:{session_id}]: {str(e)}", exc_info=True)
            try:
                await session.close()
            except:
                pass

async def _init_relationship_types(user_id: str):
    """为指定用户初始化预置的关系类型数据
    
    Args:
        user_id: 用户ID
    """
    from app.models.relationship import RelationshipType
    
    relationship_types = [
        {"name": "父亲", "category": "family", "reverse_name": "子女", "intimacy_range": "high", "icon": "👨"},
        {"name": "母亲", "category": "family", "reverse_name": "子女", "intimacy_range": "high", "icon": "👩"},
        {"name": "兄弟", "category": "family", "reverse_name": "兄弟", "intimacy_range": "high", "icon": "👬"},
        {"name": "姐妹", "category": "family", "reverse_name": "姐妹", "intimacy_range": "high", "icon": "👭"},
        {"name": "子女", "category": "family", "reverse_name": "父母", "intimacy_range": "high", "icon": "👶"},
        {"name": "配偶", "category": "family", "reverse_name": "配偶", "intimacy_range": "high", "icon": "💑"},
        {"name": "恋人", "category": "family", "reverse_name": "恋人", "intimacy_range": "high", "icon": "💕"},
        
        {"name": "师父", "category": "social", "reverse_name": "徒弟", "intimacy_range": "high", "icon": "🎓"},
        {"name": "徒弟", "category": "social", "reverse_name": "师父", "intimacy_range": "high", "icon": "📚"},
        {"name": "朋友", "category": "social", "reverse_name": "朋友", "intimacy_range": "medium", "icon": "🤝"},
        {"name": "同学", "category": "social", "reverse_name": "同学", "intimacy_range": "medium", "icon": "🎒"},
        {"name": "邻居", "category": "social", "reverse_name": "邻居", "intimacy_range": "low", "icon": "🏘️"},
        {"name": "知己", "category": "social", "reverse_name": "知己", "intimacy_range": "high", "icon": "💙"},
        
        {"name": "上司", "category": "professional", "reverse_name": "下属", "intimacy_range": "low", "icon": "👔"},
        {"name": "下属", "category": "professional", "reverse_name": "上司", "intimacy_range": "low", "icon": "💼"},
        {"name": "同事", "category": "professional", "reverse_name": "同事", "intimacy_range": "medium", "icon": "🤵"},
        {"name": "合作伙伴", "category": "professional", "reverse_name": "合作伙伴", "intimacy_range": "medium", "icon": "🤜🤛"},
        
        {"name": "敌人", "category": "hostile", "reverse_name": "敌人", "intimacy_range": "low", "icon": "⚔️"},
        {"name": "仇人", "category": "hostile", "reverse_name": "仇人", "intimacy_range": "low", "icon": "💢"},
        {"name": "竞争对手", "category": "hostile", "reverse_name": "竞争对手", "intimacy_range": "low", "icon": "🎯"},
        {"name": "宿敌", "category": "hostile", "reverse_name": "宿敌", "intimacy_range": "low", "icon": "⚡"},
    ]
    
    try:
        engine = await get_engine(user_id)
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(RelationshipType))
            existing = result.scalars().first()
            
            if existing:
                logger.info(f"用户 {user_id} 的关系类型数据已存在，跳过初始化")
                return
            
            logger.info(f"开始为用户 {user_id} 插入关系类型数据...")
            for rt_data in relationship_types:
                relationship_type = RelationshipType(**rt_data)
                session.add(relationship_type)
            
            await session.commit()
            logger.info(f"成功为用户 {user_id} 插入 {len(relationship_types)} 条关系类型数据")
            
    except Exception as e:
        logger.error(f"用户 {user_id} 初始化关系类型数据失败: {str(e)}", exc_info=True)
        raise



async def init_db(user_id: str):
    """初始化指定用户的数据库,创建所有表并插入预置数据
    
    Args:
        user_id: 用户ID
    """
    try:
        logger.info(f"开始初始化用户 {user_id} 的数据库...")
        engine = await get_engine(user_id)
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        await _init_relationship_types(user_id)
        
        logger.info(f"用户 {user_id} 的数据库初始化成功")
    except Exception as e:
        logger.error(f"用户 {user_id} 的数据库初始化失败: {str(e)}", exc_info=True)
        raise


async def close_db():
    """关闭所有数据库连接"""
    try:
        logger.info("正在关闭所有数据库连接...")
        for user_id, engine in _engine_cache.items():
            await engine.dispose()
            logger.info(f"用户 {user_id} 的数据库连接已关闭")
        _engine_cache.clear()
        logger.info("所有数据库连接已关闭")
    except Exception as e:
        logger.error(f"关闭数据库连接失败: {str(e)}", exc_info=True)
        raise