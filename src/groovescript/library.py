from pathlib import Path

from .ast_nodes import Fill, Groove
from .parser import parse

_LIBRARY_PATH = Path(__file__).parent / "library.gs"
_FILL_LIBRARY_PATH = Path(__file__).parent / "fill_library.gs"

_LIBRARY_GROOVES: dict[str, Groove] | None = None
_LIBRARY_FILLS: dict[str, Fill] | None = None

def get_library_grooves() -> dict[str, Groove]:
    global _LIBRARY_GROOVES
    if _LIBRARY_GROOVES is None:
        source = _LIBRARY_PATH.read_text()
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
