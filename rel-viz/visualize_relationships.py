"""Read relationship.xlsx and emit a Graphviz diagram + Plotly Sankey.

Flow (data direction; visualisation is rendered reversed, starting on the
left with column G — Parallel lookup — and ending on the right with
column A — Entity):

    Entity (col A)
     → Model View (col B)
     → Base Bde trigger (col C)
     → Base BDE Dependancy (col E, comma-split)
     → Parallel lookup (col G, comma-split)

When col E is empty / N/A (e.g. Transaction-Charge rows), Parallel lookup
edges are sourced from the Trigger (col C) instead so the chain doesn't
break.

Outputs (next to this script):
    relationship_graph        (DOT source)
    relationship_graph.svg
    relationship_sankey.html
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from graphviz import Digraph

HERE = Path(__file__).parent
XLSX_PATH = HERE / "relationship.xlsx"
DOT_PATH = HERE / "relationship_graph"          # graphviz appends .svg / source no ext
SANKEY_PATH = HERE / "relationship_sankey.html"

STAGES = ["Entity", "Model View", "Base Bde trigger", "Base BDE Dependancy", "Parallel lookup"]
STAGE_PREFIX = {
    "Entity": "E",
    "Model View": "M",
    "Base Bde trigger": "T",
    "Base BDE Dependancy": "D",
    "Parallel lookup": "P",
}
STAGE_COLOUR = {
    "Entity": "#4682B4",                # steelblue
    "Model View": "#E48A2B",            # orange
    "Base Bde trigger": "#2E8B57",      # sea green
    "Base BDE Dependancy": "#7B5AA6",   # purple
    "Parallel lookup": "#C04F70",       # rose
}


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------
def load_edges(xlsx: Path) -> tuple[list[tuple[str, str, str, str]], pd.DataFrame]:
    """Return (edges, dataframe). Edges are (src_stage, src, dst_stage, dst)."""
    df = pd.read_excel(xlsx, engine="openpyxl")
    df["Entity"] = df["Entity"].ffill()  # merged cells → ffill
    df = df.dropna(subset=["Model View"]).copy()
    df["Model View"] = df["Model View"].astype(str).str.strip()
    df["Base Bde trigger"] = df["Base Bde trigger"].fillna("").astype(str).str.strip()
    df["Base BDE Dependancy"] = df["Base BDE Dependancy"].fillna("").astype(str).str.strip()
    df["Parallel lookup"] = df["Parallel lookup"].fillna("").astype(str).str.strip()

    def _split(raw: str) -> list[str]:
        return [t.strip() for t in raw.split(",") if t.strip() and t.strip().upper() != "N/A"]

    edges: list[tuple[str, str, str, str]] = []
    for _, row in df.iterrows():
        entity = str(row["Entity"]).strip()
        model = row["Model View"]
        trigger = row["Base Bde trigger"]
        deps = _split(row["Base BDE Dependancy"])
        lookups = _split(row["Parallel lookup"])

        if entity and model:
            edges.append(("Entity", entity, "Model View", model))
        if model and trigger:
            edges.append(("Model View", model, "Base Bde trigger", trigger))

        for dep in deps:
            edges.append(("Base Bde trigger", trigger, "Base BDE Dependancy", dep))

        # Parallel lookup attaches to each Dependency when present, otherwise to
        # the Trigger directly so the chain still continues for rows without a
        # dependency (e.g. Transaction-Charge).
        if lookups:
            sources = (
                [("Base BDE Dependancy", d) for d in deps]
                if deps
                else [("Base Bde trigger", trigger)] if trigger else []
            )
            for src_stage, src in sources:
                for lookup in lookups:
                    edges.append((src_stage, src, "Parallel lookup", lookup))

    return edges, df


def aggregate(edges: list[tuple[str, str, str, str]]) -> Counter:
    """Count duplicate edges so Sankey link thickness reflects flow volume."""
    return Counter(edges)


# ---------------------------------------------------------------------------
# Graphviz
# ---------------------------------------------------------------------------
def render_graphviz(weighted: Counter, out_basename: Path) -> Path:
    g = Digraph(
        "relationships",
        format="svg",
        graph_attr={
            "rankdir": "RL",
            "splines": "spline",
            "nodesep": "0.25",
            "ranksep": "1.2",
            "bgcolor": "white",
            "fontname": "Helvetica",
        },
        node_attr={
            "shape": "box",
            "style": "rounded,filled",
            "fontname": "Helvetica",
            "fontsize": "10",
            "color": "#999999",
        },
        edge_attr={"color": "#888888", "arrowsize": "0.6"},
    )

    # Group nodes by stage so Graphviz aligns them in vertical columns.
    by_stage: dict[str, set[str]] = {s: set() for s in STAGES}
    for (src_stage, src, dst_stage, dst), _ in weighted.items():
        by_stage[src_stage].add(src)
        by_stage[dst_stage].add(dst)

    for stage in STAGES:
        with g.subgraph(name=f"cluster_{stage}") as sub:
            sub.attr(rank="same", label=stage, style="rounded", color="#dddddd",
                     fontsize="11", fontcolor="#444444")
            for name in sorted(by_stage[stage]):
                node_id = f"{STAGE_PREFIX[stage]}__{name}"
                sub.node(node_id, label=name, fillcolor=STAGE_COLOUR[stage], fontcolor="white")

    for (src_stage, src, dst_stage, dst), weight in weighted.items():
        sid = f"{STAGE_PREFIX[src_stage]}__{src}"
        did = f"{STAGE_PREFIX[dst_stage]}__{dst}"
        penwidth = f"{1.0 + min(weight - 1, 6) * 0.4:.1f}"
        g.edge(sid, did, penwidth=penwidth)

    # Always write the DOT source — it doesn't need the `dot` binary.
    g.save(filename=str(out_basename))
    try:
        rendered = g.render(filename=str(out_basename), cleanup=False)
        return Path(rendered)
    except Exception as exc:
        print(f"  [graphviz] could not render SVG ({exc.__class__.__name__}: {exc})")
        print(f"  [graphviz] install the `dot` binary (e.g. `brew install graphviz`) "
              f"and re-run, or render manually:  dot -Tsvg {out_basename} -o {out_basename}.svg")
        return Path(str(out_basename))


# ---------------------------------------------------------------------------
# Sankey
# ---------------------------------------------------------------------------
def render_sankey(weighted: Counter, out_path: Path) -> Path:
    # Build namespaced node list per stage so duplicate names across stages don't collide.
    nodes: list[tuple[str, str]] = []  # (stage, name)
    seen: set[tuple[str, str]] = set()
    for (src_stage, src, dst_stage, dst), _ in weighted.items():
        for stage, name in ((src_stage, src), (dst_stage, dst)):
            key = (stage, name)
            if key not in seen:
                seen.add(key)
                nodes.append(key)

    # Order nodes by stage so Sankey columns line up nicely.
    nodes.sort(key=lambda sn: (STAGES.index(sn[0]), sn[1]))
    node_index = {sn: i for i, sn in enumerate(nodes)}

    labels = [name for _, name in nodes]
    node_colours = [STAGE_COLOUR[stage] for stage, _ in nodes]

    # Reversed layout: stage 0 (Entity) on the right, last stage (Parallel
    # lookup) on the left — i.e. "start with column G".
    n_stages = len(STAGES)
    stage_to_indices: dict[str, list[int]] = {}
    for i, (stage, _) in enumerate(nodes):
        stage_to_indices.setdefault(stage, []).append(i)

    node_x = [0.5] * len(nodes)
    node_y = [0.5] * len(nodes)
    for stage, idx_list in stage_to_indices.items():
        stage_idx = STAGES.index(stage)
        if n_stages > 1:
            x_pos = 1.0 - stage_idx / (n_stages - 1)
        else:
            x_pos = 0.5
        x_pos = max(0.01, min(0.99, x_pos))
        for j, i in enumerate(idx_list):
            node_x[i] = x_pos
            n = len(idx_list)
            y_pos = (j + 0.5) / n if n > 1 else 0.5
            node_y[i] = max(0.01, min(0.99, y_pos))

    src_idx, dst_idx, values, link_colours = [], [], [], []
    # one tint per source stage for link colour
    link_tint = {
        "Entity": "rgba(70,130,180,0.45)",
        "Model View": "rgba(228,138,43,0.45)",
        "Base Bde trigger": "rgba(46,139,87,0.45)",
        "Base BDE Dependancy": "rgba(123,90,166,0.45)",
    }
    for (src_stage, src, dst_stage, dst), weight in weighted.items():
        src_idx.append(node_index[(src_stage, src)])
        dst_idx.append(node_index[(dst_stage, dst)])
        values.append(weight)
        link_colours.append(link_tint.get(src_stage, "rgba(150,150,150,0.4)"))

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=14,
            thickness=18,
            line=dict(color="#444", width=0.5),
            label=labels,
            color=node_colours,
            x=node_x,
            y=node_y,
        ),
        link=dict(source=src_idx, target=dst_idx, value=values, color=link_colours),
    ))
    fig.update_layout(
        title="Parallel lookup → Base BDE Dependancy → Base Bde trigger → Model View → Entity",
        font=dict(family="Helvetica", size=11),
        height=900,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    fig.write_html(out_path, include_plotlyjs="cdn")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if not XLSX_PATH.exists():
        raise SystemExit(
            f"{XLSX_PATH.name} not found. Run create_sample_xlsx.py first."
        )

    edges, df = load_edges(XLSX_PATH)
    weighted = aggregate(edges)
    print(f"Loaded {len(df)} rows, {sum(weighted.values())} total edges, "
          f"{len(weighted)} unique edges")

    svg_path = render_graphviz(weighted, DOT_PATH)
    print(f"Wrote {svg_path}")
    print(f"Wrote {DOT_PATH.with_suffix('')}  (DOT source)")

    html_path = render_sankey(weighted, SANKEY_PATH)
    print(f"Wrote {html_path}")


if __name__ == "__main__":
    main()
