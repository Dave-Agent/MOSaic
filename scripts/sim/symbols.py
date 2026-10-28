"""Symbol lookup from a Kick Assembler symbol file, by name.

  load(path)        -> {name: address}   `.sym` (-symbolfile): every label with its scope path ('Module.Routine', 'Module.Sub.Data.table'),
                                         locals included ('Routine.fill_loop'); `.vs` (-vicesymbols, `al C:ADDR .name`): flat names, the namespace
                                         prefix is dropped by Kick, so a name that exists in several namespaces keeps the last one.
  routines(path)    -> {name: address}   only the labels reachable from outside a routine (no labels inside a routine's own scope)
  lookup(table, name)                    the address, or a clear error naming the closest matches

No project names in here; the file comes from project.config (TRACE_SYM / TRACE_SYM_P1) or an argument.
"""
import difflib, re

def _parse(path, locals_too):
    syms = {}; stack = []      # stack entries: (name, is_routine_scope)
    for l in open(path):
        l = l.strip(); m = re.match(r'\.namespace (\w+) \{', l)
        if m: stack.append((m.group(1), False)); continue
        if l == '}':
            if stack: stack.pop()
            continue
        m = re.match(r'\.label (\w+)=\$([0-9a-fA-F]+)( \{)?$', l)
        if m:
            if locals_too or not any(sc for _, sc in stack): syms['.'.join([n for n, _ in stack] + [m.group(1)])] = int(m.group(2), 16)
            if m.group(3): stack.append((m.group(1), True))
    return syms

def _parse_vs(path):
    syms = {}
    for l in open(path):
        m = re.match(r'al C:([0-9a-fA-F]+) \.(\S+)', l.strip())
        if m: syms[m.group(2)] = int(m.group(1), 16)
    return syms

def load(path):
    """every label of the symbol file (`.vs` by extension, else Kick's `.sym`)"""
    return _parse_vs(path) if path.endswith('.vs') else _parse(path, True)

def routines(path):
    """labels reachable from outside their routine (a `.sym` file only)"""
    return _parse(path, False)

def lookup(table, name):
    if name in table: return table[name]
    close = difflib.get_close_matches(name, table, 5)
    raise KeyError('symbol %r not found%s' % (name, (' (closest: %s)' % ', '.join(close)) if close else ''))
