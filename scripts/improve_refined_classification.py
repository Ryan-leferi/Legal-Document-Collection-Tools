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
REPORT = BASE / "_refined_classification_report.csv"
SUMMARY = BASE / "_refined_summary.txt"
IMPROVE_REPORT = BASE / "_classification_improvement_report.csv"
IMPROVE_SUMMARY = BASE / "_classification_improvement_summary.txt"


def norm(value: object) -> str:
    return str(value or "").lower()


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180] or "untitled"


def contains_any(text: str, terms: Iterable[str]) -> List[str]:
    return [term for term in terms if term.lower() in text]


def score_terms(text: str, terms: Iterable[Tuple[str, int]]) -> Tuple[int, List[str]]:
    score = 0
    found: List[str] = []
    for term, weight in terms:
        if term.lower() in text:
            score += weight
            found.append(term)
    return score, found


def split_subgroup(subgroup: str) -> List[str]:
    return [part for part in subgroup.replace("/", "\\").split("\\") if part]


def current_top(subgroup: str) -> str:
    parts = split_subgroup(subgroup)
    return parts[0] if parts else ""


def current_leaf_category(row: Dict[str, str]) -> str:
    category = row.get("category") or "99_기타_법률"
    return safe_name(category)


STRONG_NON_CONTRACT_FILENAME_TERMS = [
    "실사보고서",
    "실사 보고서",
    "ldd report",
    "legal due diligence report",
    "deal report",
    "report",
    "보고서",
    "기업 분석",
    "정관",
    "이사회의사록",
    "주주총회의사록",
    "임시주주총회의사록",
    "위임장",
    "공증위임장",
    "취임승낙서",
    "인감신고서",
    "인감대지",
    "채무확인서",
    "진술서",
    "등기서류",
    "안내 메일",
    "소장",
    "답변서",
    "준비서면",
    "강평",
    "질의사항",
    "인터뷰",
    "체크리스트",
]

MNA_TRUE_CONTEXT_TERMS = [
    "\\2. m&a\\",
    "\\4. archives\\m&a\\",
    "m&a",
    "_ma_",
    "_2.1ma",
    "2.1ma",
    "인수",
    "매각",
    "합병",
    "분할",
    "투자",
    "전환사채",
    "신주",
    "rcps",
    "share purchase",
    "stock purchase",
    "subscription",
    "merger",
    "acquisition",
]

MNA_DEAL_TERMS = [
    "주식매매계약",
    "주식 매매 계약",
    "주식 및 전환사채 매매계약",
    "지분양수도계약",
    "지분 양수도 계약",
    "신주인수계약",
    "신주 인수 계약",
    "전환사채인수계약",
    "전환사채 인수계약",
    "전환사채 인수 계약",
    "사채인수계약",
    "사채 인수 계약",
    "종류주식 투자계약",
    "종류주식 투자 계약",
    "rcps 투자계약",
    "상환전환우선주 투자계약",
    "상환전환우선주 투자 계약",
    "영업양수도계약",
    "영업 양수도계약",
    "영업 양수도 계약",
    "자산양수도계약",
    "자산 양수도 계약",
    "합병계약",
    "합병 계약",
    "분할합병계약",
    "분할 합병 계약",
    "share purchase agreement",
    "stock purchase agreement",
    "subscription agreement",
    "convertible bond subscription",
    "business transfer agreement",
    "business transfer contract",
    "asset purchase agreement",
    "asset transfer agreement",
    "merger agreement",
]

MNA_ANCILLARY_TERMS = [
    "주주간협약",
    "주주간 협약",
    "주주간계약",
    "주주간 계약",
    "shareholders agreement",
    "shareholders' agreement",
    "상계합의서",
    "정산합의서",
    "채권양수도",
]

MOU_TERMS = ["mou", "loi", "term sheet", "텀시트", "양해각서"]


