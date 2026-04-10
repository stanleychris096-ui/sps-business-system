# Stanley Parking Solutions Business System v2

This package gives you one system for:
- employee records
- jobs and job assignments
- timesheets tied to jobs
- work orders
- purchase orders
- expenses
- cash-payment tracking with traceable fields
- job costing
- backups and CSV exports
- Wave reference matching fields for customer, estimate, invoice, and bill references

## Default login
- Username: `CSTANLEY`
- Password: `ASPHALT`

## Why this version fits your workflow
This version is built so your internal records can stay aligned with Wave instead of creating a second numbering system. Each job record includes fields for:
- `estimate_number`
- `invoice_number`
- `wave_estimate_id`
- `wave_invoice_id`
- customer `wave_customer_id`
- PO `wave_bill_reference`

That means you can use the same estimate and invoice numbers you already issue in Wave and store them against each job.

## Cash payment control
The `cash_payments` table is designed to trace cash payouts and store:
- payment date
- employee
- job
- related timesheet
- who paid it
- amount
- purpose
- envelope number
- witness name
- notes
- signed receipt status

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
python app.py
```

Then open:
- `http://127.0.0.1:5000`

## Recommended live deployment
Because your public website is on Google Sites, host this app on a secure subdomain such as:
- `portal.stanleyparkingsolutionsllc.com`

Recommended stack:
- Flask app on Render, Railway, or a VPS
- SQLite for MVP, then move to PostgreSQL for production
- nightly backup job that downloads the backup ZIP from `/backups/create`
- private login only for office/admin/field staff

## Website integration
On your Google Site, add buttons or links to:
- Employee Portal
- Admin Dashboard
- Job Costing
- Work Orders
- Purchase Orders

## Next production upgrades
1. Receipt/image uploads to each job and expense
2. PDF generation for work orders, cash receipts, and payroll summaries
3. Daily job reports from the field
4. Role-based permissions for office, foreman, employee, subcontractor
5. Automated Wave sync using your Wave API credentials or Wave Connect export/import workflow
6. Scheduled backup automation to cloud storage
7. Google Sites embedded launcher page

## Important note
This package stores the same numbers you use in Wave, but it does not automatically connect to Wave until API credentials or an import/export workflow is added.
