"""Asset store (ADR-2249 D3, T-0111): what a stored image is, what is refused, what survives erasure."""
import io
import json
import os
import struct
import threading
import zlib

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from src import asset_store as A


def png(w=64, h=48, color=(200, 30, 30), mode="RGB", info=None, extra_chunks=b"", trailing=b""):
    img = Image.new(mode, (w, h), color if mode == "RGB" else (*color, 128))
    out = io.BytesIO()
    kw = {"pnginfo": info} if info else {}
    img.save(out, format="PNG", **kw)
    raw = out.getvalue()
    if extra_chunks:
        raw = raw[:-12] + extra_chunks + raw[-12:]
    return raw + trailing


def chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def chunks_of(raw: bytes):
    pos, out = 8, []
    while pos < len(raw):
        n = struct.unpack(">I", raw[pos:pos + 4])[0]
        out.append(raw[pos + 4:pos + 8].decode())
        pos += 12 + n
    return out


@pytest.fixture
def store(tmp_path):
    return A.AssetStore(str(tmp_path / "tenant"))


def add(store, **kw):
    kw.setdefault("caption", "The settings page")
    kw.setdefault("uploaded_by", "user_a")
    return store.add(kw.pop("data", png()), **kw)


def test_the_image_is_rebuilt_from_pixels_and_nothing_of_the_upload_survives(store):
    info = PngInfo()
    info.add_text("Author", "Jane Doe <jane@example.com>")
    info.add_text("GPS", "48.1,11.5")
    hostile = png(info=info, extra_chunks=chunk(b"eXIf", b"MM\x00*" + b"secret") + chunk(b"iCCP", b"x\x00\x00junk"),
                  trailing=b"TRAILING-SECRET")
    assert b"jane@example.com" in hostile and b"TRAILING-SECRET" in hostile
    rec = add(store, data=hostile)
    stored = store.get(rec["id"])["png"]
    assert not {"tEXt", "iTXt", "zTXt", "eXIf", "iCCP", "tIME"} & set(chunks_of(stored)), chunks_of(stored)
    assert b"jane@example.com" not in stored and b"TRAILING-SECRET" not in stored and b"secret" not in stored
    assert chunks_of(stored)[0] == "IHDR" and chunks_of(stored)[-1] == "IEND"
    back = Image.open(io.BytesIO(stored))
    assert back.size == (64, 48) and back.getpixel((1, 1)) == (200, 30, 30)


def test_alpha_is_kept_and_palette_images_are_normalised(store):
    rec = add(store, data=png(mode="RGBA"))
    assert Image.open(io.BytesIO(store.get(rec["id"])["png"])).mode == "RGBA"
    pal = io.BytesIO()
    Image.new("P", (32, 32), 3).save(pal, format="PNG")
    assert Image.open(io.BytesIO(store.get(add(store, data=pal.getvalue())["id"])["png"])).mode == "RGB"


@pytest.mark.parametrize("bad,why", [
    (b"", "empty"), (b"GIF89a" + b"0" * 100, "only PNG"), (b"\x89PNG\r\n\x1a\n" + b"junk" * 50, "not a readable PNG"),
    (png(8, 8), "pixels per side"), (png(5000, 20), "pixels per side"),
])
def test_what_is_not_a_reasonable_png_is_refused_with_a_safe_message(store, bad, why):
    with pytest.raises(A.AssetError, match=why):
        add(store, data=bad)
    assert store.ids() == []


def test_a_decompression_bomb_is_refused_from_its_header_before_pixels_are_decoded(store):
    ihdr = struct.pack(">IIBBBBB", 20000, 20000, 8, 2, 0, 0, 0)
    bomb = A.PNG_MAGIC + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00" * 100)) + chunk(b"IEND", b"")
    with pytest.raises(A.AssetError, match="pixels per side|megapixels"):
        add(store, data=bomb)


def test_the_size_cap_applies_to_the_re_encoded_image(store, monkeypatch):
    monkeypatch.setattr(A, "MAX_IMAGE_BYTES", 300)
    noisy = Image.frombytes("RGB", (64, 64), os.urandom(64 * 64 * 3))
    buf = io.BytesIO()
    noisy.save(buf, format="PNG")
    with pytest.raises(A.AssetError, match="after it was re-encoded"):
        add(store, data=buf.getvalue())


