"""Per-tenant style store (PLAN-0945 P2)."""

import json
import os

import pytest

from src.style_pack import StyleError
from src.style_store import MAX_STYLES, StyleNotFound, StyleQuotaExceeded, StyleStore
from tests.test_style_pack import _png, make_style


@pytest.fixture
def store(tmp_path):
    return StyleStore(str(tmp_path / "tenant"))


def test_roundtrip_keeps_everything(store):
    st = make_style(id=store.new_id(), plate_png=_png((1920, 1080)), plate_safe={"x": 200, "y": 120, "w": 1500, "h": 800})
    store.save(st)
    back = store.load(st.id)
    assert back.tokens == st.tokens and back.mark_png == st.mark_png and back.plate_png == st.plate_png
    assert back.plate_safe == st.plate_safe and back.wordmark == "Acme Corp"
    assert [s.id for s in store.list()] == [st.id]


def test_a_stored_style_is_immutable(store):
    st = make_style(id=store.new_id())
    store.save(st)
    with pytest.raises(StyleError, match="already exists"):
        store.save(st)


@pytest.mark.parametrize("bad", ["../etc", "sty_/../x", "sty_ZZZZZZZZ", "", None, "corvin", "sty_0a1b2c3d/../../x"])
def test_ids_never_reach_the_filesystem_unvalidated(store, bad):
    with pytest.raises(StyleNotFound):
        store.load(bad)
    with pytest.raises(StyleNotFound):
        store.delete(bad)


def test_quota(store):
    for _ in range(MAX_STYLES):
        store.save(make_style(id=store.new_id()))
    with pytest.raises(StyleQuotaExceeded):
        store.save(make_style(id=store.new_id()))


def test_tampered_file_is_refused_not_trusted(store):
    st = make_style(id=store.new_id())
    store.save(st)
    p = store.root / st.id / "style.json"
    doc = json.loads(p.read_text())
    doc["tokens"]["dark"]["text"] = doc["tokens"]["dark"]["bg"]  # unreadable
    p.write_text(json.dumps(doc))
    with pytest.raises(StyleError):
        store.load(st.id)
    assert store.list() == [], "a damaged style must be skipped, never rendered"


def test_swapped_logo_is_revalidated(store):
    st = make_style(id=store.new_id())
    store.save(st)
    (store.root / st.id / "logo.png").write_bytes(b"<svg onload=alert(1)/>")
    with pytest.raises(StyleError):
        store.load(st.id)


def test_symlinked_style_dir_and_files_are_not_followed(store, tmp_path):
    st = make_style(id=store.new_id())
    store.save(st)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "style.json").write_text("{}")
    link = store.root / "sty_deadbeef"
    os.symlink(outside, link)
    assert "sty_deadbeef" not in store.ids()
    with pytest.raises(StyleNotFound):
        store.load("sty_deadbeef")
    os.unlink(store.root / st.id / "style.json")
    os.symlink(outside / "style.json", store.root / st.id / "style.json")
    with pytest.raises((StyleError, OSError)):
        store.load(st.id)


def test_default_follows_the_style_and_dies_with_it(store):
    a, b = make_style(id=store.new_id()), None
    store.save(a)
    assert store.get_default() is None
    store.set_default(a.id)
    assert store.get_default() == a.id
    store.delete(a.id)
    assert store.get_default() is None
    with pytest.raises(StyleNotFound):
        store.set_default("sty_00000000")


def test_files_are_private(store):
    st = make_style(id=store.new_id())
    store.save(st)
    assert oct((store.root / st.id / "style.json").stat().st_mode & 0o777) == "0o600"


def test_two_tenants_do_not_share_a_store(tmp_path):
    a, b = StyleStore(str(tmp_path / "a")), StyleStore(str(tmp_path / "b"))
    st = make_style(id=a.new_id())
    a.save(st)
    assert b.ids() == []
    with pytest.raises(StyleNotFound):
        b.load(st.id)


def test_erase_all(store):
    for _ in range(3):
        store.save(make_style(id=store.new_id()))
    assert store.erase_all() == 3 and store.ids() == []
