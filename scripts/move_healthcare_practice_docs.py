from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


BASE = Path(os.environ.get("LEGAL_DOC_BY_USE_ROOT", str(Path.home() / "Legal Documents Collection" / "_by_use")))
PRACTICE = BASE / "02_법실무자료"
HEALTHCARE = PRACTICE / "03_Healthcare"
REPORT = BASE / "_refined_classification_report.csv"
MOVE_REPORT = BASE / "_healthcare_move_report.csv"
HEALTHCARE_SUMMARY = BASE / "_healthcare_summary.txt"
REFINED_SUMMARY = BASE / "_refined_summary.txt"


def norm(value: object) -> str:
    return str(value or "").lower()


def contains(text: str, term: str) -> bool:
    return term.lower() in text


def score_terms(text: str, terms: Iterable[Tuple[str, int]]) -> Tuple[int, List[str]]:
    score = 0
    found: List[str] = []
    for term, weight in terms:
        if contains(text, term):
            score += weight
            found.append(term)
    return score, found


def healthcare_score(row: Dict[str, str]) -> Tuple[int, List[str]]:
    source_path = norm(row.get("source_path"))
    refined_path = norm(row.get("refined_path"))
    path_text = " ".join([source_path, refined_path])
    content_text = " ".join(
        norm(row.get(field))
        for field in ["excerpt", "matched_terms", "category", "classification_reason"]
    )

    path_terms = [
        ("\\1. projects\\1. healthcare\\", 30),
        ("\\4. archives\\healthcare\\", 26),
        ("healthcare", 20),
        ("health care", 20),
        ("헬스케어", 20),
        ("medical", 12),
        ("pharma", 12),
        ("pharmaceutical", 12),
        ("clinical", 12),
        ("hospital", 12),
        ("fertility", 12),
        ("의료기기", 18),
        ("디지털의료", 18),
        ("의료", 10),
        ("병원", 10),
        ("제약", 10),
        ("의약", 10),
        ("바이오", 10),
        ("임상시험", 14),
        ("임상", 8),
        ("요양급여", 12),
        ("비급여", 12),
        ("식약처", 12),
        ("mfds", 12),
        ("보건복지", 12),
        ("건강보험", 12),
        ("환자", 8),
        ("진단", 8),
        ("치료", 8),
        ("혈당", 8),
        ("당뇨", 8),
        ("간호", 8),
        ("nurses", 8),
    ]
    content_terms = [
        ("healthcare", 8),
        ("health care", 8),
        ("헬스케어", 8),
        ("medical device", 8),
        ("clinical trial", 8),
        ("hospital", 8),
        ("patient", 8),
        ("pharmaceutical", 8),
        ("의료기기", 10),
        ("디지털의료", 10),
        ("임상시험", 10),
        ("요양급여", 10),
        ("비급여", 10),
        ("식약처", 10),
        ("보건복지", 10),
        ("건강보험", 10),
        ("병원", 7),
        ("제약", 7),
        ("의약", 7),
        ("바이오", 7),
        ("환자", 6),
        ("진단", 6),
        ("치료", 6),
        ("혈당", 6),
        ("당뇨", 6),
        ("간호", 6),
        ("의료", 5),
    ]
    path_score, path_found = score_terms(path_text, path_terms)
    content_score, content_found = score_terms(content_text, content_terms)
    return path_score + content_score, path_found + content_found


def is_healthcare(row: Dict[str, str]) -> Tuple[bool, int, List[str]]:
    score, found = healthcare_score(row)
    # A strong folder or domain signal is enough. Otherwise require multiple content
    # signals so generic legal documents mentioning one medical word are not moved.
    strong = any(
        term in found
        for term in [
            "\\1. projects\\1. healthcare\\",
            "\\4. archives\\healthcare\\",
            "healthcare",
            "health care",
            "헬스케어",
            "의료기기",
            "임상시험",
            "식약처",
            "보건복지",
            "건강보험",
        ]
    )
    return (strong and score >= 10) or score >= 16, score, found


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180] or "untitled"


