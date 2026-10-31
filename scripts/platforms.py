#!/usr/bin/env python3
"""Platforms as data (issue #39): load, validate and query a platform descriptor (platforms/<id>/platform.json).

  platforms.py list                       the platforms there are
  platforms.py check [ID]                 validate a descriptor (all of them without ID); exit 1 on a problem
  platforms.py show ID                    the descriptor
  platforms.py get ID PATH                one value, PATH dotted (`memory.banking.register`, `chips.0.lo`)
  platforms.py visible ID ADDR [PORT]     what the CPU sees at ADDR (hex) when the banking register holds PORT (hex, default 07)
  platforms.py mirror ID ADDR             the register address a mirror of a chip answers on (as apply_libs.py does)
  platforms.py mapper-write ID MAPPER ADDR VALUE [ADDR VALUE ...]      the mapper state after CPU writes (hex); MAPPER is the iNES number or the name
  platforms.py mapper-window ID MAPPER SPACE ADDR ROMSIZE [NAME=VALUE ...]   which bank and ROM offset ADDR reads (SPACE prg|chr, ROMSIZE hex bytes)

A project names its platform in project.config (`PLATFORM="c64"`; the default is c64, so a project that has no such key is unchanged). Tools read what they need from the descriptor instead
of assuming it; references/platform_descriptor.md says what each section is for and which tool reads it. Standard library only."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import config, SKILL_DIR
PLATFORMS = os.path.join(SKILL_DIR, 'platforms')
DEFAULT = 'c64'

def ids(): return sorted(d for d in os.listdir(PLATFORMS) if os.path.exists(os.path.join(PLATFORMS, d, 'platform.json'))) if os.path.isdir(PLATFORMS) else []

def load(pid):
    p = os.path.join(PLATFORMS, pid, 'platform.json')
    if not os.path.exists(p): sys.exit('no platform %r (platforms: %s)' % (pid, ', '.join(ids()) or 'none'))
    return json.load(open(p))

def for_project(root):
    """The descriptor of the project's platform: PLATFORM in project.config, else c64."""
    return load(config(root).get('PLATFORM') or DEFAULT)

def addr(s): return int(str(s), 16)

def span(s):
    """`D000-D3FF` -> (0xD000, 0xD3FF)."""
    lo, _, hi = str(s).partition('-'); return addr(lo), addr(hi or lo)

def lib_dirs(d): return [os.path.join(PLATFORMS, d['id'], 'libs'), os.path.join(SKILL_DIR, 'libs')]

def find_lib(d, name):
    return next((os.path.join(x, name) for x in lib_dirs(d) if os.path.exists(os.path.join(x, name))), None)

def _hex(s): return isinstance(s, str) and re.fullmatch(r'[0-9A-Fa-f]{1,4}', s) is not None

