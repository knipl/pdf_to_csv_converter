#!/usr/bin/env python3
"""
Command‑line PDF to CSV converter tailored for MBH (formerly Takarék) Netbank statements.

This script scans a directory for PDF files and converts them into CSV files using a
simple text‑extraction and pattern‑matching approach.  It is designed to work with
the PDF account statements issued by MBH Netbank.  Each transaction detail in
the PDF is parsed into a structured record containing:

    * date:     The value date (Értéknap) of the transaction (YYYY-MM-DD)
    * name:     The counterparty name (Címzett neve or Megbízó neve)
    * amount:   Numeric value of the debit/credit (negative for debits)
    * reference:A short description taken from the “Közlemény” line
    * note:     Additional text from the “Megjegyzés” line (optional)
    * id:       Partner ID when present

The resulting CSV file will have a header row with these fields.  Lines that do
not contain all fields are still written, with missing values left blank.

To use this script from your terminal, run:

    python pdf_to_csv_converter.py /path/to/your/downloads

If the directory is omitted it defaults to your Downloads folder (based on
the operating system).  For each PDF file found, a CSV file with the same
basename is created in the same folder.

Dependencies:
    * Poppler’s `pdftotext` utility must be installed and available on your PATH.
      This utility is bundled in many Linux distributions; on macOS you can
      install it via Homebrew (`brew install poppler`).

This script does not require any third‑party Python libraries beyond the
standard library.

Author: OpenAI ChatGPT
Date: 2025‑08‑27
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Tuple  # Compatibility with older Python versions


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Run pdftotext on the given PDF and return the extracted text.

    The function uses the "-layout" option to preserve column alignment which
    helps when splitting fields separated by multiple spaces.  A temporary
    file is created to hold the result.  If pdftotext fails, a RuntimeError
    is raised.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
        tmp_path = Path(tmp.name)
    # Use pdftotext to extract with layout.  Write to temporary file.
    try:
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(tmp_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "pdftotext command not found. Please install poppler-utils (pdftotext)."
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"pdftotext failed for {pdf_path}: {exc}") from exc
    # Read the entire text and remove the temporary file.
    with tmp_path.open("r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        tmp_path.unlink()
    except OSError:
        pass
    return text


def split_label_value(line: str) -> Tuple[str, str]:
    """Split a labelled line into (label, value) based on runs of 2+ spaces.

    Many fields in MBH statements are printed as `label` followed by a large
    number of spaces and then the value.  This helper uses a regular
    expression to identify two or more consecutive whitespace characters and
    split the line around them.  The first segment is treated as the label
    and the remainder (joined) as the value.  Both are stripped of leading
    and trailing whitespace.  If no such delimiter exists, the original line
    is returned as the label with an empty string as the value.
    """
    # Use Unicode aware whitespace splitting (\s includes NBSP and other spaces).
    parts = re.split(r"\s{2,}", line.strip())
    if len(parts) >= 2:
        # label is first part, value is the remainder rejoined in case there were
        # multiple large gaps.
        label = parts[0]
        value = " ".join(parts[1:]).strip()
        return label, value
    return line.strip(), ""


def parse_statement_text(text: str) -> List[Dict[str, str]]:
    """Parse MBH Netbank statement text into a list of transaction dictionaries.

    The parser scans through the text line by line, starting a new
    transaction whenever it encounters a "Címzett neve" or "Megbízó neve"
    label.  It collects certain fields within the transaction until the
    next one starts.  At the end, any incomplete transaction still being
    built is appended to the result list.
    """
    lines = text.splitlines()
    transactions: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue  # skip empty lines
        # Identify the start of a new transaction by the presence of the
        # partner name labels.  Flush the previous transaction if necessary.
        if line.startswith("Címzett neve") or line.startswith("Megbízó neve"):
            # When encountering a new transaction, finalize the previous one
            if current:
                transactions.append(current)
            label, value = split_label_value(raw_line)
            # Create a fresh transaction dictionary.
            current = {
                "name": value,
                "date": "",
                "amount": "",
                "reference": "",
                "note": "",
                "id": "",
            }
            continue
        # If no transaction has been started yet, ignore lines until one is.
        if current is None:
            continue
        # Parse amount lines (debit or credit).  Amounts can include spaces
        # and comma decimal separators; negative numbers for debits.
        if "Jóváírás összege" in line or "Terhelés összege" in line:
            label, value = split_label_value(raw_line)
            # Remove currency (HUF) and spaces.
            # Some statements use non-breaking space (\xa0) as a thousand separator.
            amt_str = value.replace("HUF", "").replace("Ft", "")
            # Replace various types of whitespace with nothing.
            amt_str = re.sub(r"[\s\u00A0]+", "", amt_str)
            # Remove thousands separators (either dot or narrow NBSP) and convert
            # comma decimal separator to period.
            amt_str = amt_str.replace(".", "").replace(",", ".")
            # Attempt to cast to float; if it fails leave as string.
            try:
                amount_value = float(amt_str)
                # Format to preserve sign and decimal places consistently.
                current["amount"] = f"{amount_value:.2f}"
            except ValueError:
                current["amount"] = value
            continue
        # Parse value date.
        if line.startswith("Értéknap"):
            _, value = split_label_value(raw_line)
            # Normalise date by replacing dots with hyphens and trimming trailing dot.
            date_str = value.strip().rstrip(".")
            date_str = date_str.replace(".", "-")
            current["date"] = date_str
            continue
        # Parse comment/reference (Közlemény).
        if line.startswith("Közlemény"):
            _, value = split_label_value(raw_line)
            current["reference"] = value
            continue
        # Parse note (Megjegyzés).
        if line.startswith("Megjegyzés"):
            _, value = split_label_value(raw_line)
            current["note"] = value
            continue
        # Parse partner ID (Partnerek közti egyedi azonosító).
        if line.startswith("Partnerek közti egyedi azonosító"):
            _, value = split_label_value(raw_line)
            current["id"] = value
            continue
    # At the end of parsing, append the final transaction if present.
    if current:
        transactions.append(current)
    return transactions


def _classify_transaction(description: str, amount_str: str) -> str:
    """Classify a transaction based on its textual description and amount.

    This helper implements a simple rule‑based classifier that maps a
    transaction into one of the fixed categories required by the user.  It
    examines keywords in the description (case insensitive) and, where
    relevant, the sign of the amount.  The returned string will be one of
    the following values:

      - "Expense"
      - "Income"
      - "Refund"
      - "Transfer"
      - "Investment - Buy"
      - "Investment - Sell"
      - "Investment - Dividend"
      - "Investment - Capital Gain"
      - "Investment - Capital Loss"

    If no specific rule applies, the function falls back to returning
    "Income" for positive amounts and "Expense" for negative amounts.
    """
    desc = (description or "").lower()
    # Attempt to parse the amount to determine its sign.  If parsing fails
    # default to zero.
    amount = 0.0
    try:
        amount = float(amount_str)
    except Exception:
        pass
    # Refund keywords
    if re.search(r"refund|visszatérítés|visszautalás", desc):
        return "Refund"
    # Transfers between accounts
    if re.search(r"átvezetés|transfer", desc):
        return "Transfer"
    # Investment dividends
    if re.search(r"osztalék|dividend", desc):
        return "Investment - Dividend"
    # Capital gains and losses
    if re.search(r"tőke[\s_-]*nyereség|capital gain|nyereség", desc):
        return "Investment - Capital Gain"
    if re.search(r"veszteség|loss", desc):
        return "Investment - Capital Loss"
    # Investment buys and sells
    if re.search(r"\b(buy|purchase|vétel)\b", desc):
        return "Investment - Buy"
    if re.search(r"\b(sell|eladás)\b", desc):
        return "Investment - Sell"
    # Salary/income
    if re.search(r"/ref/salary|salary|munkabér", desc):
        return "Income"
    # Interest: classify based on sign
    if re.search(r"kamat", desc):
        return "Income" if amount > 0 else "Expense"
    # POS or card purchases are expenses
    if re.search(r"pos|kereskedői|bankkártya|kártya|díja|levonás|szocho|hitel|törlesztés|biztosítás|nyugd", desc):
        return "Expense"
    # Default based on amount sign
    if amount > 0:
        return "Income"
    if amount < 0:
        return "Expense"
    # If zero, categorise as Transfer as a sensible default
    return "Transfer"


def convert_pdf_to_csv(pdf_path: Path, csv_path: Path) -> None:
    """Extract transactions from a PDF statement and write them to a CSV file.

    This function reads the PDF using `pdftotext`, parses each transaction
    with `parse_statement_text`, classifies the transaction into a type,
    and writes a simplified CSV with the following columns:

        date, amount, type, description

    The `description` field is derived from the original reference; if
    the reference is missing then the note is used instead.  The
    classification rules are implemented in `_classify_transaction`.
    """
    text = extract_text_from_pdf(pdf_path)
    records = parse_statement_text(text)
    # Write to CSV with UTF‑8 encoding and newline='' to avoid blank lines on Windows.
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["date", "amount", "type", "description"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            # Combine the original counterparty name with the reference/note.  The
            # previous "name" column is prepended to the description so that
            # details about the payee/payer are retained.  If no name is
            # available, the description consists solely of the reference or
            # note.
            base_desc = (rec.get("reference", "") or rec.get("note", "")).strip()
            name_part = rec.get("name", "").strip()
            if name_part and base_desc:
                description = f"{name_part} - {base_desc}"
            elif name_part:
                description = name_part
            else:
                description = base_desc
            txn_type = _classify_transaction(base_desc, rec.get("amount", "0"))
            writer.writerow(
                {
                    "date": rec.get("date", ""),
                    "amount": rec.get("amount", ""),
                    "type": txn_type,
                    "description": description,
                }
            )


def default_downloads_path() -> Path:
    """Return the path to the user's Downloads directory based on the OS."""
    home = Path.home()
    # Most UNIX systems use ~/Downloads.  On Windows the same is typical.
    return home / "Downloads"


