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
  title = "Hi-Hat Foot Chick Demo"
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
  subtitle = "Tempo: 110    Time Signature: 4/4"
}
  \new DrumStaff \with {
    drumStyleTable = #my-drums-style
  } {
    \drummode {
      \numericTimeSignature
      \time 4/4
      \omit Score.MetronomeMark
      \tempo 4 = 110
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \fontsize #-1 \concat { \note { 4 } #1 " = 110" } \vspace #0.3 \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "CHICK ON BACKBEATS: 4" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \bar ".|:"
      \repeat volta 4 {
        bd4 <sn hhp>4 bd4 <sn hhp>4 |
      }
      \once \override Score.RehearsalMark.self-alignment-X = #LEFT
      \once \override Score.RehearsalMark.break-align-symbols = #'(staff-bar)
      \once \override Score.RehearsalMark.padding = #2
      \mark \markup \column { \override #'(box-padding . 0.5) \box \bold \fontsize #-1 { "JAZZ: 4" } \vspace #0.3 \italic \fontsize #-1 "Play 4x" }
      \repeat volta 4 {
        <cymr bd>4 \tuplet 3/2 { <cymr hhp>8 r8 cymr8 } <cymr bd>4 \tuplet 3/2 { <cymr hhp>8 r8 cymr8 } |
      }
      \label #'lastPage
    }
  }
}
