import json

from tgpipe.commands.export import last_exported_id, rewrite_clean


def _write(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_missing_file(tmp_path):
    assert last_exported_id(tmp_path / "messages.jsonl") == 0


def test_highest_id(tmp_path):
    path = tmp_path / "messages.jsonl"
    _write(path, [json.dumps({"id": i}) for i in (3, 10, 7)])
    assert last_exported_id(path) == 10


def test_truncated_last_line_ignored(tmp_path):
    path = tmp_path / "messages.jsonl"
    path.write_text(json.dumps({"id": 5}) + "\n" + '{"id": 6, "text": "tron',
                    encoding="utf-8")
    assert last_exported_id(path) == 5


def test_rewrite_clean_drops_broken_lines(tmp_path):
    path = tmp_path / "messages.jsonl"
    path.write_text(json.dumps({"id": 1}) + "\n" + "{rotta\n" + json.dumps({"id": 2}) + "\n",
                    encoding="utf-8")
    rewrite_clean(path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(l)["id"] for l in lines] == [1, 2]


def test_rewrite_clean_on_an_empty_file(tmp_path):
    path = tmp_path / "messages.jsonl"
    path.write_text("", encoding="utf-8")
    rewrite_clean(path)
    assert path.read_text(encoding="utf-8") == ""
