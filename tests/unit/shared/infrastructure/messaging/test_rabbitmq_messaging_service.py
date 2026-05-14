import aio_pika
import pytest

from shared.core.exceptions import QueueException
from shared.infrastructure.messaging.rabbitmq_client import (
    RabbitMQMessagingService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel_cm(mocker):
    """Return (channel_mock, cm) wired for `async with conn.channel() as ch`."""
    channel = mocker.AsyncMock()
    cm = mocker.MagicMock()
    cm.__aenter__ = mocker.AsyncMock(return_value=channel)
    cm.__aexit__ = mocker.AsyncMock(return_value=False)
    return channel, cm


def _open_connection(mocker, channel_cm):
    """Return an open mock connection that yields channel_cm from .channel()."""
    conn = mocker.MagicMock()
    conn.is_closed = False
    conn.channel.return_value = channel_cm
    return conn


# ---------------------------------------------------------------------------
# _get_connection
# ---------------------------------------------------------------------------


async def test_get_connection_creates_when_none(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    assert svc._connection is None

    mock_conn = mocker.MagicMock()
    mocker.patch("aio_pika.connect_robust", return_value=mock_conn)

    result = await svc._get_connection()

    assert result is mock_conn
    assert svc._connection is mock_conn


async def test_get_connection_reuses_open_connection(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    existing = mocker.MagicMock()
    existing.is_closed = False
    svc._connection = existing

    patch = mocker.patch("aio_pika.connect_robust")

    result = await svc._get_connection()

    assert result is existing
    patch.assert_not_called()


async def test_get_connection_creates_new_when_closed(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    old_conn = mocker.MagicMock()
    old_conn.is_closed = True
    svc._connection = old_conn

    new_conn = mocker.MagicMock()
    mocker.patch("aio_pika.connect_robust", return_value=new_conn)

    result = await svc._get_connection()

    assert result is new_conn
    assert svc._connection is new_conn


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


async def test_enqueue_success(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)
    svc._connection = _open_connection(mocker, cm)

    await svc.enqueue("jobs", {"job_id": 1})

    channel.declare_queue.assert_called_once_with("jobs", durable=True)
    channel.default_exchange.publish.assert_called_once()


async def test_enqueue_raises_queue_exception_on_amqp_error(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)
    channel.declare_queue.side_effect = aio_pika.exceptions.AMQPError()
    svc._connection = _open_connection(mocker, cm)

    with pytest.raises(QueueException):
        await svc.enqueue("jobs", {"job_id": 1})


# ---------------------------------------------------------------------------
# queue_depth
# ---------------------------------------------------------------------------


async def test_queue_depth_returns_message_count(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)
    declared = mocker.MagicMock()
    declared.declaration_result.message_count = 5
    channel.declare_queue.return_value = declared
    svc._connection = _open_connection(mocker, cm)

    result = await svc.queue_depth("jobs")

    assert result == 5
    channel.declare_queue.assert_called_once_with("jobs", passive=True)


async def test_queue_depth_returns_zero_on_channel_closed(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)

    class _ChannelClosed(aio_pika.exceptions.ChannelClosed):
        # ChannelClosed.__init__ requires broker reply args; bypass for testing
        def __init__(self):
            Exception.__init__(self)

    exc = _ChannelClosed()
    channel.declare_queue.side_effect = exc
    svc._connection = _open_connection(mocker, cm)

    result = await svc.queue_depth("jobs")

    assert result == 0


async def test_queue_depth_raises_queue_exception_on_amqp_error(mocker):
    svc = RabbitMQMessagingService(url="amqp://localhost")
    channel, cm = _make_channel_cm(mocker)
    channel.declare_queue.side_effect = aio_pika.exceptions.AMQPError()
    svc._connection = _open_connection(mocker, cm)

    with pytest.raises(QueueException):
        await svc.queue_depth("jobs")
