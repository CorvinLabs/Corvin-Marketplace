"""Designs for the board tests (ADR-2260, T-0197): small hand-made Penpot-shaped SVGs and the WORST design a board
allows - every bound of ``penpot_import.BOARD_*`` met at once - which the frame-time test renders (decision 10)."""

SVG_HEAD = '<svg id="shape-test" xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">'


def simple_svg() -> bytes:
    """Four shapes in three top-level groups: a title text, a stroked path, a filled ellipse, a fill-only path."""
    return (SVG_HEAD
            + '<rect x="0" y="0" width="1600" height="900" fill="#ffffff"/>'
            + '<g><text x="100" y="160" font-family="Inter" font-size="72" fill="#111111">Pipeline overview</text></g>'
            + '<g><path d="M100 400 L1500 400" fill="none" stroke="#ff8800" stroke-width="12"/></g>'
            + '<g><ellipse cx="400" cy="650" rx="140" ry="140" fill="#3366cc"/>'
            + '<path d="M900 550 L1200 550 L1050 800 Z" fill="#22aa55"/></g>'
            + '</svg>').encode()


def many_shapes_svg(n: int) -> bytes:
    rects = "".join(f'<rect x="{(i * 13) % 1500}" y="{(i * 29) % 800}" width="40" height="30" fill="#3366cc"/>'
                    for i in range(n))
    return (SVG_HEAD + rects + "</svg>").encode()


def worst_svg(pi):
    n_shapes = pi.BOARD_MAX_SHAPES
    n_text = pi.BOARD_MAX_TEXT_LENGTH            # every text stretched (textLength)
    per_text = pi.BOARD_MAX_TEXT_CHARS // n_text
    n_path = 120
    per_path = pi.BOARD_MAX_PATH_CHARS // n_path
    n_rest = n_shapes - n_text - n_path
    grads = pi.BOARD_MAX_GRADIENTS
    s = pi.BOARD_MAX_MATRIX_SCALE
    out = ['<svg id="shape-test" xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080"><defs>']
    for g in range(grads):
        stops = "".join(f'<stop offset="{k/7:.3f}" stop-color="#{(g*37+k*29)%256:02x}{(k*61)%256:02x}{(g*13)%256:02x}" stop-opacity="0.8"/>' for k in range(8))
        out.append(f'<linearGradient id="g{g}" x1="0" y1="0" x2="1" y2="1">{stops}</linearGradient>')
    out.append('</defs>')
    translucent = 0
    def op():
        nonlocal translucent
        if translucent < pi.BOARD_MAX_TRANSLUCENT:
            translucent += 1
            return ' opacity="0.7"'
        return ""
    for i in range(n_path):
        # a zig-zag path of exactly per_path characters, scaled by the maximum factor (drawn small, rendered big)
        pts, d = [], "M0 0"
        k = 0
        while len(d) < per_path - 12:
            k += 1
            d += f" L{(k*3)%60} {(k*7)%40}"
        d = d[:per_path]
        d = d.rsplit(" L", 1)[0]
        x, y = (i % 12) * 150, (i // 12) * 100
        fill = f'url(#g{i % grads})' if i < 60 else "#3366cc"
        out.append(f'<path d="{d}" fill="{fill}" stroke="#ff8800" stroke-width="{pi.BOARD_MAX_STROKE:g}" '
                   f'transform="matrix({s} 0 0 {s} {x} {y})"{op()}/>')
    for i in range(n_text):
        txt = ("Wide text " * 20)[:per_text]
        out.append(f'<text x="{(i % 6) * 300}" y="{100 + (i // 6) * 90}" font-family="Inter" font-size="{pi.BOARD_MAX_FONT:g}" '
                   f'textLength="1800"{op()} fill="#222222">{txt}</text>')
    for i in range(n_rest):
        if i % 2:
            out.append(f'<rect x="{(i*37)%1800}" y="{(i*53)%1000}" width="400" height="300" rx="20" fill="url(#g{i % grads})"{op()} stroke="#000000" stroke-width="{pi.BOARD_MAX_STROKE:g}"/>')
        else:
            out.append(f'<ellipse cx="{(i*41)%1800}" cy="{(i*59)%1000}" rx="200" ry="150" fill="#cc3344"{op()}/>')
    out.append('</svg>')
    return "".join(out).encode()
