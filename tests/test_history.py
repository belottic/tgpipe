from datetime import UTC, datetime, timedelta

import pytest

from tgpipe.errors import UsageError
from tgpipe.history import iter_history, media_filter

NOW = datetime(2026, 8, 18, 12, tzinfo=UTC)


class FakeMessage:
    def __init__(self, id, date):
        self.id = id
        self.date = date


class FakeClient:
    """Simulates iter_messages: newest first, or flipped with reverse."""

    def __init__(self, messages):
        self.messages = messages
        self.kwargs = None

    def iter_messages(self, entity, **kwargs):
        self.kwargs = kwargs
        ordered = sorted(self.messages, key=lambda m: m.id, reverse=not kwargs.get("reverse"))
        limit = kwargs.get("limit")

        async def _gen():
            for index, msg in enumerate(ordered):
                if limit is not None and index >= limit:
                    return
                yield msg

        return _gen()

    async def get_messages(self, entity, ids=None):
        by_id = {m.id: m for m in self.messages}
        return [by_id.get(i) for i in (ids or [])]


def _messages():
    return [FakeMessage(i, NOW - timedelta(hours=10 - i)) for i in range(1, 11)]


async def _collect(client, **kwargs):
    return [m.id async for m in iter_history(client, None, **kwargs)]


@pytest.mark.asyncio
async def test_newest_first_by_default():
    assert await _collect(FakeClient(_messages())) == list(range(10, 0, -1))


@pytest.mark.asyncio
async def test_reverse():
    assert await _collect(FakeClient(_messages()), reverse=True) == list(range(1, 11))


@pytest.mark.asyncio
async def test_limit_delegated_to_telethon_without_date_filters():
    client = FakeClient(_messages())
    assert await _collect(client, limit=3) == [10, 9, 8]
    assert client.kwargs["limit"] == 3


@pytest.mark.asyncio
async def test_since_stops_the_iteration():
    # messages 8, 9 and 10 fall in the last 3 hours
    since = NOW - timedelta(hours=2, minutes=30)
    assert await _collect(FakeClient(_messages()), since=since) == [10, 9, 8]


@pytest.mark.asyncio
async def test_with_date_filters_the_limit_is_applied_afterwards():
    client = FakeClient(_messages())
    since = NOW - timedelta(hours=9)
    result = await _collect(client, since=since, limit=2)
    assert result == [10, 9]
    # the limit was not delegated to Telethon: it would count discarded ones too
    assert "limit" not in client.kwargs


@pytest.mark.asyncio
async def test_until_discards_the_newest():
    until = NOW - timedelta(hours=5)
    assert await _collect(FakeClient(_messages()), until=until) == [5, 4, 3, 2, 1]


@pytest.mark.asyncio
async def test_ids_override_other_criteria():
    assert await _collect(FakeClient(_messages()), ids=[2, 4], limit=1) == [2, 4]


@pytest.mark.asyncio
async def test_ids_skip_missing_messages():
    assert await _collect(FakeClient(_messages()), ids=[2, 99]) == [2]


def test_media_filter():
    from telethon.tl import types

    assert media_filter("photo") is types.InputMessagesFilterPhotos
    assert media_filter(None) is None
    with pytest.raises(UsageError, match="unknown type"):
        media_filter("pippo")
