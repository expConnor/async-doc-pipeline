import asyncio
import json
from typing import TYPE_CHECKING

import aio_pika
import structlog
import structlog.contextvars
from aio_pika.abc import AbstractIncomingMessage

from shared.core.exceptions import (
    DatabaseException,
    JobStateConflictException,
    QueueException,
)
from shared.dtos.job import JobStatus
from shared.interfaces.infrastructure.messaging import IMessagingService
from shared.interfaces.repositories.job import IJobRepository

from ...interfaces.consumer import IMessageConsumer
from ...interfaces.processing_service import IProcessingService

if TYPE_CHECKING:
    from worker.core.container import Container

logger = structlog.get_logger()


class RabbitMQConsumer(IMessageConsumer):
    def __init__(
        self,
        container: "Container",
        processing_service: IProcessingService,
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
        structlog.contextvars.clear_contextvars()

        try:
            payload = json.loads(msg.body)
            job_id = payload["job_id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("consumer.poison_message_dropped")
            await msg.ack()
            return

        structlog.contextvars.bind_contextvars(job_id=job_id)

        async with self._container.open_session() as session:
            job = await self._job_repo.get_for_processing(session, job_id)
            if job is None:
                logger.warning("consumer.job_not_found")
                await msg.ack()
                return
            if job.status is not JobStatus.QUEUED:
                logger.info(
                    "consumer.idempotency_drop",
                    job_status=job.status.value,
                )
                await msg.ack()
                return

        async with self._container.open_session() as session:
            try:
                started = await self._job_repo.update_status(
                    session,
                    job_id,
                    JobStatus.STARTED,
                    expected_status=JobStatus.QUEUED,
                )
            except JobStateConflictException:
                logger.info("consumer.concurrent_claim_dropped")
                await msg.ack()
                return
            except DatabaseException:
                logger.warning("consumer.start_failed_requeue")
                await msg.nack(requeue=True)
                return

        logger.info(
            "consumer.job_started",
            attempt=started.attempts,
            max_attempts=started.max_attempts,
        )

        try:
            async with self._container.open_session() as session:
                await self._processing_service.process(session, job_id)
            logger.info("consumer.job_completed")
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
        try:
            if attempts < max_attempts:
                async with self._container.open_session() as session:
                    await self._job_repo.update_status(
                        session,
                        job_id,
                        JobStatus.QUEUED,
                        expected_status=JobStatus.STARTED,
                        error_message=str(exc),
                    )
                try:
                    await self._messaging.enqueue(
                        self._queue, {"job_id": job_id}
                    )
                    logger.warning(
                        "consumer.job_failed_requeued",
                        attempt=attempts,
                        max_attempts=max_attempts,
                        exc_info=exc,
                    )
                except QueueException:
                    logger.error(
                        "consumer.reenqueue_failed",
                        exc_info=exc,
                    )
            else:
                async with self._container.open_session() as session:
                    await self._job_repo.update_status(
                        session,
                        job_id,
                        JobStatus.FAILED,
                        expected_status=JobStatus.STARTED,
                        error_message=str(exc),
                    )
                logger.error(
                    "consumer.job_terminal_failure",
                    attempt=attempts,
                    max_attempts=max_attempts,
                    exc_info=exc,
                )
        except JobStateConflictException:
            logger.error("consumer.failure_handler_state_conflict")
