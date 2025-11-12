# vim-map-conflicts

A small helper plugin to inspect **key mapping conflicts** in Vim/Neovim.

It  comes with two Python scripts:

- `find_vim_conflicts.py` – **static** analysis: scans your config and
  plugin directories and finds:
  - exact duplicates: same `(mode, lhs)` defined in multiple places;
  - prefix conflicts: one mapping is a prefix of another (`s` vs `sz`,
    `<leader>a` vs `<leader>ab`, etc.).
- `find_vim_conflicts_runtime.py` – **static + runtime** analysis:
  - does the same static scan as above;
  - additionally runs `nvim --headless +verbose map` and marks each
    mapping as:
    - `ACTIVE` – this file actually owns the mapping at runtime;
    - `SHADOWED` – mapping is defined here, but overridden by another
      file;
    - `NO-RUNTIME` – mapping from this file is not present in the
      current `:verbose map` output.

The goal is to answer two questions:

- *Who* defines conflicting mappings?
- *Who* actually wins at runtime?

## Requirements

- Python 3.6+ (configurable via `g:map_conflicts_python`).
- Neovim (or Vim) with `:systemlist()` support.  
  Runtime analysis shell-execs `nvim --headless` with your `init.vim`.

The paths for static analysis are currently hard-coded to:

- `~/.config/nvim`
- `~/.local/share/nvim/plugged`

(you can change them in the Python scripts if needed).

## Installation

Using **vim-plug**:

```vim
Plug 'Alexmod/vim-map-conflicts'
