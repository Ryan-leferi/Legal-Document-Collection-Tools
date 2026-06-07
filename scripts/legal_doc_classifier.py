#!/usr/bin/env python3
"""
Scan local drives for DOCX/DOC/HWP/HWPX files, identify legal documents by
content, and copy them into category folders under a destination directory.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import datetime as dt
import hashlib
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import traceback
import zipfile
import zlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


EXTENSIONS = {".docx", ".doc", ".hwp", ".hwpx"}
DEFAULT_DESTINATION = os.environ.get(
    "LEGAL_DOC_COLLECTION_ROOT",
    str(Path.home() / "Legal Documents Collection"),
)
SCAN_LOG_INTERVAL = 20.0
TEXT_CAP = 750_000
XML_ENTRY_CAP = 50 * 1024 * 1024
FILE_READ_CAP = 120 * 1024 * 1024


SKIP_DIR_NAMES = {
    "$Recycle.Bin",
    "System Volume Information",
    "Recovery",
    "Config.Msi",
}


LEGAL_SIGNALS: Dict[str, int] = {
    "계약서": 8,
    "계약": 5,
    "약정": 5,
    "협약": 4,
    "합의서": 7,
    "비밀유지": 6,
    "손해배상": 7,
    "채권": 5,
    "채무": 5,
    "담보": 4,
    "보증": 4,
    "소송": 8,
    "소장": 8,
    "답변서": 8,
    "준비서면": 8,
    "판결": 8,
    "결정문": 8,
    "결정": 4,
    "법원": 7,
    "재판": 6,
    "항소": 6,
    "상고": 6,
    "원고": 5,
    "피고": 5,
    "청구취지": 8,
    "청구원인": 8,
    "가압류": 7,
    "가처분": 7,
    "강제집행": 7,
    "고소": 8,
    "고발": 8,
    "피의자": 7,
    "피고인": 7,
    "검찰": 6,
    "경찰": 4,
    "수사": 5,
    "공소": 6,
    "범죄": 5,
    "벌금": 5,
    "구속": 5,
    "근로기준법": 8,
    "근로": 4,
    "노동": 4,
    "임금": 5,
    "해고": 6,
    "징계": 5,
    "퇴직금": 5,
    "산업재해": 6,
    "취업규칙": 7,
    "부동산": 5,
    "임대차": 8,
    "전세": 5,
    "월세": 4,
    "보증금": 4,
    "등기": 5,
    "주택임대차보호법": 9,
    "상법": 7,
    "회사법": 7,
    "정관": 6,
    "주주": 5,
    "이사회": 5,
    "법인": 4,
    "공정거래": 6,
    "저작권": 7,
    "특허": 7,
    "상표": 6,
    "영업비밀": 7,
    "개인정보": 7,
    "정보통신망": 6,
    "라이선스": 5,
    "이혼": 8,
    "양육": 6,
    "친권": 6,
    "재산분할": 7,
    "상속": 8,
    "유언": 7,
    "가족관계": 5,
    "세무": 5,
    "조세": 6,
    "국세": 5,
    "과세": 5,
    "행정심판": 7,
    "행정소송": 8,
    "인허가": 5,
    "과징금": 6,
    "법률": 7,
    "법령": 7,
    "시행령": 7,
    "시행규칙": 7,
    "조례": 6,
    "판례": 7,
    "법제처": 7,
    "민법": 7,
    "형법": 7,
    "헌법": 7,
    "행정법": 7,
    "규정": 3,
    "내용증명": 8,
    "통지서": 5,
    "최고서": 7,
    "위임장": 7,
    "진정서": 6,
    "탄원서": 6,
    "사실확인서": 5,
    "변호사": 7,
    "공증": 7,
    "contract": 7,
    "agreement": 6,
    "legal": 7,
    "law": 4,
    "lawsuit": 8,
    "litigation": 8,
    "court": 7,
    "complaint": 6,
    "plaintiff": 7,
    "defendant": 7,
    "judgment": 7,
    "arbitration": 7,
    "statute": 7,
    "regulation": 5,
    "privacy": 5,
    "terms and conditions": 8,
    "non-disclosure": 7,
    "nda": 7,
    "power of attorney": 8,
}


CATEGORIES: List[Tuple[str, Dict[str, int]]] = [
    (
        "01_계약_협약",
        {
            "계약서": 10,
            "계약": 7,
            "약정": 7,
            "협약": 6,
            "합의서": 8,
            "양해각서": 7,
            "비밀유지": 7,
            "납품": 4,
            "용역": 4,
            "라이선스 계약": 8,
            "contract": 8,
            "agreement": 7,
            "mou": 6,
            "nda": 8,
            "non-disclosure": 8,
            "terms and conditions": 7,
        },
    ),
    (
        "02_소송_법원_분쟁",
        {
            "소송": 10,
            "소장": 10,
            "답변서": 10,
            "준비서면": 10,
            "판결": 9,
            "결정문": 9,
            "법원": 8,
            "재판": 7,
            "항소": 8,
            "상고": 8,
            "원고": 7,
            "피고": 7,
            "청구취지": 10,
            "청구원인": 10,
            "가압류": 8,
            "가처분": 8,
            "강제집행": 8,
            "litigation": 9,
            "lawsuit": 9,
            "court": 8,
            "plaintiff": 8,
            "defendant": 8,
            "judgment": 8,
            "arbitration": 7,
        },
    ),
    (
        "03_형사_수사",
        {
            "고소": 10,
            "고발": 10,
            "피의자": 9,
            "피고인": 9,
            "검찰": 8,
            "경찰": 6,
            "수사": 7,
            "공소": 8,
            "형법": 8,
            "범죄": 7,
            "벌금": 6,
            "구속": 7,
            "criminal": 8,
            "prosecution": 7,
        },
    ),
    (
        "04_노무_고용",
        {
            "근로기준법": 10,
            "근로": 6,
            "노동": 6,
            "임금": 7,
            "해고": 8,
            "징계": 7,
            "퇴직금": 7,
            "산업재해": 8,
            "취업규칙": 9,
            "고용": 5,
            "employment": 7,
            "labor": 7,
            "labour": 7,
            "wage": 6,
            "dismissal": 7,
        },
    ),
    (
        "05_부동산_임대차",
        {
            "부동산": 8,
            "임대차": 10,
            "전세": 8,
            "월세": 7,
            "보증금": 6,
            "등기": 7,
            "매매계약": 8,
            "주택임대차보호법": 10,
            "lease": 8,
            "real estate": 8,
            "tenant": 7,
            "landlord": 7,
            "rent": 5,
        },
    ),
    (
        "06_회사_상거래",
        {
            "상법": 9,
            "회사법": 9,
            "회사": 5,
            "정관": 8,
            "주주": 7,
            "이사회": 7,
            "법인": 6,
            "공정거래": 8,
            "영업양도": 7,
            "합병": 7,
            "분할": 4,
            "commercial": 7,
            "corporate": 7,
            "shareholder": 7,
            "board of directors": 7,
            "merger": 7,
        },
    ),
    (
        "07_지식재산_IT_개인정보",
        {
            "저작권": 10,
            "특허": 10,
            "상표": 8,
            "영업비밀": 9,
            "개인정보": 9,
            "정보통신망": 8,
            "라이선스": 7,
            "데이터": 4,
            "copyright": 8,
            "patent": 8,
            "trademark": 8,
            "privacy": 7,
            "data protection": 8,
            "intellectual property": 8,
            "license": 6,
        },
    ),
    (
        "08_가사_상속",
        {
            "이혼": 10,
            "양육": 8,
            "친권": 8,
            "재산분할": 9,
            "상속": 10,
            "유언": 9,
            "가족관계": 7,
            "혼인": 6,
            "estate": 7,
            "inheritance": 8,
            "divorce": 9,
            "custody": 8,
        },
    ),
    (
        "09_세무_행정_인허가",
        {
            "세무": 8,
            "조세": 9,
            "국세": 7,
            "과세": 7,
            "행정심판": 9,
            "행정소송": 9,
            "인허가": 8,
            "과징금": 8,
            "처분": 5,
            "tax": 7,
            "administrative": 7,
            "permit": 6,
            "license": 4,
        },
    ),
    (
        "10_법령_판례_리서치",
        {
            "법률": 9,
            "법령": 9,
            "시행령": 9,
            "시행규칙": 9,
            "조례": 8,
            "판례": 9,
            "법제처": 9,
            "민법": 8,
            "형법": 8,
            "헌법": 8,
            "행정법": 8,
            "해설": 5,
            "연구": 4,
            "statute": 8,
            "regulation": 7,
            "case law": 8,
            "precedent": 8,
        },
    ),
    (
        "11_통지_증명_위임",
        {
            "내용증명": 10,
            "통지서": 8,
            "최고서": 9,
            "위임장": 10,
            "진정서": 8,
            "탄원서": 8,
            "사실확인서": 7,
            "확인서": 5,
            "certificate": 6,
            "notice": 6,
            "power of attorney": 10,
            "affidavit": 8,
        },
    ),
]


@dataclass
class ExtractedText:
    text: str
    method: str
    warning: str = ""


@dataclass
class CandidateResult:
    source_path: str
    extension: str
    size: int
    modified: str
    extraction_method: str
    extraction_warning: str
    legal_score: int
    path_score: int
    category: str
    category_score: int
    matched_terms: str
    copied: bool
    destination_path: str
    status: str
    excerpt: str


class OleError(Exception):
    pass


class CompoundFile:
    FREESECT = 0xFFFFFFFF
    ENDOFCHAIN = 0xFFFFFFFE
    FATSECT = 0xFFFFFFFD
    DIFSECT = 0xFFFFFFFC
    NOSTREAM = 0xFFFFFFFF

    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        if len(self.data) < 512 or self.data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            raise OleError("not an OLE compound file")

        self.major_version = struct.unpack_from("<H", self.data, 26)[0]
        byte_order = struct.unpack_from("<H", self.data, 28)[0]
        if byte_order != 0xFFFE:
            raise OleError("unsupported OLE byte order")
        self.sector_size = 1 << struct.unpack_from("<H", self.data, 30)[0]
        self.mini_sector_size = 1 << struct.unpack_from("<H", self.data, 32)[0]
        self.num_fat_sectors = struct.unpack_from("<I", self.data, 44)[0]
        self.first_dir_sector = struct.unpack_from("<I", self.data, 48)[0]
        self.mini_cutoff = struct.unpack_from("<I", self.data, 56)[0]
        self.first_mini_fat_sector = struct.unpack_from("<I", self.data, 60)[0]
        self.num_mini_fat_sectors = struct.unpack_from("<I", self.data, 64)[0]
        self.first_difat_sector = struct.unpack_from("<I", self.data, 68)[0]
        self.num_difat_sectors = struct.unpack_from("<I", self.data, 72)[0]
        self.difat = list(struct.unpack_from("<109I", self.data, 76))
        self._load_difat()
        self.fat = self._load_fat()
        self.dir_entries = self._load_directory()
        self.path_map = self._build_path_map()
        self.root_entry = next((entry for entry in self.dir_entries if entry["type"] == 5), None)
        self.root_stream = b""
        if self.root_entry and self.root_entry["start"] != self.ENDOFCHAIN:
            self.root_stream = self._read_regular_stream(
                self.root_entry["start"], self.root_entry["size"]
            )
        self.mini_fat = self._load_mini_fat()

    def _sector_offset(self, sector: int) -> int:
        if sector >= self.FATSECT:
            raise OleError(f"invalid sector id {sector:#x}")
        return (sector + 1) * self.sector_size

    def _sector_bytes(self, sector: int) -> bytes:
        offset = self._sector_offset(sector)
        end = offset + self.sector_size
        if end > len(self.data):
            raise OleError("sector outside file")
        return self.data[offset:end]

    def _load_difat(self) -> None:
        sector = self.first_difat_sector
        for _ in range(self.num_difat_sectors):
            if sector in (self.ENDOFCHAIN, self.FREESECT):
                break
            block = self._sector_bytes(sector)
            entries = struct.unpack_from(f"<{self.sector_size // 4}I", block, 0)
            self.difat.extend(entries[:-1])
            sector = entries[-1]

    def _load_fat(self) -> List[int]:
        fat: List[int] = []
        fat_sectors = [
            sector
            for sector in self.difat
            if sector not in (self.FREESECT, self.ENDOFCHAIN, self.FATSECT, self.DIFSECT)
        ][: self.num_fat_sectors]
        for sector in fat_sectors:
            block = self._sector_bytes(sector)
            fat.extend(struct.unpack_from(f"<{self.sector_size // 4}I", block, 0))
        return fat

    def _chain(self, start_sector: int) -> List[int]:
        if start_sector in (self.ENDOFCHAIN, self.FREESECT):
            return []
        chain: List[int] = []
        seen = set()
        sector = start_sector
        while sector not in (self.ENDOFCHAIN, self.FREESECT):
            if sector in seen:
                raise OleError("sector chain loop")
            if sector >= len(self.fat):
                raise OleError("sector chain outside FAT")
            seen.add(sector)
            chain.append(sector)
            sector = self.fat[sector]
        return chain

    def _read_regular_stream(self, start_sector: int, size: int) -> bytes:
        data = bytearray()
        for sector in self._chain(start_sector):
            data.extend(self._sector_bytes(sector))
            if len(data) >= size:
                break
        return bytes(data[:size])

    def _load_directory(self) -> List[dict]:
        raw = self._read_regular_stream(self.first_dir_sector, len(self.data))
        entries: List[dict] = []
        for offset in range(0, len(raw), 128):
            chunk = raw[offset : offset + 128]
            if len(chunk) < 128:
                break
            name_len = struct.unpack_from("<H", chunk, 64)[0]
            if name_len >= 2:
                name_bytes = chunk[: name_len - 2]
                name = name_bytes.decode("utf-16le", errors="ignore")
            else:
                name = ""
            entry_type = chunk[66]
            left = struct.unpack_from("<I", chunk, 68)[0]
            right = struct.unpack_from("<I", chunk, 72)[0]
            child = struct.unpack_from("<I", chunk, 76)[0]
            start = struct.unpack_from("<I", chunk, 116)[0]
            if self.major_version >= 4:
                size = struct.unpack_from("<Q", chunk, 120)[0]
            else:
                size = struct.unpack_from("<I", chunk, 120)[0]
            entries.append(
                {
                    "index": len(entries),
                    "name": name,
                    "type": entry_type,
                    "left": left,
                    "right": right,
                    "child": child,
                    "start": start,
                    "size": size,
                }
            )
        return entries

    def _valid_entry_index(self, index: int) -> bool:
        return index != self.NOSTREAM and index < len(self.dir_entries)

    def _build_path_map(self) -> Dict[str, dict]:
        path_map: Dict[str, dict] = {}

        def walk_siblings(index: int, parent_parts: List[str], seen: set) -> None:
            if not self._valid_entry_index(index) or index in seen:
                return
            seen.add(index)
            entry = self.dir_entries[index]
            walk_siblings(entry["left"], parent_parts, seen)
            if entry["name"]:
                current = parent_parts + [entry["name"]]
                if entry["type"] == 2:
                    path_map["/".join(current).lower()] = entry
                if entry["type"] in (1, 5):
                    walk_siblings(entry["child"], current if entry["type"] != 5 else [], seen)
            walk_siblings(entry["right"], parent_parts, seen)

        root = next((entry for entry in self.dir_entries if entry["type"] == 5), None)
        if root:
            walk_siblings(root["child"], [], set())
        return path_map

    def _load_mini_fat(self) -> List[int]:
        if self.num_mini_fat_sectors == 0 or self.first_mini_fat_sector in (
            self.ENDOFCHAIN,
            self.FREESECT,
        ):
            return []
        data = bytearray()
        for sector in self._chain(self.first_mini_fat_sector)[: self.num_mini_fat_sectors]:
            data.extend(self._sector_bytes(sector))
        if not data:
            return []
        return list(struct.unpack_from(f"<{len(data) // 4}I", bytes(data), 0))

    def _read_mini_stream(self, start_sector: int, size: int) -> bytes:
        if start_sector in (self.ENDOFCHAIN, self.FREESECT) or not self.root_stream:
            return b""
        data = bytearray()
        sector = start_sector
        seen = set()
        while sector not in (self.ENDOFCHAIN, self.FREESECT):
            if sector in seen or sector >= len(self.mini_fat):
                raise OleError("mini sector chain error")
            seen.add(sector)
            offset = sector * self.mini_sector_size
            data.extend(self.root_stream[offset : offset + self.mini_sector_size])
            if len(data) >= size:
                break
            sector = self.mini_fat[sector]
        return bytes(data[:size])

    def list_streams(self) -> List[str]:
        return sorted(self.path_map)

    def open_stream(self, path: str) -> bytes:
        key = path.replace("\\", "/").lower()
        entry = self.path_map.get(key)
        if not entry:
            raise OleError(f"stream not found: {path}")
        if entry["size"] < self.mini_cutoff and self.mini_fat:
            return self._read_mini_stream(entry["start"], entry["size"])
        return self._read_regular_stream(entry["start"], entry["size"])


def clean_text(text: str, cap: int = TEXT_CAP) -> str:
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = "".join(ch if ch == "\n" or ch == "\t" or ord(ch) >= 32 else " " for ch in text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()[:cap]


def xml_text_from_bytes(data: bytes) -> str:
    parts: List[str] = []
    try:
        parser = ET.iterparse(BytesIO(data), events=("start", "end"))
        for event, elem in parser:
            if event == "end":
                tag = elem.tag.rsplit("}", 1)[-1].lower()
                if elem.text:
                    parts.append(elem.text)
                if tag in {"p", "para", "paragraph", "tbl", "tr", "br", "linebreak"}:
                    parts.append("\n")
                if tag in {"tab"}:
                    parts.append("\t")
                if elem.tail:
                    parts.append(elem.tail)
                elem.clear()
    except ET.ParseError:
        try:
            decoded = data.decode("utf-8", errors="ignore")
        except Exception:
            decoded = data.decode("cp949", errors="ignore")
        decoded = re.sub(r"<[^>]+>", " ", decoded)
        parts.append(decoded)
    return clean_text(" ".join(parts))


def extract_docx(path: Path) -> ExtractedText:
    texts: List[str] = []
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        xml_names = [
            name
            for name in names
            if name.startswith("word/")
            and name.endswith(".xml")
            and any(
                marker in name
                for marker in (
                    "document",
                    "header",
                    "footer",
                    "footnotes",
                    "endnotes",
                    "comments",
                    "textboxes",
                )
            )
        ]
        if not xml_names:
            xml_names = [name for name in names if name.endswith(".xml")]
        for name in xml_names:
            info = zf.getinfo(name)
            if info.file_size > XML_ENTRY_CAP:
                continue
            texts.append(xml_text_from_bytes(zf.read(name)))
            if sum(len(t) for t in texts) >= TEXT_CAP:
                break
    return ExtractedText(clean_text("\n".join(texts)), "docx-zip-xml")


def extract_hwpx(path: Path) -> ExtractedText:
    texts: List[str] = []
    if not zipfile.is_zipfile(path):
        try:
            return extract_hwp(path)
        except Exception as exc:
            return ExtractedText("", "hwpx-failed", str(exc))
    with zipfile.ZipFile(path) as zf:
        xml_names = [
            name
            for name in zf.namelist()
            if name.lower().endswith((".xml", ".opf"))
            and not name.lower().startswith(("meta-inf/", "_rels/"))
        ]
        for name in xml_names:
            info = zf.getinfo(name)
            if info.file_size > XML_ENTRY_CAP:
                continue
            texts.append(xml_text_from_bytes(zf.read(name)))
            if sum(len(t) for t in texts) >= TEXT_CAP:
                break
    return ExtractedText(clean_text("\n".join(texts)), "hwpx-zip-xml")


def hwp_record_text(section_data: bytes) -> str:
    parts: List[str] = []
    pos = 0
    data_len = len(section_data)
    while pos + 4 <= data_len:
        header = struct.unpack_from("<I", section_data, pos)[0]
        pos += 4
        tag_id = header & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if pos + 4 > data_len:
                break
            size = struct.unpack_from("<I", section_data, pos)[0]
            pos += 4
        if size < 0 or pos + size > data_len:
            break
        payload = section_data[pos : pos + size]
        pos += size
        if tag_id == 67:
            text = payload.decode("utf-16le", errors="ignore")
            text = text.replace("\r", "\n")
            parts.append(text)
            parts.append("\n")
    return clean_text(" ".join(parts))


def extract_hwp(path: Path) -> ExtractedText:
    ole = CompoundFile(path)
    streams = ole.list_streams()
    if "fileheader" not in streams:
        raise OleError("HWP FileHeader stream not found")
    header = ole.open_stream("FileHeader")
    if b"HWP Document File" not in header[:64]:
        raise OleError("not an HWP document")
    properties = struct.unpack_from("<I", header, 36)[0] if len(header) >= 40 else 0
    compressed = bool(properties & 0x01)
    password_protected = bool(properties & 0x02)
    distribution = bool(properties & 0x04)
    section_names = [
        stream
        for stream in streams
        if stream.lower().startswith("bodytext/section")
    ]
    section_names.sort(key=lambda value: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", value)])
    texts: List[str] = []
    warnings: List[str] = []
    if password_protected:
        warnings.append("password-protected flag set")
    if distribution:
        warnings.append("distribution-document flag set")
    for name in section_names:
        raw = ole.open_stream(name)
        data = raw
        if compressed:
            try:
                data = zlib.decompress(raw, -15)
            except zlib.error:
                try:
                    data = zlib.decompress(raw)
                except zlib.error as exc:
                    warnings.append(f"decompression failed for {name}: {exc}")
                    continue
        texts.append(hwp_record_text(data))
        if sum(len(t) for t in texts) >= TEXT_CAP:
            break
    return ExtractedText(clean_text("\n".join(texts)), "hwp-ole-records", "; ".join(warnings))


PRINTABLE_RUN = re.compile(r"[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ一-龥.,;:!?()\[\]{}<>\"'/\\_\-+*=%&@#|~·ㆍㆍ\s]{4,}")


def extract_binary_strings(path: Path) -> ExtractedText:
    size = path.stat().st_size
    warning = ""
    with path.open("rb") as fh:
        raw = fh.read(FILE_READ_CAP)
    if size > FILE_READ_CAP:
        warning = f"read first {FILE_READ_CAP} bytes of {size}"
    parts: List[str] = []
    seen = set()
    total_chars = 0
    for encoding in ("utf-16le", "utf-16be", "cp949", "utf-8", "latin1"):
        try:
            decoded = raw.decode(encoding, errors="ignore")
        except Exception:
            continue
        for match in PRINTABLE_RUN.finditer(decoded):
            value = clean_text(match.group(0), 600)
            if len(value) < 4 or value in seen:
                continue
            seen.add(value)
            parts.append(value)
            total_chars += len(value)
            if total_chars >= TEXT_CAP:
                break
        if total_chars >= TEXT_CAP:
            break
    return ExtractedText(clean_text(" ".join(parts)), "binary-strings", warning)


def printable_ratio(text: str) -> float:
    if not text:
        return 0.0
    printable = sum(1 for ch in text if ch.isspace() or ord(ch) >= 32)
    return printable / len(text)


def looks_like_text_document(sample: bytes) -> bool:
    if not sample:
        return True
    stripped = sample.lstrip().lower()
    if stripped.startswith((b"{\\rtf", b"<html", b"<!doctype", b"<?xml", b"<w:worddocument")):
        return True
    nul_ratio = sample.count(b"\x00") / max(len(sample), 1)
    if nul_ratio > 0.25:
        try:
            decoded = sample.decode("utf-16le", errors="ignore")
        except Exception:
            decoded = ""
        return len(decoded) > 20 and printable_ratio(decoded) > 0.75
    for encoding in ("utf-8", "cp949"):
        decoded = sample.decode(encoding, errors="ignore")
        if len(decoded) > 20 and printable_ratio(decoded) > 0.85:
            return True
    ascii_printable = sum(
        1 for value in sample if value in (9, 10, 13) or 32 <= value <= 126
    )
    return ascii_printable / max(len(sample), 1) > 0.9


def extract_doc(path: Path) -> ExtractedText:
    try:
        with path.open("rb") as fh:
            sample = fh.read(8192)
        signature = sample[:8]
        if signature == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            try:
                ole = CompoundFile(path)
                stream_texts: List[str] = []
                for stream_name in ole.list_streams():
                    lowered = stream_name.lower()
                    if lowered in {"worddocument", "1table", "0table"}:
                        stream_texts.append(strings_from_bytes(ole.open_stream(stream_name)))
                text = clean_text(" ".join(stream_texts))
                if len(text) >= 120:
                    return ExtractedText(text, "doc-ole-strings")
            except Exception:
                pass
        elif not looks_like_text_document(sample):
            return ExtractedText(
                "",
                "doc-non-document-skipped",
                "not an OLE/RTF/text-like DOC file",
            )
        return extract_binary_strings(path)
    except Exception as exc:
        return ExtractedText("", "doc-failed", str(exc))


def strings_from_bytes(raw: bytes) -> str:
    parts: List[str] = []
    seen = set()
    total_chars = 0
    for encoding in ("utf-16le", "cp949", "utf-8", "latin1"):
        decoded = raw.decode(encoding, errors="ignore")
        for match in PRINTABLE_RUN.finditer(decoded):
            value = clean_text(match.group(0), 600)
            if len(value) < 4 or value in seen:
                continue
            seen.add(value)
            parts.append(value)
            total_chars += len(value)
            if total_chars >= TEXT_CAP:
                return clean_text(" ".join(parts))
    return clean_text(" ".join(parts))


def extract_text(path: Path) -> ExtractedText:
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            return extract_docx(path)
        if suffix == ".hwpx":
            return extract_hwpx(path)
        if suffix == ".hwp":
            return extract_hwp(path)
        if suffix == ".doc":
            return extract_doc(path)
    except zipfile.BadZipFile as exc:
        return ExtractedText("", f"{suffix[1:]}-bad-zip", str(exc))
    except PermissionError as exc:
        return ExtractedText("", f"{suffix[1:]}-permission-denied", str(exc))
    except Exception as exc:
        return ExtractedText("", f"{suffix[1:]}-failed", str(exc))
    return ExtractedText("", "unsupported")


def count_term(text_lower: str, term: str) -> int:
    term_lower = term.lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9 -]*", term_lower):
        pattern = r"(?<![a-z0-9])" + re.escape(term_lower) + r"(?![a-z0-9])"
        return len(re.findall(pattern, text_lower))
    return text_lower.count(term_lower)


def score_terms(text: str, signals: Dict[str, int]) -> Tuple[int, List[str]]:
    if not text:
        return 0, []
    text_lower = text.lower()
    total = 0
    matched: List[str] = []
    for term, weight in signals.items():
        count = count_term(text_lower, term)
        if count:
            total += min(count, 6) * weight
            matched.append(f"{term}:{count}")
    return total, matched


def classify_text(text: str, path_text: str) -> Tuple[int, int, str, int, List[str]]:
    legal_score, matched = score_terms(text, LEGAL_SIGNALS)
    path_score, path_matched = score_terms(path_text, LEGAL_SIGNALS)
    category_scores: List[Tuple[int, str]] = []
    blended_text = f"{text[:TEXT_CAP]} {path_text}"
    for category, signals in CATEGORIES:
        category_score, _ = score_terms(blended_text, signals)
        category_scores.append((category_score, category))
    category_scores.sort(reverse=True)
    best_score, best_category = category_scores[0]
    if best_score <= 0:
        best_category = "99_기타_법률"
    return legal_score, path_score, best_category, best_score, matched + [f"path:{m}" for m in path_matched]


def is_legal_document(legal_score: int, path_score: int, text: str, extraction_warning: str) -> bool:
    if legal_score >= 10:
        return True
    if legal_score >= 5 and path_score >= 4:
        return True
    if not text and path_score >= 14:
        return True
    if extraction_warning and path_score >= 10:
        return True
    return False


def get_windows_drives() -> List[str]:
    if os.name != "nt":
        return ["/"]
    drives: List[str] = []
    kernel32 = ctypes.windll.kernel32
    bitmask = kernel32.GetLogicalDrives()
    for index in range(26):
        if bitmask & (1 << index):
            root = f"{chr(65 + index)}:\\"
            drive_type = kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
            if drive_type in {2, 3, 4}:  # removable, fixed, remote
                try:
                    if os.path.exists(root):
                        drives.append(root)
                except OSError:
                    pass
    return drives


def is_same_or_inside(path: Path, parent: Path) -> bool:
    try:
        path_resolved = path.resolve()
        parent_resolved = parent.resolve()
        return path_resolved == parent_resolved or parent_resolved in path_resolved.parents
    except Exception:
        return str(path).lower().startswith(str(parent).lower())


def normalized_path_prefix(path: Path) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def is_inside_prefix(path_prefix: str, parent_prefix: str) -> bool:
    if path_prefix == parent_prefix:
        return True
    return path_prefix.startswith(parent_prefix.rstrip("\\/") + os.sep)


def iter_candidate_files(
    roots: Sequence[Path], destination: Path, excludes: Sequence[Path]
) -> Iterator[Path]:
    destination_prefix = normalized_path_prefix(destination)
    exclude_prefixes = [normalized_path_prefix(excluded) for excluded in excludes]
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda _err: None):
            current = Path(dirpath)
            current_prefix = normalized_path_prefix(current)
            if is_inside_prefix(current_prefix, destination_prefix):
                dirnames[:] = []
                continue
            if any(is_inside_prefix(current_prefix, excluded) for excluded in exclude_prefixes):
                dirnames[:] = []
                continue
            pruned = []
            for dirname in dirnames:
                if dirname in SKIP_DIR_NAMES:
                    continue
                pruned.append(dirname)
            dirnames[:] = pruned
            for filename in filenames:
                suffix = Path(filename).suffix.lower()
                if suffix in EXTENSIONS:
                    yield current / filename


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    return cleaned or "document"


def unique_destination(destination: Path, category: str, source: Path) -> Path:
    category_dir = destination / category
    category_dir.mkdir(parents=True, exist_ok=True)
    base = safe_filename(source.stem)
    suffix = source.suffix
    candidate = category_dir / f"{base}{suffix}"
    if not candidate.exists():
        return candidate
    digest = hashlib.sha1(str(source).encode("utf-8", errors="ignore")).hexdigest()[:10]
    candidate = category_dir / f"{base}__{digest}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = category_dir / f"{base}__{digest}_{counter}{suffix}"
        counter += 1
    return candidate


def file_modified_iso(path: Path) -> str:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except Exception:
        return ""


def make_excerpt(text: str, length: int = 240) -> str:
    text = clean_text(text, length + 40)
    if len(text) > length:
        return text[:length].rstrip() + "..."
    return text


def copy_with_metadata(source: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination_path)


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def run(args: argparse.Namespace) -> int:
    destination = Path(args.destination)
    destination.mkdir(parents=True, exist_ok=True)

    if args.roots:
        roots = [Path(root) for root in args.roots]
    else:
        roots = [Path(root) for root in get_windows_drives()]
    excludes = [Path(excluded) for excluded in (args.exclude or [])]

    started = dt.datetime.now().isoformat(timespec="seconds")
    legal_rows: List[dict] = []
    all_rows: List[dict] = []
    errors: List[dict] = []
    copied_count = 0
    scanned_count = 0
    legal_count = 0
    last_log = time.time()
    print(f"[start] {started}")
    print(f"[destination] {destination}")
    print("[roots] " + ", ".join(str(root) for root in roots), flush=True)

    for source in iter_candidate_files(roots, destination, excludes):
        scanned_count += 1
        now = time.time()
        if now - last_log >= SCAN_LOG_INTERVAL:
            print(
                f"[progress] scanned={scanned_count} legal={legal_count} copied={copied_count} current={source}",
                flush=True,
            )
            last_log = now
        try:
            stat_result = source.stat()
            extracted = extract_text(source)
            path_text = str(source)
            legal_score, path_score, category, category_score, matched = classify_text(
                extracted.text, path_text
            )
            legal = is_legal_document(
                legal_score, path_score, extracted.text, extracted.warning
            )
            destination_path = ""
            copied = False
            status = "not_legal"
            if legal:
                legal_count += 1
                destination_file = unique_destination(destination, category, source)
                try:
                    copy_with_metadata(source, destination_file)
                    destination_path = str(destination_file)
                    copied = True
                    copied_count += 1
                    status = "copied"
                except Exception as exc:
                    status = f"copy_failed: {exc}"
                    errors.append(
                        {
                            "path": str(source),
                            "error": status,
                            "trace": traceback.format_exc(limit=4),
                        }
                    )
            row = {
                "source_path": str(source),
                "extension": source.suffix.lower(),
                "size": stat_result.st_size,
                "modified": file_modified_iso(source),
                "extraction_method": extracted.method,
                "extraction_warning": extracted.warning,
                "legal_score": legal_score,
                "path_score": path_score,
                "category": category if legal else "",
                "category_score": category_score,
                "matched_terms": "; ".join(matched[:40]),
                "copied": "yes" if copied else "no",
                "destination_path": destination_path,
                "status": status,
                "excerpt": make_excerpt(extracted.text),
            }
            all_rows.append(row)
            if legal:
                legal_rows.append(row)
        except Exception as exc:
            errors.append(
                {
                    "path": str(source),
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=4),
                }
            )

    fields = [
        "source_path",
        "extension",
        "size",
        "modified",
        "extraction_method",
        "extraction_warning",
        "legal_score",
        "path_score",
        "category",
        "category_score",
        "matched_terms",
        "copied",
        "destination_path",
        "status",
        "excerpt",
    ]
    write_csv(destination / "_legal_documents_report.csv", legal_rows, fields)
    write_csv(destination / "_all_candidate_documents_scanned.csv", all_rows, fields)
    write_csv(destination / "_scan_errors.csv", errors, ["path", "error", "trace"])

    category_counts: Dict[str, int] = {}
    for row in legal_rows:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1

    summary_lines = [
        "Legal document classification summary",
        f"Started: {started}",
        f"Finished: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Roots scanned: {', '.join(str(root) for root in roots)}",
        f"Excluded paths: {', '.join(str(path) for path in excludes) if excludes else '(none)'}",
        f"Destination: {destination}",
        f"Candidate files scanned: {scanned_count}",
        f"Legal documents identified: {legal_count}",
        f"Files copied: {copied_count}",
        f"Errors: {len(errors)}",
        "",
        "Category counts:",
    ]
    if category_counts:
        for category in sorted(category_counts):
            summary_lines.append(f"- {category}: {category_counts[category]}")
    else:
        summary_lines.append("- none")
    summary_lines.extend(
        [
            "",
            "Notes:",
            "- Originals were preserved; identified files were copied into category folders.",
            "- DOC/HWP extraction uses local parsers and binary-string fallback where needed.",
            "- Review _scan_errors.csv for inaccessible or unreadable files.",
        ]
    )
    (destination / "_summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")

    print(f"[done] scanned={scanned_count} legal={legal_count} copied={copied_count} errors={len(errors)}")
    for category in sorted(category_counts):
        print(f"[category] {category}={category_counts[category]}")
    print(f"[report] {destination / '_legal_documents_report.csv'}")
    print(f"[summary] {destination / '_summary.txt'}")
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify legal DOC/DOCX/HWP/HWPX files.")
    parser.add_argument(
        "--destination",
        default=DEFAULT_DESTINATION,
        help=f"Destination folder. Default: {DEFAULT_DESTINATION}",
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        help="Root folders or drives to scan. Defaults to all fixed/removable/network drives.",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        help="Folders to skip while scanning.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