def is_mna_contract(row: Dict[str, str]) -> Tuple[bool, str, List[str]]:
    source_path = norm(row.get("source_path"))
    file_name = norm(Path(row.get("source_path") or row.get("refined_path") or "").name)
    excerpt = norm(row.get("excerpt"))
    text = " ".join([source_path, file_name, excerpt])

    strong_non_contract = contains_any(file_name, STRONG_NON_CONTRACT_FILENAME_TERMS)
    if strong_non_contract:
        return False, "non_contract_filename", strong_non_contract[:8]

    deal_in_name = contains_any(file_name, MNA_DEAL_TERMS)
    if deal_in_name:
        return True, "mna_deal_filename", deal_in_name[:8]

    deal_in_text = contains_any(text, MNA_DEAL_TERMS)
    context = contains_any(text, MNA_TRUE_CONTEXT_TERMS)
    if deal_in_text and context:
        return True, "mna_deal_text_with_context", (deal_in_text + context)[:8]

    ancillary = contains_any(file_name, MNA_ANCILLARY_TERMS)
    if ancillary and (context or contains_any(text, ["투자", "인수", "매각", "신주", "전환사채", "rcps"])):
        return True, "mna_ancillary_filename_with_context", (ancillary + context)[:8]

    mou = contains_any(file_name, MOU_TERMS)
    if mou and contains_any(text, ["m&a", "인수", "매각", "합병", "투자", "acquisition", "merger"]):
        return True, "mna_mou_with_deal_context", (mou + context)[:8]

    return False, "not_mna_contract", (deal_in_text + ancillary + context)[:8]


def mna_subgroup(row: Dict[str, str]) -> str:
    text = " ".join([norm(row.get("source_path")), norm(row.get("excerpt"))])
    if contains_any(text, ["주식매매", "share purchase", "stock purchase"]):
        return r"01_M&A_계약\01_주식매매_SPA"
    if contains_any(text, ["신주인수", "전환사채", "사채인수", "rcps", "상환전환우선주", "subscription"]):
        return r"01_M&A_계약\02_신주_RCPS_CB_투자"
    if contains_any(text, ["합병", "분할", "merger"]):
        return r"01_M&A_계약\03_합병_분할"
    if contains_any(text, ["영업양수도", "자산양수도", "지분양수도", "business transfer", "asset purchase", "asset transfer"]):
        return r"01_M&A_계약\04_영업_자산_지분양수도"
    if contains_any(text, MOU_TERMS):
        return r"01_M&A_계약\05_MOU_텀시트_LOI"
    return r"01_M&A_계약\99_M&A_기타계약"


HEALTHCARE_PATH_TERMS = [
    (r"\1. projects\1. healthcare\\", 35),
    (r"\4. archives\healthcare\\", 30),
    ("healthcare", 25),
    ("health care", 25),
    ("헬스케어", 25),
    ("medical writing", 18),
    ("professional medical", 18),
    ("medical", 10),
    ("clinical", 10),
    ("hospital", 10),
    ("pharma", 10),
    ("pharmaceutical", 10),
    ("fertility", 10),
    ("의료기기", 18),
    ("디지털의료", 18),
    ("임상시험", 16),
    ("식약처", 16),
    ("보건복지", 16),
    ("건강보험", 16),
    ("요양급여", 14),
    ("비급여", 14),
    ("의료", 8),
    ("병원", 8),
    ("제약", 8),
    ("의약", 8),
    ("바이오", 8),
    ("환자", 7),
    ("진단", 7),
    ("치료", 7),
    ("간호", 7),
    ("nurses", 7),
]

HEALTHCARE_CONTENT_TERMS = [
    ("healthcare", 10),
    ("health care", 10),
    ("medical device", 10),
    ("clinical trial", 10),
    ("hospital", 8),
    ("patient", 8),
    ("pharmaceutical", 8),
    ("의료기기", 12),
    ("디지털의료", 12),
    ("임상시험", 12),
    ("식약처", 12),
    ("보건복지", 12),
    ("건강보험", 12),
    ("요양급여", 10),
    ("비급여", 10),
    ("병원", 7),
    ("제약", 7),
    ("의약", 7),
    ("바이오", 7),
    ("환자", 6),
    ("진단", 6),
    ("치료", 6),
    ("간호", 6),
    ("의료", 5),
]


