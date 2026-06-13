# ResearchSpace RAG

ResearchSpace uses retrieval-first local RAG. The default path does not require
sentence-transformers, FAISS, or an LLM.

## Search Path

1. Search local `PaperChunk` rows with simple lexical overlap.
2. If optional embeddings are enabled and installed, store local vectors.
3. If FAISS is enabled and installed, a future index may be used.
4. If no LLM provider is configured, return retrieved chunks and a
   `prompt_preview`.

## Fallback Rule

Missing optional libraries must not break the research cockpit. They should
fall back to simple local retrieval or return a clear dependency message.

## Citation Rule

Every answer stores citations with page ranges. The answer remains
retrieval-only until an explicitly configured local or approved provider is
available.
