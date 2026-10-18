"""Generates synthetic technical-drawing-style SVG preview images into backend/seed_assets/.

Run: python generate_seed_assets.py
These are referenced by seed.py when creating the 3 demo projects.
"""
import os
from xml.sax.saxutils import escape

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_assets")


def title_block(dwg_no: str, title: str, rev: str, scale: str, w: int, h: int) -> str:
    x0, y0 = w - 260, h - 100
    return f"""
    <g font-family="Consolas, monospace" font-size="10" stroke="#333" fill="#222">
      <rect x="{x0}" y="{y0}" width="250" height="90" fill="white" stroke="#333" stroke-width="1.2"/>
      <line x1="{x0}" y1="{y0+25}" x2="{x0+250}" y2="{y0+25}" stroke="#333"/>
      <line x1="{x0}" y1="{y0+50}" x2="{x0+250}" y2="{y0+50}" stroke="#333"/>
      <line x1="{x0+150}" y1="{y0+50}" x2="{x0+150}" y2="{y0+90}" stroke="#333"/>
      <text x="{x0+8}" y="{y0+17}" font-weight="bold">{escape(title)}</text>
      <text x="{x0+8}" y="{y0+40}">DWG NO: {escape(dwg_no)}</text>
      <text x="{x0+8}" y="{y0+65}">REV: {rev}</text>
      <text x="{x0+158}" y="{y0+65}">SCALE: {scale}</text>
      <text x="{x0+8}" y="{y0+85}">UNITS: mm   MATERIAL: SEE BOM</text>
    </g>
    """


def dim_line(x1, y1, x2, y2, label) -> str:
    return f"""
    <g stroke="#555" stroke-width="0.6" font-family="Consolas, monospace" font-size="9" fill="#333">
      <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>
      <line x1="{x1}" y1="{y1-5}" x2="{x1}" y2="{y1+5}"/>
      <line x1="{x2}" y1="{y2-5}" x2="{x2}" y2="{y2+5}"/>
      <text x="{(x1+x2)/2 - 12}" y="{y1 - 6}">{escape(label)}</text>
    </g>
    """


def border(w, h):
    return f'<rect x="10" y="10" width="{w-20}" height="{h-20}" fill="none" stroke="#333" stroke-width="2"/>'


def gearbox_svg() -> str:
    w, h = 1000, 700
    body = f"""
    <rect x="150" y="200" width="300" height="200" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <circle cx="230" cy="300" r="60" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <circle cx="230" cy="300" r="20" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    <circle cx="370" cy="300" r="40" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <circle cx="370" cy="300" r="14" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    <line x1="80" y1="300" x2="150" y2="300" stroke="#1a1a1a" stroke-width="3"/>
    <line x1="450" y1="300" x2="520" y2="300" stroke="#1a1a1a" stroke-width="3"/>
    {dim_line(150, 180, 450, 180, '300.0 +/-0.2')}
    {dim_line(130, 200, 130, 400, '200.0')}
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
    <rect width="{w}" height="{h}" fill="#fafafa"/>
    {border(w, h)}
    {body}
    {title_block('GB-1001', 'GEARBOX ASSEMBLY', 'B', '1:2', w, h)}
    </svg>"""


def shaft_bearing_svg() -> str:
    w, h = 1000, 700
    body = f"""
    <rect x="200" y="320" width="500" height="40" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <rect x="260" y="300" width="60" height="80" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <rect x="620" y="300" width="60" height="80" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <circle cx="290" cy="340" r="24" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    <circle cx="650" cy="340" r="24" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    {dim_line(200, 280, 700, 280, '500.0 +/-0.1')}
    {dim_line(180, 300, 180, 380, 'dia 25.0 h7')}
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
    <rect width="{w}" height="{h}" fill="#fafafa"/>
    {border(w, h)}
    {body}
    {title_block('SH-2002', 'SHAFT & BEARING ASSEMBLY', 'A', '1:1', w, h)}
    </svg>"""


