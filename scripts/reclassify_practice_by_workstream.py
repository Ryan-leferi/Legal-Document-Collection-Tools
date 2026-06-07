from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


BASE = Path(os.environ.get("LEGAL_DOC_BY_USE_ROOT", str(Path.home() / "Legal Documents Collection" / "_by_use")))
PRACTICE_ROOT = BASE / "02_법실무자료"
REPORT = BASE / "_refined_classification_report.csv"
WORKSTREAM_REPORT = BASE / "_practice_workstream_reclassification_report.csv"
WORKSTREAM_SUMMARY = BASE / "_practice_workstream_summary.txt"
REFINED_SUMMARY = BASE / "_refined_summary.txt"
PRACTICE_GROUP = "02_법실무자료"
STUDY_GROUP = "01_학습_수험자료"


def norm(value: object) -> str:
    return str(value or "").lower()


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180] or "untitled"


def contains_any(text: str, terms: Iterable[str]) -> List[str]:
    return [term for term in terms if term.lower() in text]


def score_terms(text: str, weighted_terms: Iterable[Tuple[str, int]]) -> Tuple[int, List[str]]:
    score = 0
    found: List[str] = []
    for term, weight in weighted_terms:
        if term.lower() in text:
            score += weight
            found.append(term)
    return score, found


def signal_text(row: Dict[str, str]) -> str:
    # Use original/source document signals only. Old refined paths and reasons
    # can contain stale category names and would reinforce previous buckets.
    return " ".join(
        norm(row.get(field))
        for field in ["source_path", "category", "matched_terms", "excerpt"]
    )


def content_text(row: Dict[str, str]) -> str:
    return " ".join(norm(row.get(field)) for field in ["category", "matched_terms", "excerpt"])


def path_text(row: Dict[str, str]) -> str:
    return norm(row.get("source_path"))


def file_name(row: Dict[str, str]) -> str:
    source = row.get("source_path") or row.get("refined_path") or row.get("destination_path") or ""
    return norm(Path(source).name)


def is_resource(row: Dict[str, str]) -> Tuple[bool, List[str]]:
    path = path_text(row)
    terms = [
        r"\3. resources\\",
        r"\m&a library\\",
        "library",
        "세미나",
        "seminar",
        "샘플",
        "sample",
        "standard form",
        "standard_form",
        "template",
        "양식",
        "강의",
        "교육",
        "ot",
        "신입변호사",
        "계약서 검토업무 샘플",
        "기업자문세미나",
        "associate seminar",
    ]
    found = contains_any(path, terms)
    return bool(found), found