def main(args: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert MBH (Takarék) PDF account statements into CSV files."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=str,
        default=None,
        help="Directory to scan for PDF files (defaults to your Downloads folder)",
    )
    ns = parser.parse_args(args)
    # Determine whether the provided argument is a file or a directory.  If no
    # argument is given, default to the user's Downloads folder.  If a file
    # ending in .pdf is specified, convert just that file.  Otherwise, treat
    # the argument as a directory and convert all PDF files within it.
    target = Path(ns.directory) if ns.directory else default_downloads_path()
    if target.is_file() and target.suffix.lower() == ".pdf":
        # Single file conversion
        csv_path = target.with_suffix(".csv")
        try:
            convert_pdf_to_csv(target, csv_path)
            print(f"Converted {target.name} -> {csv_path.name}")
        except RuntimeError as exc:
            print(f"Failed to convert {target.name}: {exc}", file=sys.stderr)
        return 0
    # Directory processing
    if not target.is_dir():
        print(f"Error: {target} is not a valid directory or PDF file.", file=sys.stderr)
        return 1
    pdf_files = [p for p in target.iterdir() if p.suffix.lower() == ".pdf"]
    if not pdf_files:
        print(f"No PDF files found in {target}.")
        return 0
    for pdf_path in pdf_files:
        csv_path = pdf_path.with_suffix(".csv")
        try:
            convert_pdf_to_csv(pdf_path, csv_path)
            print(f"Converted {pdf_path.name} -> {csv_path.name}")
        except RuntimeError as exc:
            print(f"Failed to convert {pdf_path.name}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())