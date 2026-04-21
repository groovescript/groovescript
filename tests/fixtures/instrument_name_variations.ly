\version "2.24.0"

% Custom drum style overrides:
%   hihat    → cross notehead at position 5 (space above staff, standard notation).
%   openhihat → xcircle notehead at position 5 (same height as hihat, circle-x style).
%   ridecymbal → cross notehead at position 4 (top line of the staff, one
%     position below hihat — conventional ride placement).
%   crashcymbal → plain cross (x) notehead at position 7, the conventional
%     crash position one ledger above the staff. Distinguished from hihat
%     (same notehead at position 5) by staff position, not shape.
#(define my-drums-style
   (alist->hash-table
     (append
       '((hihat cross #f 5)
         (openhihat xcircle #f 5)
         (ridecymbal cross #f 4)
         (crashcymbal cross #f 7))
       (filter (lambda (p) (not (memq (car p) '(hihat openhihat ridecymbal crashcymbal))))
               (hash-table->alist drums-style)))))

\header {
  title = "Instrument Name Variations"
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
      \once \override Score.RehearsalMark.break-align-symbols = #'(left-edge)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \fontsize #-1 \concat { \note { 4 } #1 " = 120" } \vspace #0.3 \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "VERSE: 4" } }
      <bd hh>8 hh8 <sn hh>8 hh8 <bd hh>8 hh8 <sn hh>8 hh8 |
      <bd cymr>8 hh8 <sn hh>8 hh8 <bd cymr>8 hh8 <sn hh>8 hh8 |
      <bd hh>8 hh8 <sn hh>8 hh8 <bd hh>8 hh8 <sn hh>8 hh8 |
      <bd hh>8 hh8 <sn hh>8 hh8 sn16 sn16 sn16 sn16 <bd cymc>4 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "CROSS-STICK: 2" } \vspace #0.3 \italic \fontsize #-1 "Play 2x" }
      \repeat volta 2 {
        <bd hh>8 hh8 <ss hh>8 hh8 <bd hh>8 hh8 <ss hh>8 hh8 |
      }
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "CLICK: 2" } \vspace #0.3 \italic \fontsize #-1 "Play 2x" }
      \repeat volta 2 {
        <bd hh>8 hh8 <ss hh>8 hh8 <bd hh>8 hh8 <ss hh>8 hh8 |
      }
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "FLOOR TOM: 2" } \vspace #0.3 \italic \fontsize #-1 "Play 2x" }
      \repeat volta 2 {
        <bd hh>8 <tomfh hh>8 <sn hh>8 hh8 <bd hh>8 <tomfh hh>8 <sn hh>8 hh8 |
      }
      \label #'lastPage
    }
  }
}
