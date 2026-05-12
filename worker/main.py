import asyncio
import signal

from worker.core.container import container


async def _run() -> None:
    consumer = container.consumer()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, consumer.request_stop)
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(_run())
