import asyncio
import json
import logging
from typing import TYPE_CHECKING

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from shared.core.exceptions import DatabaseException, QueueException
from shared.dtos.job import JobStatus
from shared.interfaces.infrastructure.messaging import IMessagingService
from shared.interfaces.repositories.job import IJobRepository

from ...interfaces.consumer import IMessageConsumer

if TYPE_CHECKING:
    from worker.core.container import Container
    from worker.services.processing_service import ProcessingService

logger = logging.getLogger(__name__)


class RabbitMQConsumer(IMessageConsumer):
    def __init__(
        self,
        container: "Container",
        processing_service: "ProcessingService",
        messaging: IMessagingService,
        job_repo: IJobRepository,
        url: str,
        queue: str,
    ) -> None:
        self._container = container
        self._processing_service = processing_service
        self._messaging = messaging
        self._job_repo = job_repo
        self._url = url
        self._queue = queue
        self._stop_event: asyncio.Event = asyncio.Event()
        self._in_flight: asyncio.Task | None = None

    async def start(self) -> None:
        connection = await aio_pika.connect_robust(self._url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await channel.declare_queue(self._queue, durable=True)

            async with queue.iterator() as it:
                async for msg in it:
                    if self._stop_event.is_set():
                        break
                    self._in_flight = asyncio.create_task(self._handle(msg))
                    await asyncio.shield(self._in_flight)
                    self._in_flight = None

        if self._in_flight is not None:
            await self._in_flight

    def request_stop(self) -> None:
        self._stop_event.set()

    async def _handle(self, msg: AbstractIncomingMessage) -> None:
        try:
            payload = json.loads(msg.body)
            job_id = payload["job_id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("poison message dropped")
            await msg.ack()
            return

        async with self._container.open_session() as session:
            job = await self._job_repo.get_for_processing(session, job_id)
            if job is None:
                logger.warning("job %s not found, dropping", job_id)
                await msg.ack()
                return
            if job.status is not JobStatus.QUEUED:
                logger.info(
                    "job %s not in QUEUED state (%s), dropping (idempotency)",
                    job_id,
                    job.status,
                )
                await msg.ack()
                return

        async with self._container.open_session() as session:
            try:
                started = await self._job_repo.update_status(
                    session, job_id, JobStatus.STARTED
                )
            except DatabaseException:
                logger.warning("could not mark job %s started, requeue", job_id)
                await msg.nack(requeue=True)
                return

        try:
            async with self._container.open_session() as session:
                await self._processing_service.process(session, job_id)
            await msg.ack()
        except Exception as e:
            await self._handle_failure(
                job_id, started.attempts, started.max_attempts, e
            )
            await msg.ack()

    async def _handle_failure(
        self,
        job_id: int,
        attempts: int,
        max_attempts: int,
        exc: Exception,
    ) -> None:
        if attempts < max_attempts:
            async with self._container.open_session() as session:
                await self._job_repo.update_status(
                    session, job_id, JobStatus.QUEUED, error_message=str(exc)
                )
            try:
                await self._messaging.enqueue(self._queue, {"job_id": job_id})
            except QueueException:
                logger.error(
                    "re-enqueue failed for job %s; job stranded in QUEUED",
                    job_id,
                )
                # stale-QUEUED sweeper is future work
        else:
            async with self._container.open_session() as session:
                await self._job_repo.update_status(
                    session, job_id, JobStatus.FAILED, error_message=str(exc)
                )
