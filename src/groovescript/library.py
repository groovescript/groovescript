import dataclasses
from pathlib import Path

from .ast_nodes import Fill, Groove, VariationDef
from .parser import parse

_GROOVE_LIBRARY_PATH = Path(__file__).parent / "groove_library.gs"
_FILL_LIBRARY_PATH = Path(__file__).parent / "fill_library.gs"
_VARIATION_LIBRARY_PATH = Path(__file__).parent / "variation_library.gs"

_LIBRARY_GROOVES: dict[str, Groove] | None = None
_LIBRARY_FILLS: dict[str, Fill] | None = None
_LIBRARY_VARIATIONS: dict[str, VariationDef] | None = None

# AST fields that hold a source position.
_LOCATION_FIELDS = ("line", "source_line", "column")


def _strip_locations(obj, _seen: set[int] | None = None) -> None:
    """Clear source positions on a parsed library AST, in place.

    Library entries are parsed from the package's own ``.gs`` files, so their
    line numbers refer to those files. Diagnostics are rendered against the
    *user's* file, so a library line number would point at an unrelated line
    there. With no position, a diagnostic is reported without a location.
    """
    if _seen is None:
        _seen = set()
    if id(obj) in _seen:
        return
    _seen.add(id(obj))
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            if f.name in _LOCATION_FIELDS and isinstance(value, int):
                setattr(obj, f.name, None)
            else:
                _strip_locations(value, _seen)
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            _strip_locations(item, _seen)
    elif isinstance(obj, dict):
        for item in obj.values():
            _strip_locations(item, _seen)


def get_library_grooves() -> dict[str, Groove]:
    global _LIBRARY_GROOVES
    if _LIBRARY_GROOVES is None:
        source = _GROOVE_LIBRARY_PATH.read_text()
        song = parse(source)
        _strip_locations(song)
        _LIBRARY_GROOVES = {g.name: g for g in song.grooves}
    return _LIBRARY_GROOVES


def get_library_fills() -> dict[str, Fill]:
    global _LIBRARY_FILLS
    if _LIBRARY_FILLS is None:
        source = _FILL_LIBRARY_PATH.read_text()
        song = parse(source)
        _strip_locations(song)
        _LIBRARY_FILLS = {f.name: f for f in song.fills}
    return _LIBRARY_FILLS


def get_library_variations() -> dict[str, VariationDef]:
    global _LIBRARY_VARIATIONS
    if _LIBRARY_VARIATIONS is None:
        source = _VARIATION_LIBRARY_PATH.read_text()
        song = parse(source)
        _strip_locations(song)
        _LIBRARY_VARIATIONS = {v.name: v for v in song.variations}
    return _LIBRARY_VARIATIONS
