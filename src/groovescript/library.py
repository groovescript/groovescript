from pathlib import Path

from .ast_nodes import Groove
from .parser import parse

_LIBRARY_PATH = Path(__file__).parent / "library.gs"

_LIBRARY_GROOVES: dict[str, Groove] | None = None

def get_library_grooves() -> dict[str, Groove]:
    global _LIBRARY_GROOVES
    if _LIBRARY_GROOVES is None:
        source = _LIBRARY_PATH.read_text()
        song = parse(source)
        _LIBRARY_GROOVES = {g.name: g for g in song.grooves}
    return _LIBRARY_GROOVES
