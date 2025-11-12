#!/usr/bin/env python3
import sys
import os
import subprocess
from pathlib import Path

ROOTS = [
    '~/.config/nvim',
    '~/.local/share/nvim/plugged',
]

USER_HINTS = [
    '/.config/nvim/',
    '/.vim/',
]

ATTR_LIST = [
    '<buffer>', '<nowait>', '<silent>', '<special>',
    '<script>', '<expr>', '<unique>', '<sid>',
]


# ---------- статическая часть ----------

def mode_from_cmd(cmd):
    c = cmd[0]
    return c if c in 'nvoxsilct' else 'map'


def peel_attrs(token):
    attrs = []
    rest = token
    while rest:
        lower = rest.lower()
        matched = False
        for a in ATTR_LIST:
            if lower.startswith(a):
                attrs.append(rest[: len(a)])
                rest = rest[len(a):]
                matched = True
                break
        if not matched:
            break
    return attrs, rest


def parse_map_line(line, path, lineno):
    s = line.lstrip()
    if not s or s.startswith('"'):
        return None

    parts = s.split()
    if not parts:
        return None

    idx = 0
    while idx < len(parts) and parts[idx].lower() in (
        'silent',
        'silent!',
        'noau',
    ):
        idx += 1
    if idx >= len(parts):
        return None

    cmd = parts[idx]
    idx += 1

    if 'map' not in cmd or 'unmap' in cmd:
        return None

    attrs = []
    while idx < len(parts):
        t = parts[idx]
        low = t.lower()
        if low in ATTR_LIST:
            attrs.append(t)
            idx += 1
            continue
        extra_attrs, rest = peel_attrs(t)
        if extra_attrs:
            attrs.extend(extra_attrs)
            if not rest:
                idx += 1
                continue
            parts[idx] = rest
        break

    if idx >= len(parts):
        return None

    lhs = parts[idx]
    rhs = ' '.join(parts[idx + 1:])

    return {
        'mode': mode_from_cmd(cmd),
        'lhs': lhs,
        'rhs': rhs,
        'attrs': ' '.join(attrs),
        'file': str(path),
        'lineno': lineno,
        'cmd': cmd,
    }


def walk_files(roots):
    for root in roots:
        p = Path(root).expanduser()
        if p.is_file():
            if p.suffix == '.vim':
                yield p
            continue
        for fpath in p.rglob('*.vim'):
            yield fpath


def collect_mappings_static():
    mappings = []
    roots = [Path(r).expanduser() for r in ROOTS]
    for path in walk_files(roots):
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            mobj = parse_map_line(line, path, lineno)
            if mobj is not None:
                mappings.append(mobj)
    return mappings


def is_user_mapping(mobj):
    fname = mobj['file']
    if not fname:
        return False
    return any(h in fname for h in USER_HINTS)


def interesting_lhs(lhs):
    low = lhs.lower()
    if low.startswith('<plug>'):
        return False
    if low.startswith('<leader>') or low.startswith('<localleader>'):
        return True
    if low.startswith('<'):
        return False
    return len(lhs) <= 3


def find_duplicates_static(mappings):
    by_key = {}
    for mobj in mappings:
        key = (mobj['mode'], mobj['lhs'])
        by_key.setdefault(key, []).append(mobj)

    dups = {}
    for (mode, lhs), items in by_key.items():
        if not interesting_lhs(lhs):
            continue
        if len(items) <= 1:
            continue
        if not any(is_user_mapping(m) for m in items):
            continue
        dups[(mode, lhs)] = items
    return dups


def modes_for_group(group):
    return {m['mode'] for m in group}


def find_prefix_conflicts_static(mappings):
    by_lhs = {}
    for mobj in mappings:
        lhs = mobj['lhs']
        if not interesting_lhs(lhs):
            continue
        by_lhs.setdefault(lhs, []).append(mobj)

    keys = sorted(by_lhs.keys(), key=len)
    nkeys = len(keys)
    seen = set()
    conflicts = []

    for i in range(nkeys):
        lhs1 = keys[i]
        for j in range(i + 1, nkeys):
            lhs2 = keys[j]
            if not (lhs2.startswith(lhs1) or lhs1.startswith(lhs2)):
                continue
            if lhs1 == lhs2:
                continue
            g1 = by_lhs[lhs1]
            g2 = by_lhs[lhs2]
            if not (modes_for_group(g1) & modes_for_group(g2)):
                continue
            if not any(is_user_mapping(m) for m in g1 + g2):
                continue
            pair = tuple(sorted((lhs1, lhs2)))
            if pair in seen:
                continue
            seen.add(pair)
            conflicts.append((lhs1, lhs2, g1, g2))
    return conflicts


# ---------- рантайм-часть ----------

