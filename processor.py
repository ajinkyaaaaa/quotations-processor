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
- If a field is missing, return "-"
- Preserve original formatting

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
- If a field is missing, return "-"
- Keep original formatting for numbers and currency
- part_description must include ALL descriptive text lines related to the item
- Exclude prices, quantities, delivery time, country of origin, and commodity codes from description

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
def extract_text_from_pdf(pdf_path: str) -> str:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def extract_table_region(full_text: str) -> str:
    if TABLE_START not in full_text or TABLE_END not in full_text:
        raise ValueError("Table boundaries not found")
    return full_text.split(TABLE_START, 1)[1].split(TABLE_END, 1)[0].strip()


def extract_header_region(full_text: str) -> str:
    if TABLE_START not in full_text:
        raise ValueError("Table start boundary not found")
    return full_text.split(TABLE_START, 1)[0].strip()


def split_into_items(table_text: str):
    lines = table_text.split("\n")
    items, current_item = [], []
    pos_pattern = re.compile(r"^\s*\d{1,2},\d")

    for line in lines:
        if pos_pattern.match(line) and current_item:
            items.append("\n".join(current_item).strip())
            current_item = []
        if line.strip():
            current_item.append(line)

    if current_item:
        items.append("\n".join(current_item).strip())

    return items


def is_valid_item(chunk: str) -> bool:
    return bool(re.search(r"\d+[,\.]\d{2}", chunk)) and \
           bool(re.search(r"\d+\s*(pc|pcs|stk)", chunk.lower()))


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
    with open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:
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

                items = [
                    i for i in split_into_items(
                        extract_table_region(full_text)
                    )
                    if is_valid_item(i)
                ]

                logging.info("Found %d item(s)", len(items))

                outfile.write("\n" + "=" * 80 + "\n")
                outfile.write(f"PDF FILE: {pdf_name}\n")
                outfile.write("=" * 80 + "\n\n")
                outfile.write(base_data + "\n\n")

                for idx, item in enumerate(items, start=1):
                    outfile.write(
                        structure_item_with_llm(
                            clean_item_text(item),
                            client
                        ) + "\n\n"
                    )
                logging.info("Processed %d/%d item(s)", idx, len(items))

                # Move processed PDF
                shutil.move(
                    pdf_path,
                    os.path.join(PROCESSED_DIR, pdf_name)
                )

            except Exception as e:
                logging.error("[Failure] Failed processing %s: %s", pdf_name, e)

    logging.info("[Success] Processing completed. Output written to %s\n", OUTPUT_FILE)


# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    main()
