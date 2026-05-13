import asyncio
import signal

from shared.core.config import get_settings
from shared.core.logging import setup_logging
from shared.core.settings.base import AppEnvTypes
from worker.core.container import container


async def _run() -> None:
    _settings = get_settings()
    setup_logging(json_logs=_settings.app_env == AppEnvTypes.production)
    consumer = container.consumer()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, consumer.request_stop)
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(_run())
