" Vim filetype plugin for GrooveScript
" Language: GrooveScript (drum notation DSL)
"
" Sets per-buffer options that pair well with the syntax file:
" two-space indentation, `//` as the default comment leader, and a
" comments= setting so `gqap` and auto-wrapping behave on `//`/`#` lines.

if exists("b:did_ftplugin")
  finish
endif
let b:did_ftplugin = 1

setlocal expandtab
setlocal shiftwidth=2
setlocal softtabstop=2
setlocal tabstop=2

setlocal commentstring=//\ %s
setlocal comments=:#,://

" Restore defaults on filetype change.
let b:undo_ftplugin = "setlocal expandtab< shiftwidth< softtabstop< tabstop<"
                   \ . " commentstring< comments<"
