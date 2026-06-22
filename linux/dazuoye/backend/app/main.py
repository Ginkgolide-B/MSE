"""
FastAPI 主应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db, engine
from app.routes import auth, game, mcp_route


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库"""
    await init_db()
    yield
    await engine.dispose()


app = FastAPI(
    title="战争雷霆卡牌对战游戏 API",
    description="以《战争雷霆》坦克载具为素材的卡牌策略对战游戏后端",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(game.router)
app.include_router(mcp_route.router)


@app.get("/")
async def root():
    return {
        "service": "战争雷霆卡牌对战游戏 API",
        "version": "1.0.0",
        "docs": "/docs",
    }