def is_healthcare(row: Dict[str, str]) -> Tuple[bool, int, List[str]]:
    source_path = norm(row.get("source_path"))
    refined_path = norm(row.get("refined_path"))
    excerpt = norm(row.get("excerpt"))
    matched = norm(row.get("matched_terms"))
    path_score, path_found = score_terms(" ".join([source_path, refined_path]), HEALTHCARE_PATH_TERMS)
    content_score, content_found = score_terms(" ".join([excerpt, matched]), HEALTHCARE_CONTENT_TERMS)
    score = path_score + content_score
    found = path_found + content_found
    strong = any(
        term in found
        for term in [
            r"\1. projects\1. healthcare\\",
            r"\4. archives\healthcare\\",
            "healthcare",
            "health care",
            "헬스케어",
            "medical writing",
            "professional medical",
            "의료기기",
            "디지털의료",
            "임상시험",
            "식약처",
            "보건복지",
            "건강보험",
        ]
    )
    return (strong and score >= 10) or score >= 18, score, found


def target_subgroup(row: Dict[str, str]) -> Tuple[str, str, List[str]]:
    healthcare, healthcare_score, healthcare_terms = is_healthcare(row)
    mna, mna_reason, mna_terms = is_mna_contract(row)

    if mna:
        subgroup = mna_subgroup(row)
        if healthcare:
            subgroup = "03_Healthcare\\" + subgroup
        reason = (
            f"improved_mna={mna_reason}; mna_terms={', '.join(mna_terms[:10])}; "
            f"healthcare={healthcare_score}; healthcare_terms={', '.join(healthcare_terms[:10])}"
        )
        return subgroup, reason, healthcare_terms + mna_terms

    leaf = current_leaf_category(row)
    if healthcare:
        subgroup = rf"03_Healthcare\02_기타_법실무\{leaf}"
        reason = f"improved_healthcare_non_mna; healthcare={healthcare_score}; healthcare_terms={', '.join(healthcare_terms[:10])}"
        return subgroup, reason, healthcare_terms

    subgroup = rf"02_기타_법실무\{leaf}"
    reason = f"improved_non_healthcare_non_mna; mna={mna_reason}; mna_terms={', '.join(mna_terms[:10])}"
    return subgroup, reason, mna_terms


def unique_target(folder: Path, old_path: Path, source_key: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / f"{safe_name(old_path.stem)}{old_path.suffix}"
    if not candidate.exists():
        return candidate
    digest = hashlib.sha1(source_key.encode("utf-8", errors="ignore")).hexdigest()[:10]
    candidate = folder / f"{safe_name(old_path.stem)}__{digest}{old_path.suffix}"
    index = 2
    while candidate.exists():
        candidate = folder / f"{safe_name(old_path.stem)}__{digest}_{index}{old_path.suffix}"
        index += 1
    return candidate


def subgroup_to_folder(subgroup: str) -> Path:
    return PRACTICE / Path(*split_subgroup(subgroup))


def read_rows() -> Tuple[List[Dict[str, str]], List[str]]:
    with REPORT.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader), list(reader.fieldnames or [])


