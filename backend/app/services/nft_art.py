from __future__ import annotations

import base64
import hashlib
import math
from html import escape

_SIZE = 512
_CENTER = _SIZE // 2


def _seed_bytes(chain_id: int, contract: str, token_id: str) -> bytes:
    seed = f"{chain_id}:{contract.lower()}:{token_id}".encode()
    return hashlib.sha256(seed).digest()


def _color(seed: bytes, offset: int) -> str:
    hue = int.from_bytes(seed[offset : offset + 2], "big") % 360
    saturation = 58 + seed[offset + 2] % 34
    lightness = 38 + seed[offset + 3] % 28
    return f"hsl({hue} {saturation}% {lightness}%)"


def svg_for(chain_id: int, contract: str, token_id: str) -> str:
    """Return deterministic, self-contained SVG art for one NFT identity."""
    seed = _seed_bytes(chain_id, contract, token_id)
    background_a = _color(seed, 0)
    background_b = _color(seed, 4)
    accent_a = _color(seed, 8)
    accent_b = _color(seed, 12)
    accent_c = _color(seed, 16)
    rotation = seed[20] % 360
    sides = 3 + seed[21] % 6
    radius = 96 + seed[22] % 88
    inner = 28 + seed[23] % 44

    points: list[str] = []
    for index in range(sides * 2):
        angle = (index / (sides * 2)) * 6.283185307179586
        point_radius = radius if index % 2 == 0 else radius - inner
        x = _CENTER + point_radius * math.cos(angle)
        y = _CENTER + point_radius * math.sin(angle)
        points.append(f"{x:.1f},{y:.1f}")

    token_text = escape(token_id[-18:])
    full_token_text = escape(token_id)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" '
        f'aria-label="Kasa collectible {token_text}">'
        f"<title>Kasa collectible #{full_token_text}</title>"
        "<defs>"
        '<linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{background_a}"/>'
        f'<stop offset="100%" stop-color="{background_b}"/>'
        "</linearGradient>"
        '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
        '<feDropShadow dx="0" dy="18" stdDeviation="18" flood-opacity=".28"/>'
        "</filter>"
        "</defs>"
        '<rect width="512" height="512" rx="44" fill="url(#bg)"/>'
        f'<circle cx="92" cy="104" r="{42 + seed[24] % 80}" fill="{accent_a}" opacity=".28"/>'
        f'<circle cx="430" cy="390" r="{54 + seed[25] % 70}" fill="{accent_b}" opacity=".24"/>'
        f'<g transform="rotate({rotation} 256 256)" filter="url(#shadow)">'
        f'<polygon points="{" ".join(points)}" fill="{accent_c}" opacity=".92"/>'
        f'<circle cx="256" cy="256" r="{46 + seed[26] % 46}" fill="{accent_a}" opacity=".82"/>'
        f'<circle cx="256" cy="256" r="{18 + seed[27] % 28}" fill="{background_a}" opacity=".9"/>'
        "</g>"
        '<rect x="56" y="396" width="400" height="64" rx="22" fill="#111827" opacity=".72"/>'
        '<text x="256" y="437" text-anchor="middle" '
        'font-family="Inter, ui-sans-serif, system-ui, -apple-system, '
        'BlinkMacSystemFont, Segoe UI, sans-serif" '
        'font-size="28" font-weight="700" fill="#ffffff">'
        f"#{token_text}"
        "</text>"
        "</svg>"
    )


def data_uri(chain_id: int, contract: str, token_id: str) -> str:
    svg = svg_for(chain_id, contract, token_id)
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
