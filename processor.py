import os
import re
import shutil
import logging
import pdfplumber
from openai import OpenAI
from dotenv import load_dotenv

# -----------------------------
# LOAD ENV
# -----------------------------
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
PDF_FOLDER = os.getenv("PDF_FOLDER")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", 0))
TABLE_START = os.getenv("TABLE_START")
TABLE_END = os.getenv("TABLE_END")

# Alternatives
alt_TABLE_START = os.getenv("ALTERNATIVE_TABLE_START")
alt_TABLE_END = os.getenv("ALTERNATIVE_TABLE_END")

# -----------------------------
# PATHS (ENV + SCRIPT RELATIVE)
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Processed PDFs folder (always next to script)
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")

# Output directory comes from .env (relative or absolute)
OUTPUT_DIR_ENV = os.getenv("OUTPUT_DIR", "output")
OUTPUT_DIR = (
    OUTPUT_DIR_ENV
    if os.path.isabs(OUTPUT_DIR_ENV)
    else os.path.join(BASE_DIR, OUTPUT_DIR_ENV)
)

# Output file name is defined in code
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "processed_output.txt")

# Ensure directories exist
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -----------------------------
# LOGGING
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s"
)

# Silence OpenAI / HTTP noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

# -----------------------------
# PROMPTS
# -----------------------------
BASE_DATA_PROMPT = """
You are extracting header-level metadata from an industrial quotation.

Rules:
- Use ONLY the provided text
- Do NOT infer or guess
- If a field is missing, return ""
- Preserve original formatting
- Quotation number is a 7 digit number

BASE_DATA_BEGIN
date:
quotation_number:
customer_code:
your_enquiry:
your_reference:
BASE_DATA_END

TEXT:
<<<
{header_text}
>>>
"""

PROMPT_TEMPLATE = """
You are extracting structured line-item data from an industrial quotation.

Rules:
- Use ONLY the provided text
- Do NOT infer or guess
- If a field is missing, return None data type (i.e., leave it blank)
- Keep original formatting for numbers and currency
- part_description must include ALL descriptive text lines related to the item
- Exclude prices, quantities, delivery time, country of origin, and commodity codes from description
- Part number can be a 6 digit number of a combination of letters and numbers

BEGIN_ITEM
part_number:
part_description:
part_quantity:
unit_price:
discount:
total_price:
delivery_time:
END_ITEM

ITEM TEXT:
<<<
{item_text}
>>>
"""

# -----------------------------
# CORE FUNCTIONS
# -----------------------------

def remove_existing_pdf_block(output_text: str, pdf_name: str) -> str:
    blocks = re.split(r"(?:\r?\n)?={10,}\r?\nPDF FILE:\s*", output_text)

    if len(blocks) == 1:
        return output_text.strip()

    cleaned = [blocks[0].strip()]  # text before first block

    for block in blocks[1:]:
        # block starts with "<pdf_name>\n=====..."
        if block.startswith(pdf_name):
            continue  # skip this block completely
        cleaned.append("=" * 80 + "\nPDF FILE: " + block.strip())

    return "\n".join([c for c in cleaned if c]).strip()

def upsert_pdf_output(pdf_name: str, new_block: str):
    """
    Ensures only one entry per PDF exists in OUTPUT_FILE.
    If PDF already exists, remove its block and write updated one.
    """
    existing_text = ""

    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_text = f.read()

    # Remove old entry for this pdf if exists
    cleaned_text = remove_existing_pdf_block(existing_text, pdf_name)

    # Append new entry
    if cleaned_text:
        cleaned_text += "\n\n"

    cleaned_text += new_block.strip() + "\n"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(cleaned_text)

def extract_text_from_pdf(pdf_path: str) -> str:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)

def normalize_part_quantity(item_block: str) -> str:
    lines = item_block.splitlines()
    normalized_lines = []

    for line in lines:
        if line.lower().startswith("part_quantity:"):
            key, value = line.split(":", 1)
            qty = value.strip()

            # If quantity exists and has no unit → append " pc"
            if qty and not re.search(r"\b(pc|pcs|stk)\b", qty.lower()):
                if re.fullmatch(r"\d+", qty):
                    qty = f"{qty} pc"

            normalized_lines.append(f"{key}: {qty}")
        else:
            normalized_lines.append(line)

    return "\n".join(normalized_lines)


def is_fully_empty_item(item_block: str) -> bool:
    """
    Returns True if ALL fields are empty, "", or None.
    """
    for line in item_block.splitlines():
        if ":" in line:
            _, value = line.split(":", 1)
            value = value.strip().lower()

            if value not in ("", '""', "none", "null"):
                return False

    return True


# def extract_table_region(full_text: str) -> str:
#     if TABLE_START not in full_text or TABLE_END not in full_text:
#         raise ValueError("Table boundaries not found")
#     return full_text.split(TABLE_START, 1)[1].split(TABLE_END, 1)[0].strip()

def extract_table_region(full_text: str) -> str:
    # Choose start token
    if TABLE_START and TABLE_START in full_text:
        start_token = TABLE_START
    elif alt_TABLE_START and alt_TABLE_START in full_text:
        start_token = alt_TABLE_START
    else:
        raise ValueError("Table start boundary not found (TABLE_START or ALTERNATIVE_TABLE_START)")

    # Choose end token
    if TABLE_END and TABLE_END in full_text:
        end_token = TABLE_END
    elif alt_TABLE_END and alt_TABLE_END in full_text:
        end_token = alt_TABLE_END
    else:
        raise ValueError("Table end boundary not found (TABLE_END or ALTERNATIVE_TABLE_END)")

    return full_text.split(start_token, 1)[1].split(end_token, 1)[0].strip()



