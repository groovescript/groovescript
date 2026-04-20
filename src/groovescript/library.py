from pathlib import Path

from .ast_nodes import Fill, Groove, VariationDef
from .parser import parse

_GROOVE_LIBRARY_PATH = Path(__file__).parent / "groove_library.gs"
_FILL_LIBRARY_PATH = Path(__file__).parent / "fill_library.gs"
_VARIATION_LIBRARY_PATH = Path(__file__).parent / "variation_library.gs"

_LIBRARY_GROOVES: dict[str, Groove] | None = None
_LIBRARY_FILLS: dict[str, Fill] | None = None
_LIBRARY_VARIATIONS: dict[str, VariationDef] | None = None

def get_library_grooves() -> dict[str, Groove]:
    global _LIBRARY_GROOVES
    if _LIBRARY_GROOVES is None:
        source = _GROOVE_LIBRARY_PATH.read_text()
        song = parse(source)
        _LIBRARY_GROOVES = {g.name: g for g in song.grooves}
    return _LIBRARY_GROOVES


def get_library_fills() -> dict[str, Fill]:
    global _LIBRARY_FILLS
    if _LIBRARY_FILLS is None:
        source = _FILL_LIBRARY_PATH.read_text()
        song = parse(source)
        _LIBRARY_FILLS = {f.name: f for f in song.fills}
    return _LIBRARY_FILLS


def get_library_variations() -> dict[str, VariationDef]:
    global _LIBRARY_VARIATIONS
    if _LIBRARY_VARIATIONS is None:
        source = _VARIATION_LIBRARY_PATH.read_text()
        song = parse(source)
        _LIBRARY_VARIATIONS = {v.name: v for v in song.variations}
    return _LIBRARY_VARIATIONS
