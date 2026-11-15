"""Implied-duration rhythm for timed lyrics, shared by the emitters.

Lyrics are onsets only. For display, each syllable lasts until the next
onset in the bar, or to the bar line if it is the last one; any gap before
the first onset is a rest. This is a display convention, not a claim about
how long the syllable is held.
"""

from dataclasses import dataclass
from fractions import Fraction
from math import lcm

from .compiler import LyricSyllable


@dataclass(frozen=True)
class LyricSegment:
    """A span of one bar's lyric rhythm, measured in beats from the bar start.

    ``syllable`` is the onset that starts the span, or ``None`` for the gap
    before the first onset. A span *sounds* (a note) when that onset is a
    syllable or a hold (``_``); stops (``.``) and breaths (``,``) start a
    rest. Emitters that need beat-aligned pieces (tuplet beats) split a
    segment at beat boundaries themselves.
    """

    start: Fraction
    end: Fraction
    syllable: LyricSyllable | None

    @property
    def sounding(self) -> bool:
        return self.syllable is not None and self.syllable.sounding

    @property
    def is_hold(self) -> bool:
        return self.syllable is not None and self.syllable.kind == "hold"

    @property
    def breath(self) -> bool:
        return self.syllable is not None and self.syllable.kind == "breath"


def lyric_segments(lyrics: list[LyricSyllable], beats_per_bar: int) -> list[LyricSegment]:
    """Return the rest/note spans covering one bar, in beats.

    Each onset lasts until the next onset or the bar line (the implied
    duration); a hold extends the previous note, a stop or breath ends it.
    """
    bar_end = Fraction(beats_per_bar)
    onsets = [syl.position * beats_per_bar for syl in lyrics]
    segments: list[LyricSegment] = []
    if not lyrics:
        return [LyricSegment(Fraction(0), bar_end, None)]
    if onsets[0] > 0:
        segments.append(LyricSegment(Fraction(0), onsets[0], None))
    for i, syl in enumerate(lyrics):
        end = onsets[i + 1] if i + 1 < len(lyrics) else bar_end
        segments.append(LyricSegment(onsets[i], end, syl))
    return segments


def ties_out(segments: list[LyricSegment], next_bar_starts_with_hold: bool) -> list[bool]:
    """For each segment, whether its note ties into the following one: the
    next segment is a hold, or it is the bar's last and the next bar opens
    with a hold on beat 1."""
    out = []
    for i, seg in enumerate(segments):
        if not seg.sounding:
            out.append(False)
        elif i + 1 < len(segments):
            out.append(segments[i + 1].is_hold)
        else:
            out.append(next_bar_starts_with_hold)
    return out


def starts_with_hold(lyrics: list[LyricSyllable]) -> bool:
    return bool(lyrics) and lyrics[0].position == 0 and lyrics[0].kind == "hold"


def is_power_of_two(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def beat_grid(offsets: list[Fraction]) -> int:
    """Slots per beat needed to place every in-beat offset on a grid."""
    return lcm(1, *(off.denominator for off in offsets))


def tuplet_normal(actual: int) -> int:
    """Largest power of two strictly below ``actual`` (3→2, 5→4, 6→4, 9→8)."""
    normal = 1
    while normal * 2 < actual:
        normal *= 2
    return normal
