# Quant4 Graph Lab

Quant4 graph services live in `quant4/services/graphs/` and persist reusable
metadata through the shared `GraphSnapshot` model. They do not create a separate
graph app or duplicate run tables.

Implemented builders:

- `CorrelationGraphBuilder`
- `PartialCorrelationGraphBuilder`
- `MutualInformationGraphBuilder` fallback
- `LeadLagSignatureGraphBuilder`
- `IMFCoherenceGraphBuilder`
- `TDAComplexityGraphBuilder`
- `NewsKnowledgeGraphBuilder` gated by `QUANT4_SOURCEFLOW_KNOWLEDGE_GRAPH`
- `DynamicSparseGraphBuilder` stub
- `HypergraphBuilder`

Graph snapshots store node, edge, and adjacency artifact paths plus config hash,
random seed, data range, split range, feature schema, and provenance. Builders
must use only observations at or before `window_end`.

```bash
python manage.py quant4_build_graphs --series-json "{\"AAA\":[[\"2024-01-01\",1],[\"2024-01-02\",2]],\"BBB\":[[\"2024-01-01\",1],[\"2024-01-02\",3]]}" --window-end 2024-01-02
```

MST, PMFG, TMFG, and random-matrix filters are validation priors. They are not
replacements for learned graphs and must not be presented as factor validity,
causal discovery, or profitability evidence.
