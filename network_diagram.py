"""
Network diagram for entity relationships across 4 levels.
Reads the Sankey CSV and renders a clean hierarchical network graph.
"""

import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import matplotlib.patches as mpatches

# Load data
df = pd.read_csv('/mnt/user-data/outputs/sankey_table_relationships.csv')

# Build directed graph with edge weights aggregated across rows
G = nx.DiGraph()
level_cols = ['level1_table', 'level2_table', 'level3_table', 'level4_table']

# Assign each node to its level (a node may appear at multiple levels;
# we keep the first/earliest level it shows up in for layout purposes)
node_level = {}
for _, row in df.iterrows():
    for lvl, col in enumerate(level_cols, start=1):
        node = row[col]
        if node not in node_level:
            node_level[node] = lvl

# Aggregate edge weights (same edge may appear in many rows)
edge_weights = {}
for _, row in df.iterrows():
    for i in range(len(level_cols) - 1):
        src, tgt = row[level_cols[i]], row[level_cols[i + 1]]
        edge_weights[(src, tgt)] = edge_weights.get((src, tgt), 0) + row['count']

for (src, tgt), w in edge_weights.items():
    G.add_edge(src, tgt, weight=w)

# Group nodes by level for hierarchical layout
levels = {}
for node, lvl in node_level.items():
    levels.setdefault(lvl, []).append(node)

# Compute positions: x = level, y = evenly spread within level
pos = {}
x_gap = 4.0
for lvl, nodes in levels.items():
    nodes_sorted = sorted(nodes)
    n = len(nodes_sorted)
    y_gap = 1.2
    total_height = (n - 1) * y_gap
    for i, node in enumerate(nodes_sorted):
        pos[node] = (lvl * x_gap, total_height / 2 - i * y_gap)

# Color palette per level
level_colors = {
    1: '#2E86AB',  # deep blue
    2: '#A23B72',  # magenta
    3: '#F18F01',  # orange
    4: '#3B8E3F',  # green
}

# Set up figure
fig, ax = plt.subplots(figsize=(18, 12))
ax.set_facecolor('#FAFAFA')

# Draw edges with thickness proportional to weight
max_w = max(edge_weights.values())
min_w = min(edge_weights.values())
for (src, tgt), w in edge_weights.items():
    width = 0.6 + (w - min_w) / (max_w - min_w) * 3.5
    alpha = 0.35 + (w - min_w) / (max_w - min_w) * 0.5
    nx.draw_networkx_edges(
        G, pos,
        edgelist=[(src, tgt)],
        width=width,
        alpha=alpha,
        edge_color='#666666',
        arrows=True,
        arrowsize=15,
        arrowstyle='-|>',
        connectionstyle='arc3,rad=0.08',
        node_size=2800,
        ax=ax,
    )

# Draw nodes as rounded boxes colored by level
for node, (x, y) in pos.items():
    lvl = node_level[node]
    color = level_colors[lvl]
    # Box width scales with label length
    label_len = len(node)
    box_w = max(1.5, label_len * 0.13)
    box_h = 0.55
    box = FancyBboxPatch(
        (x - box_w / 2, y - box_h / 2),
        box_w, box_h,
        boxstyle="round,pad=0.02,rounding_size=0.15",
        linewidth=1.5,
        edgecolor='white',
        facecolor=color,
        zorder=3,
    )
    ax.add_patch(box)
    ax.text(
        x, y, node,
        ha='center', va='center',
        fontsize=10, color='white', fontweight='bold',
        zorder=4,
    )

# Level header labels at the top
y_top = max(y for _, y in pos.values()) + 1.5
level_titles = {
    1: 'Level 1\nRoot Entity',
    2: 'Level 2\nDirect Relation',
    3: 'Level 3\nSub-Relation',
    4: 'Level 4\nLeaf Entity',
}
for lvl in sorted(levels.keys()):
    ax.text(
        lvl * x_gap, y_top, level_titles[lvl],
        ha='center', va='bottom',
        fontsize=12, fontweight='bold',
        color=level_colors[lvl],
    )

# Legend showing edge thickness meaning
legend_patches = [
    mpatches.Patch(color=level_colors[i], label=f'Level {i}') for i in range(1, 5)
]
legend1 = ax.legend(
    handles=legend_patches,
    loc='lower left',
    fontsize=10,
    title='Entity Level',
    title_fontsize=11,
    framealpha=0.95,
)
ax.add_artist(legend1)

# Title and styling
ax.set_title(
    'Entity Relationship Network — 4-Level Schema Flow',
    fontsize=18, fontweight='bold', pad=20, color='#222222',
)
ax.text(
    0.5, -0.04,
    'Edge thickness ∝ relationship count   •   Arrows point from parent to child entity',
    transform=ax.transAxes, ha='center', fontsize=10, color='#666666', style='italic',
)

ax.set_xlim(x_gap - 2, 4 * x_gap + 2)
ax.set_ylim(min(y for _, y in pos.values()) - 1, y_top + 1.5)
ax.axis('off')

plt.tight_layout()
plt.savefig('/mnt/user-data/outputs/entity_network_diagram.png', dpi=200, bbox_inches='tight', facecolor='#FAFAFA')
print("Saved: /mnt/user-data/outputs/entity_network_diagram.png")
print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
