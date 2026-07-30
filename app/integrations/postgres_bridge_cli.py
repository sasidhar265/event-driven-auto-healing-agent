import asyncio
import json

from app.config import get_settings
from app.integrations.postgres_bridge import ExternalPostgresBridge


async def validate() -> int:
    settings = get_settings()
    bridge = ExternalPostgresBridge(settings)
    try:
        result = await bridge.validate()
        print(json.dumps(result, indent=2))
        return 0 if result["valid"] else 1
    finally:
        await bridge.close()


def main() -> None:
    raise SystemExit(asyncio.run(validate()))


if __name__ == "__main__":
    main()
