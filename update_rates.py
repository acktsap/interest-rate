#!/usr/bin/env python3
"""Fetch missing KOFIA bank-bond AAA rates and append them to rate.csv."""

from __future__ import annotations

import argparse
import csv
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
TERM_6M = "0006"
TERM_5Y = "0500"

CREDIT_ORG_AVERAGE = "A20000"
ORG_NICE_PNI = "A10002"
ORG_KAP = "A10003"

CSV_COLUMNS = ("일자", "6월", "5년")


@dataclass(frozen=True)
class RateRow:
    day: date
    rate_6m: str
    rate_5y: str

    def to_csv_row(self) -> dict[str, str]:
        return {
            "일자": self.day.strftime("%Y/%m/%d"),
            "6월": self.rate_6m,
            "5년": self.rate_5y,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Append missing KOFIA 채권시가평가수익률 rows for "
            "금융채 I(은행채)/무보증/AAA, 6월 and 5년, "
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
        missing = set(CSV_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")

        for row in reader:
            try:
                rows.append(
                    RateRow(
                        day=parse_day(row["일자"]),
                        rate_6m=normalize_rate(row["6월"]),
                        rate_5y=normalize_rate(row["5년"]),
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


def make_proframe_message(dto_body: str) -> bytes:
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


def fetch_missing_rows(start_day: date, end_day: date) -> list[RateRow]:
    dto_body = f"""    <creditEstOrgCd>{CREDIT_ORG_AVERAGE}</creditEstOrgCd>
    <standardDt1>{start_day:%Y%m%d}</standardDt1>
    <standardDt2>{end_day:%Y%m%d}</standardDt2>
    <val1>{ORG_NICE_PNI}</val1>
    <val2>{ORG_KAP}</val2>
    <val3></val3>
    <val4></val4>
    <val5></val5>
    <val31>{BOND_TYPE_BANK_AAA}</val31>
    <val32>{TERM_6M}</val32>
    <val33>{BOND_TYPE_BANK_AAA}</val33>
    <val34>{TERM_5Y}</val34>"""

    request = urllib.request.Request(
        KOFIA_XMLSERVICES_URL,
        data=make_proframe_message(dto_body),
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "interest-rate-updater/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"failed to fetch KOFIA data: {exc}") from exc

    return parse_kofia_rows(payload)


def parse_kofia_rows(payload: bytes) -> list[RateRow]:
    root = ET.fromstring(payload)
    rows: list[RateRow] = []

    for node in root.findall(".//BISBndSrtPrcTrmListDTO/BISBndSrtPrcTrmDTO"):
        raw_day = text_of(node, "standardDt")
        if not raw_day:
            continue

        # With creditEstOrgCd=A20000 and selected agencies A10002/A10003:
        # val6 is the two-company average for the first tenor, val13 for the second.
        rate_6m = normalize_rate(text_of(node, "val6"))
        rate_5y = normalize_rate(text_of(node, "val13"))
        if not rate_6m or not rate_5y:
            continue

        rows.append(RateRow(day=parse_day(raw_day), rate_6m=rate_6m, rate_5y=rate_5y))

    return rows


def text_of(node: ET.Element, tag_name: str) -> str:
    child = node.find(tag_name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


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
    if start_day is None:
        start_day = current_latest + timedelta(days=1) if current_latest else date(2023, 1, 9)

    end_day = parse_day(args.end_date) if args.end_date else today_kst()
    if start_day > end_day:
        if current_latest:
            print(f"Already up to date. Latest local date: {current_latest:%Y-%m-%d}")
        else:
            print(f"Nothing to fetch. Start date {start_day:%Y-%m-%d} is after end date {end_day:%Y-%m-%d}.")
        return 0

    print(f"Latest local date: {current_latest:%Y-%m-%d}" if current_latest else "No local rows.")
    print(f"Fetching KOFIA rows from {start_day:%Y-%m-%d} to {end_day:%Y-%m-%d}.")

    fetched_rows = fetch_missing_rows(start_day, end_day)
    new_rows = [row for row in fetched_rows if row.day not in rows_by_day]

    for row in new_rows:
        rows_by_day[row.day] = row

    if args.dry_run:
        print(f"Dry run: {len(new_rows)} new rows would be added.")
        return 0

    write_csv_rows(csv_path, rows_by_day.values())

    if new_rows:
        newest = max(row.day for row in new_rows)
        oldest = min(row.day for row in new_rows)
        print(f"Added {len(new_rows)} rows to {csv_path} ({oldest:%Y-%m-%d}..{newest:%Y-%m-%d}).")
    else:
        print(f"No new rows found. Wrote {csv_path} with {len(rows_by_day)} rows.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
