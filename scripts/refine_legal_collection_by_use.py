from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


DESTINATION = Path(os.environ.get("LEGAL_DOC_COLLECTION_ROOT", str(Path.home() / "Legal Documents Collection")))
REPORT = DESTINATION / "_legal_documents_report.csv"
OUTPUT = DESTINATION / "_by_use"

STUDY_ROOT = "01_학습_수험자료"
PRACTICE_ROOT = "02_법실무자료"
MNA_ROOT = "01_M&A_계약"
PRACTICE_OTHER_ROOT = "02_기타_법실무"

CSV_FIELDS_EXTRA = [
    "refined_group",
    "refined_subgroup",
    "refined_path",
    "classification_reason",
    "link_method",
]


def norm(value: object) -> str:
    return str(value or "").lower()


def contains_any(text: str, terms: Iterable[str]) -> List[str]:
    return [term for term in terms if term.lower() in text]


def regex_any(text: str, patterns: Iterable[str]) -> List[str]:
    found: List[str] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(pattern)
    return found


def score_terms(text: str, weighted_terms: Iterable[Tuple[str, int]]) -> Tuple[int, List[str]]:
    score = 0
    found: List[str] = []
    for term, weight in weighted_terms:
        if term.lower() in text:
            score += weight
            found.append(term)
    return score, found


def signal_text(row: Dict[str, str]) -> str:
    return " ".join(
        norm(row.get(field))
        for field in [
            "source_path",
            "destination_path",
            "category",
            "matched_terms",
            "excerpt",
        ]
    )


def study_score(row: Dict[str, str]) -> Tuple[int, List[str]]:
    text = signal_text(row)
    terms = [
        ("\\법학\\", 10),
        ("법학 교재", 10),
        ("법학전문대학원", 10),
        ("로스쿨", 10),
        ("대학교 학업", 10),
        ("oneDrive - 고려대학교".lower(), 6),
        ("고려대학교", 4),
        ("변호사시험", 12),
        ("변시", 10),
        ("법전협", 10),
        ("모의고사", 10),
        ("모의시험", 10),
        ("기출", 8),
        ("선택형", 8),
        ("사례형", 8),
        ("기록형", 8),
        ("답안", 6),
        ("해설", 5),
        ("강평", 7),
        ("강의", 6),
        ("수업", 6),
        ("필기", 6),
        ("교재", 6),
        ("스터디", 6),
        ("튜터링", 6),
        ("중간시험", 6),
        ("기말시험", 6),
        ("기말고사", 6),
        ("과제답안", 6),
        ("강의계획서", 6),
        ("공부방법", 6),
        ("시험용", 5),
        ("신입변호사 ot", 4),
        ("associate seminar", 4),
    ]
    score, found = score_terms(text, terms)
    path = norm(row.get("source_path"))
    if "\\1. projects\\" in path:
        score -= 5
    if "\\downloads\\" in path and not contains_any(text, ["변시", "변호사시험", "법전협", "시험", "강의", "수업", "기출"]):
        score -= 3
    return score, found


def practice_score(row: Dict[str, str]) -> Tuple[int, List[str]]:
    text = signal_text(row)
    terms = [
        ("\\1. projects\\", 12),
        ("litigation", 8),
        ("실사", 8),
        ("ldd", 8),
        ("legal due diligence", 8),
        ("의견서", 7),
        ("memo", 5),
        ("메모", 5),
        ("검토", 6),
        ("자문", 6),
        ("계약서", 7),
        ("agreement", 6),
        ("contract", 5),
        ("소장", 7),
        ("준비서면", 7),
        ("답변서", 7),
        ("내용증명", 6),
        ("위임장", 4),
        ("등기", 4),
        ("인허가", 4),
        ("project", 4),
        ("pjt", 4),
    ]
    return score_terms(text, terms)


SPECIFIC_MNA_CONTRACT_TERMS = [
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
    "투자계약서",
    "투자 계약서",
    "영업양수도계약",
    "영업 양수도계약",
    "영업 양수도 계약",
    "자산양수도계약",
    "자산 양수도 계약",
    "영업 및 지분양수도 계약",
    "합병계약",
    "합병 계약",
    "분할합병계약",
    "분할 합병 계약",
    "주주간협약",
    "주주간 협약",
    "주주간계약",
    "주주간 계약",
    "상계합의서",
    "정산합의서",
    "채권양수도",
    "share purchase agreement",
    "stock purchase agreement",
    "shareholders agreement",
    "shareholders' agreement",
    "subscription agreement",
    "convertible bond subscription",
    "business transfer agreement",
    "business transfer contract",
    "asset purchase agreement",
    "asset transfer agreement",
    "merger agreement",
    "spa",
    "ssa",
    "cbsa",
]

MNA_CONTEXT_TERMS = [
    "m&a",
    "\\2. m&a\\",
    "_2.1ma",
    "_2.",
    "인수",
    "매각",
    "합병",
    "분할",
    "양수도",
    "주식매매",
    "신주인수",
    "전환사채",
    "rcps",
    "투자계약",
    "투자 계약",
    "share purchase",
    "stock purchase",
    "subscription",
    "asset purchase",
    "business transfer",
    "merger",
    "acquisition",
]

