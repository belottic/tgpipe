import pytest

from tgpipe.errors import EntityNotFound, UsageError
from tgpipe.resolve import parse_link, resolve


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://t.me/durov", ("username", "durov")),
        ("t.me/durov", ("username", "durov")),
        ("http://telegram.me/durov", ("username", "durov")),
        ("t.me/channel/123", ("username", "channel")),
        ("t.me/channel?single", ("username", "channel")),
        ("t.me/+AbCdEf", ("invite", "AbCdEf")),
        ("https://t.me/joinchat/XYZ", ("invite", "XYZ")),
        ("@durov", None),
        ("12345", None),
        ("Chat Title", None),
    ],
)
def test_parse_link(value, expected):
    assert parse_link(value) == expected


# --- resolution: own dialogs come before the rest of Telegram --------------


class FakeEntity:
    def __init__(self, id, name):
        self.id = id
        self.title = name


class FakeDialog:
    def __init__(self, entity):
        self.entity = entity


class FakeClient:
    """get_entity simulates the global lookup, iter_dialogs the own chats."""

    def __init__(self, dialogs=(), global_entities=None):
        self.dialogs = [FakeDialog(d) for d in dialogs]
        self.global_entities = global_entities or {}
        self.lookups: list = []
        self.me = FakeEntity(1, "Io")

    async def get_me(self):
        return self.me

    async def get_entity(self, candidate):
        self.lookups.append(candidate)
        if candidate in self.global_entities:
            return self.global_entities[candidate]
        raise ValueError(f"Cannot find any entity corresponding to {candidate!r}")

    def iter_dialogs(self):
        async def _gen():
            for dialog in self.dialogs:
                yield dialog

        return _gen()


@pytest.fixture(autouse=True)
def _display_name(monkeypatch):
    monkeypatch.setattr(
        "tgpipe.resolve.utils.get_display_name", lambda e: getattr(e, "title", "")
    )
    monkeypatch.setattr("tgpipe.resolve.utils.get_peer_id", lambda e: e.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["me", "self", "saved", "Saved Messages", "ME"])
async def test_self_aliases(alias):
    client = FakeClient()
    assert await resolve(client, alias) is client.me


@pytest.mark.asyncio
async def test_bare_title_beats_the_global_namesake():
    """The bug that almost sent a message to the wrong bot."""
    mio = FakeEntity(-1001234567890, "Progetto")
    bot = FakeEntity(987654321, "ProgettoBot")
    client = FakeClient(dialogs=[mio], global_entities={"Progetto": bot})
    assert await resolve(client, "Progetto") is mio


@pytest.mark.asyncio
async def test_at_sign_forces_the_global_lookup():
    mio = FakeEntity(-100, "Progetto")
    bot = FakeEntity(987654321, "ProgettoBot")
    client = FakeClient(dialogs=[mio], global_entities={"Progetto": bot})
    assert await resolve(client, "@Progetto") is bot


@pytest.mark.asyncio
async def test_global_username_when_not_among_own_dialogs():
    tizio = FakeEntity(42, "Durov")
    client = FakeClient(dialogs=[FakeEntity(-1, "Other")],
                        global_entities={"durov": tizio})
    assert await resolve(client, "durov") is tizio


@pytest.mark.asyncio
async def test_exact_title_beats_partial():
    esatto = FakeEntity(-1, "Progetto")
    parziale = FakeEntity(-2, "Coco's Random Updates")
    client = FakeClient(dialogs=[parziale, esatto])
    assert await resolve(client, "Progetto") is esatto


@pytest.mark.asyncio
async def test_single_partial_match_accepted():
    client = FakeClient(dialogs=[FakeEntity(-2, "Coco's Random Updates")])
    assert (await resolve(client, "Coco")).id == -2


@pytest.mark.asyncio
async def test_ambiguity_lists_the_candidates():
    client = FakeClient(dialogs=[FakeEntity(-1, "[Team] One"),
                                 FakeEntity(-2, "[Team] Two")])
    with pytest.raises(EntityNotFound) as excinfo:
        await resolve(client, "Team")
    assert "2 chats" in excinfo.value.message
    assert {m["id"] for m in excinfo.value.details["matches"]} == {-1, -2}


@pytest.mark.asyncio
async def test_numeric_id_does_not_scan_dialogs():
    target = FakeEntity(-100, "Group")
    client = FakeClient(dialogs=[FakeEntity(-999, "Other")],
                        global_entities={-100: target})
    assert await resolve(client, "-100") is target
    assert client.lookups == [-100]  # looked up as an int, exactly once


@pytest.mark.asyncio
async def test_nonexistent_id():
    with pytest.raises(EntityNotFound, match="id -100"):
        await resolve(FakeClient(), "-100")


@pytest.mark.asyncio
async def test_phone_number():
    tizio = FakeEntity(42, "Tizio")
    client = FakeClient(global_entities={"+391234567890": tizio})
    assert await resolve(client, "+391234567890") is tizio


@pytest.mark.asyncio
async def test_unknown_phone_number_explains_why():
    with pytest.raises(EntityNotFound, match="contacts"):
        await resolve(FakeClient(), "+391234567890")


@pytest.mark.asyncio
async def test_public_link_becomes_a_username():
    channel = FakeEntity(-5, "Channel")
    client = FakeClient(global_entities={"channel": channel})
    assert await resolve(client, "https://t.me/channel/123") is channel


@pytest.mark.asyncio
async def test_invite_link_points_to_join():
    with pytest.raises(UsageError, match="chats join"):
        await resolve(FakeClient(), "t.me/+AbCdEf")


@pytest.mark.asyncio
async def test_empty_chat_argument():
    with pytest.raises(UsageError, match="no chat given"):
        await resolve(FakeClient(), "   ")


@pytest.mark.asyncio
async def test_not_found():
    with pytest.raises(EntityNotFound, match="no chat matches"):
        await resolve(FakeClient(dialogs=[FakeEntity(-1, "Other")]), "nonexistent")
