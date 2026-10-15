"""Generates synthetic technical-drawing-style SVG preview images into backend/seed_assets/.

Run: python generate_seed_assets.py
These are referenced by seed.py when creating the 3 demo projects.
"""
import os

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_assets")


def title_block(dwg_no: str, title: str, rev: str, scale: str, w: int, h: int) -> str:
    x0, y0 = w - 260, h - 100
    return f"""
    <g font-family="Consolas, monospace" font-size="10" stroke="#333" fill="#222">
      <rect x="{x0}" y="{y0}" width="250" height="90" fill="white" stroke="#333" stroke-width="1.2"/>
      <line x1="{x0}" y1="{y0+25}" x2="{x0+250}" y2="{y0+25}" stroke="#333"/>
      <line x1="{x0}" y1="{y0+50}" x2="{x0+250}" y2="{y0+50}" stroke="#333"/>
      <line x1="{x0+150}" y1="{y0+50}" x2="{x0+150}" y2="{y0+90}" stroke="#333"/>
      <text x="{x0+8}" y="{y0+17}" font-weight="bold">{title}</text>
      <text x="{x0+8}" y="{y0+40}">DWG NO: {dwg_no}</text>
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
      <text x="{(x1+x2)/2 - 12}" y="{y1 - 6}">{label}</text>
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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = {
        "gearbox_assembly.svg": gearbox_svg(),
        "shaft_bearing_assembly.svg": shaft_bearing_svg(),
        "sheet_metal_bracket.svg": bracket_svg(),
    }
    for name, content in files.items():
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
