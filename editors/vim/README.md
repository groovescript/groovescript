# GrooveScript Vim plugin

Syntax highlighting and basic filetype support for GrooveScript (`.gs`)
drum-chart files in Vim and Neovim.

## What you get

- **Syntax highlighting** for metadata (`title`, `tempo`, `time_signature`,
  `dsl_version`, `default_groove`, `default_bars`), block definitions
  (`groove`, `fill`, `section`), body keywords (`bars`, `pattern`, `count`,
  `notes`, `repeat`, `like`, `play`, `cue`, `variation`, `text`, `extend`,
  `cresc`, `decresc`), placement keywords (`at`, `bar`, `bars`, `beat`,
  `placeholder`, `rest`, `from`, `to`, `except`), variation actions (`add`,
  `remove`, `replace`, `with`), hit modifiers (`ghost`, `accent`, `flam`,
  `drag`, `double`, `32nd`), canonical and long-form instrument names (`BD`,
  `SN`, `HH`, `snare`, `hihat`, ...), beat labels (`1`, `2&`, `3e`, `4a`,
  `1trip`, `1and`, ...), time signatures (`4/4`, `6/8`), repeat counts
  (`x4`), strings, numbers, and `//` / `#` line comments.
- **Filetype detection** for `*.gs` files.
- **Filetype plugin** that sets two-space indentation and the `//` comment
  leader so `gcc` (with `tpope/vim-commentary`) and `gqap` do the right
  thing.

## Layout

```
editors/vim/
  ftdetect/groovescript.vim   # maps *.gs to filetype=groovescript
  ftplugin/groovescript.vim   # per-buffer options
  syntax/groovescript.vim     # highlighting rules
```

## Installation on macOS

Vim on macOS works in a few different flavors. Pick the section that matches
your setup.

### Prerequisites

You'll want a reasonably modern Vim. The macOS system Vim under
`/usr/bin/vim` is usable, but Homebrew's Vim or MacVim is newer and supports
syntax plugins out of the box:

```sh
# Either of these is fine — pick one
brew install vim
brew install --cask macvim
```

For Neovim:

```sh
brew install neovim
```

### Option 1 — Vim with a plugin manager (recommended)

If you already use [vim-plug](https://github.com/junegunn/vim-plug),
[packer.nvim](https://github.com/wbthomason/packer.nvim),
[lazy.nvim](https://github.com/folke/lazy.nvim), or similar, point it at the
`editors/vim` subdirectory of this repository.

**vim-plug** (`~/.vimrc` or `~/.config/nvim/init.vim`):

```vim
call plug#begin()
Plug 'groovescript/groovescript', { 'rtp': 'editors/vim' }
call plug#end()
```

Then run `:PlugInstall` inside Vim.

**lazy.nvim** (`~/.config/nvim/lua/plugins/groovescript.lua`):

```lua
return {
  {
    "groovescript/groovescript",
    config = function() end,
    -- Treat the plugin's editors/vim dir as the runtime path root.
    init = function()
      vim.opt.rtp:append(vim.fn.stdpath("data") ..
        "/lazy/groovescript/editors/vim")
    end,
  },
}
```

### Option 2 — Vim's native package loader

Vim 8+ and Neovim both support the built-in `pack/` layout. Clone the repo
somewhere convenient, then symlink `editors/vim` into a package directory.
This keeps the plugin in sync with whatever branch you have checked out.

```sh
# Clone (or use your existing checkout)
git clone https://github.com/groovescript/groovescript.git ~/src/groovescript

# --- For Vim ---
mkdir -p ~/.vim/pack/groovescript/start
ln -s ~/src/groovescript/editors/vim \
      ~/.vim/pack/groovescript/start/groovescript

# --- For Neovim ---
mkdir -p ~/.config/nvim/pack/groovescript/start
ln -s ~/src/groovescript/editors/vim \
      ~/.config/nvim/pack/groovescript/start/groovescript
```

Restart Vim; `:scriptnames` should now list
`groovescript/syntax/groovescript.vim` once a `.gs` buffer is open.

### Option 3 — Copy the files in by hand

If you'd rather not symlink, just copy the three files into the matching
subdirectories under `~/.vim` (Vim) or `~/.config/nvim` (Neovim):

```sh
# Vim
mkdir -p ~/.vim/ftdetect ~/.vim/ftplugin ~/.vim/syntax
cp editors/vim/ftdetect/groovescript.vim ~/.vim/ftdetect/
cp editors/vim/ftplugin/groovescript.vim ~/.vim/ftplugin/
cp editors/vim/syntax/groovescript.vim   ~/.vim/syntax/

# Neovim
mkdir -p ~/.config/nvim/ftdetect ~/.config/nvim/ftplugin ~/.config/nvim/syntax
cp editors/vim/ftdetect/groovescript.vim ~/.config/nvim/ftdetect/
cp editors/vim/ftplugin/groovescript.vim ~/.config/nvim/ftplugin/
cp editors/vim/syntax/groovescript.vim   ~/.config/nvim/syntax/
```

You'll need to repeat this whenever the plugin updates, so the symlink or
plugin-manager approach is nicer for day-to-day work.

## Verifying it works

1. Open any `.gs` file from this repo, e.g.
   `vim charts/standard-rock.gs`.
2. Run `:set filetype?` — it should print `filetype=groovescript`. If it
   doesn't, run `:filetype detect` or reload with `:e`.
3. Run `:syntax list` — you should see `gsString`, `gsInstrument`,
   `gsBeatLabel`, etc.
4. Eyeball the buffer: `title`/`tempo`/`time_signature` lines, `groove`,
   `fill`, `section` headers, `"quoted names"`, instrument tokens
   (`BD`, `SN`, `HH`), beat labels (`1`, `2&`, `3e`), and `//` comments
   should all be colorized.

If nothing is highlighted, make sure `syntax on` (or `syntax enable`) is in
your `~/.vimrc` / `~/.config/nvim/init.vim`, and that `filetype plugin on`
is set so the `ftplugin` file is picked up:

```vim
syntax enable
filetype plugin indent on
```

## Notes and caveats

- **`.gs` is not unique to GrooveScript.** Google Apps Script, Gosu, and
  a few other languages also claim it. If you routinely edit more than
  one, delete `ftdetect/groovescript.vim` and set the filetype per
  project instead — for example, drop this in a local `.vimrc`:

  ```vim
  autocmd BufRead,BufNewFile ~/src/groovescript/**/*.gs set filetype=groovescript
  ```

  or add a modeline to each file:

  ```
  // vim: ft=groovescript
  ```
- The plugin only does syntax highlighting and basic indentation. There's
  no LSP, no go-to-definition, no linting. That's tracked as a separate
  backlog item.
- The highlighting is intentionally conservative about beat labels — it
  only matches them as whole words so it won't recolor identifiers or
  numbers inside string bodies. Count-string contents
  (`count: "1 e & a 2 e & a ..."`) are highlighted as a string; the
  GrooveScript parser tokenizes them internally.
