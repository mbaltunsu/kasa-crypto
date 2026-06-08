import base64
from xml.etree import ElementTree as ET

from app.services import nft_art

CONTRACT = "0x88F67A2EbD4C342496d0A477EF58F3a89BCF95F2"


def test_svg_art_is_deterministic_and_distinctive() -> None:
    first = nft_art.svg_for(11_155_111, CONTRACT, "12345678901234567890")
    replay = nft_art.svg_for(11_155_111, CONTRACT, "12345678901234567890")
    other = nft_art.svg_for(11_155_111, CONTRACT, "12345678901234567891")

    assert first == replay
    assert first != other
    assert "linearGradient" in first
    assert "#12345678901234567890" in first


def test_data_uri_contains_valid_svg() -> None:
    uri = nft_art.data_uri(11_155_111, CONTRACT, "7")

    assert uri.startswith("data:image/svg+xml;base64,")
    encoded = uri.removeprefix("data:image/svg+xml;base64,")
    svg = base64.b64decode(encoded).decode("utf-8")
    root = ET.fromstring(svg)  # noqa: S314 - parsing deterministic SVG generated in-process.

    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.attrib["viewBox"] == "0 0 512 512"
