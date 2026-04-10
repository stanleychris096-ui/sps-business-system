# Wave and Deployment Notes

## Wave alignment strategy
Use this system as your operational source while preserving the same invoice and estimate numbering already used inside Wave.

Recommended process:
1. Create estimate or invoice in Wave.
2. Copy the exact Wave estimate number or invoice number into the matching job record.
3. Store the Wave IDs when available.
4. Use the same job record for labor, materials, PO costs, expenses, and cash payouts.
5. Run backups weekly or nightly.

## Suggested live deployment path
- Public website stays on Google Sites.
- Business app goes on a protected subdomain such as `portal.stanleyparkingsolutionsllc.com`.
- Use HTTPS only.
- Move from SQLite to PostgreSQL for the live version.
- Add cloud file storage for receipts, signed forms, and job photos.
- Add scheduled backup automation to Google Drive, Dropbox, or S3-compatible storage.

## Recommended modules for your next build phase
- Receipt upload and OCR review
- Daily field reports
- Customer install portal tie-in
- Payroll summary export
- Wave sync or import/export bridge
- Equipment maintenance and fuel log
- Subcontractor compliance portal