def validate(d):
    """List of problems of one descriptor ([] when it is in order)."""
    bad = []
    def need(obj, key, where, kind=None):
        if not isinstance(obj, dict) or key not in obj: bad.append('%s: no `%s`' % (where, key)); return None
        if kind and not isinstance(obj[key], kind): bad.append('%s.%s: expected %s' % (where, key, kind.__name__)); return None
        return obj[key]
    if need(d, 'schema', 'descriptor') != 1: bad.append('descriptor: schema must be 1')
    pid = need(d, 'id', 'descriptor', str)
    if pid is not None and not re.fullmatch(r'[a-z][a-z0-9]*(-[a-z0-9]+)*', pid): bad.append('id %r is not kebab-case' % pid)
    for k in ('name', 'family'): need(d, k, 'descriptor', str)
    cpu = need(d, 'cpu', 'descriptor', dict)
    if cpu:
        need(cpu, 'variant', 'cpu', str); need(cpu, 'assembler', 'cpu', dict); vec = need(cpu, 'vectors', 'cpu', dict)
        for k, v in (vec or {}).items():
            if not _hex(v): bad.append('cpu.vectors.%s: %r is not a hex address' % (k, v))
        for k in ('nmi', 'reset', 'irq'):
            if vec is not None and k not in vec: bad.append('cpu.vectors: no `%s`' % k)
    mem = need(d, 'memory', 'descriptor', dict); size = (mem or {}).get('size', 0); regs = []; names = set()
    if mem:
        if not isinstance(size, int) or size <= 0 or size & (size - 1): bad.append('memory.size %r is not a power of two' % size)
        for i, r in enumerate(need(mem, 'regions', 'memory', list) or []):
            w = 'memory.regions.%d' % i
            if not (_hex(r.get('lo')) and _hex(r.get('hi'))): bad.append('%s: lo and hi must be hex addresses' % w); continue
            lo, hi = addr(r['lo']), addr(r['hi'])
            if lo > hi or hi >= size: bad.append('%s (%s): the range %04X-%04X is reversed or outside the %d bytes' % (w, r.get('name'), lo, hi, size))
            if r.get('kind') not in ('ram', 'rom', 'io'): bad.append('%s (%s): kind must be ram, rom or io' % (w, r.get('name')))
            if not r.get('name') or r['name'] in names: bad.append('%s: the name %r is missing or repeated' % (w, r.get('name')))
            names.add(r.get('name')); regs.append((lo, hi, r.get('name')))
            if r.get('alternate'): names.add(r['alternate'])
        regs.sort()
        for (a1, b1, n1), (a2, b2, n2) in zip(regs, regs[1:]):
            if a2 <= b1: bad.append('memory.regions: %s (%04X-%04X) overlaps %s (%04X-%04X)' % (n1, a1, b1, n2, a2, b2))
        if regs and (regs[0][0] != 0 or regs[-1][1] != size - 1 or any(a2 != b1 + 1 for (_, b1, _), (a2, _, _) in zip(regs, regs[1:]))): bad.append('memory.regions do not tile the address space 0000-%04X without a gap' % (size - 1))
        for k, v in ((vec or {}) if cpu else {}).items():
            if _hex(v) and addr(v) + 1 >= size: bad.append('cpu.vectors.%s: $%s is outside the memory' % (k, v))
        bk = mem.get('banking')
        if bk:
            bits = bk.get('bits', {}); bn = set(bits.values())
            if not _hex(bk.get('register')): bad.append('memory.banking.register is not a hex address')
            for j, v in enumerate(bk.get('visible', [])):
                if v.get('region') not in names: bad.append('memory.banking.visible.%d: the region %r is not defined' % (j, v.get('region')))
                e = v.get('when', '')
                if not re.fullmatch(r'[A-Za-z_ ()]+', e) or not {t for t in re.findall(r'[A-Za-z_]+', e)} <= (bn | {'and', 'or', 'not'}): bad.append('memory.banking.visible.%d: `when` may use only %s, and, or, not and parentheses: %r' % (j, ', '.join(sorted(bn)), e))
    chips = need(d, 'chips', 'descriptor', list); io = [(lo, hi) for lo, hi, n in regs if any(r.get('name') == n and r.get('kind') == 'io' for r in (mem or {}).get('regions', []))]
    for i, c in enumerate(chips or []):
        w = 'chips.%d (%s)' % (i, c.get('name'))
        if not (_hex(c.get('lo')) and _hex(c.get('hi'))): bad.append('%s: lo and hi must be hex addresses' % w); continue
        lo, hi = addr(c['lo']), addr(c['hi'])
        if not any(a <= lo and hi <= b for a, b in io): bad.append('%s: %04X-%04X is not inside an io region of the memory map' % (w, lo, hi))
        if c.get('mirror_step') is not None:
            ms = addr(c['mirror_step']) if _hex(c['mirror_step']) else 0
            if ms <= 0 or ms & (ms - 1) or (hi - lo + 1) % ms: bad.append('%s: mirror_step %r must be a power of two that divides the block' % (w, c['mirror_step']))
        if c.get('registers'):
            a, b = span(c['registers'])
            if not (lo <= a <= b <= hi): bad.append('%s: registers %s are outside the block' % (w, c['registers']))
    for l in need(d, 'libs', 'descriptor', list) or []:
        if pid and not find_lib(d, l): bad.append('libs: %s is not in platforms/%s/libs or libs/' % (l, pid))
    for c in chips or []:
        if c.get('lib') and c['lib'] not in d.get('libs', []): bad.append('chips: %s names lib %s that is not in libs' % (c.get('name'), c['lib']))
    media = need(d, 'media', 'descriptor', dict)
    if media and not (isinstance(media.get('types'), list) and media['types'] and all(isinstance(t, str) and t == t.lower() for t in media['types'])): bad.append('media.types must be a list of lower-case file extensions')
    return bad

