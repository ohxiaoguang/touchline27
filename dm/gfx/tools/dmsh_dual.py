"""Add a dual-source fragment entry while retaining the ordinary MRT entry."""
import re


def variant(src):
    st = re.search(r'struct main0_out\s*\{(.*?)\};', src, re.S)
    fn = re.search(r'fragment\s+main0_out\s+main0\s*\(', src)
    if not st or not fn:
        return None
    colors = re.findall(r'\[\[color\((\d+)\)\]\]', st[1])
    if sorted(colors) != ['0', '1']:
        return None
    # Maxwell's second output serves either MRT1 or source1, selected by blend state.
    # Metal requires a different signature for the latter: color(0), index(1).
    decl = st[0].replace('main0_out', 'main0_out_dual').replace('[[color(0)]]', '[[color(0), index(0)]]').replace('[[color(1)]]', '[[color(0), index(1)]]')
    body = src[fn.start():]
    body = body.replace('fragment main0_out main0(', 'fragment main0_out_dual main0_dual(', 1)
    body = body.replace('main0_out out', 'main0_out_dual out', 1)
    return '\n' + decl + '\n' + body
