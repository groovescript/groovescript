\version "2.24.0"

% Custom drum style overrides:
%   hihat    → cross notehead at position 5 (space above staff, standard notation).
%   openhihat → xcircle notehead at position 5 (same height as hihat, circle-x style).
%   crashcymbal → plain cross (x) notehead at position 7, the conventional
%     crash position one ledger above the staff. Distinguished from hihat
%     (same notehead at position 5) by staff position, not shape.
#(define my-drums-style
   (alist->hash-table
     (append
       '((hihat cross #f 5)
         (openhihat xcircle #f 5)
         (crashcymbal cross #f 7))
       (filter (lambda (p) (not (memq (car p) '(hihat openhihat crashcymbal))))
               (hash-table->alist drums-style)))))

\header {
  title = "{{TITLE}}"
  tagline = "Made with groovescript"
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
}

\layout {
  indent = 0\mm
}

\score {
\header {
  subtitle = "Tempo: 96    Time Signature: 4/4"
}
  \new DrumStaff \with {
    drumStyleTable = #my-drums-style
  } {
    \drummode {
      \numericTimeSignature
      \time 4/4
      \omit Score.MetronomeMark
      \tempo 4 = 96
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \fontsize #-1 \concat { \note { 4 } #1 " = 96" } \vspace #0.3 \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "VERSE: 8" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \bar ".|:"
      \repeat volta 4 {
        <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 hh16 hh16 <bd hh>16 hh16 <sn hh>16 hh16 hh16 hh16 |
      }
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \once \override Score.RehearsalMark.outside-staff-priority = #1000
      \mark \markup \italic \fontsize #-1 "Play 3x"
      \repeat volta 3 {
        <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 hh16 hh16 <bd hh>16 hh16 <sn hh>16 hh16 hh16 hh16 |
      }
      <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 hh16 hh16 <bd hh>16 hh16 sn16 sn16 sn16 <sn cymc>16 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "CHORUS: 8" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \repeat volta 4 {
        <bd hho>16 hh16 hh16 hh16 <sn hho>16 hh16 <bd hh>16 hh16 hho16 hh16 <bd hh>16 hh16 <sn hho>16 hh16 hh16 hh16 |
      }
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \once \override Score.RehearsalMark.outside-staff-priority = #1000
      \mark \markup \italic \fontsize #-1 "Play 3x"
      \repeat volta 3 {
        <bd hho>16 hh16 hh16 hh16 <sn hho>16 hh16 <bd hh>16 hh16 hho16 hh16 <bd hh>16 hh16 <sn hho>16 hh16 hh16 hh16 |
      }
      <bd hho>16 hh16 hh16 hh16 <sn hho>16 hh16 <bd hh>16 hh16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "VERSE 2: 8" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \repeat volta 4 {
        <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 hh16 hh16 <bd hh>16 hh16 <sn hh>16 hh16 hh16 hh16 |
      }
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \once \override Score.RehearsalMark.outside-staff-priority = #1000
      \mark \markup \italic \fontsize #-1 "Play 3x"
      \repeat volta 3 {
        <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 hh16 hh16 <bd hh>16 hh16 <sn hh>16 hh16 hh16 hh16 |
      }
      <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 hh16 hh16 <bd hh>16 hh16 sn16 sn16 sn16 <sn cymc>16 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "CHORUS 2: 8" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \repeat volta 4 {
        <bd hho>16 hh16 hh16 hh16 <sn hho>16 hh16 <bd hh>16 hh16 hho16 hh16 <bd hh>16 hh16 <sn hho>16 hh16 hh16 hh16 |
      }
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \once \override Score.RehearsalMark.outside-staff-priority = #1000
      \mark \markup \italic \fontsize #-1 "Play 3x"
      \repeat volta 3 {
        <bd hho>16 hh16 hh16 hh16 <sn hho>16 hh16 <bd hh>16 hh16 hho16 hh16 <bd hh>16 hh16 <sn hho>16 hh16 hh16 hh16 |
      }
      <bd hho>16 hh16 hh16 hh16 <sn hho>16 hh16 <bd hh>16 hh16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "BRIDGE: 4" } \vspace #0.3 \italic \fontsize #-1 "Play 3x" }
      \repeat volta 3 {
        <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 hh16 hh16 <bd hh>16 hh16 <sn hh>16 hh16 hh16 hh16 |
      }
      <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "OUTRO: 8" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \repeat volta 4 {
        <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 hh16 hh16 <bd hh>16 hh16 <sn hh>16 hh16 hh16 hh16 |
      }
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \once \override Score.RehearsalMark.outside-staff-priority = #1000
      \mark \markup \italic \fontsize #-1 "Play 4x"
      \repeat volta 4 {
        <bd hh>16 hh16 hh16 hh16 <sn hh>16 hh16 <bd hh>16 hh16 hh16 hh16 <bd hh>16 hh16 <sn hh>16 hh16 hh16 hh16 |
      }
      \label #'lastPage
    }
  }
}