def unique_destination(folder: Path, source: Path, source_key: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / f"{safe_name(source.stem)}{source.suffix}"
    if not candidate.exists():
        return candidate
    digest = hashlib.sha1(source_key.encode("utf-8", errors="ignore")).hexdigest()[:10]
    candidate = folder / f"{safe_name(source.stem)}__{digest}{source.suffix}"
    index = 2
    while candidate.exists():
        candidate = folder / f"{safe_name(source.stem)}__{digest}_{index}{source.suffix}"
        index += 1
    return candidate


def read_rows() -> List[Dict[str, str]]:
    with REPORT.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path: Path, rows: List[Dict[str, str]], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def practice_relative_subgroup(row: Dict[str, str]) -> Path:
    subgroup = row.get("refined_subgroup") or "99_기타"
    subgroup = subgroup.replace("/", "\\")
    if subgroup.startswith("03_Healthcare\\"):
        subgroup = subgroup[len("03_Healthcare\\") :]
    return Path(*[safe_name(part) for part in subgroup.split("\\") if part])


def remove_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        path = Path(dirpath)
        if path == root or path == HEALTHCARE:
            continue
        try:
            if not any(path.iterdir()):
                path.rmdir()
        except OSError:
            pass


def rebuild_refined_summary(rows: List[Dict[str, str]], moved_count: int) -> None:
    group_counts: Dict[str, int] = {}
    subgroup_counts: Dict[str, int] = {}
    for row in rows:
        group = row.get("refined_group") or ""
        subgroup = row.get("refined_subgroup") or ""
        group_counts[group] = group_counts.get(group, 0) + 1
        subgroup_counts[subgroup] = subgroup_counts.get(subgroup, 0) + 1

    study_total = group_counts.get("01_학습_수험자료", 0)
    practice_total = group_counts.get("02_법실무자료", 0)
    healthcare_total = sum(
        count for subgroup, count in subgroup_counts.items() if subgroup.startswith("03_Healthcare")
    )
    mna_total = sum(
        count for subgroup, count in subgroup_counts.items() if subgroup.startswith("01_M&A_계약")
    )
    other_practice_total = practice_total - healthcare_total - mna_total

    lines = [
        "Refined legal document classification summary",
        f"Updated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Source report: {REPORT}",
        f"Output folder: {BASE}",
        f"Total legal documents processed: {len(rows)}",
        f"Study/exam materials: {study_total}",
        f"Legal practice materials: {practice_total}",
        f"- M&A contracts: {mna_total}",
        f"- Healthcare legal practice: {healthcare_total}",
        f"- Other legal practice: {other_practice_total}",
        f"Healthcare files moved in latest run: {moved_count}",
        "",
        "Folder counts:",
    ]
    for subgroup in sorted(subgroup_counts):
        lines.append(f"- {subgroup}: {subgroup_counts[subgroup]}")
    lines.extend(
        [
            "",
            "Notes:",
            "- Existing study/exam folders were preserved.",
            "- Healthcare legal practice files were moved under 02_법실무자료\\03_Healthcare while preserving their prior subcategory below that folder.",
            "- _healthcare_move_report.csv records every file moved and the matched healthcare signals.",
        ]
    )
    REFINED_SUMMARY.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    rows = read_rows()
    fields = list(rows[0].keys()) if rows else []
    move_fields = fields + [
        "old_refined_subgroup",
        "old_refined_path",
        "new_refined_subgroup",
        "new_refined_path",
        "healthcare_score",
        "healthcare_terms",
        "move_status",
    ]
    moved_rows: List[Dict[str, str]] = []
    skipped_missing: List[Dict[str, str]] = []

    HEALTHCARE.mkdir(parents=True, exist_ok=True)

    for index, row in enumerate(rows, start=1):
        if row.get("refined_group") != "02_법실무자료":
            continue
        old_path_text = row.get("refined_path") or ""
        if not old_path_text:
            continue
        old_path = Path(old_path_text)
        if old_path_text.lower().startswith(str(HEALTHCARE).lower()):
            continue
        healthcare, score, terms = is_healthcare(row)
        if not healthcare:
            continue

        old_subgroup = row.get("refined_subgroup") or ""
        new_subgroup = str(Path("03_Healthcare") / practice_relative_subgroup(row))
        target_folder = PRACTICE / new_subgroup
        target = unique_destination(target_folder, old_path, row.get("source_path") or old_path_text)

        move_row = dict(row)
        move_row["old_refined_subgroup"] = old_subgroup
        move_row["old_refined_path"] = old_path_text
        move_row["new_refined_subgroup"] = new_subgroup
        move_row["new_refined_path"] = str(target)
        move_row["healthcare_score"] = str(score)
        move_row["healthcare_terms"] = "; ".join(terms[:40])

        if old_path.exists():
            shutil.move(str(old_path), str(target))
            row["refined_subgroup"] = new_subgroup
            row["refined_path"] = str(target)
            row["classification_reason"] = (
                (row.get("classification_reason") or "")
                + f"; healthcare_move_score={score}; healthcare_terms={', '.join(terms[:12])}"
            ).strip("; ")
            move_row["move_status"] = "moved"
            moved_rows.append(move_row)
        else:
            move_row["move_status"] = "missing_source"
            skipped_missing.append(move_row)

        if index % 500 == 0:
            print(f"[progress] scanned_rows={index} moved={len(moved_rows)} missing={len(skipped_missing)}")

    write_rows(REPORT, rows, fields)
    write_rows(MOVE_REPORT, moved_rows + skipped_missing, move_fields)
    rebuild_refined_summary(rows, len(moved_rows))
    remove_empty_dirs(PRACTICE / "01_M&A_계약")
    remove_empty_dirs(PRACTICE / "02_기타_법실무")

    top_counts: Dict[str, int] = {}
    for row in rows:
        if row.get("refined_group") != "02_법실무자료":
            continue
        subgroup = row.get("refined_subgroup") or ""
        top = subgroup.split("\\", 1)[0]
        top_counts[top] = top_counts.get(top, 0) + 1

    summary = [
        "Healthcare legal practice move summary",
        f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Moved files: {len(moved_rows)}",
        f"Missing source files: {len(skipped_missing)}",
        f"Healthcare destination: {HEALTHCARE}",
        "",
        "Legal practice top-level counts after move:",
    ]
    for key in sorted(top_counts):
        summary.append(f"- {key}: {top_counts[key]}")
    summary.append("")
    summary.append(f"Move report: {MOVE_REPORT}")
    HEALTHCARE_SUMMARY.write_text("\n".join(summary), encoding="utf-8")

    print(
        f"[done] moved={len(moved_rows)} missing={len(skipped_missing)} "
        f"healthcare_count={top_counts.get('03_Healthcare', 0)}"
    )
    print(f"[report] {MOVE_REPORT}")
    print(f"[summary] {HEALTHCARE_SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
