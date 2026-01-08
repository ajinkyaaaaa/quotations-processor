--> Project Overview

Quotation processor for VISPL

This project extracts structured data from industrial quotation PDFs and converts it into a consolidated CSV using a two-step terminal workflow.

--> Project Structure

quotations-processor/
│
├── quotation_processor.py # PDF → structured text
├── build_excel.py # structured text → CSV
├── requirements.txt
├── .env # environment config (ignored by git)
├── .gitignore
│
├── output/
│ ├── quotation_details.csv
│ └── archive/
│
├── processed/ # processed PDFs
├── quotation/ # input quotation PDFs

--> Workflow
Add PDFs → Run processor → Run builder → CSV updated

--> Notes & Behavior

All processed PDFs are automatically moved to the processed/ folder
(you can keep adding new PDFs to the input folder)

quotation_details.csv is continuously updated with data from newly processed PDFs
(delete the CSV if you want to start fresh)

The archive/ folder stores timestamped processed text files for each batch run,
providing a clear audit trail

Setup + Run:

1. add pdf folder and the path of that in the .env
2. activate venv
3. run processor -> run builder
