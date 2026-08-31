#!/usr/bin/env python3
"""Fetch missing KOFIA bank-bond AAA & Treasury bond rates and append/update rate.csv."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.9+ has zoneinfo.
    ZoneInfo = None


KOFIA_XMLSERVICES_URL = "https://www.kofiabond.or.kr/proframeWeb/XMLSERVICES/"

BOND_TYPE_BANK_AAA = "5030110"  # 금융채 I(은행채) / 무보증 / AAA
BOND_TYPE_TREASURY = "1010000"  # 국고채

CREDIT_ORG_AVERAGE = "A20000"
ORG_NICE_PNI = "A10002"
ORG_KAP = "A10003"

CSV_COLUMNS = (
    "일자",
    "금융채 6월",
    "금융채 5년",
    "국채 1년",
    "국채 3년",
    "국채 5년",
    "국채 10년",
)

# Max 4 items allowed per single XML request by KOFIA API
GROUP_BANK = [
    ("bank_6m", BOND_TYPE_BANK_AAA, "0006"),
    ("bank_5y", BOND_TYPE_BANK_AAA, "0500"),
]

GROUP_TREASURY = [
    ("gov_1y", BOND_TYPE_TREASURY, "0100"),
    ("gov_3y", BOND_TYPE_TREASURY, "0300"),
    ("gov_5y", BOND_TYPE_TREASURY, "0500"),
    ("gov_10y", BOND_TYPE_TREASURY, "1000"),
]


@dataclass(frozen=True)
class RateRow:
    day: date
    bank_6m: str = ""
    bank_5y: str = ""
    gov_1y: str = ""
    gov_3y: str = ""
    gov_5y: str = ""
    gov_10y: str = ""

    def is_complete(self) -> bool:
        return bool(
            self.bank_6m
            and self.bank_5y
            and self.gov_1y
            and self.gov_3y
            and self.gov_5y
            and self.gov_10y
        )

    def to_csv_row(self) -> dict[str, str]:
        return {
            "일자": self.day.strftime("%Y/%m/%d"),
            "금융채 6월": self.bank_6m,
            "금융채 5년": self.bank_5y,
            "국채 1년": self.gov_1y,
            "국채 3년": self.gov_3y,
            "국채 5년": self.gov_5y,
            "국채 10년": self.gov_10y,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Append and update KOFIA rates for "
            "금융채 I(은행채)/AAA (6월, 5년) and 국고채 (1년, 3년, 5년, 10년), "
            "using the NICE P&I + KAP two-company average."
        )
    )
    parser.add_argument("--csv", default="rate.csv", help="CSV data file to create/update.")
    parser.add_argument(
        "--start-date",
        help="Override fetch start date. Accepts YYYY-MM-DD, YYYY/MM/DD, or YYYYMMDD.",
    )
    parser.add_argument(
        "--end-date",
        help="Override fetch end date. Defaults to today in Asia/Seoul.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill missing Treasury rates for historical rows (from 2023-01-09 onwards).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report without writing.")
    return parser.parse_args()


def parse_day(value: str | int | float) -> date:
    text = str(value).strip()
    if not text:
        raise ValueError("empty date")

    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    raise ValueError(f"unsupported date format: {value!r}")


def today_kst() -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def normalize_rate(value: object) -> str:
    text = str(value).strip()
    if text in ("", "-"):
        return ""

    try:
        return f"{float(text):.3f}"
    except ValueError:
        return text


def load_existing_rows(csv_path: Path) -> list[RateRow]:
    if csv_path.exists():
        return load_csv_rows(csv_path)

    return []


def load_csv_rows(path: Path) -> list[RateRow]:
    rows: list[RateRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            try:
                # Support legacy column names '6월' and '5년' alongside new '금융채 6월' and '금융채 5년'
                bank_6m = normalize_rate(row.get("금융채 6월") or row.get("6월") or "")
                bank_5y = normalize_rate(row.get("금융채 5년") or row.get("5년") or "")
                gov_1y = normalize_rate(row.get("국채 1년") or "")
                gov_3y = normalize_rate(row.get("국채 3년") or "")
                gov_5y = normalize_rate(row.get("국채 5년") or "")
                gov_10y = normalize_rate(row.get("국채 10년") or "")

                rows.append(
                    RateRow(
                        day=parse_day(row["일자"]),
                        bank_6m=bank_6m,
                        bank_5y=bank_5y,
                        gov_1y=gov_1y,
                        gov_3y=gov_3y,
                        gov_5y=gov_5y,
                        gov_10y=gov_10y,
                    )
                )
            except ValueError as exc:
                raise ValueError(f"invalid row in {path}: {row}") from exc

    return rows


def write_csv_rows(path: Path, rows: Iterable[RateRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(rows, key=lambda row: row.day, reverse=True)

    with NamedTemporaryFile(
        "w",
        encoding="utf-8-sig",
        newline="",
        dir=path.parent,
        delete=False,
    ) as temp_file:
        writer = csv.DictWriter(temp_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in sorted_rows:
            writer.writerow(row.to_csv_row())
        temp_path = Path(temp_file.name)

    temp_path.replace(path)


def make_proframe_message(items: list[tuple[str, str, str]], start_day: date, end_day: date) -> bytes:
    dto_lines = [
        f"    <creditEstOrgCd>{CREDIT_ORG_AVERAGE}</creditEstOrgCd>",
        f"    <standardDt1>{start_day:%Y%m%d}</standardDt1>",
        f"    <standardDt2>{end_day:%Y%m%d}</standardDt2>",
        f"    <val1>{ORG_NICE_PNI}</val1>",
        f"    <val2>{ORG_KAP}</val2>",
        "    <val3></val3>",
        "    <val4></val4>",
        "    <val5></val5>",
    ]
    for idx, (_, b_code, term) in enumerate(items):
        b_tag = f"val{31 + idx * 2}"
        t_tag = f"val{32 + idx * 2}"
        dto_lines.append(f"    <{b_tag}>{b_code}</{b_tag}>")
        dto_lines.append(f"    <{t_tag}>{term}</{t_tag}>")

    dto_body = "\n".join(dto_lines)
    message = f"""<?xml version="1.0" encoding="utf-8"?>
