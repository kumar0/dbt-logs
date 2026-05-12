#!/usr/bin/env python3
"""
Build a MODEL-LEVEL relationship diagram from dbt's manifest.json.

One node per dbt model (e.g. `account_transform`), edges = ref() dependencies.
Sources are included as separate nodes (so you can see what feeds the graph).
Views, dev variants, and physical-table noise are ignored — this works at the
dbt model level, not the warehouse table level.

Run from the directory that contains manifest.json:
    python model_graph.py

Outputs:
    models.csv         - one row per model/source
    model_edges.csv    - one row per ref() / source() edge
    model_graph.png    - static diagram
    model_graph.html   - interactive diagram (requires pyvis)
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

MANIFEST_PATH = "manifest.json"

MODELS_CSV = "models.csv"
EDGES_CSV = "model_edges.csv"
PNG_OUT = "model_graph.png"
HTML_OUT = "model_graph.html"

# Optional filter — set to a package name (e.g. "avqdf") to include only
# models from that package. Leave as None to include all.
PACKAGE_FILTER = None

# Whether to show source nodes (raw inputs) in addition to models
INCLUDE_SOURCES = True


def load_manifest():
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def extract(manifest):
    """Pull just model + source nodes and the ref/source edges between them."""
    nodes = manifest.get("nodes", {})
    sources = manifest.get("sources", {})

    kept = {}   # unique_id -> {name, kind, schema, package}
    edges = []  # (from_uid, to_uid)

    for uid, n in nodes.items():
        if n.get("resource_type") not in ("model", "seed", "snapshot"):
            continue
        if PACKAGE_FILTER and n.get("package_name") != PACKAGE_FILTER:
            continue
        kept[uid] = {
            "unique_id": uid,
            "name": n.get("name"),
            "kind": n.get("resource_type"),
            "schema": n.get("schema"),
            "package": n.get("package_name"),
        }

    if INCLUDE_SOURCES:
        for uid, s in sources.items():
            if PACKAGE_FILTER and s.get("package_name") != PACKAGE_FILTER:
                continue
            kept[uid] = {
                "unique_id": uid,
                "name": s.get("name"),
                "kind": "source",
                "schema": s.get("schema"),
                "package": s.get("package_name"),
            }

    # Edges: each kept model's depends_on.nodes -> kept model
    for uid, n in nodes.items():
        if uid not in kept:
            continue
        for upstream in n.get("depends_on", {}).get("nodes", []):
            if upstream in kept:
                edges.append((upstream, uid))

    # Deduplicate
    edges = sorted(set(edges))
    return kept, edges


def write_csvs(models, edges):
    with open(MODELS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["unique_id", "name", "kind", "schema", "package"])
        for m in models.values():
            w.writerow([m["unique_id"], m["name"], m["kind"],
                        m["schema"], m["package"]])

    with open(EDGES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["from_unique_id", "from_name", "to_unique_id", "to_name"])
        for a, b in edges:
            w.writerow([a, models[a]["name"], b, models[b]["name"]])


KIND_COLOR = {
    "model": "#4C9AFF",
    "seed": "#FFAB00",
    "snapshot": "#6554C0",
    "source": "#36B37E",
}


def draw_static(models, edges):
    import networkx as nx
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    G = nx.DiGraph()
    for uid, m in models.items():
        G.add_node(uid, **m)
    for a, b in edges:
        G.add_edge(a, b)

    if G.number_of_nodes() == 0:
        print("Nothing to draw.")
        return

    # Try graphviz dot for a top-down DAG, else fall back
    try:
        pos = nx.nx_agraph.graphviz_layout(G, prog="dot")
    except Exception:
        try:
            pos = nx.nx_pydot.graphviz_layout(G, prog="dot")
        except Exception:
            pos = nx.spring_layout(G, k=2.0, iterations=120, seed=42)

    n = G.number_of_nodes()
    side = max(12, min(40, n * 0.5))
    plt.figure(figsize=(side, side * 0.7))

    colors = [KIND_COLOR.get(G.nodes[x]["kind"], "#999999") for x in G.nodes]
    nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=1400,
                           edgecolors="#1f2937", linewidths=0.8)
    nx.draw_networkx_edges(G, pos, edge_color="#9AA5B1", arrows=True,
                           arrowsize=12, width=1.0,
                           connectionstyle="arc3,rad=0.05")
    labels = {x: G.nodes[x]["name"] for x in G.nodes}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8)

    legend_kinds = sorted({G.nodes[x]["kind"] for x in G.nodes})
    legend = [Line2D([0], [0], marker="o", color="w", label=k,
                     markerfacecolor=KIND_COLOR.get(k, "#999"), markersize=10)
              for k in legend_kinds]
    plt.legend(handles=legend, loc="upper left", bbox_to_anchor=(1.0, 1.0),
               frameon=True)
    plt.title(f"dbt model graph ({G.number_of_nodes()} nodes, "
              f"{G.number_of_edges()} edges)")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(PNG_OUT, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Wrote {PNG_OUT}")


def draw_interactive(models, edges):
    try:
        from pyvis.network import Network
    except ImportError:
        print("(skipping HTML — install pyvis to enable: pip install pyvis)")
        return

    net = Network(height="850px", width="100%", directed=True,
                  bgcolor="#ffffff", font_color="#111827")
    net.barnes_hut(spring_length=180)

    for uid, m in models.items():
        net.add_node(
            uid,
            label=m["name"],
            color=KIND_COLOR.get(m["kind"], "#999999"),
            title=f"{m['name']}\nkind: {m['kind']}\nschema: {m['schema']}\n"
                  f"package: {m['package']}",
            shape="box",
        )
    for a, b in edges:
        net.add_edge(a, b, color="#9AA5B1")

    net.write_html(HTML_OUT, notebook=False, open_browser=False)
    print(f"Wrote {HTML_OUT}")


def summary(models, edges):
    by_kind = defaultdict(int)
    for m in models.values():
        by_kind[m["kind"]] += 1
    parts = ", ".join(f"{v} {k}s" for k, v in sorted(by_kind.items()))
    print(f"\n{len(models)} nodes ({parts}), {len(edges)} edges")

    # Top hubs by combined degree — useful for "what are the central tables?"
    deg = defaultdict(int)
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1
    top = sorted(deg.items(), key=lambda x: -x[1])[:10]
    if top:
        print("\nTop 10 most connected models:")
        for uid, d in top:
            print(f"  {d:>3}  {models[uid]['name']}")


def main():
    if not Path(MANIFEST_PATH).exists():
        raise SystemExit(f"Could not find {MANIFEST_PATH} in {Path.cwd()}")

    manifest = load_manifest()
    models, edges = extract(manifest)
    write_csvs(models, edges)
    print(f"Wrote {MODELS_CSV}, {EDGES_CSV}")
    summary(models, edges)
    draw_static(models, edges)
    draw_interactive(models, edges)


if __name__ == "__main__":
    main()
