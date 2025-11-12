if exists('g:loaded_map_conflicts')
  finish
endif
let g:loaded_map_conflicts = 1

if !exists('g:map_conflicts_python')
  let g:map_conflicts_python = 'python3'
endif

function! s:script_dir() abort
  return fnamemodify(expand('<sfile>:p'), ':h')
endfunction

function! s:show_output(lines, title) abort
  " новый scratch-буфер без имени
  new
  setlocal buftype=nofile bufhidden=wipe nobuflisted
  setlocal noswapfile nonumber norelativenumber

  if a:title !=# ''
    call setline(1, a:title)
    call append(1, '')
    call append(2, a:lines)
  else
    call setline(1, a:lines)
  endif

  normal! gg
endfunction

function! s:run(cmd, title) abort
  let l:out = systemlist(a:cmd)
  if v:shell_error
    echohl ErrorMsg
    echom 'map-conflicts: command failed: ' . a:cmd
    echohl None
    return
  endif
  call s:show_output(l:out, a:title)
endfunction

function! s:run_static() abort
  let l:root = s:script_dir()
  let l:py   = g:map_conflicts_python
  let l:cmd  = printf(
        \ '%s %s %s %s',
        \ shellescape(l:py),
        \ shellescape(l:root . '/python/find_vim_conflicts.py'),
        \ shellescape(expand('~/.config/nvim')),
        \ shellescape(expand('~/.local/share/nvim/plugged'))
        \ )
  call s:run(l:cmd, 'Static mapping conflicts')
endfunction

function! s:run_runtime() abort
  let l:root = s:script_dir()
  let l:py   = g:map_conflicts_python
  let l:cmd  = printf(
        \ '%s %s',
        \ shellescape(l:py),
        \ shellescape(l:root . '/python/find_vim_conflicts_runtime.py')
        \ )
  call s:run(l:cmd, 'Runtime mapping conflicts')
endfunction

command! MapConflictsStatic  call s:run_static()

command! MapConflictsRuntime call s:run_runtime()

