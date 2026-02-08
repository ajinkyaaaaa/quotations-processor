import pdfplumber

pdf_path = r"C:\Users\Ajinkya\Desktop\Projects\quotations-processor\quotations\1007989_VIKAS.pdf"

def extract_text_from_pdf(pdf_path: str) -> str:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text:
                pages.append(f"\n--- PAGE {i} ---\n{text}")
            else:
                pages.append(f"\n--- PAGE {i} ---\n[NO TEXT FOUND]")
    return "\n".join(pages)

text = extract_text_from_pdf(pdf_path)
print(text)
