import json

import aio_pika
from aio_pika.abc import AbstractRobustConnection

from ...interfaces.infrastructure.messaging import IMessagingService


class RabbitMQMessagingService(IMessagingService):
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: AbstractRobustConnection | None = None

    async def _get_connection(self) -> AbstractRobustConnection:
        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(self._url)
        return self._connection

    async def enqueue(self, queue: str, payload: dict) -> None:
        connection = await self._get_connection()
        async with connection.channel() as channel:
            await channel.declare_queue(queue, durable=True)
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(payload).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=queue,
            )

    async def queue_depth(self, queue: str) -> int:
        connection = await self._get_connection()
        async with connection.channel() as channel:
            declared = await channel.declare_queue(queue, passive=True)
            return declared.declaration_result.message_count or 0