def test_at_most_fifty_per_tenant_even_when_uploads_race(store, monkeypatch):
    monkeypatch.setattr(A, "MAX_ASSETS", 5)
    results, lock = [], threading.Lock()

    def one():
        try:
            add(store)
            r = "ok"
        except A.AssetQuotaExceeded:
            r = "quota"
        with lock:
            results.append(r)

    ts = [threading.Thread(target=one) for _ in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count("ok") == 5 and results.count("quota") == 7 and len(store.ids()) == 5


@pytest.mark.parametrize("evil", ["../x", "ast_../../x", "ast_ZZZZZZZZ", "ast_0123456", "ast_012345678", "", "/etc/passwd",
                                  "ast_01234567/../../x", None, 5])
def test_an_id_that_is_not_ast_8hex_never_touches_a_path(store, evil):
    for call in (store.get, store.delete):
        with pytest.raises(A.AssetNotFound):
            call(evil)


def test_a_symlinked_asset_or_file_is_never_followed(store, tmp_path):
    rec = add(store)
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    link = store.root / "ast_deadbeef"
    link.symlink_to(store.root / rec["id"], target_is_directory=True)
    with pytest.raises(A.AssetNotFound):
        store.get("ast_deadbeef")
    assert "ast_deadbeef" not in store.ids()
    img = store.root / rec["id"] / "image.png"
    img.unlink()
    img.symlink_to(secret)
    with pytest.raises(A.AssetError):
        store.get(rec["id"])


def test_a_hand_edited_record_is_refused_not_trusted(store):
    rec = add(store, hotspots=[{"name": "save", "x": .5, "y": .5, "description": "the save button"}])
    p = store.root / rec["id"] / "asset.json"
    doc = json.loads(p.read_text())
    doc["hotspots"][0]["x"] = 7
    p.write_text(json.dumps(doc))
    with pytest.raises(A.AssetError):
        store.get(rec["id"])
    assert store.list() == [] and store.catalogue() == {}


def test_caption_and_hotspots_are_user_text_that_is_cleaned_and_bounded(store):
    rec = add(store, caption="  Settings‮ page\x00 \n tab ", hotspots=[
        {"name": "save", "x": 0.25, "y": 1, "description": "the​ save   button"}])
    assert rec["caption"] == "Settings page tab" and rec["hotspots"][0]["description"] == "the save button"
    for bad in ({"caption": ""}, {"caption": "x" * 161}, {"caption": 5}):
        with pytest.raises(A.AssetError):
            add(store, **bad)
    for bad in ([{"name": "Save", "x": .1, "y": .1}], [{"name": "ok_1", "x": 1.5, "y": .1}],
                [{"name": "ok_1", "x": True, "y": .1}], [{"name": "ok_1", "x": .1, "y": .1, "selector": "#a"}],
                [{"name": "dup", "x": .1, "y": .1}, {"name": "dup", "x": .2, "y": .2}],
                [{"name": f"s{i:02d}", "x": .1, "y": .1} for i in range(9)], "x"):
        with pytest.raises(A.AssetError):
            add(store, hotspots=bad)


@pytest.mark.parametrize("raw,clean", [
    ("https://user:pw@Example.COM/a/b?token=SECRET#frag", "https://example.com/a/b"),
    ("http://host.test", "http://host.test"),
    ("https://signed.test/p?X-Amz-Signature=abc", "https://signed.test/p"),
    (None, ""), ("", ""),
])
def test_provenance_keeps_scheme_host_path_only(raw, clean):
    assert A.sanitise_provenance(raw) == clean


@pytest.mark.parametrize("raw", ["javascript:alert(1)", "file:///etc/passwd", "ftp://h/x", "not a url", "https://", "http://[::1"])
def test_provenance_refuses_anything_that_is_not_plain_http(raw):
    with pytest.raises(A.AssetError):
        A.sanitise_provenance(raw)


def test_the_uploader_is_a_session_id_never_a_path(store):
    a1, a2 = add(store, uploaded_by="console-owner:tenant_a"), add(store, uploaded_by="user_b")
    assert store.public(a1["id"])["uploaded_by"] == "console-owner:tenant_a" and a1["id"] != a2["id"]
    with pytest.raises(A.AssetError, match="uploading user"):
        add(store, uploaded_by="../../etc")


def test_delete_removes_the_whole_asset_directory(store):
    rec = add(store)
    store.delete(rec["id"])
    assert store.ids() == [] and not (store.root / rec["id"]).exists()
    with pytest.raises(A.AssetNotFound):
        store.delete(rec["id"])


def test_hygiene_is_clean_for_a_stored_asset_and_names_every_defect(store):
    info = PngInfo()
    info.add_text("Author", "Jane")
    rec = add(store, data=png(info=info, trailing=b"X"), source="https://u:p@h.test/a?sig=1#f")
    got = store.get(rec["id"])
    assert A.hygiene_findings(got["png"], got) == []
    dirty = png(info=info, trailing=b"X")
    found = A.hygiene_findings(dirty, {**got, "source": "https://h.test/a?sig=1"})
    assert found[0].startswith("metadata:") and "tEXt" in found[0] and "<trailing>" in found[0]
    assert "provenance" in found
    assert A.hygiene_findings(got["png"], {**got, "width": 99999}) == ["dimensions"]
    assert A.hygiene_findings(b"GIF89a", got) == ["metadata:<not-png>"]


def test_a_tenant_without_assets_gets_no_directory_and_the_binding_is_scoped(tmp_path):
    outer = A.current()  # conftest binds the fixture tenant
    base = str(tmp_path / "t")
    with A.bound(base) as s:
        assert A.current() is s and not (tmp_path / "t" / "assets").exists()
    assert A.current() is outer
    with A.bound(None) as s:
        assert s is None and A.current() is None
    assert A.current() is outer


def test_before_commit_sees_the_final_record_and_a_refusal_stores_nothing(store):
    seen = []
    rec = add(store, before_commit=lambda doc: seen.append(doc) or True)
    assert seen[0]["id"] == rec["id"] and seen[0]["bytes"] == rec["bytes"]
    with pytest.raises(A.AssetNotRecorded):
        add(store, before_commit=lambda doc: False)
    assert store.ids() == [rec["id"]] and [p.name for p in store.root.iterdir() if p.name.startswith(".new")] == []