def run_verbose_map(nvim='nvim', init=None):
    if init is None:
        init = os.path.expanduser('~/.config/nvim/init.vim')
    else:
        init = os.path.expanduser(init)

    cmd = [
        nvim,
        '--headless',
        '-u', init,
        '+verbose map',
        '+qall',
    ]

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    if proc.returncode != 0:
        print('Error running {}: {}'.format(nvim, proc.returncode),
              file=sys.stderr)
        print(proc.stdout, file=sys.stderr)
        sys.exit(1)
    return proc.stdout.splitlines()


def parse_verbose_map(lines):
    entries = []
    cur = None

    for line in lines:
        s = line.rstrip('\n')
        if not s.strip():
            continue

        stripped = s.lstrip()

        if stripped.startswith('Last set from') and cur is not None:
            rest = stripped[len('Last set from'):].strip()
            fname = ''
            lnum = 0
            if ' line ' in rest:
                try:
                    fname, lnum_str = rest.rsplit(' line ', 1)
                    fname = fname.strip()
                    lnum = int(lnum_str.strip())
                except Exception:
                    fname = rest.strip()
                    lnum = 0
            else:
                fname = rest.strip()
                lnum = 0
            cur['file'] = fname
            cur['lineno'] = lnum
            continue

        parts = stripped.split()
        if len(parts) >= 3 and len(parts[0]) == 1 \
                and parts[0] in 'nvxsotcil ':
            mode = parts[0].strip() or 'map'
            lhs = parts[1]
            rhs = ' '.join(parts[2:]).strip()

            if cur is not None:
                entries.append(cur)

            cur = {
                'mode': mode,
                'lhs': lhs,
                'rhs': rhs,
                'file': '',
                'lineno': 0,
            }
            continue

        if cur is not None:
            cur['rhs'] += ' | ' + stripped

    if cur is not None:
        entries.append(cur)

    return entries


def build_runtime_index(runtime_maps):
    rt = {}
    for m in runtime_maps:
        key = (m['mode'], m['lhs'])
        rt[key] = m
    return rt


def norm_path(p):
    if not p:
        return ''
    return os.path.normpath(
        os.path.abspath(os.path.expanduser(p))
    )


def same_path(a, b):
    return norm_path(a) == norm_path(b)


# ---------- отчёт ----------

def print_report(static_maps, dups, prefixes, runtime_idx):
    uniq = {(m['mode'], m['lhs']) for m in static_maps}
    print('Static mapping lines: {}'.format(len(static_maps)))
    print('Static unique (mode, lhs): {}'.format(len(uniq)))

    print('\n=== Static duplicates involving user config (with runtime) ===')
    if not dups:
        print('None')
    else:
        for (mode, lhs), items in sorted(dups.items()):
            print('[{}] {}:'.format(mode, lhs))
            active = runtime_idx.get((mode, lhs))
            for mobj in items:
                status = 'NO-RUNTIME'
                if active is not None:
                    if same_path(active['file'], mobj['file']):
                        status = 'ACTIVE'
                    else:
                        status = 'SHADOWED'
                line = '{} [{} {}]: {}:{}: {} {} {}'.format(
                    status,
                    mobj['mode'],
                    mobj['lhs'],
                    mobj['file'],
                    mobj['lineno'],
                    mobj['cmd'],
                    mobj['attrs'],
                    mobj['rhs'],
                )
                print('  {}'.format(line.rstrip()))

    print('\n=== Static prefix conflicts involving user config (with runtime) ===')
    if not prefixes:
        print('None')
    else:
        for lhs1, lhs2, g1, g2 in prefixes:
            print('{!r} ~ {!r}:'.format(lhs1, lhs2))
            for group in (g1, g2):
                for mobj in group:
                    key = (mobj['mode'], mobj['lhs'])
                    active = runtime_idx.get(key)
                    status = 'NO-RUNTIME'
                    if active is not None:
                        if same_path(active['file'], mobj['file']):
                            status = 'ACTIVE'
                        else:
                            status = 'SHADOWED'
                    line = '{} [{} {}]: {}:{}: {} {} {}'.format(
                        status,
                        mobj['mode'],
                        mobj['lhs'],
                        mobj['file'],
                        mobj['lineno'],
                        mobj['cmd'],
                        mobj['attrs'],
                        mobj['rhs'],
                    )
                    print('  {}'.format(line.rstrip()))


def main(argv):
    nvim = 'nvim'
    init = None
    if len(argv) > 1:
        nvim = argv[1]
    if len(argv) > 2:
        init = argv[2]

    static_maps = collect_mappings_static()
    dups = find_duplicates_static(static_maps)
    prefixes = find_prefix_conflicts_static(static_maps)

    rt_lines = run_verbose_map(nvim=nvim, init=init)
    runtime_maps = parse_verbose_map(rt_lines)
    runtime_idx = build_runtime_index(runtime_maps)

    print_report(static_maps, dups, prefixes, runtime_idx)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
