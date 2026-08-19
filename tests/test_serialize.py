from datetime import UTC, datetime

from telethon.tl import types

from tgpipe import serialize


def _user(**kwargs):
    base = dict(id=42, first_name="Bruno", last_name="M", username="bam", bot=False)
    return types.User(**{**base, **kwargs})


def test_entity_user():
    record = serialize.entity(_user(phone="391234"))
    assert record.kind == "user"
    assert record.id == 42
    assert record.name == "Bruno M"
    assert record.phone == "391234"
    assert record.title is None


def test_entity_bot():
    assert serialize.entity(_user(bot=True)).kind == "bot"


def test_entity_channel_has_a_marked_id():
    channel = types.Channel(
        id=777, title="Notizie", photo=None, date=None,
        broadcast=True, megagroup=False, username="news",
    )
    record = serialize.entity(channel)
    assert record.kind == "channel"
    assert record.id == -1000000000777
    assert record.title == "Notizie"


def test_entity_supergroup_is_a_group():
    channel = types.Channel(
        id=1, title="Group", photo=None, date=None, broadcast=False, megagroup=True
    )
    assert serialize.entity(channel).kind == "group"


def test_entity_none():
    assert serialize.entity(None) is None


def _message(**kwargs):
    base = dict(
        id=7,
        peer_id=types.PeerUser(user_id=42),
        date=datetime(2026, 8, 18, 10, tzinfo=UTC),
        message="hello",
        out=False,
    )
    return types.Message(**{**base, **kwargs})


def test_message_base():
    record = serialize.message(_message())
    assert record.id == 7
    assert record.chat_id == 42
    assert record.text == "hello"
    assert record.media is None
    assert record.reactions == []


def test_message_empty_text_becomes_none():
    assert serialize.message(_message(message="")).text is None


def test_message_reactions():
    reactions = types.MessageReactions(
        results=[
            types.ReactionCount(reaction=types.ReactionEmoji(emoticon="👍"), count=3,
                                chosen_order=0),
            types.ReactionCount(reaction=types.ReactionEmoji(emoticon="🔥"), count=1),
        ],
        min=False, can_see_list=True,
    )
    record = serialize.message(_message(reactions=reactions))
    assert [(r.emoji, r.count, r.chosen) for r in record.reactions] == [
        ("👍", 3, True), ("🔥", 1, False)
    ]


def test_message_forward():
    fwd = types.MessageFwdHeader(
        date=datetime(2026, 8, 17, tzinfo=UTC),
        from_id=types.PeerUser(user_id=99), from_name="Tizio",
    )
    record = serialize.message(_message(fwd_from=fwd))
    assert record.forward.from_id == 99
    assert record.forward.from_name == "Tizio"


def test_message_denormalised_chat():
    chat = serialize.entity(_user())
    record = serialize.message(_message(), chat=chat)
    assert record.chat.id == 42


def test_message_raw_only_on_request():
    assert serialize.message(_message()).raw is None
    assert serialize.message(_message(), raw=True).raw["_"] == "Message"


def test_folder_title_from_text_with_entities():
    flt = types.DialogFilter(
        id=2, title=types.TextWithEntities(text="Lavoro", entities=[]),
        pinned_peers=[], include_peers=[], exclude_peers=[], emoticon="💼",
    )
    record = serialize.folder(flt)
    assert record.title == "Lavoro"
    assert record.emoticon == "💼"


# --- participants: the tag lives on the participant, not on the user -------


def _participant(cls, **kwargs):
    user = _user()
    user.participant = cls(**kwargs)
    return user


def test_member_extracts_the_custom_title():
    """A group's "tag" (e.g. 'Moderator') is participant.rank: serialising only
    the user makes it disappear."""
    user = _participant(types.ChannelParticipant, user_id=42, date=None, rank="Moderatore")
    record = serialize.member(user)
    assert record.rank == "Moderatore"
    assert record.role == "member"
    assert record.entity.username == "bam"


def test_member_admin_role():
    user = _participant(types.ChannelParticipantAdmin, user_id=42, date=None,
                        admin_rights=None, rank="COC", promoted_by=7,
                        can_edit=True, is_self=False)
    record = serialize.member(user)
    assert record.role == "admin"
    assert record.rank == "COC"
    assert record.promoted_by == 7


def test_member_creator_role():
    user = _participant(types.ChannelParticipantCreator, user_id=42, admin_rights=None)
    assert serialize.member(user).role == "creator"


def test_member_banned_versus_restricted():
    kicked = _participant(types.ChannelParticipantBanned, peer=types.PeerUser(42),
                          kicked_by=1, date=None, banned_rights=None, left=True)
    limited = _participant(types.ChannelParticipantBanned, peer=types.PeerUser(42),
                           kicked_by=1, date=None, banned_rights=None, left=False)
    assert serialize.member(kicked).role == "banned"
    assert serialize.member(limited).role == "restricted"


def test_member_basic_group():
    user = _participant(types.ChatParticipantAdmin, user_id=42, inviter_id=9, date=None)
    record = serialize.member(user)
    assert record.role == "admin"
    assert record.inviter_id == 9


def test_member_without_participant_still_usable():
    """iter_participants does not always attach the participant."""
    record = serialize.member(_user())
    assert record.role == "member"
    assert record.rank is None
    assert record.entity.id == 42


def test_member_empty_rank_becomes_none():
    user = _participant(types.ChannelParticipant, user_id=42, date=None, rank="")
    assert serialize.member(user).rank is None
