#!/usr/bin/env python3
"""
Draw a network diagram of the dbt entities + relationships.

Reads (in current dir):
    entities.csv
    relationships.csv

Writes:
    er_network.png   - static diagram (matplotlib)
    er_network.html  - interactive diagram (only if pyvis is installed)

Run after extract_er.py:
    python draw_network.py
"""

import csv
from pathlib import Path

ENTITIES_CSV = "entities.csv"
RELATIONSHIPS_CSV = "relationships.csv"
PNG_OUT = "er_network.png"
HTML_OUT = "er_network.html"

# Visual config
KIND_COLOR = {
    "node": "#4C9AFF",     # models / seeds / snapshots
    "source": "#36B37E",   # source tables
}
EDGE_COLOR = {
    "lineage": "#9AA5B1",
    "foreign_key": "#FF5630",
}


def load_entities():
    entities = {}
    with open(ENTITIES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            entities[row["unique_id"]] = row
    return entities


def load_relationships():
    rels = []
    with open(RELATIONSHIPS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rels.append(row)
    return rels


def short_label(entity_row):
    """Nice short label: name + schema, e.g. fct_orders (core)."""
    name = entity_row.get("name") or entity_row["unique_id"].split(".")[-1]
    schema = entity_row.get("schema")
    return f"{name}\n({schema})" if schema else name


def draw_static(entities, relationships):
    import networkx as nx
    import matplotlib.pyplot as plt

    G = nx.DiGraph()
    for uid, e in entities.items():
        G.add_node(uid, kind=e["kind"], label=short_label(e))

    for r in relationships:
        if r["from"] in entities and r["to"] in entities:
            G.add_edge(r["from"], r["to"], kind=r["kind"])

    if G.number_of_nodes() == 0:
        print("No entities found — nothing to draw.")
        return

    # Layout: try graphviz 'dot' for a clean DAG, fall back to spring layout.
    try:
        pos = nx.nx_agraph.graphviz_layout(G, prog="dot")
    except Exception:
        pos = nx.spring_layout(G, k=1.5, iterations=80, seed=42)

    # Size figure to the graph
    n = G.number_of_nodes()
    side = max(10, min(30, n * 0.6))
    plt.figure(figsize=(side, side * 0.7))

    node_colors = [KIND_COLOR.get(G.nodes[n]["kind"], "#999999") for n in G.nodes]
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=1600,
                           edgecolors="#1f2937", linewidths=1.0)

    # Edges split by kind so each gets its own color
    for kind, color in EDGE_COLOR.items():
        edges = [(u, v) for u, v, d in G.edges(data=True) if d["kind"] == kind]
        if edges:
            nx.draw_networkx_edges(
                G, pos, edgelist=edges, edge_color=color,
                arrows=True, arrowsize=14, width=1.4,
                connectionstyle="arc3,rad=0.05",
            )

    labels = {n: G.nodes[n]["label"] for n in G.nodes}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8)

    # Legend
    from matplotlib.lines import Line2D
    legend = [
        Line2D([0], [0], marker="o", color="w", label="model/seed/snapshot",
               markerfacecolor=KIND_COLOR["node"], markersize=10),
        Line2D([0], [0], marker="o", color="w", label="source",
               markerfacecolor=KIND_COLOR["source"], markersize=10),
        Line2D([0], [0], color=EDGE_COLOR["lineage"], label="lineage (ref/source)"),
        Line2D([0], [0], color=EDGE_COLOR["foreign_key"], label="foreign key"),
    ]
    plt.legend(handles=legend, loc="upper left", bbox_to_anchor=(1.0, 1.0),
               frameon=True)
    plt.title(f"dbt entity-relationship network "
              f"({G.number_of_nodes()} entities, {G.number_of_edges()} edges)")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(PNG_OUT, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Wrote {PNG_OUT}")


def draw_interactive(entities, relationships):
    try:
        from pyvis.network import Network
    except ImportError:
        print("(skipping interactive HTML — install pyvis to enable: pip install pyvis)")
        return

    net = Network(height="800px", width="100%", directed=True,
                  bgcolor="#ffffff", font_color="#111827")
    net.barnes_hut()

    for uid, e in entities.items():
        net.add_node(
            uid,
            label=short_label(e),
            color=KIND_COLOR.get(e["kind"], "#999999"),
            title=f"{uid}\nkind: {e['kind']}\ntype: {e.get('type')}\n"
                  f"columns: {e.get('column_count')}",
            shape="box",
        )

    for r in relationships:
        if r["from"] in entities and r["to"] in entities:
            net.add_edge(
                r["from"], r["to"],
                color=EDGE_COLOR.get(r["kind"], "#888888"),
                title=r["kind"] + (
                    f"  {r['from_column']} -> {r['to_column']}"
                    if r["kind"] == "foreign_key" else ""
                ),
            )

    # write_html avoids pyvis trying to pop a browser window
    net.write_html(HTML_OUT, notebook=False, open_browser=False)
    print(f"Wrote {HTML_OUT}")


def main():
    if not Path(ENTITIES_CSV).exists() or not Path(RELATIONSHIPS_CSV).exists():
        raise SystemExit(
            f"Missing {ENTITIES_CSV} or {RELATIONSHIPS_CSV} — run extract_er.py first."
        )

    entities = load_entities()
    relationships = load_relationships()
    print(f"Loaded {len(entities)} entities, {len(relationships)} relationships")

    draw_static(entities, relationships)
    draw_interactive(entities, relationships)


if __name__ == "__main__":
    main()
