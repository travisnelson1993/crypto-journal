import asyncio

from app.db.database import get_db
from app.services.execution_matcher_persist import rebuild_execution_matches


async def main():
    async for session in get_db():
        total = await rebuild_execution_matches(session)
        print(f"✅ execution_matches rebuilt: {total} rows")


if __name__ == "__main__":
    asyncio.run(main())