<message>
  <proframeHeader>
    <pfmAppName>BIS-KOFIABOND</pfmAppName>
    <pfmSvcName>BISBndSrtPrcSrchSO</pfmSvcName>
    <pfmFnName>selectTrm</pfmFnName>
  </proframeHeader>
  <systemHeader></systemHeader>
  <BISBndSrtPrcTrmDTO>
{dto_body}
  </BISBndSrtPrcTrmDTO>
</message>
"""
    return message.encode("utf-8")


def parse_kofia_payload(payload: bytes, item_count: int) -> dict[date, list[str]]:
    text = payload.decode("utf-8", errors="replace")
    results: dict[date, list[str]] = {}

    try:
        root = ET.fromstring(text)
        for node in root.findall(".//BISBndSrtPrcTrmListDTO/BISBndSrtPrcTrmDTO"):
            raw_day = text_of(node, "standardDt")
            if not raw_day:
                continue
            day = parse_day(raw_day)
            vals = []
            for i in range(item_count):
                v_idx = 6 + i * 7
                vals.append(normalize_rate(text_of(node, f"val{v_idx}")))
            results[day] = vals
    except Exception:
        # Regex fallback if ElementTree expat is unavailable or fails
        dto_blocks = re.findall(
            r"<BISBndSrtPrcTrmDTO>(.*?)</BISBndSrtPrcTrmDTO>", text, re.DOTALL
        )
        for block in dto_blocks:
            day_match = re.search(r"<standardDt>\s*(\d+)\s*</standardDt>", block)
            if not day_match:
                continue
            day = parse_day(day_match.group(1))
            vals = []
            for i in range(item_count):
                v_idx = 6 + i * 7
                val_match = re.search(rf"<val{v_idx}>\s*(.*?)\s*</val{v_idx}>", block)
                vals.append(normalize_rate(val_match.group(1) if val_match else ""))
            results[day] = vals

    return results


def text_of(node: ET.Element, tag_name: str) -> str:
    child = node.find(tag_name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def fetch_group_range(items: list[tuple[str, str, str]], start_day: date, end_day: date) -> dict[date, list[str]]:
    request = urllib.request.Request(
        KOFIA_XMLSERVICES_URL,
        data=make_proframe_message(items, start_day, end_day),
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "interest-rate-updater/1.0",
        },
        method="POST",
    )

    payload = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                break
        except (urllib.error.URLError, Exception):
            if attempt == 2:
                raise

    if payload is None:
        return {}

    return parse_kofia_payload(payload, len(items))


def fetch_agency_group(agency_cd: str, start_day: date, end_day: date) -> dict[date, list[str]]:
    dto_lines = [
        f"    <creditEstOrgCd>{agency_cd}</creditEstOrgCd>",
        f"    <standardDt1>{start_day:%Y%m%d}</standardDt1>",
        f"    <standardDt2>{end_day:%Y%m%d}</standardDt2>",
        "    <val1></val1>",
        "    <val2></val2>",
        "    <val3></val3>",
        "    <val4></val4>",
        "    <val5></val5>",
        f"    <val31>{BOND_TYPE_TREASURY}</val31>",
        "    <val32>0100</val32>",
        f"    <val33>{BOND_TYPE_TREASURY}</val33>",
        "    <val34>0300</val34>",
        f"    <val35>{BOND_TYPE_TREASURY}</val35>",
        "    <val36>0500</val36>",
        f"    <val37>{BOND_TYPE_TREASURY}</val37>",
        "    <val38>1000</val38>",
    ]
    dto_body = "\n".join(dto_lines)
    message = f"""<?xml version="1.0" encoding="utf-8"?>
