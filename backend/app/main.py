"""FastAPI应用主入口"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings
from app.database import close_db, _session_stats
from app.logger import setup_logging, get_logger
from app.middleware import RequestIDMiddleware
from app.middleware.auth_middleware import AuthMiddleware

setup_logging(
    level=settings.log_level,
    log_to_file=settings.log_to_file,
    log_file_path=settings.log_file_path,
    max_bytes=settings.log_max_bytes,
    backup_count=settings.log_backup_count
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("应用启动，等待用户登录...")
    
    yield
    await close_db()
    logger.info("应用已关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI写小说工具 - 智能小说创作助手",
    lifespan=lifespan
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误"""
    logger.error(f"请求验证失败: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "请求参数验证失败",
            "errors": exc.errors()
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """处理所有未捕获的异常"""
    logger.error(f"未处理的异常: {type(exc).__name__}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "服务器内部错误",
            "message": str(exc) if settings.debug else "请稍后重试"
        }
    )

app.add_middleware(RequestIDMiddleware)
app.add_middleware(AuthMiddleware)

if settings.debug:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


@app.get("/health/db-sessions")
async def db_session_stats():
    """
    数据库会话统计（监控连接泄漏）
    
    返回：
    - created: 总创建会话数
    - closed: 总关闭会话数
    - active: 当前活跃会话数（应该接近0）
    - errors: 错误次数
    - generator_exits: SSE断开次数
    - last_check: 最后检查时间
    """
    return {
        "status": "ok",
        "session_stats": _session_stats,
        "warning": "活跃会话数过多" if _session_stats["active"] > 10 else None
    }


from app.api import (
    projects, outlines, characters, chapters,
    wizard_stream, relationships, organizations,
    auth, users
)
from app.api import settings as settings_router  # 使用别名避免与配置对象冲突

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")  # 使用别名

app.include_router(projects.router, prefix="/api")
app.include_router(wizard_stream.router, prefix="/api")
app.include_router(outlines.router, prefix="/api")
app.include_router(characters.router, prefix="/api")
app.include_router(chapters.router, prefix="/api")
app.include_router(relationships.router, prefix="/api")
app.include_router(organizations.router, prefix="/api")

static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """服务单页应用，所有非API路径返回index.html"""
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"detail": "API路径不存在"}
            )
        
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        
        return JSONResponse(
            status_code=404,
            content={"detail": "页面不存在"}
        )
else:
    logger.warning("静态文件目录不存在，请先构建前端: cd frontend && npm run build")
    
    @app.get("/")
    async def root():
        return {
            "message": "欢迎使用AI Story Creator",
            "version": settings.app_version,
            "docs": "/docs",
            "notice": "请先构建前端: cd frontend && npm run build"
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug
    )