CONTRACT_TERMS = [
    "계약서",
    "계약",
    "agreement",
    "contract",
    "mou",
    "term sheet",
    "loi",
    "합의서",
    "협약서",
]

NON_CONTRACT_MNA_TERMS = [
    "실사보고서",
    "실사 보고서",
    "ldd report",
    "legal due diligence report",
    "deal report",
    "report",
    "보고서",
    "기업 분석",
    "기업 분석 보고",
    "리서치",
    "질의사항",
    "인터뷰",
    "체크리스트",
    "checklist",
    "의견서",
    "메모",
    "memo",
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
]

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
]


def is_mna_contract(row: Dict[str, str]) -> Tuple[bool, str, List[str]]:
    # Use the real path/name and excerpt, not the classifier's matched_terms counts.
    # Otherwise LDD reports inside an M&A matter get pulled into "contracts" just
    # because their summaries mention many agreements.
    source_path = norm(row.get("source_path"))
    destination_path = norm(row.get("destination_path"))
    file_name = norm(Path(row.get("source_path") or row.get("destination_path") or "").name)
    excerpt = norm(row.get("excerpt"))
    raw_text = " ".join([source_path, destination_path, excerpt])

    specific_in_name = contains_any(file_name, SPECIFIC_MNA_CONTRACT_TERMS)
    specific_in_raw = contains_any(raw_text, SPECIFIC_MNA_CONTRACT_TERMS)
    mna = contains_any(raw_text, MNA_CONTEXT_TERMS)
    contract_in_name = contains_any(file_name, CONTRACT_TERMS)
    non_contract_in_name = contains_any(file_name, NON_CONTRACT_MNA_TERMS)
    strong_non_contract_in_name = contains_any(file_name, STRONG_NON_CONTRACT_FILENAME_TERMS)

    if strong_non_contract_in_name:
        return False, "mna_strong_non_contract_filename", strong_non_contract_in_name[:6]

    if non_contract_in_name and not specific_in_name:
        return False, "mna_non_contract_filename", non_contract_in_name[:6]

    if specific_in_name:
        return True, "specific_mna_contract_filename", specific_in_name[:8]

    if specific_in_raw and not non_contract_in_name:
        return True, "specific_mna_contract_excerpt_or_path", specific_in_raw[:8]

    if mna and contract_in_name:
        return True, "mna_context_plus_contract_filename", (mna + contract_in_name)[:8]

    return False, "not_mna_contract", (mna + contract_in_name + non_contract_in_name)[:8]


def study_subgroup(row: Dict[str, str]) -> str:
    text = signal_text(row)
    if contains_any(text, ["변호사시험", "변시", "법전협", "모의고사", "모의시험", "기출", "선택형", "사례형", "기록형", "강평"]):
        return "01_변호사시험_모의고사_기출"
    if contains_any(text, ["강의", "수업", "필기", "교재", "강의계획서", "공부방법"]):
        return "02_강의_필기_교재"
    if contains_any(text, ["과제", "스터디", "튜터링", "답안", "해설"]):
        return "03_과제_스터디_답안"
    return "04_학교_교육_기타"


def mna_subgroup(row: Dict[str, str]) -> str:
    text = signal_text(row)
    if contains_any(text, ["주식매매", "share purchase", "stock purchase", "spa"]):
        return "01_주식매매_SPA"
    if contains_any(text, ["신주인수", "전환사채", "사채인수", "rcps", "subscription", "투자계약", "투자 계약", "cbsa", "ssa"]):
        return "02_신주_RCPS_CB_투자"
    if contains_any(text, ["합병", "분할", "merger"]):
        return "03_합병_분할"
    if contains_any(text, ["영업양수도", "자산양수도", "지분양수도", "business transfer", "asset purchase", "asset transfer"]):
        return "04_영업_자산_지분양수도"
    if contains_any(text, ["mou", "term sheet", "loi", "양해각서"]):
        return "05_MOU_텀시트_LOI"
    return "99_M&A_기타계약"


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180] or "untitled"