def _eval(expr, bits, port):
    env = {name: bool(port >> int(b) & 1) for b, name in bits.items()}
    if not re.fullmatch(r'[A-Za-z_ ()]+', expr) or not set(re.findall(r'[A-Za-z_]+', expr)) <= set(env) | {'and', 'or', 'not'}: raise ValueError('bad banking expression %r' % expr)
    return bool(eval(expr, {'__builtins__': {}}, env))

def visible_at(d, a, port=7):
    """What the CPU sees at address a when the banking register holds `port`: the name of the region (`ram` where a ROM or the I/O area is switched out, `character ROM` where it replaces the I/O area)."""
    mem = d['memory']; bk = mem.get('banking') or {}; bits = bk.get('bits', {}); rules = {v['region']: v for v in bk.get('visible', [])}
    for r in mem['regions']:
        lo, hi = addr(r['lo']), addr(r['hi'])
        if not lo <= a <= hi: continue
        if r['kind'] == 'ram' or not bk: return r['name'] if r['kind'] == 'ram' else r['name']
        if r['name'] in rules and _eval(rules[r['name']]['when'], bits, port): return r['name']
        alt = r.get('alternate')
        if alt and alt in rules and _eval(rules[alt]['when'], bits, port): return alt
        return r.get('under', 'ram')
    return None

def mirror(d, a):
    """The register address a mirror answers on (a chip decodes fewer address lines than its block has), or the address itself."""
    for c in d['chips']:
        if c.get('mirror_step') and addr(c['lo']) <= a <= addr(c['hi']): return addr(c['lo']) + (a - addr(c['lo'])) % addr(c['mirror_step'])
    return a

# ---- mappers: bank switching done by the cartridge (platforms/<id>/mappers/<name>.json) ----
def mapper_dir(pid): return os.path.join(PLATFORMS, pid, 'mappers')

def mappers(pid):
    """{iNES number: mapper description} of a platform that has mapper files (empty for one that has none)."""
    d = mapper_dir(pid)
    out = {}
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.endswith('.json'): m = json.load(open(os.path.join(d, f))); m['_file'] = f; out[m['ines']] = m
    return out

def mapper_find(pid, key):
    """A mapper by iNES number or by name (case does not matter)."""
    for n, m in mappers(pid).items():
        if str(n) == str(key) or m['name'].lower() == str(key).lower(): return m
    sys.exit('platform %s has no mapper %r (it has: %s)' % (pid, key, ', '.join('%d %s' % (n, m['name']) for n, m in mappers(pid).items()) or 'none'))

def _mexpr(expr, state):
    names = set(re.findall(r'[A-Za-z_]\w*', expr))
    if not re.fullmatch(r'[A-Za-z0-9_ ()&|+\-<>=!^~]+', expr) or not names <= set(state) | {'d', 'and', 'or', 'not'}:
        raise ValueError('bad mapper expression %r' % expr)
    return eval(expr, {'__builtins__': {}}, state)

def mapper_state(m): return dict(m['state'])

def mapper_write(m, state, a, value):
    """The state after the CPU writes `value` to address `a`; also the name of the register hit (None when none decodes it)."""
    st = dict(state)
    for r in m['registers']:
        if a & addr(r['mask']) == addr(r['value']):
            env = dict(st, d=value)
            for k, e in r.get('set', {}).items():
                key = k.format(**st)
                if key not in st: raise ValueError('%s: no state %r' % (m['name'], key))
                st[key] = _mexpr(e, env)
            return st, r['name']
    return st, None

