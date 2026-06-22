"""
MCP 路由 - AI 决策接口
提供 /mcp/recommend 端点，用于获取最优决策建议
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Game
from app.mcp_server import get_decision_recommendation
from app.schemas import MCPRequest, MCPResponse

router = APIRouter(prefix="/mcp", tags=["MCP AI 决策"])


@router.post("/recommend", response_model=MCPResponse)
async def recommend_action(req: MCPRequest, db: AsyncSession = Depends(get_db)):
    """
    MCP 决策推荐端点
    接收当前游戏状态，返回推荐行动。
    可扩展为调用外部 LLM 或强化学习模型。
    """
    # 验证游戏存在
    game_query = await db.execute(select(Game).where(Game.id == req.game_id))
    game = game_query.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="对局不存在")

    result = await get_decision_recommendation(db, req.game_id, req.player_id)
    return MCPResponse(**result)


@router.get("/health")
async def mcp_health():
    """MCP 服务器健康检查"""
    return {
        "status": "ok",
        "version": "1.0.0",
        "description": "战争雷霆卡牌游戏 MCP 决策服务 - 规则引擎模式",
        "extensible": True,
        "note": "可接入外部 LLM 或强化学习模型替代当前规则引擎",
    }