def bracket_svg() -> str:
    w, h = 1000, 700
    body = f"""
    <path d="M250 250 H550 V300 H400 V450 H250 Z" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <circle cx="280" cy="420" r="10" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    <circle cx="520" cy="280" r="10" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    {dim_line(250, 230, 550, 230, '300.0')}
    {dim_line(230, 250, 230, 450, '200.0')}
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
    <rect width="{w}" height="{h}" fill="#fafafa"/>
    {border(w, h)}
    {body}
    {title_block('BR-3003', 'SHEET METAL BRACKET', 'C', '1:1', w, h)}
    </svg>"""


def no_bom_table_svg() -> str:
    """A single 2D sketch view with dimensions and a material legend, but deliberately NO
    ITEM/QTY/PART-NO BOM table grid anywhere - used to test that reference_bom_service
    correctly reports no detection on a drawing that legitimately has none (as opposed to a
    detector that never fires, or one that over-triggers on any text block)."""
    w, h = 1000, 700
    body = f"""
    <rect x="220" y="220" width="400" height="260" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <circle cx="300" cy="300" r="30" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    <circle cx="540" cy="300" r="30" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    <circle cx="300" cy="400" r="30" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    <circle cx="540" cy="400" r="30" fill="none" stroke="#1a1a1a" stroke-width="1.5"/>
    {dim_line(220, 200, 620, 200, '400.0 +/-0.15')}
    {dim_line(200, 220, 200, 480, '260.0')}
    <g font-family="Consolas, monospace" font-size="10" fill="#222">
      <text x="220" y="520">LEGEND:</text>
      <text x="220" y="535">4x HOLES, dia 12.0mm THRU</text>
      <text x="220" y="550">MATERIAL: Aluminum 6061-T6</text>
    </g>
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
    <rect width="{w}" height="{h}" fill="#fafafa"/>
    {border(w, h)}
    {body}
    {title_block('MB-10045-REV-C', 'PUMP HOUSING BRACKET', 'C', '1:2', w, h)}
    </svg>"""


def _convolutions(x_start: float, x_end: float, outer: float, inner: float, count: int) -> str:
    """Zigzag outline of a bellows convolution pack between x_start and x_end, mirrored about
    the centre line so the top edge peaks at `outer` and dips to `inner`."""
    step = (x_end - x_start) / (count * 2)
    top = [f"{x_start},{inner}"]
    for i in range(count * 2):
        top.append(f"{x_start + (i + 1) * step:.1f},{outer if i % 2 == 0 else inner}")
    return " ".join(top)


def bom_table(x: int, y: int, rows: list[tuple[str, str, str, str]]) -> str:
    widths = [40, 130, 190, 40]
    head = ("ITEM", "PART NO", "DESCRIPTION", "QTY")
    out = ['<g font-family="Consolas, monospace" font-size="10" fill="#222" stroke="#333">']
    for r_i, row in enumerate([head] + rows):
        cx = x
        ry = y + r_i * 18
        for val, wdt in zip(row, widths):
            out.append(f'<rect x="{cx}" y="{ry}" width="{wdt}" height="18" fill="white" stroke-width="0.8"/>')
            weight = ' font-weight="bold"' if r_i == 0 else ""
            out.append(f'<text x="{cx + 4}" y="{ry + 13}" stroke="none"{weight}>{escape(val)}</text>')
            cx += wdt
    out.append("</g>")
    return "\n".join(out)


