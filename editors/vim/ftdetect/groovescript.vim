" GrooveScript filetype detection
" Associates *.gs files with the groovescript filetype.
"
" Note: the .gs extension is not unique to GrooveScript (Google Apps Script
" and a handful of other languages also use it). If you work with more than
" one of those, remove this file and set the filetype manually per-project,
" e.g. via a modeline (`// vim: ft=groovescript`) or an autocommand scoped
" to a directory.

autocmd BufRead,BufNewFile *.gs set filetype=groovescript
