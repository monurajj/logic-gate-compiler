"""Export the optimised circuit as a Graphviz DOT diagram (bonus feature).

Render with:  dot -Tpng circuit.dot -o circuit.png
or paste the .dot text into https://dreampuf.github.io/GraphvizOnline
"""

from .icg import is_const


def to_dot(quads, inputs, outputs, name="circuit"):
    lines = [f'digraph "{name}" {{', "  rankdir=LR;", '  node [fontname="Helvetica"];']
    src = {}
    for i in inputs:
        lines.append(f'  "in_{i}" [label="{i}", shape=box, style=filled, fillcolor="#cfe8ff"];')
        src[i] = f"in_{i}"
    n_const = 0

    def node_of(x):
        nonlocal n_const
        if is_const(x):
            n_const += 1
            nid = f"const{n_const}"
            lines.append(f'  "{nid}" [label="{x}", shape=plaintext];')
            return nid
        return src[x]

    for k, q in enumerate(quads):
        if q.op == "COPY":
            src[q.result] = node_of(q.arg1)
            continue
        gid = f"g{k}"
        lines.append(f'  "{gid}" [label="{q.op}", shape=invhouse, style=filled, fillcolor="#fff2b3"];')
        for a in q.args():
            lines.append(f'  "{node_of(a)}" -> "{gid}";')
        src[q.result] = gid
    for o in outputs:
        lines.append(f'  "out_{o}" [label="{o}", shape=box, style=filled, fillcolor="#c8f7c5"];')
        lines.append(f'  "{src[o]}" -> "out_{o}";')
    lines.append("}")
    return "\n".join(lines)
