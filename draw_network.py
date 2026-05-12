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
from collections import defaultdict
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


# If True: drop everything that isn't a BASE TABLE or a source.
# Edges through dropped (view) nodes are rewired so the graph stays connected.
TABLES_ONLY = True


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


def is_kept(entity):
    """Keep sources always; for everything else, only BASE TABLE."""
    if entity["kind"] == "source":
        return True
    etype = (entity.get("type") or "").upper()
    return etype == "BASE TABLE"


def filter_to_tables(entities, relationships):
    """Drop view-like entities and rewire edges around them.

    If A -> V -> B and V is dropped, we produce A -> B. Repeats until no
    edges touch a dropped node. Self-loops and duplicates are removed.
    """
    if not TABLES_ONLY:
        return entities, relationships

    kept = {uid: e for uid, e in entities.items() if is_kept(e)}
    dropped = set(entities) - set(kept)

    # Build adjacency just for lineage rewiring. FK edges stay as-is but
    # are filtered to kept-only endpoints.
    out_edges = defaultdict(list)   # parent -> [children]
    in_edges = defaultdict(list)    # child  -> [parents]
    fk_edges = []
    for r in relationships:
        if r["kind"] == "foreign_key":
            fk_edges.append(r)
            continue
        out_edges[r["from"]].append(r["to"])
        in_edges[r["to"]].append(r["from"])

    def reachable_kept_descendants(start):
        """Walk through dropped nodes until we land on kept nodes."""
        seen, stack, result = set(), list(out_edges.get(start, [])), set()
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            if n in kept:
                result.add(n)
            else:
                stack.extend(out_edges.get(n, []))
        return result

    new_lineage = set()
    for parent in kept:
        for desc in reachable_kept_descendants(parent):
            if desc != parent:
                new_lineage.add((parent, desc))

    # Also handle the case where a dropped node is the root (e.g. a source
    # feeding only views which then feed tables) -- the loop above already
    # walks from each kept parent, and sources are kept, so this is covered.

    relationships_out = [
        {"kind": "lineage", "from": p, "to": c,
         "from_column": "", "to_column": ""}
        for (p, c) in sorted(new_lineage)
    ]

    # Keep FK edges only if both endpoints survived
    for r in fk_edges:
        if r["from"] in kept and r["to"] in kept:
            relationships_out.append(r)

    print(f"Filter: kept {len(kept)}/{len(entities)} entities "
          f"(dropped {len(dropped)} views), "
          f"{len(relationships_out)} edges after rewiring")
    return kept, relationships_out


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

    entities, relationships = filter_to_tables(entities, relationships)

    draw_static(entities, relationships)
    draw_interactive(entities, relationships)


if __name__ == "__main__":
    main()