def is_table_header_block(block: str) -> bool:
    header_markers = [
        "Pos. Item/Description",
        "Quantity Price",
        "Amount in EUR",
    ]
    block_lower = block.lower()
    return all(h.lower() in block_lower for h in header_markers)


# def extract_header_region(full_text: str) -> str:
#     if TABLE_START not in full_text:
#         raise ValueError("Table start boundary not found")
#     return full_text.split(TABLE_START, 1)[0].strip()

def extract_header_region(full_text: str) -> str:
    if TABLE_START and TABLE_START in full_text:
        start_token = TABLE_START
    elif alt_TABLE_START and alt_TABLE_START in full_text:
        start_token = alt_TABLE_START
    else:
        raise ValueError("Table start boundary not found (TABLE_START or ALTERNATIVE_TABLE_START)")

    return full_text.split(start_token, 1)[0].strip()

def split_into_items(table_text: str):
    lines = table_text.split("\n")
    items, current_item = [], []
    pos_pattern = re.compile(r"^\s*\d{1,3}([.,]\d+)?\s+")

    for line in lines:
        if pos_pattern.match(line) and current_item:
            items.append("\n".join(current_item).strip())
            current_item = []
        if line.strip():
            current_item.append(line)

    if current_item:
        items.append("\n".join(current_item).strip())

    return items

# Removing this because it was filtering out valid items in some cases
# def is_valid_item(chunk: str) -> bool:
#     return bool(re.search(r"\d+[,\.]\d{2}", chunk)) and \
#            bool(re.search(r"\d+\s*(pc|pcs|stk)", chunk.lower()))

def strip_code_fences(text: str) -> str:
    """
    Removes markdown code fences like:
    ```plaintext
    ```
    ```python
    ```
    """
    text = re.sub(r"```[a-zA-Z]*", "", text)  # remove ```plaintext etc
    text = text.replace("```", "")
    return text.strip()

def normalize_none_fields(item_block: str) -> str:
    lines = []

    for line in item_block.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)

            if value.strip().lower() in ("none", "null"):
                line = f"{key}:"

        lines.append(line)

    return "\n".join(lines)


def clean_item_text(item_text: str) -> str:
    return "\n".join(
        line for line in item_text.split("\n")
        if not line.lower().startswith(("com.-code", "country of origin"))
    )


def structure_item_with_llm(item_text: str, client: OpenAI) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(item_text=item_text)}],
        temperature=TEMPERATURE
    )
    return response.choices[0].message.content.strip()


def extract_base_data_with_llm(header_text: str, client: OpenAI) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": BASE_DATA_PROMPT.format(header_text=header_text)}],
        temperature=TEMPERATURE
    )
    return response.choices[0].message.content.strip()

# -----------------------------
# MAIN PIPELINE
# -----------------------------
def main():
    choice = input("\nRun processor? (y/n): ").strip().lower()

    if choice != "y":
        logging.info("Process aborted by user.")
        return

    if not PDF_FOLDER or not os.path.isdir(PDF_FOLDER):
        logging.error("Invalid or missing PDF_FOLDER in .env")
        return

    client = OpenAI(api_key=API_KEY)
    pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")]

    if not pdf_files:
        logging.warning("[End] No PDFs found in folder.\n")
        return

    logging.info("[Start] Found %d PDFs", len(pdf_files))

    count = 1
    for pdf_name in pdf_files:
        pdf_path = os.path.join(PDF_FOLDER, pdf_name)
        logging.info(f"[{count}/{len(pdf_files)}] Processing PDF: %s", pdf_name)
        count += 1
        try:
            full_text = extract_text_from_pdf(pdf_path)

            base_data = extract_base_data_with_llm(
                extract_header_region(full_text),
                client
            )

            block = "\n" + "=" * 80 + "\n"
            block += f"PDF FILE: {pdf_name}\n"
            block += "=" * 80 + "\n\n"
            block += strip_code_fences(base_data) + "\n\n"

            raw_items = split_into_items(
                extract_table_region(full_text)
            )

            valid_items = []

            for item in raw_items:
                raw_item = strip_code_fences(
                    structure_item_with_llm(
                        clean_item_text(item),
                        client
                    )
                )
                normalized_item = normalize_part_quantity(raw_item)
                normalized_item = normalize_none_fields(normalized_item)

                if not is_fully_empty_item(normalized_item):
                    valid_items.append(normalized_item)

            logging.info(
                "Extracted %d valid item(s)",
                len(valid_items)
            )

            # Write output
            for item in valid_items:
                block += item + "\n\n"

            upsert_pdf_output(pdf_name, block)

            logging.info("Processed %d item(s)", len(valid_items))

            # Move processed PDF
            shutil.move(
                pdf_path,
                os.path.join(PROCESSED_DIR, pdf_name)
            )

        except Exception as e:
            logging.error("[Failure] Failed processing %s: %s", pdf_name, e)

    logging.info(">> Executed. Output written to %s\n", OUTPUT_FILE)


# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    main()
