"""
认证路由 - 用户注册 / 登录
注意：演示版本使用简化认证，生产环境应使用 JWT + bcrypt
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["认证"])

# 演示用 - 简单的密码校验（仅用于测试，非生产安全）
SIMPLE_PASSWORDS = {
    "Player1": "test123",
    "Player2": "test123",
    "AI_Bot": "test123",
}


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录（简化版）"""
    query = select(User).where(User.username == req.username)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 演示版：简单密码比对
    expected_pw = SIMPLE_PASSWORDS.get(req.username)
    if not expected_pw or req.password != expected_pw:
        raise HTTPException(status_code=401, detail="密码错误")

    return LoginResponse(
        user_id=user.id,
        username=user.username,
        token=f"demo-token-{user.id}-{user.username}",
    )


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)):
    """列出所有用户（用于选择对手）"""
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [{"id": u.id, "username": u.username} for u in users]