def bellows_assembly_svg() -> str:
    w, h = 1000, 700
    cy = 330
    pack_top = _convolutions(244, 696, 215, 255, 10)
    pack_bot = " ".join(f"{p.split(',')[0]},{2 * cy - float(p.split(',')[1])}" for p in pack_top.split())
    holes = "".join(
        f'<circle cx="{880 + 72 * __import__("math").cos(a * 3.14159 / 4):.1f}" '
        f'cy="{230 + 72 * __import__("math").sin(a * 3.14159 / 4):.1f}" r="6" fill="none" stroke="#1a1a1a" stroke-width="1.2"/>'
        for a in range(8)
    )
    body = f"""
    <line x1="120" y1="{cy}" x2="800" y2="{cy}" stroke="#777" stroke-width="0.8" stroke-dasharray="14 4 3 4"/>
    <rect x="170" y="200" width="24" height="260" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <rect x="746" y="200" width="24" height="260" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <rect x="194" y="255" width="50" height="150" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <rect x="696" y="255" width="50" height="150" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <polyline points="{pack_top}" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <polyline points="{pack_bot}" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <line x1="194" y1="290" x2="746" y2="290" stroke="#1a1a1a" stroke-width="1" stroke-dasharray="6 4"/>
    <line x1="194" y1="370" x2="746" y2="370" stroke="#1a1a1a" stroke-width="1" stroke-dasharray="6 4"/>
    <circle cx="880" cy="230" r="90" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <circle cx="880" cy="230" r="55" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <circle cx="880" cy="230" r="72" fill="none" stroke="#777" stroke-width="0.6" stroke-dasharray="8 4"/>
    {holes}
    <text x="842" y="345" font-family="Consolas, monospace" font-size="10" fill="#333">END VIEW</text>
    {dim_line(170, 170, 770, 170, '600.0 OAL')}
    {dim_line(130, 200, 130, 460, 'DIA 260.0')}
    {bom_table(40, 500, [
        ("1", "BLW-1005-01", "Bellows Element SS321", "1"),
        ("2", "FLG-1005-02", "Flange ASME 150#", "2"),
        ("3", "LNR-1005-03", "Internal Liner", "1"),
        ("4", "TIE-ROD-M16", "Tie Rod M16", "4"),
        ("5", "HEX-NUT-M16", "Hex Nut M16", "8"),
    ])}
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
    <rect width="{w}" height="{h}" fill="#fafafa"/>
    {border(w, h)}
    {body}
    {title_block('EX-1005', 'BELLOWS ASSEMBLY', 'A', '1:4', w, h)}
    </svg>"""


def expansion_joint_svg() -> str:
    w, h = 1000, 700
    cy = 330
    pack_top = _convolutions(232, 768, 250, 280, 12)
    pack_bot = " ".join(f"{p.split(',')[0]},{2 * cy - float(p.split(',')[1])}" for p in pack_top.split())
    nuts = "".join(
        f'<rect x="{x}" y="{y - 9}" width="14" height="18" fill="white" stroke="#1a1a1a" stroke-width="1.5"/>'
        for x in (182, 236, 750, 804) for y in (215, 445)
    )
    body = f"""
    <line x1="40" y1="{cy}" x2="960" y2="{cy}" stroke="#777" stroke-width="0.8" stroke-dasharray="14 4 3 4"/>
    <rect x="60" y="290" width="150" height="80" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <rect x="790" y="290" width="150" height="80" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <rect x="210" y="230" width="22" height="200" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <rect x="768" y="230" width="22" height="200" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <polyline points="{pack_top}" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <polyline points="{pack_bot}" fill="none" stroke="#1a1a1a" stroke-width="2"/>
    <line x1="190" y1="215" x2="810" y2="215" stroke="#1a1a1a" stroke-width="2.5"/>
    <line x1="190" y1="445" x2="810" y2="445" stroke="#1a1a1a" stroke-width="2.5"/>
    {nuts}
    {dim_line(60, 175, 940, 175, '880.0 OAL')}
    {dim_line(232, 485, 768, 485, '536.0 LIVE LENGTH')}
    {bom_table(40, 520, [
        ("1", "PL-4001-01", "Bellows Pack SS316L", "1"),
        ("2", "PL-4001-02", "Pipe End NB200", "2"),
        ("3", "TIE-ROD-M16", "Tie Rod M16", "2"),
        ("4", "HEX-NUT-M16", "Hex Nut M16", "8"),
    ])}
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
    <rect width="{w}" height="{h}" fill="#fafafa"/>
    {border(w, h)}
    {body}
    {title_block('PL-4001', 'PIPE EXPANSION JOINT', 'B', '1:5', w, h)}
    </svg>"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = {
        "gearbox_assembly.svg": gearbox_svg(),
        "shaft_bearing_assembly.svg": shaft_bearing_svg(),
        "sheet_metal_bracket.svg": bracket_svg(),
        "no_bom_table_fixture.svg": no_bom_table_svg(),
        "bellows_assembly.svg": bellows_assembly_svg(),
        "pipe_expansion_joint.svg": expansion_joint_svg(),
    }
    for name, content in files.items():
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
