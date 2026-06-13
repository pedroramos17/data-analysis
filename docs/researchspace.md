# ResearchSpace

ResearchSpace is the local-first research cockpit for papers. It stores PDF
metadata in SQLite, keeps heavy derived artifacts in local files, and avoids any
paid API requirement.

## Boundaries

- Runs locally on CPU.
- Uploads and deduplicates PDFs by SHA-256.
- Uses PyMuPDF only when installed and enabled.
- Falls back to simple local vector search when embedding or FAISS libraries are
  missing.
- Returns retrieved chunks plus `prompt_preview` when no LLM provider exists.
- Stores support status on extracted and generated items.
- Factor candidates default to `NEEDS_BACKTEST`.

## URLs

- `/researchspace/papers/`
- `/researchspace/papers/upload/`
- `/researchspace/papers/<id>/`
- `/researchspace/papers/<id>/ask/`
- `/researchspace/papers/<id>/extract/`
- `/researchspace/factor-lab/`

## Commands

```bash
python manage.py ingest_paper_pdf --path paper.pdf --title "Paper"
python manage.py build_paper_index --paper-id 1
python manage.py ask_paper --paper-id 1 --question "What validation is used?"
python manage.py extract_quant_methodology --paper-id 1
python manage.py generate_factor_candidates --extraction-id 1
python manage.py export_researchspace_parquet --paper-id 1
```
