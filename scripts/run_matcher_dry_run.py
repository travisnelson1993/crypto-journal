import asyncio
from app.db.database import get_db
from app.services.execution_matcher_dry_run import run_dry_run_matcher


async def main():
    async for session in get_db():
        await run_dry_run_matcher(session)


if __name__ == "__main__":
    asyncio.run(main())
