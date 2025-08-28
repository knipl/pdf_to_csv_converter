# PDF to CSV Converter

_Made by chatGPT v5_

---

## Overview

This repository provides a Python script for converting MBH (formerly Takarék) Netbank PDF account statements into CSV files for easier analysis and record-keeping.

---

## Features

- **Batch Processing:** Scans a directory for PDF statements and converts each to a CSV file.
- **Single File Processing:** converts only a single pdf file.
- **Structured Output:** Extracts transaction details such as:
  - **Date**
  - **Amount**
  - **Description**
- **Simple CSV Format:** Output includes a header row and handles missing fields gracefully.
---

## Requirements

- **Poppler’s `pdftotext` Utility:**  
  Must be installed and available in your system’s PATH.
  - Linux: Usually available via package managers.
  - macOS: Install with Homebrew using  
    ```sh
    brew install poppler
    ```

---

## Usage

1. Place your MBH Netbank PDF statements in a directory (e.g., your Downloads folder).
2. Run the script from your terminal:

    ```sh
    python pdf_to_csv_converter.py /path/to/your/downloads
    ```
OR
    ```sh
    python pdf_to_csv_converter.py /path/to/your/downloads/my_bank_statement.pdf
    ```
    

   - If you omit the directory, it defaults to your Downloads folder.
   - CSV files will be created in the same directory as the PDFs.

---

## Example

| date       | amount   | type    | description                           |
|------------|----------|---------|---------------------------------------|
| 2025-08-01 | -2000.00 | Expense | Grocery Store - Közlemény: Vásárlás   |
| 2025-08-02 | 50000.00 | Income  | Employer Ltd. - Közlemény: Munkabér   |

---
