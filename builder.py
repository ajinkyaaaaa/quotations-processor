import os
import csv
import re
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# -----------------------------
# LOAD ENV
# -----------------------------
load_dotenv()

# -----------------------------
# PATHS (ENV + SCRIPT RELATIVE)
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_DIR_ENV = os.getenv("OUTPUT_DIR", "output")
OUTPUT_DIR = (
    OUTPUT_DIR_ENV
    if os.path.isabs(OUTPUT_DIR_ENV)
    else os.path.join(BASE_DIR, OUTPUT_DIR_ENV)
)

ARCHIVE_DIR = os.path.join(OUTPUT_DIR, "archive")

INPUT_FILE = os.path.join(OUTPUT_DIR, "processed_output.txt")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "quotation_details.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# -----------------------------
# LOGGING
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s"
)

# -----------------------------
# CSV CONFIG
# -----------------------------
CSV_COLUMNS = [
    "Sr_no",
    "quotation_number",
    "enquiry",
    "item_no",
    "part_number",
    "part_description",
    "date",
    "reference",
    "customer_code",
    "pdf_name",
]

# -----------------------------
# HELPERS
# -----------------------------
def strip_code_fences(text: str) -> str:
    return text.replace("```", "").strip()


def parse_key_value_block(block: str) -> dict:
    data = {}
    for line in block.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def extract_blocks(text: str, start: str, end: str):
    pattern = re.compile(
        re.escape(start) + r"(.*?)" + re.escape(end),
        re.DOTALL,
    )
    return [m.group(1).strip() for m in pattern.finditer(text)]


def extract_pdf_sections(text: str):
    pattern = re.compile(
        r"={80}\s*PDF FILE:\s*(.*?)\s*\n={80}(.*?)(?=\n={80}\s*PDF FILE:|\Z)",
        re.DOTALL,
    )
    return pattern.findall(text)

# -----------------------------
# MAIN BUILDER
# -----------------------------
def build_csv():
    choice = input("\nRun builder? (y/n): ").strip().lower()

    if choice != "y":
        logging.info("Builder aborted by user.")
        return

    if not os.path.exists(INPUT_FILE):
        logging.warning(
            "No processed_output.txt found in output folder.\n"
            "[End] Please run the processor first.\n"
        )
        return

    logging.info("[Start] Found processed_output.txt — starting CSV build")

    raw_text = Path(INPUT_FILE).read_text(encoding="utf-8")
    raw_text = strip_code_fences(raw_text)

    rows = []
    global_index = 1

    pdf_sections = extract_pdf_sections(raw_text)

    for pdf_name, section in pdf_sections:
        pdf_name = pdf_name.strip()

        # -----------------------------
        # BASE DATA
        # -----------------------------
        base_blocks = extract_blocks(
            section,
            "BASE_DATA_BEGIN",
            "BASE_DATA_END",
        )

        if not base_blocks:
            continue

        base_data = parse_key_value_block(base_blocks[0])

        quotation_number = base_data.get("quotation_number", "-")
        date = base_data.get("date", "-")
        customer_code = base_data.get("customer_code", "-")
        enquiry = base_data.get("your_enquiry", "-")
        reference = base_data.get("your_reference", "-")

        # -----------------------------
        # ITEMS
        # -----------------------------
        item_blocks = extract_blocks(
            section,
            "BEGIN_ITEM",
            "END_ITEM",
        )

        item_count = 1

        for item_block in item_blocks:
            item_data = parse_key_value_block(item_block)

            row = {
                "Sr_no": global_index,
                "quotation_number": quotation_number,
                "enquiry": enquiry,
                "item_no": item_count,
                "part_number": item_data.get("part_number", "-"),
                "part_description": item_data.get("part_description", "-"),
                "date": date,
                "reference": reference,
                "customer_code": customer_code,
                "pdf_name": pdf_name,
            }

            rows.append(row)

            global_index += 1
            item_count += 1

    if not rows:
        logging.warning("No valid rows extracted. CSV not updated.")
        return

    # -----------------------------
    # WRITE / APPEND CSV
    # -----------------------------
    file_exists = os.path.exists(OUTPUT_CSV)

    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)

        if not file_exists:
            writer.writeheader()

        writer.writerows(rows)

    logging.info(
        "CSV updated: %s (%d new rows)",
        OUTPUT_CSV,
        len(rows)
    )

    # -----------------------------
    # ARCHIVE INPUT FILE
    # -----------------------------
    timestamp = datetime.now().strftime("%d_%b_%H%M")
    archived_name = f"processed_{timestamp}.txt"
    archived_path = os.path.join(ARCHIVE_DIR, archived_name)

    os.rename(INPUT_FILE, archived_path)

    logging.info(
        "[Success] Processed file archived as: %s\n",
        archived_path
    )


# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    build_csv()
