if exists('g:loaded_map_conflicts')
  finish
endif
let g:loaded_map_conflicts = 1

if !exists('g:map_conflicts_python')
  let g:map_conflicts_python = 'python3'
endif

function! s:plugin_root() abort
  " .../vim-map-conflicts/plugin -> .../vim-map-conflicts
  return fnamemodify(expand('<sfile>:p'), ':h:h')
endfunction

function! s:resolve_script(name) abort
  " 0) явные переменные
  if a:name =~# 'runtime' && exists('g:map_conflicts_runtime_script')
    let p = expand(g:map_conflicts_runtime_script)
    if filereadable(p) | return p | endif
  endif
  if a:name =~# 'find_vim_conflicts.py' && exists('g:map_conflicts_static_script')
    let p = expand(g:map_conflicts_static_script)
    if filereadable(p) | return p | endif
  endif

  " 1) рядом с плагином (репо)
  let root = s:plugin_root()
  let cand = root . '/python/' . a:name
  if filereadable(cand) | return cand | endif

  " 2) поиск по всем runtimepath (без **, совместимо со старыми версиями)
  for dir in split(&runtimepath, ',')
    let cand1 = dir . '/vim-map-conflicts/python/' . a:name
    if filereadable(cand1) | return cand1 | endif
    let cand2 = dir . '/python/' . a:name
    if filereadable(cand2) | return cand2 | endif
  endfor

  return ''
endfunction

function! s:show_output(lines, title) abort
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
  let out = systemlist(a:cmd)
  if v:shell_error
    echohl ErrorMsg
    echom 'map-conflicts: command failed: ' . a:cmd
    echohl None
    return
  endif
  call s:show_output(out, a:title)
endfunction

function! s:run_static() abort
  let py = g:map_conflicts_python
  let script = s:resolve_script('find_vim_conflicts.py')
  if empty(script)
    echohl ErrorMsg
    echom 'map-conflicts: static script not found; set g:map_conflicts_static_script'
    echohl None
    return
  endif
  let cmd = printf('%s %s %s %s',
        \ shellescape(py),
        \ shellescape(script),
        \ shellescape(expand('~/.config/nvim')),
        \ shellescape(expand('~/.local/share/nvim/plugged')))
  call s:run(cmd, 'Static mapping conflicts')
endfunction

function! s:run_runtime() abort
  let py = g:map_conflicts_python
  let script = s:resolve_script('find_vim_conflicts_runtime.py')
  if empty(script)
    echohl ErrorMsg
    echom 'map-conflicts: runtime script not found; set g:map_conflicts_runtime_script'
    echohl None
    return
  endif
  let cmd = printf('%s %s', shellescape(py), shellescape(script))
  call s:run(cmd, 'Runtime mapping conflicts')
endfunction

function! s:debug() abort
  let root = s:plugin_root()
  let rt   = &runtimepath
  let stc  = s:resolve_script('find_vim_conflicts.py')
  let rtm  = s:resolve_script('find_vim_conflicts_runtime.py')
  call s:show_output([
        \ 'plugin root: ' . root,
        \ 'runtimepath: ' . rt,
        \ 'static.py:   ' . (empty(stc) ? '<not found>' : stc),
        \ 'runtime.py:  ' . (empty(rtm) ? '<not found>' : rtm),
        \ ], 'map-conflicts: debug')
endfunction

command! MapConflictsStatic  call s:run_static()
command! MapConflictsRuntime call s:run_runtime()
command! MapConflictsDebug   call s:debug()