def unique_path(folder: Path, source: Path, row: Dict[str, str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    name = safe_name(source.stem)
    suffix = source.suffix
    candidate = folder / f"{name}{suffix}"
    if not candidate.exists():
        return candidate
    digest = hashlib.sha1(norm(row.get("source_path")).encode("utf-8", errors="ignore")).hexdigest()[:10]
    candidate = folder / f"{name}__{digest}{suffix}"
    index = 2
    while candidate.exists():
        candidate = folder / f"{name}__{digest}_{index}{suffix}"
        index += 1
    return candidate


def classify(row: Dict[str, str]) -> Tuple[str, str, str]:
    study, study_terms = study_score(row)
    practice, practice_terms = practice_score(row)
    mna, mna_reason, mna_terms = is_mna_contract(row)

    if study >= 10 and study >= practice - 6:
        subgroup = study_subgroup(row)
        reason = f"study_score={study}; practice_score={practice}; terms={', '.join(study_terms[:8])}"
        return STUDY_ROOT, subgroup, reason

    if mna:
        subgroup = str(Path(MNA_ROOT) / mna_subgroup(row))
        reason = f"{mna_reason}; terms={', '.join(mna_terms[:8])}; study_score={study}; practice_score={practice}"
        return PRACTICE_ROOT, subgroup, reason

    category = row.get("category") or "99_기타_법률"
    subgroup = str(Path(PRACTICE_OTHER_ROOT) / safe_name(category))
    reason = f"practice_default; study_score={study}; practice_score={practice}; terms={', '.join(practice_terms[:8])}"
    return PRACTICE_ROOT, subgroup, reason


def archive_existing_output() -> None:
    if not OUTPUT.exists():
        return
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    archived = DESTINATION / f"_by_use_previous_{stamp}"
    shutil.move(str(OUTPUT), str(archived))


def link_or_copy(source: Path, target: Path) -> str:
    try:
        os.link(source, target)
        shutil.copystat(source, target, follow_symlinks=False)
        return "hardlink"
    except Exception:
        shutil.copy2(source, target)
        return "copy"


def read_rows() -> List[Dict[str, str]]:
    with REPORT.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> int:
    if not REPORT.exists():
        raise SystemExit(f"Missing report: {REPORT}")

    archive_existing_output()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    rows = read_rows()
    refined_rows: List[Dict[str, str]] = []
    counts: Dict[str, int] = {}
    methods: Dict[str, int] = {}
    missing_sources: List[Dict[str, str]] = []

    for index, row in enumerate(rows, start=1):
        source_text = row.get("destination_path") or row.get("source_path") or ""
        source = Path(source_text)
        group, subgroup, reason = classify(row)
        target_folder = OUTPUT / group / subgroup
        refined_row = dict(row)
        refined_row["refined_group"] = group
        refined_row["refined_subgroup"] = subgroup
        refined_row["classification_reason"] = reason

        if not source.exists():
            refined_row["refined_path"] = ""
            refined_row["link_method"] = "missing_source"
            missing_sources.append(refined_row)
        else:
            target = unique_path(target_folder, source, row)
            method = link_or_copy(source, target)
            refined_row["refined_path"] = str(target)
            refined_row["link_method"] = method
            methods[method] = methods.get(method, 0) + 1

        counts[f"{group}\\{subgroup}"] = counts.get(f"{group}\\{subgroup}", 0) + 1
        refined_rows.append(refined_row)
        if index % 500 == 0:
            print(f"[progress] refined={index}/{len(rows)}")

    base_fields = list(rows[0].keys()) if rows else []
    write_csv(OUTPUT / "_refined_classification_report.csv", refined_rows, base_fields + CSV_FIELDS_EXTRA)
    if missing_sources:
        write_csv(OUTPUT / "_missing_sources.csv", missing_sources, base_fields + CSV_FIELDS_EXTRA)
    else:
        write_csv(OUTPUT / "_missing_sources.csv", [], base_fields + CSV_FIELDS_EXTRA)

    study_total = sum(count for key, count in counts.items() if key.startswith(STUDY_ROOT + "\\"))
    mna_total = sum(count for key, count in counts.items() if key.startswith(f"{PRACTICE_ROOT}\\{MNA_ROOT}\\"))
    practice_total = sum(count for key, count in counts.items() if key.startswith(PRACTICE_ROOT + "\\"))
    practice_other_total = practice_total - mna_total

    summary = [
        "Refined legal document classification summary",
        f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Source report: {REPORT}",
        f"Output folder: {OUTPUT}",
        f"Total legal documents processed: {len(rows)}",
        f"Study/exam materials: {study_total}",
        f"Legal practice materials: {practice_total}",
        f"- M&A contracts: {mna_total}",
        f"- Other legal practice: {practice_other_total}",
        f"Missing source files: {len(missing_sources)}",
        "Link methods:",
    ]
    for method in sorted(methods):
        summary.append(f"- {method}: {methods[method]}")
    summary.extend(["", "Folder counts:"])
    for key in sorted(counts):
        summary.append(f"- {key}: {counts[key]}")
    summary.extend(
        [
            "",
            "Notes:",
            "- Existing original legal-category folders were preserved.",
            "- Link methods above show whether files were hardlinked or copied; this environment may fall back to copies.",
            "- M&A contract classification includes SPA/share purchase, new share/RCPS/CB investments, merger, and business/asset/equity transfer agreements.",
            "- Study/exam classification prioritizes law school, bar exam, mock exam, lecture, notes, assignment, and course-material signals.",
        ]
    )
    (OUTPUT / "_refined_summary.txt").write_text("\n".join(summary), encoding="utf-8")

    print(f"[done] processed={len(rows)} study={study_total} practice={practice_total} mna_contracts={mna_total} missing={len(missing_sources)}")
    print(f"[summary] {OUTPUT / '_refined_summary.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
