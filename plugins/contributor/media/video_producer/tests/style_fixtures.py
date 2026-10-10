"""Synthetic PowerPoint decks for the style importer tests. No real data: everything is generated.

``make_deck(**opts)`` returns the bytes of a small valid deck. ``HOSTILE`` maps a name to a
zero-argument builder returning hostile bytes; ``HOSTILE_REFUSED`` must raise PptxImportError,
``HOSTILE_NEUTRALISED`` must import with the dangerous part ignored.
"""

import io
import struct
import warnings
import zipfile
import zlib
from typing import Callable, Dict, Optional

SECRET_TEXT = "SECRET-SLIDE-TEXT"
SECRET_NOTE = "SECRET-NOTE-TEXT"
SECRET_AUTHOR = "SECRET-AUTHOR-NAME"

DISTINCT_SCHEME = dict(dk1="1a1a2e", lt1="ffffff", dk2="16213e", lt2="e9ecef", accent1="c2185b",
                       accent2="0f3460", accent3="533483", accent4="e94560", accent5="2b6777", accent6="52ab98")
OFFICE_2013_SCHEME = dict(dk1="000000", lt1="ffffff", dk2="44546A", lt2="E7E6E6", accent1="4472C4",
                          accent2="ED7D31", accent3="A5A5A5", accent4="FFC000", accent5="5B9BD5", accent6="70AD47")
OFFICE_2007_SCHEME = dict(dk1="000000", lt1="ffffff", dk2="1F497D", lt2="EEECE1", accent1="4F81BD",
                          accent2="C0504D", accent3="9BBB59", accent4="8064A2", accent5="4BACC6", accent6="F79646")

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
RELNS = "http://schemas.openxmlformats.org/package/2006/relationships"
RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def png_bytes(size=(200, 100), color=(11, 114, 133, 255)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def declared_huge_png(w=60000, h=60000) -> bytes:
    """A syntactically valid PNG header that claims w x h pixels, with almost no data."""
    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" * 16)) + chunk(b"IEND", b""))


def theme_xml(scheme: Dict[str, str], major="Calibri", minor="Calibri") -> bytes:
    cols = "".join(f'<a:{k}><a:srgbClr val="{v}"/></a:{k}>' for k, v in scheme.items())
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme {NS} name="T"><a:themeElements>'
            f'<a:clrScheme name="Custom">{cols}</a:clrScheme><a:fontScheme name="F">'
            f'<a:majorFont><a:latin typeface="{major}"/></a:majorFont>'
            f'<a:minorFont><a:latin typeface="{minor}"/></a:minorFont></a:fontScheme>'
            f'</a:themeElements></a:theme>').encode()


def _rels(items) -> bytes:
    body = "".join(
        f'<Relationship Id="{i}" Type="{t}" Target="{tg}"' + (' TargetMode="External"' if ext else "") + "/>"
        for i, t, tg, ext in items)
    return f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{RELNS}">{body}</Relationships>'.encode()


