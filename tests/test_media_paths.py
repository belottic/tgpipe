from datetime import UTC, datetime
from pathlib import Path

import pytest

from tgpipe.commands.media import build_path, safe_component
from tgpipe.errors import UsageError

DATE = datetime(2026, 8, 18, 10, 30, tzinfo=UTC)


def _build(template, **kwargs):
    args = dict(chat="Chat", msg_id=7, date=DATE, name="foto.jpg", kind="photo")
    return build_path(template, Path("dl"), **{**args, **kwargs})


def test_default_template():
    assert _build("{chat}/{date}_{id}{ext}") == Path("dl/Chat/2026-08-18_7.jpg")


def test_name_and_type_placeholders():
    assert _build("{type}/{name}{ext}") == Path("dl/photo/foto.jpg")


def test_directory_traversal_neutralised():
    path = _build("{chat}/{name}{ext}", chat="../../etc", name="../../../passwd.txt")
    assert ".." not in str(path)
    assert str(path).startswith("dl/")


def test_separators_in_telegram_names_do_not_create_directories():
    path = _build("{name}{ext}", name="a/b/c.bin")
    assert path == Path("dl/a_b_c.bin")


def test_without_a_file_name_the_id_is_used():
    assert _build("{name}{ext}", name=None) == Path("dl/media_7")


def test_without_a_date():
    assert _build("{date}_{id}", date=None) == Path("dl/no-date_7")


def test_unknown_placeholder():
    with pytest.raises(UsageError, match="unknown placeholder"):
        _build("{pippo}")


def test_empty_template():
    with pytest.raises(UsageError):
        _build("")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("a/b", "a_b"), ("..", "_"), (" name ", "name"), ("", "_"), ("a:b|c", "a_b_c")],
)
def test_safe_component(value, expected):
    assert safe_component(value) == expected


# --- recognising the already-downloaded file --------------------------------


def test_ext_hint_used_when_the_name_is_missing():
    assert _build("{id}{ext}", name=None, ext_hint=".jpg") == Path("dl/7.jpg")


def test_ext_hint_ignored_when_the_name_already_has_one():
    assert _build("{name}{ext}", name="foto.png", ext_hint=".jpg") == Path("dl/foto.png")


def test_ext_hint_without_a_dot():
    assert _build("{id}{ext}", name=None, ext_hint="jpg") == Path("dl/7.jpg")


def _touch(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_find_existing_finds_the_exact_path(tmp_path):
    from tgpipe.commands.media import find_existing

    target = tmp_path / "7.jpg"
    _touch(target, 10)
    assert find_existing(target, 10) == target


def test_find_existing_finds_the_extension_telethon_chose(tmp_path):
    """Telethon picks the extension at download time: the template may lack it."""
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "7.jpg", 10)
    assert find_existing(tmp_path / "7", 10) == tmp_path / "7.jpg"


def test_find_existing_rejects_a_different_size(tmp_path):
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "7.jpg", 5)
    assert find_existing(tmp_path / "7", 10) is None


def test_find_existing_accepts_when_no_size_is_expected(tmp_path):
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "7.jpg", 5)
    assert find_existing(tmp_path / "7", None) == tmp_path / "7.jpg"


def test_find_existing_does_not_confuse_a_prefix_stem(tmp_path):
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "77.jpg", 10)
    assert find_existing(tmp_path / "7", 10) is None


def test_find_existing_ignores_suffixed_duplicates(tmp_path):
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "7 (1).jpg", 10)
    assert find_existing(tmp_path / "7", 10) is None


def test_find_existing_missing_directory(tmp_path):
    from tgpipe.commands.media import find_existing

    assert find_existing(tmp_path / "manca" / "7.jpg", 10) is None


def test_find_existing_stem_with_glob_characters(tmp_path):
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "foto[1].jpg", 10)
    assert find_existing(tmp_path / "foto[1]", 10) == tmp_path / "foto[1].jpg"


# --- for photos the declared size is not the size saved ---------------------


def test_photo_recognised_despite_a_different_size(tmp_path):
    """file.size for photos is the largest progressive variant, not the bytes
    that end up on disk: demanding an exact match would re-download the photo
    on every run."""
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "7.jpg", 311)
    assert find_existing(tmp_path / "7", 663, "photo") == tmp_path / "7.jpg"


def test_web_preview_and_sticker_same_tolerance(tmp_path):
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "7.jpg", 1)
    assert find_existing(tmp_path / "7", 999, "webpage") is not None
    assert find_existing(tmp_path / "7", 999, "sticker") is not None


def test_documents_stay_strict(tmp_path):
    """For documents the declared size is exact: a mismatch means the file is
    truncated and must be downloaded again."""
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "7.pdf", 100)
    assert find_existing(tmp_path / "7", 999, "document") is None
    assert find_existing(tmp_path / "7", 100, "document") == tmp_path / "7.pdf"


def test_empty_photo_does_not_count_as_downloaded(tmp_path):
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "7.jpg", 0)
    assert find_existing(tmp_path / "7", 663, "photo") is None


def test_without_a_kind_the_old_behaviour_stands(tmp_path):
    from tgpipe.commands.media import find_existing

    _touch(tmp_path / "7.jpg", 311)
    assert find_existing(tmp_path / "7", 663) is None
