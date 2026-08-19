"""contacts.Search returns more entities than asked for: users and chats also
hold the ones merely referenced by the results."""

from telethon.tl import types

from tgpipe.commands.chats import rank_search_results


def _user(uid):
    return types.User(id=uid, first_name=f"U{uid}")


def _channel(cid):
    return types.Channel(id=cid, title=f"C{cid}", photo=None, date=None,
                         broadcast=True, megagroup=False)


class FakeResult:
    def __init__(self, my_results=(), results=(), users=(), chats=()):
        self.my_results = list(my_results)
        self.results = list(results)
        self.users = list(users)
        self.chats = list(chats)


def test_honours_the_limit():
    users = [_user(i) for i in range(1, 11)]
    result = FakeResult(results=[types.PeerUser(u.id) for u in users], users=users)
    assert len(rank_search_results(result, 3)) == 3


def test_limit_zero_means_all():
    users = [_user(i) for i in range(1, 6)]
    result = FakeResult(results=[types.PeerUser(u.id) for u in users], users=users)
    assert len(rank_search_results(result, 0)) == 5


def test_result_order_preserved():
    users = [_user(1), _user(2), _user(3)]
    result = FakeResult(
        results=[types.PeerUser(3), types.PeerUser(1), types.PeerUser(2)], users=users
    )
    assert [u.id for u in rank_search_results(result, 0)] == [3, 1, 2]


def test_my_results_come_first():
    users = [_user(1), _user(2)]
    result = FakeResult(my_results=[types.PeerUser(2)], results=[types.PeerUser(1)],
                        users=users)
    assert [u.id for u in rank_search_results(result, 0)] == [2, 1]


def test_merely_referenced_entities_excluded():
    """The bug: emitting users+chats included entities outside the ranking."""
    cercato, referenziato = _user(1), _user(99)
    result = FakeResult(results=[types.PeerUser(1)], users=[cercato, referenziato])
    assert [u.id for u in rank_search_results(result, 0)] == [1]


def test_duplicates_between_my_results_and_results():
    result = FakeResult(my_results=[types.PeerUser(1)], results=[types.PeerUser(1)],
                        users=[_user(1)])
    assert len(rank_search_results(result, 0)) == 1


def test_users_and_channels_together():
    result = FakeResult(
        results=[types.PeerUser(1), types.PeerChannel(7)],
        users=[_user(1)], chats=[_channel(7)],
    )
    assert len(rank_search_results(result, 0)) == 2


def test_peer_without_a_matching_entity_is_skipped():
    result = FakeResult(results=[types.PeerUser(1), types.PeerUser(2)], users=[_user(2)])
    assert [u.id for u in rank_search_results(result, 0)] == [2]


def test_empty_result():
    assert rank_search_results(FakeResult(), 5) == []
