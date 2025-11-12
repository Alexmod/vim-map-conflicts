#!/usr/bin/env python3
import sys
from pathlib import Path

ATTR_LIST = [
    '<buffer>', '<nowait>', '<silent>', '<special>',
    '<script>', '<expr>', '<unique>', '<sid>',
]

USER_HINTS = [
    '/.config/nvim/',
    '/.vim/',
]


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
    if not s or s.startswith('\"'):
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


def collect_mappings(roots):
    mappings = []
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
    return any(hint in fname for hint in USER_HINTS)


def interesting_lhs(lhs):
    low = lhs.lower()
    if low.startswith('<plug>'):
        return False
    if low.startswith('<leader>') or low.startswith('<localleader>'):
        return True
    if low.startswith('<'):
        return False
    return len(lhs) <= 3


def find_duplicates(mappings):
    by_key = {}
    for mobj in mappings:
        key = (mobj['mode'], mobj['lhs'])
        by_key.setdefault(key, []).append(mobj)

    dups = {}
    for (mode, lhs), items in by_key.items():
        if not interesting_lhs(lhs):
            continue
        if not any(is_user_mapping(m) for m in items):
            continue
        if len(items) > 1:
            dups[(mode, lhs)] = items
    return dups


def modes_for_lhs_group(group):
    return {m['mode'] for m in group}


def find_prefix_conflicts(mappings):
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
            if not (interesting_lhs(lhs1) and interesting_lhs(lhs2)):
                continue
            g1 = by_lhs[lhs1]
            g2 = by_lhs[lhs2]
            # нужен общий режим, иначе j(n) vs jj(i) отсекаем
            if not (modes_for_lhs_group(g1) & modes_for_lhs_group(g2)):
                continue
            if not any(is_user_mapping(m) for m in g1 + g2):
                continue
            pair = tuple(sorted((lhs1, lhs2)))
            if pair in seen:
                continue
            seen.add(pair)
            conflicts.append((lhs1, lhs2, g1, g2))
    return conflicts


def print_human(mappings, dups, prefixes):
    uniq_keys = {(m['mode'], m['lhs']) for m in mappings}
    print('Raw mapping lines: {}'.format(len(mappings)))
    print('Unique (mode, lhs): {}'.format(len(uniq_keys)))

    print('\n=== Exact duplicates involving user config ===')
    if not dups:
        print('None')
    else:
        for (mode, lhs), items in sorted(dups.items()):
            print('[{}] {}:'.format(mode, lhs))
            for mobj in items:
                line = (
                    '{}:{}: {} {} {} {}'.format(
                        mobj['file'],
                        mobj['lineno'],
                        mobj['cmd'],
                        mobj['attrs'],
                        mobj['lhs'],
                        mobj['rhs'],
                    )
                )
                print('  {}'.format(line.rstrip()))

    print('\n=== Prefix conflicts involving user config ===')
    if not prefixes:
        print('None')
    else:
        for lhs1, lhs2, list1, list2 in prefixes:
            print('{!r} ~ {!r}:'.format(lhs1, lhs2))
            for mobj in list1 + list2:
                line = (
                    '[{}] {}:{}: {} {} {} {}'.format(
                        mobj['mode'],
                        mobj['file'],
                        mobj['lineno'],
                        mobj['cmd'],
                        mobj['attrs'],
                        mobj['lhs'],
                        mobj['rhs'],
                    )
                )
                print('  {}'.format(line.rstrip()))


def print_qf(dups, prefixes):
    for (mode, lhs), items in dups.items():
        for mobj in items:
            rhs = mobj['rhs'].replace('\t', ' ')
            attrs = mobj['attrs'].replace('\t', ' ')
            print(
                'D\t{}\t{}\t{}\t{}\t{}\t{}\t{}'.format(
                    mode,
                    lhs,
                    mobj['file'],
                    mobj['lineno'],
                    mobj['cmd'],
                    attrs,
                    rhs,
                )
            )
    for lhs1, lhs2, list1, list2 in prefixes:
        for mobj in list1 + list2:
            rhs = mobj['rhs'].replace('\t', ' ')
            attrs = mobj['attrs'].replace('\t', ' ')
            print(
                'P\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}'.format(
                    lhs1,
                    lhs2,
                    mobj['mode'],
                    mobj['lhs'],
                    mobj['file'],
                    mobj['lineno'],
                    mobj['cmd'],
                    attrs,
                    rhs,
                )
            )


def main(argv):
    qf = False
    roots = []
    for arg in argv[1:]:
        if arg == '--qf':
            qf = True
        else:
            roots.append(arg)

    if not roots:
        print(
            'Usage: find_vim_conflicts.py [--qf] DIR [DIR2 ...]\n'
            'Example: find_vim_conflicts.py '
            '~/.config/nvim ~/.local/share/nvim/plugged'
        )
        return 1

    mappings = collect_mappings(roots)
    dups = find_duplicates(mappings)
    prefixes = find_prefix_conflicts(mappings)

    if qf:
        print_qf(dups, prefixes)
    else:
        print_human(mappings, dups, prefixes)

    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
