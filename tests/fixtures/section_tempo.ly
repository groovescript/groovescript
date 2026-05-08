\version "2.24.0"

% Extend drumPitchNames so the stack cymbal — which has no built-in
% LilyPond drum-pitch entry — can be referenced as ``stcym`` in the
% emitter output. The stcym pitch class is then styled below.
drumPitchNames =
  #(append drumPitchNames
           '((stcym . stcym)
             (stackcymbal . stcym)))

% Custom drum style overrides:
%   hihat    → cross notehead at position 5 (space above staff, standard notation).
%   openhihat → xcircle notehead at position 5 (same height as hihat, circle-x style).
%   ridecymbal → cross notehead at position 4 (top line of the staff, one
%     position below hihat — conventional ride placement).
%   ridebell → diamond notehead at position 4 (same line as ride; the diamond
%     shape distinguishes the bell stroke from the bow).
%   crashcymbal → plain cross (x) notehead at position 7, the conventional
%     crash position one ledger above the staff. Distinguished from hihat
%     (same notehead at position 5) by staff position, not shape.
%   crashcymbalb → cross notehead at position 6 — second crash drawn one
%     position below crash 1 to mirror the conventional left/right kit
%     placement on opposite sides of the drummer.
%   splashcymbal → diamond notehead at position 8 — small high-pitched
%     cymbal drawn above crash 1; the diamond shape further distinguishes
%     it from the surrounding cross-noteheaded cymbals.
%   chinesecymbal → xcircle notehead at position 9, the highest cymbal on
%     the staff; the circled-x evokes the trashy ringing character.
%   stcym (stack) → slash notehead at position 7 — sits on the same line
%     as crash 1 but the slashed notehead immediately marks it as a
%     short, choked-by-design stack rather than a ringing crash.
%   cowbell → triangle notehead at position 6, between hi-hat and crash —
%     standard PAS / Weinberg position for cowbell on a 5-line drum staff.
#(define my-drums-style
   (alist->hash-table
     (append
       '((hihat cross #f 5)
         (openhihat xcircle #f 5)
         (ridecymbal cross #f 4)
         (ridebell harmonic #f 4)
         (crashcymbal cross #f 7)
         (crashcymbalb cross #f 6)
         (splashcymbal diamond #f 8)
         (chinesecymbal xcircle #f 9)
         (stcym slash #f 7)
         (cowbell triangle #f 6))
       (filter (lambda (p) (not (memq (car p) '(hihat openhihat ridecymbal ridebell crashcymbal crashcymbalb splashcymbal chinesecymbal stcym cowbell))))
               (hash-table->alist drums-style)))))

\header {
  title = "Section Tempo"
  tagline = ##f
}

\paper {
  print-page-number = ##t
  print-first-page-number = ##t
  top-margin = 10\mm
  bottom-margin = 10\mm
  left-margin = 12\mm
  right-margin = 12\mm
  system-system-spacing.basic-distance = #12
  score-markup-spacing.basic-distance = #8
  markup-system-spacing.basic-distance = #8
  oddHeaderMarkup = \markup \fill-line {
    ""
    \on-the-fly #(lambda (layout props arg)
                   (if (= 1 (chain-assoc-get 'page:page-number props -1))
                       empty-stencil
                       (interpret-markup layout props arg)))
      \fromproperty #'header:title
    \concat {
      \fromproperty #'page:page-number-string
      " of "
      \page-ref #'lastPage "00" "?"
    }
  }
  evenHeaderMarkup = \markup \fill-line {
    ""
    \on-the-fly #(lambda (layout props arg)
                   (if (= 1 (chain-assoc-get 'page:page-number props -1))
                       empty-stencil
                       (interpret-markup layout props arg)))
      \fromproperty #'header:title
    \concat {
      \fromproperty #'page:page-number-string
      " of "
      \page-ref #'lastPage "00" "?"
    }
  }
  oddFooterMarkup = \markup \fill-line {
    "" "Made with groovescript" ""
  }
  evenFooterMarkup = \markup \fill-line {
    "" "Made with groovescript" ""
  }
}

\layout {
  indent = 0\mm
}

\score {
\header {
  subtitle = "Tempo: 120    Time Signature: 4/4"
}
  \new DrumStaff \with {
    drumStyleTable = #my-drums-style
  } {
    \drummode {
      \numericTimeSignature
      \time 4/4
      \omit Score.MetronomeMark
      \tempo 4 = 120
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \fontsize #-1 \concat { \note { 4 } #1 " = 120" } \vspace #0.3 \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "INTRO: 4" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \bar ".|:"
      \repeat volta 4 {
        <bd hh>8 hh8 <sn hh>8 hh8 <bd hh>8 hh8 <sn hh>8 hh8 |
      }
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "VERSE: 8" } \vspace #0.3 \italic \fontsize #-1 "Play 7x" }
      \repeat volta 7 {
        <bd hh>8 hh8 <sn hh>8 hh8 <bd hh>8 hh8 <sn hh>8 hh8 |
      }
      r4 r4 r4 <bd cymc>4 |
      \tempo 4 = 80
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \fontsize #-1 \concat { \note { 4 } #1 " = 80" } \vspace #0.3 \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "BREAKDOWN: 4" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \repeat volta 4 {
        <bd hh>8 hh8 hh8 <bd hh>8 <sn hh>8 hh8 hh8 hh8 |
      }
      \tempo 4 = 140
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \fontsize #-1 \concat { \note { 4 } #1 " = 140" } \vspace #0.3 \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "CHORUS: 8" } \vspace #0.3 \italic \fontsize #-1 "Play 7x" }
      \repeat volta 7 {
        <bd hh>8 hh8 <sn hh>8 hh8 <bd hh>8 hh8 <sn hh>8 hh8 |
      }
      r4 r4 r4 <bd cymc>4 |
      \tempo 4 = 100
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \fontsize #-1 \concat { \note { 4 } #1 " = 100" } \vspace #0.3 \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "OUTRO: 4" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \repeat volta 4 {
        <bd hh>8 hh8 <sn hh>8 hh8 <bd hh>8 hh8 <sn hh>8 hh8 |
      }
      \label #'lastPage
    }
  }
}
