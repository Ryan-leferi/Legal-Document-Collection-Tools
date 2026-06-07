# Legal Document Collection Tools

This repository stores the Python scripts used to scan, classify, and reorganize local legal document files.

It does **not** include source documents, copied legal files, extracted document text, CSV reports, move logs, or any confidential work-product content.

## Scripts

- `scripts/legal_doc_classifier.py`  
  Scans local `docx`, `doc`, `hwp`, and `hwpx` files, extracts available text signals, identifies legal documents, and copies matching files into a configured collection directory.

- `scripts/refine_legal_collection_by_use.py`  
  Splits the classified legal collection into study/exam materials and legal practice materials.

- `scripts/move_healthcare_practice_docs.py`  
  Moves healthcare-related legal practice materials into the healthcare practice bucket.

- `scripts/improve_refined_classification.py`  
  Improves the earlier classification using additional heuristics and updates the refined reports.

- `scripts/reclassify_practice_by_workstream.py`  
  Reclassifies only `02_법실무자료` into workstream-oriented folders, including M&A, Healthcare, disputes, corporate/governance, HR, IP/IT/privacy, real estate, regulatory/tax, research, and sample/library materials.

## Original Execution Order

```powershell
$env:LEGAL_DOC_COLLECTION_ROOT = "$HOME\Legal Documents Collection"
$env:LEGAL_DOC_BY_USE_ROOT = "$HOME\Legal Documents Collection\_by_use"

python scripts/legal_doc_classifier.py
python scripts/refine_legal_collection_by_use.py
python scripts/move_healthcare_practice_docs.py
python scripts/improve_refined_classification.py
python scripts/reclassify_practice_by_workstream.py --dry-run
python scripts/reclassify_practice_by_workstream.py
```

## Notes

- The scripts default to `$HOME\Legal Documents Collection`.
- Override paths with `LEGAL_DOC_COLLECTION_ROOT` and `LEGAL_DOC_BY_USE_ROOT`.
- The scripts were written for a one-off local organization task and prioritize conservative file movement plus CSV traceability.