def write_rows(path: Path, rows: List[Dict[str, str]], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def remove_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for dirpath, _, _ in os.walk(root, topdown=False):
        path = Path(dirpath)
        if path == root or path == PRACTICE:
            continue
        try:
            if not any(path.iterdir()):
                path.rmdir()
        except OSError:
            pass


def rebuild_summary(rows: List[Dict[str, str]], moved_count: int, missing_count: int) -> None:
    group_counts: Dict[str, int] = {}
    subgroup_counts: Dict[str, int] = {}
    for row in rows:
        group = row.get("refined_group") or ""
        subgroup = row.get("refined_subgroup") or ""
        group_counts[group] = group_counts.get(group, 0) + 1
        subgroup_counts[subgroup] = subgroup_counts.get(subgroup, 0) + 1

    practice_total = group_counts.get("02_법실무자료", 0)
    study_total = group_counts.get("01_학습_수험자료", 0)
    mna_total = sum(count for subgroup, count in subgroup_counts.items() if subgroup.startswith("01_M&A_계약"))
    healthcare_total = sum(count for subgroup, count in subgroup_counts.items() if subgroup.startswith("03_Healthcare"))
    healthcare_mna = sum(count for subgroup, count in subgroup_counts.items() if subgroup.startswith(r"03_Healthcare\01_M&A_계약"))
    other_practice = practice_total - mna_total - healthcare_total

    lines = [
        "Refined legal document classification summary",
        f"Updated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Output folder: {BASE}",
        f"Total legal documents processed: {len(rows)}",
        f"Study/exam materials: {study_total}",
        f"Legal practice materials: {practice_total}",
        f"- M&A contracts: {mna_total}",
        f"- Healthcare legal practice: {healthcare_total}",
        f"  - Healthcare M&A contracts: {healthcare_mna}",
        f"- Other legal practice: {other_practice}",
        f"Files moved in latest improvement: {moved_count}",
        f"Missing files in latest improvement: {missing_count}",
        "",
        "Folder counts:",
    ]
    for subgroup in sorted(subgroup_counts):
        lines.append(f"- {subgroup}: {subgroup_counts[subgroup]}")
    lines.extend(
        [
            "",
            "Notes:",
            "- M&A contract rules were tightened to require actual deal-contract terms, not generic matter-number or agreement signals.",
            "- Healthcare rules were expanded for medical writing, hospital, clinical, and pharma signals.",
            "- _classification_improvement_report.csv records every file moved by this improvement pass.",
        ]
    )
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    rows, fields = read_rows()
    improvement_fields = fields + [
        "old_refined_subgroup",
        "old_refined_path",
        "new_refined_subgroup",
        "new_refined_path",
        "improvement_reason",
        "move_status",
    ]
    changes: List[Dict[str, str]] = []
    moved = 0
    missing = 0

    for row in rows:
        if row.get("refined_group") != "02_법실무자료":
            continue
        old_subgroup = row.get("refined_subgroup") or ""
        old_path_text = row.get("refined_path") or ""
        new_subgroup, reason, _ = target_subgroup(row)
        if new_subgroup == old_subgroup:
            continue

        change = dict(row)
        change["old_refined_subgroup"] = old_subgroup
        change["old_refined_path"] = old_path_text
        change["new_refined_subgroup"] = new_subgroup
        change["improvement_reason"] = reason

        old_path = Path(old_path_text)
        if old_path.exists():
            target = unique_target(subgroup_to_folder(new_subgroup), old_path, row.get("source_path") or old_path_text)
            shutil.move(str(old_path), str(target))
            row["refined_subgroup"] = new_subgroup
            row["refined_path"] = str(target)
            row["classification_reason"] = ((row.get("classification_reason") or "") + "; " + reason).strip("; ")
            change["new_refined_path"] = str(target)
            change["move_status"] = "moved"
            moved += 1
        else:
            change["new_refined_path"] = ""
            change["move_status"] = "missing_current_refined_path"
            missing += 1
        changes.append(change)

    write_rows(REPORT, rows, fields)
    write_rows(IMPROVE_REPORT, changes, improvement_fields)
    rebuild_summary(rows, moved, missing)
    remove_empty_dirs(PRACTICE)

    top_counts: Dict[str, int] = {}
    for row in rows:
        if row.get("refined_group") == "02_법실무자료":
            top_counts[current_top(row.get("refined_subgroup") or "")] = top_counts.get(current_top(row.get("refined_subgroup") or ""), 0) + 1

    lines = [
        "Classification improvement summary",
        f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Moved files: {moved}",
        f"Missing current refined paths: {missing}",
        "",
        "Legal practice top-level counts after improvement:",
    ]
    for key in sorted(top_counts):
        lines.append(f"- {key}: {top_counts[key]}")
    lines.append("")
    lines.append(f"Improvement report: {IMPROVE_REPORT}")
    IMPROVE_SUMMARY.write_text("\n".join(lines), encoding="utf-8")

    print(f"[done] moved={moved} missing={missing}")
    for key in sorted(top_counts):
        print(f"[top] {key}={top_counts[key]}")
    print(f"[report] {IMPROVE_REPORT}")
    print(f"[summary] {IMPROVE_SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
