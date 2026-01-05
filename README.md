SCRIPT Overview + How to use

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

---

Workflow:
Add PDFs → Run processor → Run builder → CSV updated

---

- All processed PDFs will be moved to the processed folder, so you can keep adding new PDFs if required.
- quotation_details.csv will keep getting updated with new information from the new PDFs
  (Delete the existing csv to start maaking a new one)
- archive folder will have the date and time stamp for all processed (batched) pdfs.
