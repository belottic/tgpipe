import json

import pytest

from tgpipe.models import Entity, Ok
from tgpipe.output import Emitter


def _records():
    return [
        Entity(kind="user", id=1, name="Bruno", username="bam"),
        Entity(kind="channel", id=-100777, title="Notizie"),
    ]


def test_json_is_an_array(capsys):
    Emitter("json").many(_records())
    parsed = json.loads(capsys.readouterr().out)
    assert isinstance(parsed, list) and len(parsed) == 2


def test_jsonl_one_line_per_record(capsys):
    Emitter("jsonl").many(_records())
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == 1


def test_nulls_excluded_by_default(capsys):
    Emitter("json").one(Entity(kind="user", id=1))
    assert "title" not in json.loads(capsys.readouterr().out)


def test_nulls_included_on_request(capsys):
    Emitter("json", include_nulls=True).one(Entity(kind="user", id=1))
    assert json.loads(capsys.readouterr().out)["title"] is None


def test_table_is_not_json(capsys):
    Emitter("table").many(_records())
    out = capsys.readouterr().out
    assert "kind" in out and "Bruno" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


def test_empty_table(capsys):
    Emitter("table").many([])
    assert "no results" in capsys.readouterr().out


def test_returned_count():
    assert Emitter("jsonl").many(_records()) == 2


def test_nested_dict_is_flattened(capsys):
    Emitter("table").one(Ok(action="test", details={"chat_id": 5}))
    out = capsys.readouterr().out
    assert "details.chat_id" in out


@pytest.mark.asyncio
async def test_async_stream(capsys):
    async def _gen():
        for record in _records():
            yield record

    count = await Emitter("jsonl").many_async(_gen())
    assert count == 2
    assert len(capsys.readouterr().out.strip().splitlines()) == 2
