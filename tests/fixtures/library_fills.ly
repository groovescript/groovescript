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
  title = "Library Fills"
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
      \mark \markup \column { \fontsize #-1 \concat { \note { 4 } #1 " = 120" } \vspace #0.3 \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "ACCENTS: 4" } }
      <bd cymc>4 r4 r4 r4 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \once \override Score.RehearsalMark.outside-staff-priority = #1000
      \mark \markup \italic \fontsize #-1 "Play 2x"
      \repeat volta 2 {
        <hh bd>8 hh8 <hh sn>8 hh8 <hh bd>8 hh8 <hh sn>8 hh8 |
      }
      r4 r4 r4 <bd cymc>4 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(left-edge)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "SNARE ROLLS: 4" }
      <hh bd>8 hh8 <hh sn>8 hh8 <hh bd>8 hh8 sn16 sn16 sn16 sn16 |
      <hh bd>8 hh8 <hh sn>8 hh8 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 |
      <hh bd>8 hh8 <hh sn>8 hh8 <hh bd>8 hh8 <hh sn>8 hh8 |
      sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 sn16 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(left-edge)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "SNARE ROLL TRIPLETS: 4" }
      <hh bd>8 hh8 <hh sn>8 hh8 <hh bd>8 hh8 <hh sn>8 hh8 |
      <hh bd>8 hh8 <hh sn>8 hh8 \tuplet 3/2 { sn8 sn8 sn8 } \tuplet 3/2 { sn8 sn8 sn8 } |
      <hh bd>8 hh8 <hh sn>8 hh8 <hh bd>8 hh8 <hh sn>8 hh8 |
      \tuplet 3/2 { sn8 sn8 sn8 } \tuplet 3/2 { sn8 sn8 sn8 } \tuplet 3/2 { sn8 sn8 sn8 } \tuplet 3/2 { sn8 sn8 sn8 } |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(left-edge)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "BUZZ ROLLS: 4" }
      <hh bd>8 hh8 <hh sn>8 hh8 <hh bd>8 hh8 sn4:32 |
      <hh bd>8 hh8 <hh sn>8 hh8 sn2:32 |
      <hh bd>8 hh8 <hh sn>8 hh8 <hh bd>8 hh8 <hh sn>8 hh8 |
      sn1:32 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(left-edge)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "TOM ROLLS: 4" }
      <hh bd>16 hh16 hh16 hh16 <hh sn>16 hh16 hh16 hh16 <hh bd>16 hh16 hh16 hh16 <hh sn>16 hh16 hh16 hh16 |
      <hh bd>16 hh16 hh16 hh16 <hh sn>16 hh16 hh16 hh16 tommh16 tommh16 tommh16 tommh16 tomfh16 tomfh16 tomfh16 tomfh16 |
      tomfh16 tomfh16 tomfh16 tomfh16 tommh16 tommh16 tommh16 tommh16 tomh16 tomh16 tomh16 tomh16 tomh16 tomh16 tomh16 tomh16 |
      tomh16 tomh16 tomh16 tomh16 tommh16 tommh16 tommh16 tommh16 tomfh16 tomfh16 tomfh16 tomfh16 tomfh16 tomfh16 tomfh16 tomfh16 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(left-edge)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "TOM TRIPLETS: 2" }
      \tuplet 3/2 { <hh bd>8 r8 hh8 } \tuplet 3/2 { <hh sn>8 r8 hh8 } \tuplet 3/2 { <hh bd>8 r8 hh8 } \tuplet 3/2 { <hh sn>8 r8 hh8 } |
      \tuplet 3/2 { tomh8 tomh8 tomh8 } \tuplet 3/2 { tommh8 tommh8 tommh8 } \tuplet 3/2 { tomfh8 tomfh8 tomfh8 } \tuplet 3/2 { tomfh8 tomfh8 tomfh8 } |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(left-edge)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "AROUND THE KIT: 4" }
      <hh bd>8 hh8 <hh sn>8 hh8 <hh bd>8 hh8 <hh sn>8 hh8 |
      sn4 tomh4 tommh4 tomfh4 |
      <hh bd>8 hh8 <hh sn>8 hh8 sn16 sn16 sn16 sn16 tomh16 tomh16 tomfh16 tomfh16 |
      sn16 sn16 sn16 sn16 tomh16 tomh16 tomh16 tomh16 tommh16 tommh16 tommh16 tommh16 tomfh16 tomfh16 tomfh16 tomfh16 |
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(left-edge)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "RUDIMENTAL: 4" }
      <hh bd>16 hh16 hh16 hh16 <hh sn>16 hh16 <hh bd>16 <hh sn>16 hh16 <hh bd>16 hh16 hh16 <hh sn>16 hh16 hh16 <hh sn>16 |
      <hh bd>16 hh16 hh16 hh16 <hh sn>16 hh16 <hh bd>16 <hh sn>16 sn16 bd16 sn16 bd16 tomh16 bd16 tommh16 tomfh16 |
      <hh bd>16 hh16 hh16 hh16 <hh sn>16 hh16 <hh bd>16 <hh sn>16 hh16 <hh bd>16 hh16 hh16 <hh sn>16 hh16 hh16 <hh sn>16 |
      <hh bd>16 hh16 hh16 hh16 <hh sn>16 hh16 <hh bd>16 <hh sn>16 \slashedGrace sn16 sn16 sn16 sn16 sn16 \slashedGrace sn16 sn16 sn16 sn16 sn16 |
      \label #'lastPage
    }
  }
}