def mapper_window(m, space, a, rom_size, state):
    """(window span, bank, ROM offset) that address `a` of the CPU (space `prg`) or PPU (`chr`) reads from a ROM of rom_size bytes; None outside every window."""
    unit = addr(m[space + '_unit']); count = max(rom_size // unit, 1)
    for w in m[space]:
        lo, hi = span(w.get('cpu') or w['ppu'])
        if not lo <= a <= hi: continue
        for alt in w['bank']:
            if 'when' in alt and not _mexpr(alt['when'], state): continue
            b = _mexpr(str(alt['bank']), state); b = (count + b if b < 0 else b) % count
            return (lo, hi), b, b * unit + (a - lo)
    return None

def validate_mapper(m):
    bad = []
    for k in ('ines', 'name', 'prg_unit', 'chr_unit', 'state', 'registers', 'prg', 'chr'):
        if k not in m: bad.append('no `%s`' % k)
    if bad: return bad
    if m['schema'] != 1: bad.append('schema must be 1')
    try:
        if not isinstance(m['ines'], int): bad.append('ines must be a number')
        if not (_hex(m['prg_unit']) and _hex(m['chr_unit'])): bad.append('prg_unit and chr_unit must be hex')
        for r in m['registers']:
            if not (_hex(r.get('mask')) and _hex(r.get('value'))): bad.append('register %s: mask and value must be hex' % r.get('name'))
            elif addr(r['value']) & ~addr(r['mask']): bad.append('register %s: value has bits outside the mask' % r['name'])
        if bad: return bad
        for space, key in (('prg', 'cpu'), ('chr', 'ppu')):
            spans = sorted(span(w[key]) for w in m[space])
            for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
                if b0 <= a1: bad.append('%s windows overlap at %04X' % (space, b0))
            for w in m[space]:
                if not w['bank'] or 'when' in w['bank'][-1]: bad.append('%s window %s: the last alternative must have no `when`' % (space, w[key]))
        # every register written with several values, and every window resolved
        for v in (0, 0xFF, 0x5A, 0xC7):
            st = mapper_state(m)
            for r in m['registers']:
                st, _ = mapper_write(m, st, addr(r['value']), v)
                for sp in ('prg', 'chr'):
                    for w in m[sp]: mapper_window(m, sp, span(w.get('cpu') or w['ppu'])[0], 0x40000, st)
    except (ValueError, KeyError, TypeError) as e: bad.append(str(e))
    return bad

def get(d, path):
    for k in path.split('.'):
        d = d[int(k)] if isinstance(d, list) else d[k]
    return d

def main():
    a = sys.argv[1:]
    if not a or a[0] not in ('list', 'check', 'show', 'get', 'visible', 'mirror', 'mapper-write', 'mapper-window'): print(__doc__); return 2
    c = a[0]
    if c == 'list':
        for i in ids(): d = load(i); print('%-10s %s (%s)' % (i, d['name'], d['cpu']['variant']))
        return 0
    if c == 'check':
        rc = 0
        for i in ([a[1]] if len(a) > 1 else ids()):
            bad = validate(load(i)); print('%s: %s' % (i, 'ok' if not bad else '%d problem(s)' % len(bad)))
            for b in bad: print('  - ' + b)
            rc |= bool(bad)
            for n, m in mappers(i).items():
                mb = validate_mapper(m); print('%s mapper %d %s: %s' % (i, n, m['name'], 'ok' if not mb else '%d problem(s)' % len(mb)))
                for b in mb: print('  - ' + b)
                rc |= bool(mb)
        return rc
    if c in ('mapper-write', 'mapper-window'):
        m = mapper_find(a[1], a[2]); st = mapper_state(m)
        if c == 'mapper-write':          # ID MAPPER ADDR VALUE [ADDR VALUE ...]: the state after a series of writes
            for x, v in zip(a[3::2], a[4::2]):
                st, hit = mapper_write(m, st, addr(x), int(v, 16)); print('%s <- %s: %s' % (x.upper(), v, hit or 'no register'))
            print(json.dumps(st)); return 0
        for kv in a[6:]:                 # ID MAPPER SPACE ADDR ROMSIZE [NAME=VALUE ...]
            k, _, v = kv.partition('='); st[k] = int(v, 0)
        w = mapper_window(m, a[3], addr(a[4]), addr(a[5]), st)
        print('not mapped' if not w else 'window %04X-%04X bank %d ROM offset %X' % (w[0][0], w[0][1], w[1], w[2])); return 0
    d = load(a[1])
    if c == 'show': print(json.dumps(d, indent=2)); return 0
    if c == 'get': v = get(d, a[2]); print(json.dumps(v) if isinstance(v, (dict, list)) else v); return 0
    if c == 'visible': print(visible_at(d, addr(a[2]), addr(a[3]) if len(a) > 3 else 7)); return 0
    print('%04X' % mirror(d, addr(a[2]))); return 0
if __name__ == '__main__': sys.exit(main())
