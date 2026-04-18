" Vim syntax file
" Language:     GrooveScript (drum notation DSL)
" Maintainer:   GrooveScript project
" Filenames:    *.gs
"
" Highlights the GrooveScript drum-chart DSL: metadata, groove/fill/section
" definitions, pattern and count+notes bodies, variations, play blocks,
" cues and fill placeholders. See ../README.md for installation instructions.

if exists("b:current_syntax")
  finish
endif

" -- Comments ---------------------------------------------------------------
" GrooveScript accepts both `//` and `#` line comments.
syn match gsComment "//.*$"   contains=@Spell
syn match gsComment "#.*$"    contains=@Spell

" -- Strings ----------------------------------------------------------------
" Double-quoted strings are used for titles, groove/fill/section names,
" count/notes bodies, text annotations, cues, and fill placeholder labels.
syn region gsString start=+"+ skip=+\\"+ end=+"+ oneline contains=@Spell

" -- Numbers ----------------------------------------------------------------
" Time signatures are defined further down so they take precedence over
" gsNumber and gsBeatLabel at the same position (Vim :syn-priority: the last
" matching item defined at a given position wins).
syn match gsNumber        "\<\d\+\>"

" -- Repeat count (x2, x4, ...) in play blocks ------------------------------
syn match gsRepeatCount   "\<x\d\+\>"

" -- Top-level metadata keywords --------------------------------------------
" These appear as `keyword: value` lines, either inside a `metadata:` block
" or at the top level of the file.
syn keyword gsMetadataKeyword title tempo time_signature dsl_version
                            \ default_groove default_bars
syn keyword gsMetadataBlock   metadata

" -- Definition keywords ----------------------------------------------------
" `groove "name":`, `fill "name":`, `section "name":`
syn keyword gsDefinition groove fill section

" -- Section / groove body keywords -----------------------------------------
syn keyword gsBodyKeyword bars pattern count notes repeat like
                        \ play cue variation text extend
                        \ cresc decresc crescendo decrescendo
" `crash in` is a section flag. Match as a two-word token so the ``crash``
" token highlights as a body keyword here (not as the crash instrument).
" Defined after the instrument rules below so it takes precedence on the
" ``crash`` word when followed by ``in``.
syn match gsBodyKeyword "\<crash\s\+in\>"

" -- Placement keywords (used in fill/cue/variation/placeholder lines) ------
" `fill "..." at bar N beat X`, `cue "..." at bar N`, `variation at bar N:`,
" `fill placeholder at bar N`.
syn keyword gsPlacement at bar bars beat placeholder rest from to except

" -- Variation action keywords ----------------------------------------------
" `add BD at 1`, `remove HH at *`, `replace SN with SN accent at 2`,
" `modify add flam at 2`, `modify remove accent at 1`.
syn keyword gsAction add remove replace with modify

" -- Hit modifiers ----------------------------------------------------------
syn keyword gsModifier ghost accent flam drag double
" `32nd` is an alias for `double`; starts with a digit so `keyword` won't match.
syn match   gsModifier "\<32nd\>"
" `buzz` — snare buzz-roll modifier, optionally with a duration suffix
" (e.g. `buzz:2`, `buzz:2d`, `buzz:16dd`). Defined as a match so the
" `:<duration>` portion is highlighted together with the keyword.
syn match   gsModifier "\<buzz\>\(:[1-9][0-9]\?d\{0,2}\)\?"

" -- Instruments ------------------------------------------------------------
" Canonical short names.
syn keyword gsInstrument BD SN HH OH RD CR FT HT MT SCS HF
syn keyword gsInstrument bd sn hh oh rd cr ft ht mt hf
" Long-form and lowercase aliases accepted by the parser.
syn keyword gsInstrument bass kick snare click hihat openhat hat
                       \ open ride crash lowtom floortom hightom hitom midtom
                       \ hihatfoot footchick
" cross-stick and hi-hat-foot / foot-chick contain hyphens, so they need
" match rules (vim `keyword` doesn't allow hyphens).
syn match gsInstrument "\<cross-stick\>"
syn match gsInstrument "\<hi-hat-foot\>"
syn match gsInstrument "\<foot-chick\>"

" -- Beat labels (1, 2&, 3e, 4a, 1trip, 2let, 1and, bare trip/let/and) ------
" Matches the shape allowed by BEAT_LABEL in grammar.lark. These only
" highlight when followed by either whitespace, a comma, or end-of-line so
" they don't accidentally eat parts of longer tokens.
syn match gsBeatLabel "\<[1-9]\(trip\|let\|and\|[e&atl]\)\?\>"
syn match gsBeatLabel "\<\(trip\|let\|and\)\>"

" -- Star (`*N` / `*Nt` — hit on every Nth note, straight or triplet) ------
" e.g. `*2`, `*4`, `*8`, `*16`, `*4t`, `*8t`. Also matches the bare `*`
" used in variation actions (`remove HH at *`).
syn match gsStar "\*\(2\|4\|8\|16\)t\?"
syn match gsStar "\*"

" -- Time signatures --------------------------------------------------------
" Defined after gsNumber / gsBeatLabel so it wins at the shared start
" position (e.g. the leading `4` of `4/4`).
syn match gsTimeSignature "\<\d\+/\d\+\>"

" -- Highlight linking ------------------------------------------------------
hi def link gsComment          Comment
hi def link gsString           String
hi def link gsNumber           Number
hi def link gsTimeSignature    Number
hi def link gsRepeatCount      Number

hi def link gsMetadataBlock    Structure
hi def link gsMetadataKeyword  Keyword
hi def link gsDefinition       Structure
hi def link gsBodyKeyword      Keyword
hi def link gsPlacement        Keyword
hi def link gsAction           Statement
hi def link gsModifier         Special
hi def link gsInstrument       Identifier
hi def link gsBeatLabel        Constant
hi def link gsStar             Operator

let b:current_syntax = "groovescript"
