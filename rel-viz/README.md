# rel-viz

Generate and visualise the BDE relationship spreadsheet.

## Files

- `create_sample_xlsx.py` — writes `relationship.xlsx` mirroring the layout of the source `relationship.xls` (Entity → Model View → Trigger → Time Travel → Dependancy → Dependent Time Travel → Parallel lookup → Reference lookup → Status).
- `visualize_relationships.py` — reads `relationship.xlsx` and emits standalone files (`relationship_graph.svg`, `relationship_graph` DOT source, `relationship_sankey.html`).
- `app.py` — Streamlit app over the same data: upload an xlsx, filter by Entity, view the Graphviz / Sankey / data tabs interactively. Graphviz tab uses `st.graphviz_chart` so it renders without the `dot` binary.

## Setup

```bash
pip install -r requirements.txt
brew install graphviz   # the python package is bindings only — `dot` must be on PATH
```

## Usage

```bash
python create_sample_xlsx.py        # → relationship.xlsx
python visualize_relationships.py   # → relationship_graph.svg, relationship_sankey.html
open relationship_graph.svg relationship_sankey.html

# OR run the interactive app
streamlit run app.py
```

## Flow rendered

```
Entity (A) → Model View (B) → Base Bde trigger (C) → Base BDE Dependancy (E) → Parallel lookup (G)
```

- Columns **D** (Base BDE Time Travel) and **F** (Dependent BDE Time Travel) are labels, not flow steps — skipped.
- Columns **E** and **G** are comma-split.
- `N/A` / empty values produce no outgoing edge.
- When **E** is empty (Transaction-Charge rows), Parallel lookup edges attach to the Trigger (col C) instead so the chain doesn't break.
