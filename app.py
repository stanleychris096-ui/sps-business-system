from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_file
import sqlite3, os, hashlib, csv, io, zipfile, shutil, tempfile
from datetime import datetime, date
from functools import wraps

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'sps_business.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
os.makedirs(BACKUP_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'CHANGE-ME-SPS-SECRET')


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def now_ts() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def generate_number(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def init_db():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.executescript('''
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        mailing_address TEXT,
        hourly_rate REAL DEFAULT 0,
        cash_rate REAL DEFAULT 0,
        position TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        employee_id INTEGER,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(employee_id) REFERENCES employees(id)
    );

    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT NOT NULL,
        contact_name TEXT,
        phone TEXT,
        email TEXT,
        billing_address TEXT,
        city TEXT,
        state TEXT,
        zip TEXT,
        notes TEXT,
        wave_customer_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_number TEXT UNIQUE NOT NULL,
        customer_id INTEGER NOT NULL,
        job_name TEXT NOT NULL,
        service_type TEXT,
        status TEXT DEFAULT 'Open',
        site_address TEXT,
        city TEXT,
        state TEXT,
        zip TEXT,
        estimate_number TEXT,
        invoice_number TEXT,
        wave_estimate_id TEXT,
        wave_invoice_id TEXT,
        contract_amount REAL DEFAULT 0,
        estimated_cost REAL DEFAULT 0,
        start_date TEXT,
        end_date TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(customer_id) REFERENCES customers(id)
    );

    CREATE TABLE IF NOT EXISTS job_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        employee_id INTEGER NOT NULL,
        assigned_date TEXT,
        role_on_job TEXT,
        FOREIGN KEY(job_id) REFERENCES jobs(id),
        FOREIGN KEY(employee_id) REFERENCES employees(id)
    );

    CREATE TABLE IF NOT EXISTS timesheets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        job_id INTEGER NOT NULL,
        work_date TEXT NOT NULL,
        time_in TEXT,
        time_out TEXT,
        total_hours REAL DEFAULT 0,
        pay_type TEXT DEFAULT 'hourly',
        pay_rate REAL DEFAULT 0,
        labor_cost REAL DEFAULT 0,
        notes TEXT,
        approved INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(employee_id) REFERENCES employees(id),
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    );

    CREATE TABLE IF NOT EXISTS work_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_order_no TEXT UNIQUE NOT NULL,
        job_id INTEGER NOT NULL,
        issue_date TEXT,
        requested_by TEXT,
        scope_of_work TEXT,
        status TEXT DEFAULT 'Open',
        scheduled_date TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    );

    CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        po_number TEXT UNIQUE NOT NULL,
        job_id INTEGER,
        vendor_name TEXT NOT NULL,
        po_date TEXT,
        item_description TEXT,
        quantity REAL DEFAULT 1,
        unit_cost REAL DEFAULT 0,
        total_cost REAL DEFAULT 0,
        payment_status TEXT DEFAULT 'Unpaid',
        wave_bill_reference TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    );

    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        expense_date TEXT,
        category TEXT,
        vendor_name TEXT,
        description TEXT,
        amount REAL DEFAULT 0,
        payment_method TEXT DEFAULT 'card',
        payment_reference TEXT,
        entered_by TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    );

    CREATE TABLE IF NOT EXISTS cash_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_date TEXT NOT NULL,
        employee_id INTEGER,
        job_id INTEGER,
        related_timesheet_id INTEGER,
        paid_by TEXT,
        amount REAL NOT NULL,
        purpose TEXT NOT NULL,
        envelope_number TEXT,
        witness_name TEXT,
        notes TEXT,
        receipt_signed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(employee_id) REFERENCES employees(id),
        FOREIGN KEY(job_id) REFERENCES jobs(id),
        FOREIGN KEY(related_timesheet_id) REFERENCES timesheets(id)
    );

    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        doc_type TEXT NOT NULL,
        filename TEXT NOT NULL,
        storage_path TEXT,
        uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS system_backups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        notes TEXT
    );
    ''')

    cur.execute('SELECT COUNT(*) FROM employees')
    if cur.fetchone()[0] == 0:
        cur.execute('''INSERT INTO employees
            (first_name, last_name, phone, email, hourly_rate, cash_rate, position)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            ('Christopher', 'Stanley', '7652834899', 'cstanley@stanleyparkingsolutionsllc.com', 0, 0, 'Owner/Admin'))
        employee_id = cur.lastrowid
        cur.execute('INSERT INTO users (username,password_hash,role,employee_id) VALUES (?,?,?,?)',
                    ('CSTANLEY', hash_password('ASPHALT'), 'admin', employee_id))
    db.commit()
    db.close()


def query_all(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def query_one(sql, params=()):
    return get_db().execute(sql, params).fetchone()


@app.route('/')
def home():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().upper()
        password = request.form.get('password', '')
        user = query_one('SELECT * FROM users WHERE username=? AND is_active=1', (username,))
        if user and user['password_hash'] == hash_password(password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['employee_id'] = user['employee_id']
            return redirect(url_for('dashboard'))
        flash('Invalid login.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required()
def dashboard():
    db = get_db()
    stats = {
        'employees': query_one('SELECT COUNT(*) c FROM employees WHERE active=1')['c'],
        'open_jobs': query_one("SELECT COUNT(*) c FROM jobs WHERE status IN ('Open','Scheduled','In Progress')")['c'],
        'unpaid_pos': query_one("SELECT COUNT(*) c FROM purchase_orders WHERE payment_status!='Paid'")['c'],
        'labor_cost': query_one('SELECT ROUND(COALESCE(SUM(labor_cost),0),2) c FROM timesheets')['c'],
        'cash_paid': query_one('SELECT ROUND(COALESCE(SUM(amount),0),2) c FROM cash_payments')['c'],
        'expense_total': query_one('SELECT ROUND(COALESCE(SUM(amount),0),2) c FROM expenses')['c'],
    }
    jobs = db.execute('''
        SELECT j.*, c.customer_name,
               ROUND(COALESCE((SELECT SUM(labor_cost) FROM timesheets t WHERE t.job_id=j.id),0),2) labor_cost,
               ROUND(COALESCE((SELECT SUM(total_cost) FROM purchase_orders p WHERE p.job_id=j.id),0),2) po_cost,
               ROUND(COALESCE((SELECT SUM(amount) FROM expenses e WHERE e.job_id=j.id),0),2) expense_cost,
               ROUND(COALESCE((SELECT SUM(amount) FROM cash_payments cp WHERE cp.job_id=j.id),0),2) cash_cost
        FROM jobs j
        JOIN customers c ON c.id=j.customer_id
        ORDER BY j.id DESC LIMIT 10
    ''').fetchall()
    return render_template('dashboard.html', stats=stats, jobs=jobs)


@app.route('/employees', methods=['GET', 'POST'])
@login_required('admin')
def employees():
    db = get_db()
    if request.method == 'POST':
        first_name = request.form['first_name'].strip()
        last_name = request.form['last_name'].strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('mailing_address', '').strip()
        hourly_rate = float(request.form.get('hourly_rate') or 0)
        cash_rate = float(request.form.get('cash_rate') or 0)
        position = request.form.get('position', '').strip()
        username = last_name.upper()
        temp_password = request.form.get('temp_password') or 'STANLEY123'
        cur = db.execute('''INSERT INTO employees
            (first_name,last_name,phone,email,mailing_address,hourly_rate,cash_rate,position)
            VALUES (?,?,?,?,?,?,?,?)''',
            (first_name,last_name,phone,email,address,hourly_rate,cash_rate,position))
        employee_id = cur.lastrowid
        try:
            db.execute('INSERT INTO users (username,password_hash,role,employee_id) VALUES (?,?,?,?)',
                       (username, hash_password(temp_password), 'employee', employee_id))
            db.commit()
            flash(f'Employee added. Login username: {username}', 'success')
        except sqlite3.IntegrityError:
            db.commit()
            flash('Employee added, but user login already exists for that last name.', 'warning')
        return redirect(url_for('employees'))
    rows = query_all('SELECT * FROM employees ORDER BY id DESC')
    return render_template('employees.html', employees=rows)


@app.route('/customers', methods=['GET', 'POST'])
@login_required()
def customers():
    db = get_db()
    if request.method == 'POST':
        db.execute('''INSERT INTO customers
            (customer_name,contact_name,phone,email,billing_address,city,state,zip,notes,wave_customer_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (request.form['customer_name'], request.form.get('contact_name'), request.form.get('phone'),
             request.form.get('email'), request.form.get('billing_address'), request.form.get('city'),
             request.form.get('state'), request.form.get('zip'), request.form.get('notes'), request.form.get('wave_customer_id')))
        db.commit()
        flash('Customer added.', 'success')
        return redirect(url_for('customers'))
    rows = query_all('SELECT * FROM customers ORDER BY id DESC')
    return render_template('customers.html', customers=rows)


@app.route('/jobs', methods=['GET', 'POST'])
@login_required()
def jobs():
    db = get_db()
    if request.method == 'POST':
        job_number = request.form.get('job_number') or generate_number('JOB')
        db.execute('''INSERT INTO jobs
            (job_number,customer_id,job_name,service_type,status,site_address,city,state,zip,
             estimate_number,invoice_number,wave_estimate_id,wave_invoice_id,contract_amount,estimated_cost,
             start_date,end_date,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (job_number, request.form['customer_id'], request.form['job_name'], request.form.get('service_type'),
             request.form.get('status') or 'Open', request.form.get('site_address'), request.form.get('city'),
             request.form.get('state'), request.form.get('zip'), request.form.get('estimate_number'),
             request.form.get('invoice_number'), request.form.get('wave_estimate_id'), request.form.get('wave_invoice_id'),
             float(request.form.get('contract_amount') or 0), float(request.form.get('estimated_cost') or 0),
             request.form.get('start_date'), request.form.get('end_date'), request.form.get('notes')))
        db.commit()
        flash('Job created.', 'success')
        return redirect(url_for('jobs'))
    jobs = query_all('''SELECT j.*, c.customer_name FROM jobs j JOIN customers c ON c.id=j.customer_id ORDER BY j.id DESC''')
    customers = query_all('SELECT * FROM customers ORDER BY customer_name')
    return render_template('jobs.html', jobs=jobs, customers=customers)


@app.route('/assignments', methods=['POST'])
@login_required()
def assignments():
    db = get_db()
    db.execute('INSERT INTO job_assignments (job_id, employee_id, assigned_date, role_on_job) VALUES (?,?,?,?)',
               (request.form['job_id'], request.form['employee_id'], request.form.get('assigned_date') or date.today().isoformat(), request.form.get('role_on_job')))
    db.commit()
    flash('Employee assigned to job.', 'success')
    return redirect(url_for('jobs'))


@app.route('/timesheets', methods=['GET', 'POST'])
@login_required()
def timesheets():
    db = get_db()
    if request.method == 'POST':
        employee_id = int(request.form['employee_id'])
        job_id = int(request.form['job_id'])
        total_hours = float(request.form.get('total_hours') or 0)
        pay_type = request.form.get('pay_type') or 'hourly'
        employee = query_one('SELECT * FROM employees WHERE id=?', (employee_id,))
        pay_rate = employee['cash_rate'] if pay_type == 'cash' and employee['cash_rate'] else employee['hourly_rate']
        labor_cost = round(total_hours * float(pay_rate or 0), 2)
        db.execute('''INSERT INTO timesheets
            (employee_id,job_id,work_date,time_in,time_out,total_hours,pay_type,pay_rate,labor_cost,notes,approved)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (employee_id, job_id, request.form['work_date'], request.form.get('time_in'), request.form.get('time_out'),
             total_hours, pay_type, pay_rate, labor_cost, request.form.get('notes'), 1 if request.form.get('approved') else 0))
        db.commit()
        flash('Timesheet saved.', 'success')
        return redirect(url_for('timesheets'))
    rows = query_all('''SELECT t.*, e.first_name || ' ' || e.last_name employee_name, j.job_number
                        FROM timesheets t JOIN employees e ON e.id=t.employee_id JOIN jobs j ON j.id=t.job_id
                        ORDER BY t.id DESC''')
    employees = query_all('SELECT * FROM employees WHERE active=1 ORDER BY last_name, first_name')
    jobs = query_all("SELECT * FROM jobs WHERE status != 'Closed' ORDER BY job_number")
    return render_template('timesheets.html', rows=rows, employees=employees, jobs=jobs)


@app.route('/work-orders', methods=['GET', 'POST'])
@login_required()
def work_orders():
    db = get_db()
    if request.method == 'POST':
        no = request.form.get('work_order_no') or generate_number('WO')
        db.execute('''INSERT INTO work_orders (work_order_no, job_id, issue_date, requested_by, scope_of_work, status, scheduled_date, notes)
                      VALUES (?,?,?,?,?,?,?,?)''',
                   (no, request.form['job_id'], request.form.get('issue_date'), request.form.get('requested_by'),
                    request.form.get('scope_of_work'), request.form.get('status') or 'Open', request.form.get('scheduled_date'), request.form.get('notes')))
        db.commit()
        flash('Work order saved.', 'success')
        return redirect(url_for('work_orders'))
    rows = query_all('''SELECT w.*, j.job_number FROM work_orders w JOIN jobs j ON j.id=w.job_id ORDER BY w.id DESC''')
    jobs = query_all('SELECT * FROM jobs ORDER BY job_number')
    return render_template('work_orders.html', rows=rows, jobs=jobs)


@app.route('/purchase-orders', methods=['GET', 'POST'])
@login_required()
def purchase_orders():
    db = get_db()
    if request.method == 'POST':
        po_number = request.form.get('po_number') or generate_number('PO')
        qty = float(request.form.get('quantity') or 0)
        unit_cost = float(request.form.get('unit_cost') or 0)
        total_cost = round(qty * unit_cost, 2)
        db.execute('''INSERT INTO purchase_orders
            (po_number,job_id,vendor_name,po_date,item_description,quantity,unit_cost,total_cost,payment_status,wave_bill_reference,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (po_number, request.form.get('job_id') or None, request.form['vendor_name'], request.form.get('po_date'),
             request.form.get('item_description'), qty, unit_cost, total_cost, request.form.get('payment_status') or 'Unpaid',
             request.form.get('wave_bill_reference'), request.form.get('notes')))
        db.commit()
        flash('Purchase order saved.', 'success')
        return redirect(url_for('purchase_orders'))
    rows = query_all('''SELECT p.*, j.job_number FROM purchase_orders p LEFT JOIN jobs j ON j.id=p.job_id ORDER BY p.id DESC''')
    jobs = query_all('SELECT * FROM jobs ORDER BY job_number')
    return render_template('purchase_orders.html', rows=rows, jobs=jobs)


@app.route('/expenses', methods=['GET', 'POST'])
@login_required()
def expenses():
    db = get_db()
    if request.method == 'POST':
        db.execute('''INSERT INTO expenses
            (job_id,expense_date,category,vendor_name,description,amount,payment_method,payment_reference,entered_by,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (request.form.get('job_id') or None, request.form.get('expense_date'), request.form.get('category'),
             request.form.get('vendor_name'), request.form.get('description'), float(request.form.get('amount') or 0),
             request.form.get('payment_method'), request.form.get('payment_reference'), session.get('username'), request.form.get('notes')))
        db.commit()
        flash('Expense saved.', 'success')
        return redirect(url_for('expenses'))
    rows = query_all('''SELECT e.*, j.job_number FROM expenses e LEFT JOIN jobs j ON j.id=e.job_id ORDER BY e.id DESC''')
    jobs = query_all('SELECT * FROM jobs ORDER BY job_number')
    return render_template('expenses.html', rows=rows, jobs=jobs)


@app.route('/cash-payments', methods=['GET', 'POST'])
@login_required()
def cash_payments():
    db = get_db()
    if request.method == 'POST':
        db.execute('''INSERT INTO cash_payments
            (payment_date,employee_id,job_id,related_timesheet_id,paid_by,amount,purpose,envelope_number,witness_name,notes,receipt_signed)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (request.form['payment_date'], request.form.get('employee_id') or None, request.form.get('job_id') or None,
             request.form.get('related_timesheet_id') or None, request.form.get('paid_by'), float(request.form.get('amount') or 0),
             request.form.get('purpose'), request.form.get('envelope_number'), request.form.get('witness_name'),
             request.form.get('notes'), 1 if request.form.get('receipt_signed') else 0))
        db.commit()
        flash('Cash payment saved and traceable.', 'success')
        return redirect(url_for('cash_payments'))
    rows = query_all('''SELECT cp.*, 
                               COALESCE(e.first_name || ' ' || e.last_name, '') employee_name,
                               COALESCE(j.job_number, '') job_number
                        FROM cash_payments cp
                        LEFT JOIN employees e ON e.id=cp.employee_id
                        LEFT JOIN jobs j ON j.id=cp.job_id
                        ORDER BY cp.id DESC''')
    employees = query_all('SELECT * FROM employees ORDER BY last_name')
    jobs = query_all('SELECT * FROM jobs ORDER BY job_number')
    timesheets = query_all('''SELECT t.id, j.job_number, e.first_name || ' ' || e.last_name employee_name, t.work_date, t.total_hours
                              FROM timesheets t JOIN employees e ON e.id=t.employee_id JOIN jobs j ON j.id=t.job_id
                              ORDER BY t.id DESC LIMIT 100''')
    return render_template('cash_payments.html', rows=rows, employees=employees, jobs=jobs, timesheets=timesheets)


@app.route('/job-costing')
@login_required()
def job_costing():
    rows = query_all('''
        SELECT j.job_number, j.job_name, c.customer_name, j.contract_amount,
               ROUND(COALESCE((SELECT SUM(labor_cost) FROM timesheets t WHERE t.job_id=j.id),0),2) labor_cost,
               ROUND(COALESCE((SELECT SUM(total_cost) FROM purchase_orders p WHERE p.job_id=j.id),0),2) po_cost,
               ROUND(COALESCE((SELECT SUM(amount) FROM expenses e WHERE e.job_id=j.id),0),2) expense_cost,
               ROUND(COALESCE((SELECT SUM(amount) FROM cash_payments cp WHERE cp.job_id=j.id),0),2) cash_cost
        FROM jobs j JOIN customers c ON c.id=j.customer_id
        ORDER BY j.id DESC
    ''')
    enriched = []
    for r in rows:
        total = round(r['labor_cost'] + r['po_cost'] + r['expense_cost'] + r['cash_cost'], 2)
        gross_profit = round((r['contract_amount'] or 0) - total, 2)
        enriched.append({**dict(r), 'total_cost': total, 'gross_profit': gross_profit})
    return render_template('job_costing.html', rows=enriched)


@app.route('/backups')
@login_required('admin')
def backups():
    rows = query_all('SELECT * FROM system_backups ORDER BY id DESC')
    return render_template('backups.html', rows=rows)


@app.route('/backups/create')
@login_required('admin')
def create_backup():
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_name = f'sps_backup_{stamp}.zip'
    zip_path = os.path.join(BACKUP_DIR, zip_name)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(DB_PATH):
            zf.write(DB_PATH, arcname='sps_business.db')
        csv_tables = ['employees', 'customers', 'jobs', 'job_assignments', 'timesheets', 'work_orders', 'purchase_orders', 'expenses', 'cash_payments']
        db = get_db()
        for table in csv_tables:
            data = db.execute(f'SELECT * FROM {table}').fetchall()
            output = io.StringIO()
            writer = csv.writer(output)
            if data:
                writer.writerow(data[0].keys())
                for row in data:
                    writer.writerow(list(row))
            else:
                cols = [c[1] for c in db.execute(f'PRAGMA table_info({table})').fetchall()]
                writer.writerow(cols)
            zf.writestr(f'exports/{table}.csv', output.getvalue())
    db = get_db()
    db.execute('INSERT INTO system_backups (file_name, file_path, notes) VALUES (?,?,?)', (zip_name, zip_path, 'Manual backup'))
    db.commit()
    return send_file(zip_path, as_attachment=True)


@app.route('/export/<table_name>')
@login_required()
def export_table(table_name):
    allowed = {'employees', 'customers', 'jobs', 'timesheets', 'work_orders', 'purchase_orders', 'expenses', 'cash_payments'}
    if table_name not in allowed:
        flash('Invalid export.', 'danger')
        return redirect(url_for('dashboard'))
    db = get_db()
    rows = db.execute(f'SELECT * FROM {table_name}').fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(list(row))
    else:
        cols = [c[1] for c in db.execute(f'PRAGMA table_info({table_name})').fetchall()]
        writer.writerow(cols)
    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=f'{table_name}.csv')


@app.context_processor
def inject_today():
    return {'today': date.today().isoformat()}


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
