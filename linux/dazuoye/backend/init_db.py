#!/usr/bin/env python3
"""
数据库初始化脚本 - 由 docker-compose 在启动时调用
确保所有表已创建
"""
import asyncio
from app.database import init_db, engine


async def main():
    print("正在初始化数据库表...")
    await init_db()
    print("数据库表初始化完成！")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())