HEALTHCARE_TERMS: Sequence[Tuple[str, int]] = [
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


def is_healthcare(row: Dict[str, str]) -> Tuple[bool, int, List[str]]:
    score, found = score_terms(signal_text(row), HEALTHCARE_TERMS)
    strong_terms = {
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
    }
    strong = any(term in strong_terms for term in found)
    return (strong and score >= 10) or score >= 18, score, found


MNA_CONTEXT: Sequence[Tuple[str, int]] = [
    (r"\1. projects\2. m&a\\", 35),
    (r"\4. archives\m&a\\", 30),
    ("m&a", 20),
    ("_2.1ma", 12),
    ("2.1ma", 12),
    ("인수", 8),
    ("매각", 8),
    ("합병", 8),
    ("분할", 8),
    ("투자", 7),
    ("전환사채", 7),
    ("신주", 7),
    ("rcps", 7),
    ("share purchase", 8),
    ("stock purchase", 8),
    ("subscription", 8),
    ("merger", 8),
    ("acquisition", 8),
    ("실사", 8),
    ("ldd", 8),
    ("due diligence", 8),
]

MNA_DEAL_TERMS = [
    "주식매매계약",
    "주식 매매 계약",
    "주식 및 전환사채 매매계약",
    "지분양수도계약",
    "지분 양수도 계약",
    "신주인수계약",
    "신주인수 계약",
    "신주 인수 계약",
    "전환사채인수계약",
    "전환사채 인수계약",
    "전환사채 인수 계약",
    "사채인수계약",
    "사채 인수 계약",
    "종류주식 투자계약",
    "종류주식 투자 계약",
    "투자계약",
    "투자 계약",
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

MNA_MOU_TERMS = ["mou", "loi", "term sheet", "텀시트", "양해각서"]


def mna_score(row: Dict[str, str]) -> Tuple[int, List[str]]:
    return score_terms(signal_text(row), MNA_CONTEXT)


def is_mna_matter(row: Dict[str, str]) -> Tuple[bool, int, List[str]]:
    score, found = mna_score(row)
    filename_terms = contains_any(file_name(row), MNA_DEAL_TERMS + MNA_ANCILLARY_TERMS + MNA_MOU_TERMS)
    return score >= 16 or bool(filename_terms), score, found + filename_terms


def is_mna_contract(row: Dict[str, str]) -> Tuple[bool, str, List[str]]:
    name = file_name(row)
    text = signal_text(row)
    non_contract = contains_any(
        name,
        [
            "실사보고서",
            "실사 보고서",
            "ldd report",
            "legal due diligence report",
            "deal report",
            "report",
            "보고서",
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
        ],
    )
    if non_contract:
        return False, "mna_non_contract_filename", non_contract

    deal_name = contains_any(name, MNA_DEAL_TERMS)
    if deal_name:
        return True, "mna_deal_filename", deal_name

    deal_text = contains_any(text, MNA_DEAL_TERMS)
    context = contains_any(text, [term for term, _ in MNA_CONTEXT])
    if deal_text and context:
        return True, "mna_deal_text_with_context", deal_text + context

    investment_text = contains_any(
        text,
        [
            "신주인수",
            "신주를 인수",
            "신주 인수",
            "투자기업",
            "투자대상기업",
            "상환전환우선주",
            "전환사채",
            "인수인은",
            "인수대금",
        ],
    )
    if investment_text and contains_any(text, ["본 계약", "계약서", "agreement"]):
        return True, "mna_investment_contract_text", investment_text

    ancillary = contains_any(name, MNA_ANCILLARY_TERMS)
    if ancillary and context:
        return True, "mna_ancillary_filename_with_context", ancillary + context

    mou = contains_any(name, MNA_MOU_TERMS)
    if mou and contains_any(text, ["m&a", "인수", "매각", "합병", "투자", "acquisition", "merger"]):
        return True, "mna_mou_with_context", mou + context

    return False, "not_mna_contract", deal_text + ancillary + context


def mna_contract_subfolder(row: Dict[str, str]) -> str:
    text = signal_text(row)
    if contains_any(text, ["주식매매", "share purchase", "stock purchase", "spa"]):
        return r"01_거래계약\01_SPA_주식매매"
    if contains_any(
        text,
        [
            "신주인수",
            "신주를 인수",
            "신주 인수",
            "전환사채",
            "사채인수",
            "인수대금",
            "투자기업",
            "투자대상기업",
            "rcps",
            "상환전환우선주",
            "subscription",
        ],
    ):
        return r"01_거래계약\02_투자_RCPS_CB"
    if contains_any(text, ["주주간", "shareholders", "상계합의", "정산합의", "채권양수도"]):
        return r"01_거래계약\03_주주간_부속합의"
    if contains_any(text, ["합병", "분할", "merger"]):
        return r"01_거래계약\04_합병_분할"
    if contains_any(text, ["영업양수도", "자산양수도", "지분양수도", "business transfer", "asset purchase", "asset transfer"]):
        return r"01_거래계약\05_영업_자산_지분양수도"
    if contains_any(text, MNA_MOU_TERMS):
        return r"01_거래계약\06_MOU_LOI_텀시트"
    return r"01_거래계약\99_기타_거래계약"


def mna_non_contract_subfolder(row: Dict[str, str]) -> str:
    text = signal_text(row)
    path = path_text(row)
    name = file_name(row)
    if contains_any(text, ["ldd report", "legal due diligence report", "법률실사보고서", "실사보고서", "실사 보고서"]):
        return r"02_법률실사\01_실사보고서"
    if contains_any(path, ["\\g. contracts\\", "\\contracts\\", "\\추가rfi\\", "\\rfi\\", "\\1차 자료", "\\vdr\\", "\\dataroom\\", "\\data room\\", "실사"]):
        return r"02_법률실사\02_실사자료_RFI_체크리스트"
    if contains_any(text, ["rfi", "요청자료", "실사자료", "제출자료", "체크리스트", "checklist", "질의사항", "인터뷰"]):
        return r"02_법률실사\02_실사자료_RFI_체크리스트"
    if contains_any(text, ["실사", "ldd", "due diligence"]):
        return r"02_법률실사\03_분야별_실사메모"
    if contains_any(name, ["정관", "이사회의사록", "주주총회", "등기", "위임장", "취임승낙", "인감", "closing", "클로징"]):
        return r"03_클로징_등기_거버넌스"
    if contains_any(text, ["공시", "자본시장", "거래구조", "deal report", "구조", "유상증자", "전환사채 발행"]):
        return r"04_거래구조_공시_자본시장"
    if contains_any(text, ["소송", "분쟁", "준비서면", "답변서", "소장", "post-m&a", "post m&a", "해지", "termination", "notice", "내용증명", "손해배상"]):
        return r"05_거래분쟁_Post_M&A"
    return r"99_M&A_기타"


def healthcare_subfolder(row: Dict[str, str]) -> str:
    text = signal_text(row)
    content = content_text(row)
    path = path_text(row)
    name = file_name(row)
    mna, _, _ = is_mna_contract(row)
    mna_matter, _, _ = is_mna_matter(row)
    healthcare_deal_terms = contains_any(
        content,
        MNA_DEAL_TERMS
        + MNA_ANCILLARY_TERMS
        + [
            "m&a",
            "투자",
            "인수",
            "매각",
            "지분",
            "주식매매",
            "실사",
            "ldd",
            "due diligence",
            "기업 분석",
            "기업분석",
        ],
    )
    if mna or (mna_matter and healthcare_deal_terms):
        if mna:
            return "04_헬스케어_M&A_투자\\" + mna_contract_subfolder(row)
        if contains_any(path, ["ldd", "실사", "rfi", "추가rfi", "diligence"]):
            return r"04_헬스케어_M&A_투자\02_법률실사"
        if contains_any(content, ["ldd", "실사", "due diligence", "실사보고서"]):
            return r"04_헬스케어_M&A_투자\02_법률실사"
        return r"04_헬스케어_M&A_투자\99_기타"
    if contains_any(text, ["식약처", "mfds", "인허가", "허가", "승인", "요양급여", "비급여", "건강보험", "보건복지", "심평원", "신의료기술", "혁신의료"]):
        return r"01_규제_인허가_보험급여"
    if contains_any(text, ["의료기기", "디지털의료", "디지털 헬스", "digital health", "sa md", "sa-md", "소프트웨어 의료기기", "진단기기", "체외진단"]):
        return r"02_의료기기_디지털헬스"
    if contains_any(text, ["임상시험", "clinical trial", "iit", "제약", "의약", "약품", "신약", "바이오", "pharma", "pharmaceutical"]):
        return r"03_제약_바이오_임상"
    if contains_any(text, ["개인정보", "의료 데이터", "의료데이터", "데이터", "patient data", "보건의료데이터", "마이데이터"]):
        return r"05_의료데이터_개인정보"
    if contains_any(text, ["소송", "분쟁", "조사", "준비서면", "답변서", "소장", "행정소송", "처분취소"]):
        return r"07_분쟁_조사"
    if contains_any(
        text,
        [
            "계약서",
            "계약",
            "합의서",
            "agreement",
            "contract",
            "nda",
            "비밀유지",
            "공급",
            "구매",
            "유통",
            "용역",
            "서비스",
            "service",
            "services",
            "license",
            "라이선스",
            "msa",
            "odm",
            "oem",
            "mou",
            "업무협약",
            "memorandum of understanding",
        ],
    ):
        return r"06_계약_사업제휴"
    if contains_any(name, ["등기", "정관", "이사회의사록", "주주총회", "위임장", "취임승낙", "인감", "corporate certificate"]) or contains_any(
        content,
        ["등기", "정관", "이사회", "주주총회", "공증", "아포스티유", "apostille", "영업소", "주소변경", "corporate certificate"],
    ):
        return r"09_기업일반_등기"
    if contains_any(text, ["의견서", "메모", "리서치", "memo", "검토", "뉴스레터"]):
        return r"08_리서치_의견서"
    return r"99_Healthcare_기타"


def general_subfolder(row: Dict[str, str]) -> str:
    text = signal_text(row)
    name = file_name(row)
    category = row.get("category") or ""
    if contains_any(text, ["자본시장", "공정거래", "금융위원회", "금융감독원", "금감원", "한국거래소", "시행령", "신구조문", "신구대조", "불공정거래", "공시"]):
        return r"09_규제_인허가_공정거래_세무"
    if contains_any(
        name + " " + text,
        ["형사", "고소", "고발", "검찰", "경찰", "피고인", "피의자", "변호인 의견서", "영장", "공소장", "공소사실", "불기소"],
    ):
        return r"04_소송_분쟁_조사\02_형사_수사"
    if contains_any(text, ["소송", "분쟁", "준비서면", "답변서", "소장", "내용증명", "가압류", "가처분", "중재", "siac", "소송_법원"]):
        return r"04_소송_분쟁_조사"
    if contains_any(text, ["근로", "노무", "hr", "임금", "퇴직금", "해고", "취업규칙", "근로기준법", "노동", "산업재해"]):
        return r"06_노무_HR"
    if contains_any(text, ["개인정보", "정보통신망", "데이터", "저작권", "특허", "상표", "라이선스", "영업비밀", "ip", "it"]):
        return r"07_IP_IT_개인정보"
    if contains_any(text, ["부동산", "임대차", "전대차", "전세", "보증금", "건물", "토지", "lease", "leasing"]):
        return r"08_부동산_임대차"
    if contains_any(text, ["공정거래", "세무", "조세", "국세", "인허가", "행정", "과징금", "신고", "등록", "허가", "승인"]):
        return r"09_규제_인허가_공정거래_세무"
    if contains_any(name, ["정관", "이사회의사록", "주주총회", "등기", "위임장", "취임승낙", "인감"]) or contains_any(text, ["정관", "이사회", "주주총회", "등기", "법인", "회사법", "상법"]):
        return r"05_기업일반_등기_거버넌스"
    if contains_any(text, ["의견서", "메모", "리서치", "memo", "검토", "법률검토", "판례", "법령", "뉴스레터"]):
        return r"10_리서치_메모_의견서"
    if contains_any(text, ["계약서", "agreement", "contract", "nda", "비밀유지", "msa", "service", "services", "공급", "유통", "라이선스", "용역", "업무협약"]):
        if contains_any(text, ["공급", "유통", "distribution", "distributor", "supply", "라이선스", "license"]):
            return r"03_계약자문\02_공급_유통_라이선스"
        if contains_any(text, ["번역", "translation", "markup", "mark-up", "redline", "검토"]):
            return r"03_계약자문\03_계약검토_번역_마크업"
        return r"03_계약자문\01_일반계약_NDA_MSA_서비스"
    if category:
        return r"99_기타\원분류_" + safe_name(category)
    return r"99_기타"


def classify(row: Dict[str, str]) -> Tuple[str, str]:
    resource, resource_terms = is_resource(row)
    healthcare, healthcare_score, healthcare_terms = is_healthcare(row)
    mna_matter, mna_score_value, mna_terms = is_mna_matter(row)
    mna_contract, mna_contract_reason, mna_contract_terms = is_mna_contract(row)

    if healthcare:
        subgroup = "02_Healthcare\\" + healthcare_subfolder(row)
        reason = f"healthcare score={healthcare_score}; terms={', '.join(healthcare_terms[:12])}"
        return subgroup, reason

    if mna_contract:
        subgroup = "01_M&A\\" + mna_contract_subfolder(row)
        reason = f"mna_contract {mna_contract_reason}; terms={', '.join(mna_contract_terms[:12])}"
        return subgroup, reason

    if mna_matter:
        subgroup = "01_M&A\\" + mna_non_contract_subfolder(row)
        reason = f"mna_matter score={mna_score_value}; terms={', '.join(mna_terms[:12])}"
        return subgroup, reason

    if resource:
        subgroup = "11_자료실_샘플_세미나"
        reason = f"resource_or_sample; terms={', '.join(resource_terms[:12])}"
        return subgroup, reason

    subgroup = general_subfolder(row)
    reason = "general_workstream_rules"
    return subgroup, reason


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


def subgroup_to_path(subgroup: str) -> Path:
    parts = [safe_name(part) for part in subgroup.replace("/", "\\").split("\\") if part]
    return PRACTICE_ROOT / Path(*parts)


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
        if path == root:
            continue
        try:
            if not any(path.iterdir()):
                path.rmdir()
        except OSError:
            pass


def rebuild_summaries(rows: List[Dict[str, str]], moved_count: int, missing_count: int) -> None:
    group_counts: Dict[str, int] = {}
    subgroup_counts: Dict[str, int] = {}
    practice_top: Dict[str, int] = {}
    for row in rows:
        group = row.get("refined_group") or ""
        subgroup = row.get("refined_subgroup") or ""
        group_counts[group] = group_counts.get(group, 0) + 1
        subgroup_counts[subgroup] = subgroup_counts.get(subgroup, 0) + 1
        if group == PRACTICE_GROUP:
            top = subgroup.split("\\", 1)[0]
            practice_top[top] = practice_top.get(top, 0) + 1

    lines = [
        "Refined legal document classification summary",
        f"Updated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Output folder: {BASE}",
        f"Total legal documents processed: {len(rows)}",
        f"Study/exam materials: {group_counts.get(STUDY_GROUP, 0)}",
        f"Legal practice materials: {group_counts.get(PRACTICE_GROUP, 0)}",
        f"Files moved in latest workstream reclassification: {moved_count}",
        f"Missing files in latest workstream reclassification: {missing_count}",
        "",
        "Legal practice top-level counts:",
    ]
    for key in sorted(practice_top):
        lines.append(f"- {key}: {practice_top[key]}")
    lines.extend(["", "Folder counts:"])
    for key in sorted(subgroup_counts):
        lines.append(f"- {key}: {subgroup_counts[key]}")
    lines.extend(
        [
            "",
            "Notes:",
            "- Legal practice files were reclassified around M&A / Healthcare workstreams.",
            "- Study/exam folders were not changed.",
            f"- Detailed move log: {WORKSTREAM_REPORT}",
        ]
    )
    REFINED_SUMMARY.write_text("\n".join(lines), encoding="utf-8")

    ws_lines = [
        "Legal practice workstream reclassification summary",
        f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Moved files: {moved_count}",
        f"Missing current refined paths: {missing_count}",
        "",
        "Top-level legal practice counts:",
    ]
    for key in sorted(practice_top):
        ws_lines.append(f"- {key}: {practice_top[key]}")
    ws_lines.extend(
        [
            "",
            "Design:",
            "- 01_M&A: transaction contracts, LDD, closing/governance, transaction research, and post-M&A disputes.",
            "- 02_Healthcare: healthcare regulatory, medical device/digital health, pharma/clinical, healthcare M&A, data/privacy, contracts, disputes, and corporate registration/governance.",
            "- Remaining folders capture general contracts, disputes, corporate, HR, IP/IT/privacy, real estate, regulatory/tax, research, and samples.",
            "",
            f"Move report: {WORKSTREAM_REPORT}",
        ]
    )
    WORKSTREAM_SUMMARY.write_text("\n".join(ws_lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows, fields = read_rows()
    move_fields = fields + [
        "old_refined_subgroup",
        "old_refined_path",
        "new_refined_subgroup",
        "new_refined_path",
        "workstream_reason",
        "move_status",
    ]
    move_rows: List[Dict[str, str]] = []
    practice_counts: Dict[str, int] = {}
    moved = 0
    missing = 0

    for row in rows:
        if row.get("refined_group") != PRACTICE_GROUP:
            continue
        old_subgroup = row.get("refined_subgroup") or ""
        new_subgroup, reason = classify(row)
        practice_counts[new_subgroup] = practice_counts.get(new_subgroup, 0) + 1

        if args.dry_run:
            continue
        if new_subgroup == old_subgroup:
            continue

        old_path_text = row.get("refined_path") or ""
        old_path = Path(old_path_text)
        move_row = dict(row)
        move_row["old_refined_subgroup"] = old_subgroup
        move_row["old_refined_path"] = old_path_text
        move_row["new_refined_subgroup"] = new_subgroup
        move_row["workstream_reason"] = reason

        if old_path.exists():
            target = unique_target(subgroup_to_path(new_subgroup), old_path, row.get("source_path") or old_path_text)
            shutil.move(str(old_path), str(target))
            row["refined_subgroup"] = new_subgroup
            row["refined_path"] = str(target)
            row["classification_reason"] = ((row.get("classification_reason") or "") + "; workstream: " + reason).strip("; ")
            move_row["new_refined_path"] = str(target)
            move_row["move_status"] = "moved"
            moved += 1
        else:
            move_row["new_refined_path"] = ""
            move_row["move_status"] = "missing_current_refined_path"
            missing += 1
        move_rows.append(move_row)

    if args.dry_run:
        print("[dry-run] practice files=" + str(sum(practice_counts.values())))
        for subgroup in sorted(practice_counts):
            print(f"[count] {subgroup}={practice_counts[subgroup]}")
        return 0

    write_rows(REPORT, rows, fields)
    write_rows(WORKSTREAM_REPORT, move_rows, move_fields)
    remove_empty_dirs(PRACTICE_ROOT)
    rebuild_summaries(rows, moved, missing)

    print(f"[done] moved={moved} missing={missing}")
    top_counts: Dict[str, int] = {}
    for row in rows:
        if row.get("refined_group") == PRACTICE_GROUP:
            top = (row.get("refined_subgroup") or "").split("\\", 1)[0]
            top_counts[top] = top_counts.get(top, 0) + 1
    for top in sorted(top_counts):
        print(f"[top] {top}={top_counts[top]}")
    print(f"[report] {WORKSTREAM_REPORT}")
    print(f"[summary] {WORKSTREAM_SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
