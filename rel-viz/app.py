"""Streamlit app: upload relationship.xlsx and view the flow as a Graphviz
graph and a Plotly Sankey.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import io
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

from visualize_relationships import (
    STAGES,
    STAGE_COLOUR,
    STAGE_PREFIX,
    aggregate,
    load_edges,
    render_sankey,
)
from graphviz import Digraph

HERE = Path(__file__).parent
DEFAULT_XLSX = HERE / "relationship.xlsx"


# ---------------------------------------------------------------------------
# Cached IO
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_from_path(path: str, _mtime: float):
    """Cache key includes mtime so edits to the file invalidate the cache."""
    edges, df = load_edges(Path(path))
    return edges, df


@st.cache_data(show_spinner=False)
def load_from_bytes(content: bytes):
    tmp = HERE / "_uploaded.xlsx"
    tmp.write_bytes(content)
    try:
        return load_edges(tmp)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Graphviz — emit DOT string for st.graphviz_chart (no `dot` binary needed)
# ---------------------------------------------------------------------------
def build_dot(weighted: Counter) -> str:
    g = Digraph(
        "relationships",
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
    by_stage: dict[str, set[str]] = {s: set() for s in STAGES}
    for (src_stage, src, dst_stage, dst), _ in weighted.items():
        by_stage[src_stage].add(src)
        by_stage[dst_stage].add(dst)

    for stage in STAGES:
        with g.subgraph(name=f"cluster_{stage}") as sub:
            sub.attr(rank="same", label=stage, style="rounded", color="#dddddd",
                     fontsize="11", fontcolor="#444444")
            for name in sorted(by_stage[stage]):
                sub.node(
                    f"{STAGE_PREFIX[stage]}__{name}",
                    label=name,
                    fillcolor=STAGE_COLOUR[stage],
                    fontcolor="white",
                )

    for (src_stage, src, dst_stage, dst), weight in weighted.items():
        sid = f"{STAGE_PREFIX[src_stage]}__{src}"
        did = f"{STAGE_PREFIX[dst_stage]}__{dst}"
        penwidth = f"{1.0 + min(weight - 1, 6) * 0.4:.1f}"
        g.edge(sid, did, penwidth=penwidth)

    return g.source


def filter_edges(edges: list[tuple[str, str, str, str]], entities: list[str]):
    """Keep only edges reachable from the selected entities (forward closure)."""
    if not entities:
        return edges
    keep_nodes: set[tuple[str, str]] = {("Entity", e) for e in entities}
    changed = True
    while changed:
        changed = False
        for src_stage, src, dst_stage, dst in edges:
            if (src_stage, src) in keep_nodes and (dst_stage, dst) not in keep_nodes:
                keep_nodes.add((dst_stage, dst))
                changed = True
    return [
        e for e in edges
        if (e[0], e[1]) in keep_nodes and (e[2], e[3]) in keep_nodes
    ]


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Relationship Visualiser", page_icon="🔗", layout="wide")
st.markdown("## 🔗 Relationship Visualiser")
st.caption("Parallel lookup → Base BDE Dependancy → Base Bde trigger → Model View → Entity")

with st.sidebar:
    st.markdown("### Source")
    uploaded = st.file_uploader("Upload relationship.xlsx", type=["xlsx"])
    if uploaded is not None:
        edges, df = load_from_bytes(uploaded.getvalue())
        st.success(f"Loaded uploaded file ({len(df)} rows)")
    elif DEFAULT_XLSX.exists():
        edges, df = load_from_path(str(DEFAULT_XLSX), DEFAULT_XLSX.stat().st_mtime)
        st.info(f"Using `{DEFAULT_XLSX.name}` ({len(df)} rows)")
    else:
        st.error(
            f"No upload and {DEFAULT_XLSX.name} not found. "
            "Run `python create_sample_xlsx.py` first or upload a file."
        )
        st.stop()

    st.markdown("### Filter")
    all_entities = sorted(df["Entity"].dropna().unique().tolist())
    selected_entities = st.multiselect(
        "Entities", all_entities, default=all_entities,
        help="Forward closure from each selected entity through the flow.",
    )

filtered_edges = filter_edges(edges, selected_entities)
weighted = aggregate(filtered_edges)

# KPI strip
node_counts = {s: 0 for s in STAGES}
for (src_stage, src, dst_stage, dst), _ in weighted.items():
    node_counts.setdefault(src_stage, 0)
    node_counts.setdefault(dst_stage, 0)
unique_nodes = {s: set() for s in STAGES}
for (src_stage, src, dst_stage, dst), _ in weighted.items():
    unique_nodes[src_stage].add(src)
    unique_nodes[dst_stage].add(dst)

cols = st.columns(len(STAGES) + 1)
for col, stage in zip(cols[:-1], STAGES):
    col.metric(stage, len(unique_nodes[stage]))
cols[-1].metric("Edges", sum(weighted.values()))

# Tabs
tab_graph, tab_sankey, tab_data = st.tabs(["Graphviz", "Sankey", "Data"])

with tab_graph:
    if not weighted:
        st.warning("No edges to display — adjust the entity filter.")
    else:
        dot_source = build_dot(weighted)
        st.graphviz_chart(dot_source, width="stretch")
        with st.expander("DOT source"):
            st.code(dot_source, language="dot")

with tab_sankey:
    if not weighted:
        st.warning("No edges to display — adjust the entity filter.")
    else:
        tmp_html = HERE / "_sankey_tmp.html"
        render_sankey(weighted, tmp_html)
        st.components.v1.html(tmp_html.read_text(), height=820, scrolling=True)
        tmp_html.unlink(missing_ok=True)

with tab_data:
    st.dataframe(df, width="stretch", hide_index=True)
    edge_df = pd.DataFrame(
        [
            {"src_stage": s_st, "src": s, "dst_stage": d_st, "dst": d, "weight": w}
            for (s_st, s, d_st, d), w in weighted.items()
        ]
    ).sort_values(["src_stage", "src", "dst_stage", "dst"])
    st.markdown("**Derived edges**")
    st.dataframe(edge_df, width="stretch", hide_index=True)
    csv_buf = io.StringIO()
    edge_df.to_csv(csv_buf, index=False)
    st.download_button("Download edges CSV", csv_buf.getvalue(),
                       "edges.csv", "text/csv")