def make_deck(*, aspect="16:9", scheme: Optional[Dict[str, str]] = None, major="Georgia", minor="Verdana",
              logo: object = "png", logo_color=(11, 114, 133, 255), bg: Optional[str] = None,
              clrmap=("lt1", "dk1"), shape_fill: Optional[str] = None, external_rels=0, embedded_fonts=0,
              template=False, extra_parts: Optional[Dict[str, bytes]] = None, theme: Optional[bytes] = None,
              extra_content_types="") -> bytes:
    """logo: "png" | "svg" | None | raw bytes (PNG)."""
    scheme = scheme or DISTINCT_SCHEME
    cx, cy = (12192000, 6858000) if aspect == "16:9" else (9144000, 6858000)
    parts: Dict[str, bytes] = {}
    pres_type = "template" if template else "presentation"
    parts["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.{pres_type}.main+xml"/>'
        f'{extra_content_types}</Types>').encode()
    parts["_rels/.rels"] = _rels([("rId1", f"{RT}/officeDocument", "ppt/presentation.xml", False)])
    parts["docProps/core.xml"] = (f'<cp:coreProperties xmlns:cp="x"><dc:creator xmlns:dc="y">{SECRET_AUTHOR}'
                                  '</dc:creator></cp:coreProperties>').encode()
    parts["ppt/presentation.xml"] = (f'<p:presentation {NS}><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/>'
                                     f'</p:sldMasterIdLst><p:sldSz cx="{cx}" cy="{cy}"/></p:presentation>').encode()
    parts["ppt/_rels/presentation.xml.rels"] = _rels([
        ("rId1", f"{RT}/slideMaster", "slideMasters/slideMaster1.xml", False),
        ("rId2", f"{RT}/slide", "slides/slide1.xml", False)])
    parts["ppt/slides/slide1.xml"] = f'<p:sld {NS}><a:t>{SECRET_TEXT}</a:t></p:sld>'.encode()
    parts["ppt/notesSlides/notesSlide1.xml"] = f'<p:notes {NS}><a:t>{SECRET_NOTE}</a:t></p:notes>'.encode()
    parts["ppt/theme/theme1.xml"] = theme if theme is not None else theme_xml(scheme, major, minor)

    mrels = [("rId1", f"{RT}/theme", "../theme/theme1.xml", False),
             ("rId2", f"{RT}/slideLayout", "../slideLayouts/slideLayout1.xml", False)]
    pic = ""
    if logo:
        ext = "svg" if logo == "svg" else "png"
        if logo == "svg":
            parts["ppt/media/image1.svg"] = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        else:
            parts["ppt/media/image1.png"] = logo if isinstance(logo, (bytes, bytearray)) else png_bytes(color=logo_color)
        mrels.append(("rId3", f"{RT}/image", f"../media/image1.{ext}", False))
        pic = ('<p:pic><p:nvPicPr><p:cNvPr id="9" name="Logo"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>'
               '<p:blipFill><a:blip r:embed="rId3"/></p:blipFill><p:spPr><a:xfrm><a:off x="10500000" y="300000"/>'
               '<a:ext cx="1200000" cy="600000"/></a:xfrm></p:spPr></p:pic>')
    for i in range(external_rels):
        mrels.append((f"rIdX{i}", f"{RT}/hyperlink", f"http://203.0.113.{i}/x", True))
    bgxml = (f'<p:bg><p:bgPr><a:solidFill><a:srgbClr val="{bg}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
             if bg else "")
    shape = (f'<p:sp><p:nvSpPr><p:cNvPr id="5" name="Band"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm>'
             f'<a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy // 6}"/></a:xfrm><a:solidFill><a:srgbClr val="{shape_fill}"/>'
             f'</a:solidFill></p:spPr></p:sp>' if shape_fill else "")
    bg1, tx1 = clrmap
    parts["ppt/slideMasters/slideMaster1.xml"] = (
        f'<p:sldMaster {NS}><p:cSld>{bgxml}<p:spTree>{shape}{pic}</p:spTree></p:cSld>'
        f'<p:clrMap bg1="{bg1}" tx1="{tx1}" bg2="lt2" tx2="dk2" accent1="accent1"/></p:sldMaster>').encode()
    parts["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = _rels(mrels)
    parts["ppt/slideLayouts/slideLayout1.xml"] = f'<p:sldLayout {NS}><p:cSld><p:spTree/></p:cSld></p:sldLayout>'.encode()
    parts["ppt/slideLayouts/_rels/slideLayout1.xml.rels"] = _rels([("rId1", f"{RT}/slideMaster", "../slideMasters/slideMaster1.xml", False)])
    for i in range(embedded_fonts):
        parts[f"ppt/fonts/font{i + 1}.fntdata"] = b"\x00obfuscated" * 4
    parts.update(extra_parts or {})
    return zip_of(parts)


def zip_of(parts: Dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return buf.getvalue()


# ── hostile corpus ───────────────────────────────────────────────────────────

def _with_raw_entries(entries) -> bytes:
    """Valid deck plus entries whose NAMES are written verbatim (ZipInfo, no normalisation)."""
    base = zipfile.ZipFile(io.BytesIO(make_deck()))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for n in base.namelist():
            z.writestr(n, base.read(n))
        for name, data, attr in entries:
            zi = zipfile.ZipInfo(name)
            zi.external_attr = attr
            z.writestr(zi, data)
    return buf.getvalue()


def zip_bomb() -> bytes:
    return make_deck(extra_parts={"ppt/media/big.bin": bytes(40_000_000)})


def total_size_bomb() -> bytes:
    """180 entries of 900 KB zeros: each below the per-entry ratio floor, together > 150 MB."""
    return make_deck(extra_parts={f"ppt/media/z{i}.bin": bytes(900_000) for i in range(180)})


def too_many_entries() -> bytes:
    return make_deck(extra_parts={f"customXml/i{i}.xml": b"<a/>" for i in range(1600)})


def dtd_entity_bomb() -> bytes:
    lol = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
           '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]><a:theme xmlns:a="x">&lol3;</a:theme>')
    return make_deck(theme=lol.encode())


def external_entity() -> bytes:
    xxe = ('<?xml version="1.0"?><!DOCTYPE t [<!ENTITY x SYSTEM "file:///etc/passwd">]><a:theme xmlns:a="x">&x;</a:theme>')
    return make_deck(theme=xxe.encode())


def utf16_doctype() -> bytes:
    return make_deck(theme='<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE t [<!ENTITY x "y">]><t>&x;</t>'.encode("utf-16"))


def macro_deck() -> bytes:
    return make_deck(extra_parts={"ppt/vbaProject.bin": b"\xd0\xcf\x11\xe0 fake macro"},
                     extra_content_types='<Override PartName="/ppt/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/>')


def macro_content_type_only() -> bytes:
    return make_deck(extra_content_types='<Override PartName="/ppt/other.xml" ContentType="application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml"/>')


def path_traversal() -> bytes:
    return _with_raw_entries([("../../evil.xml", b"<a/>", 0)])


def absolute_name() -> bytes:
    return _with_raw_entries([("/etc/cron.d/evil", b"x", 0)])


def backslash_name() -> bytes:
    return _with_raw_entries([("ppt\\..\\..\\evil.xml", b"x", 0)])


def symlink_entry() -> bytes:
    return _with_raw_entries([("ppt/media/link.png", b"/etc/passwd", 0o120777 << 16)])


def duplicate_names() -> bytes:
    return _with_raw_entries([("ppt/theme/theme1.xml", b"<a/>", 0)])


def svg_script_logo() -> bytes:
    return make_deck(logo="svg")


def image_bomb() -> bytes:
    return make_deck(logo=declared_huge_png())


def oversize() -> bytes:
    return b"PK\x03\x04" + bytes(26 * 1024 * 1024)


def not_a_zip() -> bytes:
    return b"this is not a presentation at all"


def ole_ppt() -> bytes:
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(2048)


def truncated() -> bytes:
    d = make_deck()
    return d[: len(d) // 2]


def deeply_nested_xml() -> bytes:
    return make_deck(theme=b"<a:t xmlns:a='x'>" + b"<a:x>" * 5000 + b"</a:x>" * 5000 + b"</a:t>")


def node_bomb() -> bytes:
    return make_deck(theme=b"<a:t xmlns:a='x'>" + b"<a:b/>" * 400_000 + b"</a:t>")


def empty_file() -> bytes:
    return b""


HOSTILE_REFUSED: Dict[str, Callable[[], bytes]] = {
    "zip_bomb": zip_bomb, "total_size_bomb": total_size_bomb, "too_many_entries": too_many_entries,
    "dtd_entity_bomb": dtd_entity_bomb, "external_entity": external_entity, "utf16_doctype": utf16_doctype,
    "macro_deck": macro_deck, "macro_content_type_only": macro_content_type_only,
    "path_traversal": path_traversal, "absolute_name": absolute_name, "backslash_name": backslash_name,
    "symlink_entry": symlink_entry, "duplicate_names": duplicate_names, "oversize": oversize,
    "not_a_zip": not_a_zip, "ole_ppt": ole_ppt, "truncated": truncated, "deeply_nested_xml": deeply_nested_xml,
    "node_bomb": node_bomb, "empty_file": empty_file,
}
HOSTILE_NEUTRALISED: Dict[str, Callable[[], bytes]] = {
    "svg_script_logo": svg_script_logo, "image_bomb": image_bomb,
}
HOSTILE: Dict[str, Callable[[], bytes]] = {**HOSTILE_REFUSED, **HOSTILE_NEUTRALISED}