<message>
  <proframeHeader>
    <pfmAppName>BIS-KOFIABOND</pfmAppName>
    <pfmSvcName>BISBndSrtPrcSrchSO</pfmSvcName>
    <pfmFnName>selectTrm</pfmFnName>
  </proframeHeader>
  <systemHeader></systemHeader>
  <BISBndSrtPrcTrmDTO>
{dto_body}
  </BISBndSrtPrcTrmDTO>
</message>
"""
    request = urllib.request.Request(
        KOFIA_XMLSERVICES_URL,
        data=message.encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "interest-rate-updater/1.0",
        },
        method="POST",
    )

    payload = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                break
        except (urllib.error.URLError, Exception):
            if attempt == 2:
                raise

    if payload is None:
        return {}

    text = payload.decode("utf-8", errors="replace")
    results: dict[date, list[str]] = {}

    try:
        root = ET.fromstring(text)
        for node in root.findall(".//BISBndSrtPrcTrmListDTO/BISBndSrtPrcTrmDTO"):
            raw_day = text_of(node, "standardDt")
            if not raw_day:
                continue
            day = parse_day(raw_day)
            vals = [
                normalize_rate(text_of(node, "val1")),
                normalize_rate(text_of(node, "val6")),
                normalize_rate(text_of(node, "val11")),
                normalize_rate(text_of(node, "val16")),
            ]
            results[day] = vals
    except Exception:
        dto_blocks = re.findall(
            r"<BISBndSrtPrcTrmDTO>(.*?)</BISBndSrtPrcTrmDTO>", text, re.DOTALL
        )
        for block in dto_blocks:
            day_match = re.search(r"<standardDt>\s*(\d+)\s*</standardDt>", block)
            if not day_match:
                continue
            day = parse_day(day_match.group(1))
            vals = []
            for tag in ("val1", "val6", "val11", "val16"):
                val_match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", block)
                vals.append(normalize_rate(val_match.group(1) if val_match else ""))
            results[day] = vals

    return results



def fetch_all_rates_in_range(start_day: date, end_day: date) -> dict[date, dict[str, str]]:
    """Fetch rates for start_day..end_day in 60-day chunks to prevent connection drops."""
    combined: dict[date, dict[str, str]] = {}
    chunk_days = 60

    cur_start = start_day
    avg_api_start = date(2023, 1, 9)

    while cur_start <= end_day:
        cur_end = min(cur_start + timedelta(days=chunk_days), end_day)

        if cur_end >= avg_api_start:
            # Use pre-computed 2-company average API (A20000) for dates >= 2023-01-09
            req_start = max(cur_start, avg_api_start)
            bank_data = fetch_group_range(GROUP_BANK, req_start, cur_end)
            treasury_data = fetch_group_range(GROUP_TREASURY, req_start, cur_end)

            all_days = set(bank_data.keys()) | set(treasury_data.keys())
            for d in all_days:
                b_vals = bank_data.get(d, ["", ""])
                t_vals = treasury_data.get(d, ["", "", "", ""])

                combined[d] = {
                    "bank_6m": b_vals[0] if len(b_vals) > 0 else "",
                    "bank_5y": b_vals[1] if len(b_vals) > 1 else "",
                    "gov_1y": t_vals[0] if len(t_vals) > 0 else "",
                    "gov_3y": t_vals[1] if len(t_vals) > 1 else "",
                    "gov_5y": t_vals[2] if len(t_vals) > 2 else "",
                    "gov_10y": t_vals[3] if len(t_vals) > 3 else "",
                }

        if cur_start < avg_api_start:
            # For dates < 2023-01-09, fetch Treasury rates via NICE + KAP agency average
            req_end = min(cur_end, avg_api_start - timedelta(days=1))
            nice_data = fetch_agency_group(ORG_NICE_PNI, cur_start, req_end)
            kap_data = fetch_agency_group(ORG_KAP, cur_start, req_end)

            all_days = set(nice_data.keys()) | set(kap_data.keys())
            for d in all_days:
                n_vals = nice_data.get(d, ["", "", "", ""])
                k_vals = kap_data.get(d, ["", "", "", ""])

                t_rates = []
                for i in range(4):
                    nv = float(n_vals[i]) if n_vals[i] and n_vals[i] != "-" else None
                    kv = float(k_vals[i]) if k_vals[i] and k_vals[i] != "-" else None

                    if nv is not None and kv is not None:
                        t_rates.append(f"{(nv + kv) / 2.0:.3f}")
                    elif nv is not None:
                        t_rates.append(f"{nv:.3f}")
                    elif kv is not None:
                        t_rates.append(f"{kv:.3f}")
                    else:
                        t_rates.append("")

                if d not in combined:
                    combined[d] = {
                        "bank_6m": "",
                        "bank_5y": "",
                        "gov_1y": t_rates[0],
                        "gov_3y": t_rates[1],
                        "gov_5y": t_rates[2],
                        "gov_10y": t_rates[3],
                    }
                else:
                    combined[d]["gov_1y"] = t_rates[0]
                    combined[d]["gov_3y"] = t_rates[1]
                    combined[d]["gov_5y"] = t_rates[2]
                    combined[d]["gov_10y"] = t_rates[3]

        cur_start = cur_end + timedelta(days=1)

    return combined


def latest_day(rows: Iterable[RateRow]) -> date | None:
    days = [row.day for row in rows]
    return max(days) if days else None


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv)

    rows = load_existing_rows(csv_path)
    rows_by_day = {row.day: row for row in rows}

    current_latest = latest_day(rows)
    start_day = parse_day(args.start_date) if args.start_date else None
    end_day = parse_day(args.end_date) if args.end_date else today_kst()

    if start_day is None:
        if args.backfill:
            # Backfill earliest available date in rate.csv (or 2000-10-30)
            earliest_in_csv = min(r.day for r in rows) if rows else date(2000, 10, 30)
            start_day = earliest_in_csv
        elif current_latest:
            # Check if current_latest row is incomplete
            latest_row = rows_by_day.get(current_latest)
            if latest_row and not latest_row.is_complete():
                start_day = current_latest
            else:
                start_day = current_latest + timedelta(days=1)
        else:
            start_day = date(2023, 1, 9)

    if start_day > end_day:
        if current_latest:
            print(f"Already up to date. Latest local date: {current_latest:%Y-%m-%d}")
        else:
            print(f"Nothing to fetch. Start date {start_day:%Y-%m-%d} is after end date {end_day:%Y-%m-%d}.")
        return 0

    print(f"Latest local date: {current_latest:%Y-%m-%d}" if current_latest else "No local rows.")
    print(f"Fetching KOFIA rates from {start_day:%Y-%m-%d} to {end_day:%Y-%m-%d}.")

    fetched_data = fetch_all_rates_in_range(start_day, end_day)

    updated_count = 0
    added_count = 0

    for d, rates in fetched_data.items():
        if d in rows_by_day:
            existing = rows_by_day[d]
            new_row = RateRow(
                day=d,
                bank_6m=rates.get("bank_6m") or existing.bank_6m,
                bank_5y=rates.get("bank_5y") or existing.bank_5y,
                gov_1y=rates.get("gov_1y") or existing.gov_1y,
                gov_3y=rates.get("gov_3y") or existing.gov_3y,
                gov_5y=rates.get("gov_5y") or existing.gov_5y,
                gov_10y=rates.get("gov_10y") or existing.gov_10y,
            )
            if new_row != existing:
                rows_by_day[d] = new_row
                updated_count += 1
        else:
            rows_by_day[d] = RateRow(
                day=d,
                bank_6m=rates.get("bank_6m", ""),
                bank_5y=rates.get("bank_5y", ""),
                gov_1y=rates.get("gov_1y", ""),
                gov_3y=rates.get("gov_3y", ""),
                gov_5y=rates.get("gov_5y", ""),
                gov_10y=rates.get("gov_10y", ""),
            )
            added_count += 1

    if args.dry_run:
        print(f"Dry run: {added_count} new rows would be added, {updated_count} rows would be updated.")
        return 0

    write_csv_rows(csv_path, rows_by_day.values())

    print(f"Wrote {csv_path} with {len(rows_by_day)} rows ({added_count} added, {updated_count} updated).")
    return 0



if __name__ == "__main__":
    sys.exit(main())

