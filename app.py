from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'estacle_secret_key_change_in_production_2026'
app.config['DATABASE'] = os.path.join(app.instance_path, 'estacle.db')
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads', 'properties')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

os.makedirs(app.instance_path, exist_ok=True)


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'agent', 'customer')),
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            property_type TEXT NOT NULL,
            status TEXT DEFAULT 'available',
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            bedrooms INTEGER,
            bathrooms REAL,
            area_sqft REAL,
            agent_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            status TEXT DEFAULT 'lead',
            notes TEXT,
            agent_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            property_id INTEGER,
            agent_id INTEGER,
            appointment_date TIMESTAMP,
            status TEXT DEFAULT 'scheduled',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id),
            FOREIGN KEY (property_id) REFERENCES properties (id),
            FOREIGN KEY (agent_id) REFERENCES users (id)
        );
    
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'medium',
            assigned_to INTEGER,
            related_client_id INTEGER,
            related_property_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_to) REFERENCES users (id),
            FOREIGN KEY (related_client_id) REFERENCES clients (id),
            FOREIGN KEY (related_property_id) REFERENCES properties (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            property_id INTEGER,
            client_id INTEGER,
            agent_id INTEGER,
            stage TEXT DEFAULT 'offer',
            value REAL DEFAULT 0,
            commission_rate REAL DEFAULT 2.5,
            expected_close TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (property_id) REFERENCES properties (id),
            FOREIGN KEY (client_id) REFERENCES clients (id),
            FOREIGN KEY (agent_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            doc_type TEXT,
            related_type TEXT,
            related_id INTEGER,
            expiry_date TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

''')
    db.commit()

    cursor = db.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        users = [
            ('admin@estacle.com', generate_password_hash('admin123'), 'System Admin', 'admin', '+1-555-0100'),
            ('agent@estacle.com', generate_password_hash('agent123'), 'John Agent', 'agent', '+1-555-0101'),
            ('customer@estacle.com', generate_password_hash('customer123'), 'Sarah Customer', 'customer', '+1-555-0102'),
        ]
        db.executemany(
            'INSERT INTO users (email, password, full_name, role, phone) VALUES (?, ?, ?, ?, ?)',
            users
        )
        db.commit()
        print("Default users created successfully!")

        # Default settings
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('currency', 'USD')")
        db.commit()

    # Ensure default currency setting
    if not db.execute("SELECT value FROM settings WHERE key = 'currency'").fetchone():
        db.execute("INSERT INTO settings (key, value) VALUES ('currency', 'USD')")
        db.commit()



def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('role_redirect'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator




def get_setting(key, default=''):
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else default


def set_setting(key, value):
    db = get_db()
    db.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, value))
    db.commit()


def format_money(amount, currency=None):
    if amount is None:
        return '—'
    currency = currency or get_setting('currency', 'USD')
    symbols = {'USD': '$', 'INR': '₹', 'AED': 'AED '}
    sym = symbols.get(currency, currency + ' ')
    try:
        return f"{sym}{float(amount):,.0f}"
    except (TypeError, ValueError):
        return str(amount)


def migrate_db():
    """Add extra property columns if missing."""
    db = get_db()
    cols = {r[1] for r in db.execute('PRAGMA table_info(properties)').fetchall()}
    extras = [
        ('category', 'TEXT DEFAULT "sale"'),
        ('listing_type', 'TEXT DEFAULT "sale"'),  # sale / rent
        ('floor', 'TEXT'),
        ('carpet_area', 'REAL'),
        ('furnishing', 'TEXT'),
        ('parking', 'TEXT'),
        ('amenities', 'TEXT'),
        ('seller_name', 'TEXT'),
        ('seller_phone', 'TEXT'),
        ('monthly_rent', 'REAL'),
        ('security_deposit', 'REAL'),
        ('maintenance', 'REAL'),
        ('per_sqft', 'REAL'),
        ('latitude', 'TEXT'),
        ('longitude', 'TEXT'),
        ('photos', 'TEXT'),  # comma-separated filenames
        ('year_built', 'TEXT'),
        ('facing', 'TEXT'),
    ]
    for name, typedef in extras:
        if name not in cols:
            try:
                db.execute(f'ALTER TABLE properties ADD COLUMN {name} {typedef}')
            except Exception:
                pass
    db.commit()
    # settings table may need create if old db
    db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    db.execute('''CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        property_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, property_id),
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (property_id) REFERENCES properties (id)
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        source TEXT,
        interest TEXT,
        budget REAL,
        status TEXT DEFAULT 'new',
        notes TEXT,
        assigned_to INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (assigned_to) REFERENCES users (id)
    )''')
    if not db.execute("SELECT value FROM settings WHERE key = 'currency'").fetchone():
        db.execute("INSERT INTO settings (key, value) VALUES ('currency', 'USD')")
    db.execute("""CREATE TABLE IF NOT EXISTS saved_searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        filters TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS inquiries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER,
        user_id INTEGER,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        message TEXT NOT NULL,
        status TEXT DEFAULT 'new',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (property_id) REFERENCES properties (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )""")
    db.commit()



def log_activity(action, entity_type=None, entity_id=None, details=None):
    try:
        db = get_db()
        uid = session.get('user_id')
        db.execute(
            'INSERT INTO activity_log (user_id, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?)',
            (uid, action, entity_type, entity_id, details)
        )
        db.commit()
    except Exception:
        pass


def get_redirect_for_role(role):
    if role == 'admin':
        return url_for('admin_dashboard')
    elif role == 'agent':
        return url_for('agent_dashboard')
    else:
        return url_for('client_dashboard')


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(get_redirect_for_role(session.get('role')))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(get_redirect_for_role(session.get('role')))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please fill in all fields.', 'danger')
            return render_template('login.html')

        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE email = ? AND is_active = 1',
            (email,)
        ).fetchone()

        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            return redirect(get_redirect_for_role(user['role']))
        else:
            flash('Invalid email or password. Please try again.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


@app.route('/redirect')
@login_required
def role_redirect():
    return redirect(get_redirect_for_role(session.get('role')))


# ==================== ADMIN ====================

@app.route('/admin')
@login_required
@role_required('admin')
def admin_dashboard():
    db = get_db()
    stats = {
        'total_users': db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        'total_agents': db.execute("SELECT COUNT(*) FROM users WHERE role = 'agent'").fetchone()[0],
        'total_customers': db.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'").fetchone()[0],
        'total_properties': db.execute('SELECT COUNT(*) FROM properties').fetchone()[0],
        'available_properties': db.execute("SELECT COUNT(*) FROM properties WHERE status = 'available'").fetchone()[0],
        'total_clients': db.execute('SELECT COUNT(*) FROM clients').fetchone()[0],
        'total_appointments': db.execute('SELECT COUNT(*) FROM appointments').fetchone()[0],
    }
    recent_users = db.execute(
        'SELECT id, full_name, email, role, created_at, is_active FROM users ORDER BY created_at DESC LIMIT 8'
    ).fetchall()
    recent_properties = db.execute(
        'SELECT id, title, price, status, city, created_at FROM properties ORDER BY created_at DESC LIMIT 5'
    ).fetchall()
    return render_template('admin.html', stats=stats, recent_users=recent_users, recent_properties=recent_properties)


@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    db = get_db()
    q = request.args.get('q', '').strip()
    role_filter = request.args.get('role', '').strip()
    sql = 'SELECT id, full_name, email, role, phone, created_at, is_active FROM users WHERE 1=1'
    params = []
    if q:
        sql += ' AND (full_name LIKE ? OR email LIKE ? OR phone LIKE ?)'
        params.extend([f'%{q}%', f'%{q}%', f'%{q}%'])
    if role_filter in ('admin', 'agent', 'customer'):
        sql += ' AND role = ?'
        params.append(role_filter)
    sql += ' ORDER BY created_at DESC'
    users = db.execute(sql, params).fetchall()
    return render_template('admin_users.html', users=users, q=q, role_filter=role_filter)


@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_user():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', 'agent')
        phone = request.form.get('phone', '').strip()

        if not full_name or not email or not password or role not in ('admin', 'agent', 'customer'):
            flash('Please fill all required fields correctly.', 'danger')
            return redirect(url_for('admin_add_user'))

        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            flash('Email already exists.', 'danger')
            return redirect(url_for('admin_add_user'))

        db.execute(
            'INSERT INTO users (email, password, full_name, role, phone) VALUES (?, ?, ?, ?, ?)',
            (email, generate_password_hash(password), full_name, role, phone)
        )
        db.commit()
        flash(f'User {full_name} created successfully.', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin_add_user.html')


@app.route('/admin/users/toggle/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_toggle_user(user_id):
    db = get_db()
    user = db.execute('SELECT id, is_active, role FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users'))
    if user['id'] == session['user_id']:
        flash('You cannot deactivate yourself.', 'warning')
        return redirect(url_for('admin_users'))

    new_status = 0 if user['is_active'] else 1
    db.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_status, user_id))
    db.commit()
    flash('User status updated.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/properties')
@login_required
@role_required('admin')
def admin_properties():
    db = get_db()
    properties = db.execute('''
        SELECT p.*, u.full_name as agent_name
        FROM properties p
        LEFT JOIN users u ON p.agent_id = u.id
        ORDER BY p.created_at DESC
    ''').fetchall()
    currency = get_setting('currency', 'USD')
    return render_template('admin_properties.html', properties=properties, currency=currency, format_money=format_money)


@app.route('/admin/clients')
@login_required
@role_required('admin')
def admin_clients():
    db = get_db()
    clients = db.execute('''
        SELECT c.*, u.full_name as agent_name
        FROM clients c
        LEFT JOIN users u ON c.agent_id = u.id
        ORDER BY c.created_at DESC
    ''').fetchall()
    return render_template('admin_clients.html', clients=clients)



@app.route('/admin/appointments')
@login_required
@role_required('admin')
def admin_appointments():
    db = get_db()
    appointments = db.execute("""
        SELECT a.*,
               c.full_name as client_name,
               p.title as property_title,
               u.full_name as agent_name
        FROM appointments a
        LEFT JOIN clients c ON a.client_id = c.id
        LEFT JOIN properties p ON a.property_id = p.id
        LEFT JOIN users u ON a.agent_id = u.id
        ORDER BY a.appointment_date DESC
    """).fetchall()
    return render_template('admin_appointments.html', appointments=appointments)



@app.route('/admin/properties/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_property():
    db = get_db()
    migrate_db()
    agents = db.execute("SELECT id, full_name FROM users WHERE role = 'agent' AND is_active = 1 ORDER BY full_name").fetchall()
    currency = get_setting('currency', 'USD')

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('admin_add_property'))
        try:
            price = float(request.form.get('price') or 0)
            bedrooms = int(request.form.get('bedrooms') or 0) or None
            bathrooms = float(request.form.get('bathrooms') or 0) or None
            area_sqft = float(request.form.get('area_sqft') or 0) or None
            carpet_area = float(request.form.get('carpet_area') or 0) or None
            monthly_rent = float(request.form.get('monthly_rent') or 0) or None
            security_deposit = float(request.form.get('security_deposit') or 0) or None
            maintenance = float(request.form.get('maintenance') or 0) or None
            per_sqft = float(request.form.get('per_sqft') or 0) or None
            agent_id = int(request.form.get('agent_id') or 0) or None
        except ValueError:
            flash('Invalid numeric values.', 'danger')
            return redirect(url_for('admin_add_property'))

        photo_names = []
        files = request.files.getlist('photos')
        for f in files:
            if f and f.filename:
                fname = secure_filename(f.filename)
                unique = f"{int(__import__('time').time())}_{fname}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique))
                photo_names.append(unique)
        photos_str = ','.join(photo_names) if photo_names else None

        db.execute(
            """INSERT INTO properties (
                title, description, price, property_type, status, address, city, state, zip_code,
                bedrooms, bathrooms, area_sqft, agent_id, category, listing_type, floor, carpet_area,
                furnishing, parking, amenities, seller_name, seller_phone, monthly_rent, security_deposit,
                maintenance, per_sqft, latitude, longitude, photos, year_built, facing
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                title, request.form.get('description', ''), price,
                request.form.get('property_type', 'house'), request.form.get('status', 'available'),
                request.form.get('address', ''), request.form.get('city', ''), request.form.get('state', ''),
                request.form.get('zip_code', ''), bedrooms, bathrooms, area_sqft, agent_id,
                request.form.get('category', 'residential'), request.form.get('listing_type', 'sale'),
                request.form.get('floor', ''), carpet_area, request.form.get('furnishing', ''),
                request.form.get('parking', ''), request.form.get('amenities', ''),
                request.form.get('seller_name', ''), request.form.get('seller_phone', ''),
                monthly_rent, security_deposit, maintenance, per_sqft,
                request.form.get('latitude', ''), request.form.get('longitude', ''),
                photos_str, request.form.get('year_built', ''), request.form.get('facing', '')
            )
        )
        db.commit()
        log_activity('Added property', 'property', None, title)
        flash(f'Property "{title}" published.', 'success')
        return redirect(url_for('admin_properties'))

    return render_template('admin_add_property.html', agents=agents, currency=currency)


@app.route('/admin/clients/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_client():
    db = get_db()
    agents = db.execute("SELECT id, full_name FROM users WHERE role = 'agent' AND is_active = 1 ORDER BY full_name").fetchall()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        status = request.form.get('status', 'lead')
        notes = request.form.get('notes', '').strip()
        agent_id = request.form.get('agent_id') or None

        if not full_name:
            flash('Full name is required.', 'danger')
            return redirect(url_for('admin_add_client'))

        agent_id = int(agent_id) if agent_id else None
        db.execute(
            'INSERT INTO clients (full_name, email, phone, status, notes, agent_id) VALUES (?, ?, ?, ?, ?, ?)',
            (full_name, email, phone, status, notes, agent_id)
        )
        db.commit()
        flash(f'Client "{full_name}" added successfully.', 'success')
        return redirect(url_for('admin_clients'))

    return render_template('admin_add_client.html', agents=agents)




@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_user(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        role = request.form.get('role', user['role'])
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        if not full_name or not email or role not in ('admin', 'agent', 'customer'):
            flash('Please fill all required fields correctly.', 'danger')
            return redirect(url_for('admin_edit_user', user_id=user_id))

        existing = db.execute('SELECT id FROM users WHERE email = ? AND id != ?', (email, user_id)).fetchone()
        if existing:
            flash('Email already in use by another user.', 'danger')
            return redirect(url_for('admin_edit_user', user_id=user_id))

        if password:
            db.execute(
                'UPDATE users SET full_name=?, email=?, role=?, phone=?, password=? WHERE id=?',
                (full_name, email, role, phone, generate_password_hash(password), user_id)
            )
        else:
            db.execute(
                'UPDATE users SET full_name=?, email=?, role=?, phone=? WHERE id=?',
                (full_name, email, role, phone, user_id)
            )
        db.commit()
        flash('User updated successfully.', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin_edit_user.html', user=user)


@app.route('/admin/properties/delete/<int:prop_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_property(prop_id):
    db = get_db()
    prop = db.execute('SELECT id, title FROM properties WHERE id = ?', (prop_id,)).fetchone()
    if not prop:
        flash('Property not found.', 'danger')
        return redirect(url_for('admin_properties'))
    db.execute('DELETE FROM properties WHERE id = ?', (prop_id,))
    db.commit()
    flash(f'Property "{prop["title"]}" deleted.', 'success')
    return redirect(url_for('admin_properties'))


@app.route('/admin/clients/delete/<int:client_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_client(client_id):
    db = get_db()
    client = db.execute('SELECT id, full_name FROM clients WHERE id = ?', (client_id,)).fetchone()
    if not client:
        flash('Client not found.', 'danger')
        return redirect(url_for('admin_clients'))
    db.execute('DELETE FROM clients WHERE id = ?', (client_id,))
    db.commit()
    flash(f'Client "{client["full_name"]}" deleted.', 'success')
    return redirect(url_for('admin_clients'))




@app.route('/admin/properties/status/<int:prop_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_update_property_status(prop_id):
    status = request.form.get('status', '')
    if status not in ('available', 'under_offer', 'sold', 'rented'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_properties'))
    db = get_db()
    prop = db.execute('SELECT id, title FROM properties WHERE id = ?', (prop_id,)).fetchone()
    if not prop:
        flash('Property not found.', 'danger')
        return redirect(url_for('admin_properties'))
    db.execute('UPDATE properties SET status = ? WHERE id = ?', (status, prop_id))
    db.commit()
    flash(f'Status of "{prop["title"]}" updated to {status}.', 'success')
    return redirect(url_for('admin_properties'))


@app.route('/admin/clients/status/<int:client_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_update_client_status(client_id):
    status = request.form.get('status', '')
    if status not in ('lead', 'contacted', 'qualified', 'negotiation', 'closed', 'lost'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_clients'))
    db = get_db()
    client = db.execute('SELECT id, full_name FROM clients WHERE id = ?', (client_id,)).fetchone()
    if not client:
        flash('Client not found.', 'danger')
        return redirect(url_for('admin_clients'))
    db.execute('UPDATE clients SET status = ? WHERE id = ?', (status, client_id))
    db.commit()
    flash(f'Status of "{client["full_name"]}" updated to {status}.', 'success')
    return redirect(url_for('admin_clients'))



@app.route('/admin/appointments/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_appointment():
    db = get_db()
    clients = db.execute('SELECT id, full_name FROM clients ORDER BY full_name').fetchall()
    properties = db.execute('SELECT id, title FROM properties ORDER BY title').fetchall()
    agents = db.execute("SELECT id, full_name FROM users WHERE role = 'agent' AND is_active = 1 ORDER BY full_name").fetchall()

    if request.method == 'POST':
        client_id = request.form.get('client_id') or None
        property_id = request.form.get('property_id') or None
        agent_id = request.form.get('agent_id') or None
        appointment_date = request.form.get('appointment_date', '').strip()
        notes = request.form.get('notes', '').strip()
        status = request.form.get('status', 'scheduled')

        if not appointment_date:
            flash('Appointment date is required.', 'danger')
            return redirect(url_for('admin_add_appointment'))

        client_id = int(client_id) if client_id else None
        property_id = int(property_id) if property_id else None
        agent_id = int(agent_id) if agent_id else None

        db.execute(
            'INSERT INTO appointments (client_id, property_id, agent_id, appointment_date, status, notes) VALUES (?, ?, ?, ?, ?, ?)',
            (client_id, property_id, agent_id, appointment_date, status, notes)
        )
        db.commit()
        flash('Appointment scheduled successfully.', 'success')
        return redirect(url_for('admin_appointments'))

    return render_template('admin_add_appointment.html', clients=clients, properties=properties, agents=agents)



@app.route('/admin/analytics')
@login_required
@role_required('admin')
def admin_analytics():
    db = get_db()
    stats = {
        'total_users': db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        'total_agents': db.execute("SELECT COUNT(*) FROM users WHERE role = 'agent'").fetchone()[0],
        'total_customers': db.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'").fetchone()[0],
        'total_properties': db.execute('SELECT COUNT(*) FROM properties').fetchone()[0],
        'available': db.execute("SELECT COUNT(*) FROM properties WHERE status = 'available'").fetchone()[0],
        'sold': db.execute("SELECT COUNT(*) FROM properties WHERE status = 'sold'").fetchone()[0],
        'rented': db.execute("SELECT COUNT(*) FROM properties WHERE status = 'rented'").fetchone()[0],
        'under_offer': db.execute("SELECT COUNT(*) FROM properties WHERE status = 'under_offer'").fetchone()[0],
        'total_clients': db.execute('SELECT COUNT(*) FROM clients').fetchone()[0],
        'leads': db.execute("SELECT COUNT(*) FROM clients WHERE status = 'lead'").fetchone()[0],
        'closed': db.execute("SELECT COUNT(*) FROM clients WHERE status = 'closed'").fetchone()[0],
        'total_appointments': db.execute('SELECT COUNT(*) FROM appointments').fetchone()[0],
        'scheduled': db.execute("SELECT COUNT(*) FROM appointments WHERE status = 'scheduled'").fetchone()[0],
    }
    by_type = db.execute('SELECT property_type, COUNT(*) as cnt FROM properties GROUP BY property_type').fetchall()
    by_city = db.execute('SELECT city, COUNT(*) as cnt FROM properties WHERE city IS NOT NULL AND city != "" GROUP BY city ORDER BY cnt DESC LIMIT 8').fetchall()
    return render_template('admin_analytics.html', stats=stats, by_type=by_type, by_city=by_city)


@app.route('/admin/reports')
@login_required
@role_required('admin')
def admin_reports():
    db = get_db()
    recent_props = db.execute('SELECT id, title, price, status, city, created_at FROM properties ORDER BY created_at DESC LIMIT 10').fetchall()
    recent_clients = db.execute('SELECT id, full_name, status, email, created_at FROM clients ORDER BY created_at DESC LIMIT 10').fetchall()
    agents = db.execute("""
        SELECT u.id, u.full_name,
               (SELECT COUNT(*) FROM properties WHERE agent_id = u.id) as prop_count,
               (SELECT COUNT(*) FROM clients WHERE agent_id = u.id) as client_count
        FROM users u WHERE u.role = 'agent' ORDER BY u.full_name
    """).fetchall()
    return render_template('admin_reports.html', recent_props=recent_props, recent_clients=recent_clients, agents=agents)


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_settings():
    if request.method == 'POST':
        currency = request.form.get('currency', 'USD')
        if currency not in ('USD', 'INR', 'AED'):
            flash('Invalid currency.', 'danger')
            return redirect(url_for('admin_settings'))
        set_setting('currency', currency)
        set_setting('company_name', request.form.get('company_name', 'Estacle').strip() or 'Estacle')
        set_setting('support_email', request.form.get('support_email', '').strip())
        set_setting('support_phone', request.form.get('support_phone', '').strip())
        set_setting('timezone', request.form.get('timezone', 'Asia/Kolkata').strip() or 'Asia/Kolkata')
        set_setting('address', request.form.get('address', '').strip())
        flash('Settings saved.', 'success')
        return redirect(url_for('admin_settings'))
    settings = {
        'currency': get_setting('currency', 'USD'),
        'company_name': get_setting('company_name', 'Estacle'),
        'support_email': get_setting('support_email', 'support@estacle.com'),
        'support_phone': get_setting('support_phone', ''),
        'timezone': get_setting('timezone', 'Asia/Kolkata'),
        'address': get_setting('address', ''),
    }
    return render_template('admin_settings.html', **settings)


# ---------- Property detail / edit ----------
@app.route('/admin/properties/<int:prop_id>')
@login_required
@role_required('admin')
def admin_property_detail(prop_id):
    db = get_db()
    migrate_db()
    prop = db.execute(
        "SELECT p.*, u.full_name as agent_name FROM properties p LEFT JOIN users u ON p.agent_id = u.id WHERE p.id = ?",
        (prop_id,)
    ).fetchone()
    if not prop:
        flash('Property not found.', 'danger')
        return redirect(url_for('admin_properties'))
    photos = []
    if prop['photos']:
        photos = [p.strip() for p in prop['photos'].split(',') if p.strip()]
    currency = get_setting('currency', 'USD')
    return render_template('admin_property_detail.html', prop=prop, photos=photos, currency=currency, format_money=format_money)


@app.route('/admin/properties/edit/<int:prop_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_property(prop_id):
    db = get_db()
    prop = db.execute('SELECT * FROM properties WHERE id = ?', (prop_id,)).fetchone()
    if not prop:
        flash('Property not found.', 'danger')
        return redirect(url_for('admin_properties'))
    agents = db.execute("SELECT id, full_name FROM users WHERE role = 'agent' AND is_active = 1 ORDER BY full_name").fetchall()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title required.', 'danger')
            return redirect(url_for('admin_edit_property', prop_id=prop_id))
        try:
            price = float(request.form.get('price') or 0)
            bedrooms = int(request.form.get('bedrooms') or 0) or None
            bathrooms = float(request.form.get('bathrooms') or 0) or None
            area_sqft = float(request.form.get('area_sqft') or 0) or None
            agent_id = int(request.form.get('agent_id') or 0) or None
        except ValueError:
            flash('Invalid numbers.', 'danger')
            return redirect(url_for('admin_edit_property', prop_id=prop_id))
        db.execute(
            "UPDATE properties SET title=?, description=?, price=?, property_type=?, status=?, address=?, city=?, state=?, zip_code=?, bedrooms=?, bathrooms=?, area_sqft=?, agent_id=? WHERE id=?",
            (title, request.form.get('description',''), price, request.form.get('property_type','house'),
             request.form.get('status','available'), request.form.get('address',''), request.form.get('city',''),
             request.form.get('state',''), request.form.get('zip_code',''), bedrooms, bathrooms, area_sqft, agent_id, prop_id)
        )
        db.commit()
        log_activity('Updated property', 'property', prop_id, title)
        flash('Property updated.', 'success')
        return redirect(url_for('admin_property_detail', prop_id=prop_id))
    return render_template('admin_edit_property.html', prop=prop, agents=agents)


@app.route('/admin/tasks')
@login_required
@role_required('admin')
def admin_tasks():
    db = get_db()
    tasks = db.execute(
        "SELECT t.*, u.full_name as assignee_name, c.full_name as client_name, p.title as property_title FROM tasks t LEFT JOIN users u ON t.assigned_to = u.id LEFT JOIN clients c ON t.related_client_id = c.id LEFT JOIN properties p ON t.related_property_id = p.id ORDER BY t.created_at DESC"
    ).fetchall()
    return render_template('admin_tasks.html', tasks=tasks)


@app.route('/admin/tasks/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_task():
    db = get_db()
    agents = db.execute("SELECT id, full_name FROM users WHERE role IN ('admin','agent') AND is_active=1 ORDER BY full_name").fetchall()
    clients = db.execute('SELECT id, full_name FROM clients ORDER BY full_name').fetchall()
    properties = db.execute('SELECT id, title FROM properties ORDER BY title').fetchall()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title required.', 'danger')
            return redirect(url_for('admin_add_task'))
        assigned = request.form.get('assigned_to') or None
        client_id = request.form.get('related_client_id') or None
        prop_id = request.form.get('related_property_id') or None
        db.execute(
            "INSERT INTO tasks (title, description, due_date, status, priority, assigned_to, related_client_id, related_property_id, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (title, request.form.get('description',''), request.form.get('due_date') or None,
             request.form.get('status','pending'), request.form.get('priority','medium'),
             int(assigned) if assigned else None, int(client_id) if client_id else None,
             int(prop_id) if prop_id else None, session['user_id'])
        )
        db.commit()
        log_activity('Created task', 'task', None, title)
        flash('Task created.', 'success')
        return redirect(url_for('admin_tasks'))
    return render_template('admin_add_task.html', agents=agents, clients=clients, properties=properties)


@app.route('/admin/tasks/status/<int:task_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_task_status(task_id):
    status = request.form.get('status', 'pending')
    if status not in ('pending', 'in_progress', 'done', 'cancelled'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_tasks'))
    db = get_db()
    db.execute('UPDATE tasks SET status=? WHERE id=?', (status, task_id))
    db.commit()
    flash('Task updated.', 'success')
    return redirect(url_for('admin_tasks'))


@app.route('/admin/tasks/delete/<int:task_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    db.commit()
    flash('Task deleted.', 'success')
    return redirect(url_for('admin_tasks'))


@app.route('/admin/deals')
@login_required
@role_required('admin')
def admin_deals():
    db = get_db()
    deals = db.execute(
        "SELECT d.*, p.title as property_title, c.full_name as client_name, u.full_name as agent_name FROM deals d LEFT JOIN properties p ON d.property_id = p.id LEFT JOIN clients c ON d.client_id = c.id LEFT JOIN users u ON d.agent_id = u.id ORDER BY d.updated_at DESC"
    ).fetchall()
    return render_template('admin_deals.html', deals=deals)


@app.route('/admin/deals/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_deal():
    db = get_db()
    properties = db.execute('SELECT id, title FROM properties ORDER BY title').fetchall()
    clients = db.execute('SELECT id, full_name FROM clients ORDER BY full_name').fetchall()
    agents = db.execute("SELECT id, full_name FROM users WHERE role='agent' AND is_active=1 ORDER BY full_name").fetchall()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title required.', 'danger')
            return redirect(url_for('admin_add_deal'))
        try:
            value = float(request.form.get('value') or 0)
            rate = float(request.form.get('commission_rate') or 2.5)
            prop_id = int(request.form.get('property_id') or 0) or None
            client_id = int(request.form.get('client_id') or 0) or None
            agent_id = int(request.form.get('agent_id') or 0) or None
        except ValueError:
            flash('Invalid numbers.', 'danger')
            return redirect(url_for('admin_add_deal'))
        db.execute(
            "INSERT INTO deals (title, property_id, client_id, agent_id, stage, value, commission_rate, expected_close, notes) VALUES (?,?,?,?,?,?,?,?,?)",
            (title, prop_id, client_id, agent_id, request.form.get('stage','offer'), value, rate,
             request.form.get('expected_close') or None, request.form.get('notes',''))
        )
        db.commit()
        log_activity('Created deal', 'deal', None, title)
        flash('Deal created.', 'success')
        return redirect(url_for('admin_deals'))
    return render_template('admin_add_deal.html', properties=properties, clients=clients, agents=agents)


@app.route('/admin/deals/stage/<int:deal_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_deal_stage(deal_id):
    stage = request.form.get('stage', 'offer')
    if stage not in ('offer', 'negotiation', 'under_contract', 'closed', 'lost'):
        flash('Invalid stage.', 'danger')
        return redirect(url_for('admin_deals'))
    db = get_db()
    db.execute("UPDATE deals SET stage=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (stage, deal_id))
    db.commit()
    flash('Deal stage updated.', 'success')
    return redirect(url_for('admin_deals'))


@app.route('/admin/deals/delete/<int:deal_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_deal(deal_id):
    db = get_db()
    db.execute('DELETE FROM deals WHERE id=?', (deal_id,))
    db.commit()
    flash('Deal deleted.', 'success')
    return redirect(url_for('admin_deals'))


@app.route('/admin/activity')
@login_required
@role_required('admin')
def admin_activity():
    db = get_db()
    logs = db.execute(
        "SELECT a.*, u.full_name as user_name FROM activity_log a LEFT JOIN users u ON a.user_id = u.id ORDER BY a.created_at DESC LIMIT 100"
    ).fetchall()
    return render_template('admin_activity.html', logs=logs)


@app.route('/admin/documents')
@login_required
@role_required('admin')
def admin_documents():
    db = get_db()
    docs = db.execute(
        "SELECT d.*, u.full_name as creator_name FROM documents d LEFT JOIN users u ON d.created_by = u.id ORDER BY d.created_at DESC"
    ).fetchall()
    return render_template('admin_documents.html', docs=docs)


@app.route('/admin/documents/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_document():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title required.', 'danger')
            return redirect(url_for('admin_add_document'))
        db = get_db()
        rid = request.form.get('related_id') or None
        db.execute(
            "INSERT INTO documents (title, doc_type, related_type, related_id, expiry_date, notes, created_by) VALUES (?,?,?,?,?,?,?)",
            (title, request.form.get('doc_type',''), request.form.get('related_type',''),
             int(rid) if rid else None, request.form.get('expiry_date') or None,
             request.form.get('notes',''), session['user_id'])
        )
        db.commit()
        log_activity('Added document', 'document', None, title)
        flash('Document recorded.', 'success')
        return redirect(url_for('admin_documents'))
    return render_template('admin_add_document.html')


@app.route('/admin/documents/delete/<int:doc_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_document(doc_id):
    db = get_db()
    db.execute('DELETE FROM documents WHERE id=?', (doc_id,))
    db.commit()
    flash('Document removed.', 'success')
    return redirect(url_for('admin_documents'))



@app.route('/admin/properties/display')
@login_required
@role_required('admin')
def admin_display_properties():
    db = get_db()
    migrate_db()
    q = request.args.get('q', '').strip()
    listing_type = request.args.get('listing_type', '').strip()
    prop_type = request.args.get('property_type', '').strip()
    city = request.args.get('city', '').strip()
    status = request.args.get('status', '').strip()
    beds = request.args.get('beds', '').strip()
    pmin = request.args.get('pmin', '').strip()
    pmax = request.args.get('pmax', '').strip()

    sql = "SELECT p.*, u.full_name as agent_name FROM properties p LEFT JOIN users u ON p.agent_id = u.id WHERE 1=1"
    params = []
    if q:
        sql += " AND (p.title LIKE ? OR p.city LIKE ? OR p.address LIKE ? OR p.description LIKE ?)"
        params.extend([f'%{q}%'] * 4)
    if listing_type in ('sale', 'rent'):
        sql += " AND p.listing_type = ?"
        params.append(listing_type)
    if prop_type:
        sql += " AND p.property_type = ?"
        params.append(prop_type)
    if city:
        sql += " AND p.city LIKE ?"
        params.append(f'%{city}%')
    if status:
        sql += " AND p.status = ?"
        params.append(status)
    if beds:
        try:
            sql += " AND p.bedrooms >= ?"
            params.append(int(beds))
        except ValueError:
            pass
    if pmin:
        try:
            sql += " AND p.price >= ?"
            params.append(float(pmin))
        except ValueError:
            pass
    if pmax:
        try:
            sql += " AND p.price <= ?"
            params.append(float(pmax))
        except ValueError:
            pass
    sql += " ORDER BY p.created_at DESC"
    properties = db.execute(sql, params).fetchall()
    currency = get_setting('currency', 'USD')
    return render_template(
        'admin_display_properties.html',
        properties=properties,
        currency=currency,
        format_money=format_money,
        filters={'q': q, 'listing_type': listing_type, 'property_type': prop_type, 'city': city, 'status': status, 'beds': beds, 'pmin': pmin, 'pmax': pmax}
    )



@app.route('/admin/search')
@login_required
@role_required('admin')
def admin_search():
    q = request.args.get('q', '').strip()
    db = get_db()
    results = {'users': [], 'properties': [], 'clients': [], 'deals': []}
    if q:
        like = f'%{q}%'
        results['users'] = db.execute(
            "SELECT id, full_name, email, role FROM users WHERE full_name LIKE ? OR email LIKE ? LIMIT 20", (like, like)
        ).fetchall()
        results['properties'] = db.execute(
            "SELECT id, title, city, price, status FROM properties WHERE title LIKE ? OR city LIKE ? OR address LIKE ? LIMIT 20",
            (like, like, like)
        ).fetchall()
        results['clients'] = db.execute(
            "SELECT id, full_name, email, status FROM clients WHERE full_name LIKE ? OR email LIKE ? OR phone LIKE ? LIMIT 20",
            (like, like, like)
        ).fetchall()
        results['deals'] = db.execute(
            "SELECT id, title, stage, value FROM deals WHERE title LIKE ? LIMIT 20", (like,)
        ).fetchall()
    currency = get_setting('currency', 'USD')
    return render_template('admin_search.html', q=q, results=results, currency=currency, format_money=format_money)


@app.route('/admin/leads')
@login_required
@role_required('admin')
def admin_leads():
    db = get_db()
    migrate_db()
    leads = db.execute(
        "SELECT l.*, u.full_name as agent_name FROM leads l LEFT JOIN users u ON l.assigned_to = u.id ORDER BY l.created_at DESC"
    ).fetchall()
    return render_template('admin_leads.html', leads=leads)


@app.route('/admin/leads/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_lead():
    db = get_db()
    migrate_db()
    agents = db.execute("SELECT id, full_name FROM users WHERE role IN ('admin','agent') AND is_active=1 ORDER BY full_name").fetchall()
    if request.method == 'POST':
        name = request.form.get('full_name', '').strip()
        if not name:
            flash('Name required.', 'danger')
            return redirect(url_for('admin_add_lead'))
        assigned = request.form.get('assigned_to') or None
        try:
            budget = float(request.form.get('budget') or 0) or None
        except ValueError:
            budget = None
        db.execute(
            "INSERT INTO leads (full_name, email, phone, source, interest, budget, status, notes, assigned_to) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, request.form.get('email',''), request.form.get('phone',''), request.form.get('source',''),
             request.form.get('interest',''), budget, request.form.get('status','new'), request.form.get('notes',''),
             int(assigned) if assigned else None)
        )
        db.commit()
        log_activity('Created lead', 'lead', None, name)
        flash('Lead added.', 'success')
        return redirect(url_for('admin_leads'))
    return render_template('admin_add_lead.html', agents=agents)


@app.route('/admin/leads/status/<int:lead_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_lead_status(lead_id):
    status = request.form.get('status', 'new')
    if status not in ('new', 'contacted', 'qualified', 'converted', 'lost'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_leads'))
    db = get_db()
    db.execute('UPDATE leads SET status=? WHERE id=?', (status, lead_id))
    db.commit()
    flash('Lead updated.', 'success')
    return redirect(url_for('admin_leads'))


@app.route('/admin/leads/delete/<int:lead_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_lead(lead_id):
    db = get_db()
    db.execute('DELETE FROM leads WHERE id=?', (lead_id,))
    db.commit()
    flash('Lead deleted.', 'success')
    return redirect(url_for('admin_leads'))


@app.route('/admin/commission')
@login_required
@role_required('admin')
def admin_commission():
    db = get_db()
    deals = db.execute(
        """SELECT d.*, p.title as property_title, u.full_name as agent_name
           FROM deals d LEFT JOIN properties p ON d.property_id = p.id
           LEFT JOIN users u ON d.agent_id = u.id
           WHERE d.stage = 'closed'
           ORDER BY d.updated_at DESC"""
    ).fetchall()
    total_value = sum((d['value'] or 0) for d in deals)
    total_comm = sum(((d['value'] or 0) * (d['commission_rate'] or 0) / 100) for d in deals)
    currency = get_setting('currency', 'USD')
    return render_template(
        'admin_commission.html', deals=deals, total_value=total_value, total_comm=total_comm,
        currency=currency, format_money=format_money
    )


@app.route('/admin/compare')
@login_required
@role_required('admin')
def admin_compare():
    db = get_db()
    migrate_db()
    all_props = db.execute("SELECT id, title FROM properties ORDER BY title").fetchall()
    ids = request.args.getlist('ids')
    props = []
    if ids:
        try:
            id_list = [int(i) for i in ids][:4]
            if id_list:
                placeholders = ','.join('?' * len(id_list))
                props = db.execute(
                    f"SELECT * FROM properties WHERE id IN ({placeholders})", id_list
                ).fetchall()
        except ValueError:
            pass
    currency = get_setting('currency', 'USD')
    return render_template('admin_compare.html', all_props=all_props, props=props, currency=currency, format_money=format_money)



@app.route('/admin/properties/bulk', methods=['POST'])
@login_required
@role_required('admin')
def admin_bulk_properties():
    db = get_db()
    action = request.form.get('action', '')
    ids = request.form.getlist('ids')
    if not ids:
        flash('No properties selected.', 'warning')
        return redirect(url_for('admin_properties'))
    try:
        ids = [int(i) for i in ids]
    except ValueError:
        flash('Invalid selection.', 'danger')
        return redirect(url_for('admin_properties'))
    placeholders = ','.join('?' * len(ids))
    if action == 'delete':
        db.execute(f'DELETE FROM properties WHERE id IN ({placeholders})', ids)
        db.commit()
        log_activity('Bulk deleted properties', 'property', None, f'{len(ids)} items')
        flash(f'Deleted {len(ids)} properties.', 'success')
    elif action in ('available', 'under_offer', 'sold', 'rented'):
        db.execute(f"UPDATE properties SET status = ? WHERE id IN ({placeholders})", [action] + ids)
        db.commit()
        log_activity('Bulk status update', 'property', None, f'{len(ids)} → {action}')
        flash(f'Updated status of {len(ids)} properties to {action}.', 'success')
    else:
        flash('Unknown action.', 'warning')
    return redirect(url_for('admin_properties'))


@app.route('/admin/export/properties')
@login_required
@role_required('admin')
def admin_export_properties():
    import csv
    import io
    from flask import Response
    db = get_db()
    rows = db.execute('''
        SELECT p.id, p.title, p.property_type, p.listing_type, p.status, p.price, p.city, p.state,
               p.bedrooms, p.bathrooms, p.area_sqft, u.full_name as agent_name, p.created_at
        FROM properties p LEFT JOIN users u ON p.agent_id = u.id
        ORDER BY p.id
    ''').fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Title', 'Type', 'Listing', 'Status', 'Price', 'City', 'State',
                     'Bedrooms', 'Bathrooms', 'Area Sqft', 'Agent', 'Created'])
    for r in rows:
        writer.writerow([r['id'], r['title'], r['property_type'], r['listing_type'], r['status'],
                         r['price'], r['city'], r['state'], r['bedrooms'], r['bathrooms'],
                         r['area_sqft'], r['agent_name'], r['created_at']])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=estacle_properties.csv'}
    )


@app.route('/admin/export/clients')
@login_required
@role_required('admin')
def admin_export_clients():
    import csv
    import io
    from flask import Response
    db = get_db()
    rows = db.execute('''
        SELECT c.id, c.full_name, c.email, c.phone, c.status, u.full_name as agent_name, c.created_at
        FROM clients c LEFT JOIN users u ON c.agent_id = u.id ORDER BY c.id
    ''').fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Full Name', 'Email', 'Phone', 'Status', 'Agent', 'Created'])
    for r in rows:
        writer.writerow([r['id'], r['full_name'], r['email'], r['phone'], r['status'], r['agent_name'], r['created_at']])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=estacle_clients.csv'}
    )


@app.route('/admin/export/users')
@login_required
@role_required('admin')
def admin_export_users():
    import csv
    import io
    from flask import Response
    db = get_db()
    rows = db.execute(
        'SELECT id, full_name, email, role, phone, is_active, created_at FROM users ORDER BY id'
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Full Name', 'Email', 'Role', 'Phone', 'Active', 'Created'])
    for r in rows:
        writer.writerow([r['id'], r['full_name'], r['email'], r['role'], r['phone'], r['is_active'], r['created_at']])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=estacle_users.csv'}
    )


@app.route('/admin/export/deals')
@login_required
@role_required('admin')
def admin_export_deals():
    import csv
    import io
    from flask import Response
    db = get_db()
    rows = db.execute('''
        SELECT d.id, d.title, d.stage, d.value, d.commission_rate, d.expected_close,
               p.title as property_title, c.full_name as client_name, u.full_name as agent_name, d.created_at
        FROM deals d
        LEFT JOIN properties p ON d.property_id = p.id
        LEFT JOIN clients c ON d.client_id = c.id
        LEFT JOIN users u ON d.agent_id = u.id
        ORDER BY d.id
    ''').fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Title', 'Stage', 'Value', 'Commission %', 'Expected Close',
                     'Property', 'Client', 'Agent', 'Created'])
    for r in rows:
        writer.writerow([r['id'], r['title'], r['stage'], r['value'], r['commission_rate'],
                         r['expected_close'], r['property_title'], r['client_name'],
                         r['agent_name'], r['created_at']])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=estacle_deals.csv'}
    )


# ==================== AGENT ====================

@app.route('/agent')
@login_required
@role_required('agent')
def agent_dashboard():
    db = get_db()
    migrate_db()
    agent_id = session['user_id']
    currency = get_setting('currency', 'USD')
    stats = {
        'my_properties': db.execute('SELECT COUNT(*) FROM properties WHERE agent_id = ?', (agent_id,)).fetchone()[0],
        'my_clients': db.execute('SELECT COUNT(*) FROM clients WHERE agent_id = ?', (agent_id,)).fetchone()[0],
        'appointments': db.execute('SELECT COUNT(*) FROM appointments WHERE agent_id = ?', (agent_id,)).fetchone()[0],
        'available': db.execute("SELECT COUNT(*) FROM properties WHERE agent_id = ? AND status = 'available'", (agent_id,)).fetchone()[0],
        'pending_tasks': db.execute("SELECT COUNT(*) FROM tasks WHERE assigned_to = ? AND status = 'pending'", (agent_id,)).fetchone()[0],
        'open_deals': db.execute("SELECT COUNT(*) FROM deals WHERE agent_id = ? AND stage NOT IN ('closed', 'lost')", (agent_id,)).fetchone()[0],
        'new_leads': db.execute("SELECT COUNT(*) FROM leads WHERE assigned_to = ? AND status = 'new'", (agent_id,)).fetchone()[0],
    }
    my_properties = db.execute('''
        SELECT id, title, price, status, city, property_type, listing_type, created_at
        FROM properties WHERE agent_id = ? ORDER BY created_at DESC LIMIT 8
    ''', (agent_id,)).fetchall()
    upcoming = db.execute('''
        SELECT a.*, c.full_name as client_name, p.title as property_title
        FROM appointments a
        LEFT JOIN clients c ON a.client_id = c.id
        LEFT JOIN properties p ON a.property_id = p.id
        WHERE a.agent_id = ? AND a.status = 'scheduled'
        ORDER BY a.appointment_date ASC LIMIT 6
    ''', (agent_id,)).fetchall()
    my_tasks = db.execute('''
        SELECT * FROM tasks WHERE assigned_to = ? AND status != 'completed'
        ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date ASC LIMIT 6
    ''', (agent_id,)).fetchall()
    recent_leads = db.execute('''
        SELECT * FROM leads WHERE assigned_to = ? ORDER BY created_at DESC LIMIT 5
    ''', (agent_id,)).fetchall()
    return render_template('agent.html', stats=stats, my_properties=my_properties,
                           upcoming=upcoming, my_tasks=my_tasks, recent_leads=recent_leads,
                           currency=currency, format_money=format_money)



# ==================== CLIENT / CUSTOMER ====================

@app.route('/client')
@login_required
@role_required('customer')
def client_dashboard():
    db = get_db()
    migrate_db()
    currency = get_setting('currency', 'USD')
    stats = {
        'available_properties': db.execute("SELECT COUNT(*) FROM properties WHERE status = 'available'").fetchone()[0],
        'my_appointments': db.execute(
            "SELECT COUNT(*) FROM appointments a JOIN clients c ON a.client_id = c.id WHERE c.email = ?",
            (session.get('email'),)
        ).fetchone()[0],
    }
    recent = db.execute(
        "SELECT id, title, price, city, property_type, listing_type, photos, status FROM properties WHERE status = 'available' ORDER BY created_at DESC LIMIT 6"
    ).fetchall()
    return render_template('client.html', stats=stats, recent=recent, currency=currency, format_money=format_money)


@app.route('/client/browse')
@login_required
@role_required('customer')
def client_browse():
    db = get_db()
    migrate_db()
    q = request.args.get('q', '').strip()
    listing_type = request.args.get('listing_type', '').strip()
    prop_type = request.args.get('property_type', '').strip()
    city = request.args.get('city', '').strip()
    min_price = request.args.get('min_price', '').strip()
    max_price = request.args.get('max_price', '').strip()
    bedrooms = request.args.get('bedrooms', '').strip()
    sql = "SELECT * FROM properties WHERE status = 'available'"
    params = []
    if q:
        sql += " AND (title LIKE ? OR city LIKE ? OR address LIKE ? OR description LIKE ?)"
        params.extend([f'%{q}%'] * 4)
    if listing_type in ('sale', 'rent'):
        sql += " AND listing_type = ?"
        params.append(listing_type)
    if prop_type:
        sql += " AND property_type = ?"
        params.append(prop_type)
    if city:
        sql += " AND city LIKE ?"
        params.append(f'%{city}%')
    if min_price:
        try:
            sql += " AND price >= ?"
            params.append(float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            sql += " AND price <= ?"
            params.append(float(max_price))
        except ValueError:
            pass
    if bedrooms:
        try:
            sql += " AND bedrooms >= ?"
            params.append(int(bedrooms))
        except ValueError:
            pass
    sql += " ORDER BY created_at DESC"
    properties = db.execute(sql, params).fetchall()
    currency = get_setting('currency', 'USD')
    filters = {
        'q': q, 'listing_type': listing_type, 'property_type': prop_type, 'city': city,
        'min_price': min_price, 'max_price': max_price, 'bedrooms': bedrooms
    }
    saved = db.execute(
        'SELECT id, name, filters FROM saved_searches WHERE user_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    return render_template(
        'client_browse.html',
        properties=properties,
        currency=currency,
        format_money=format_money,
        filters=filters,
        saved_searches=saved
    )


@app.route('/client/saved-search', methods=['POST'])
@login_required
@role_required('customer')
def client_save_search():
    import json
    name = request.form.get('name', '').strip() or 'My Search'
    filters = {
        'q': request.form.get('q', ''),
        'listing_type': request.form.get('listing_type', ''),
        'property_type': request.form.get('property_type', ''),
        'city': request.form.get('city', ''),
        'min_price': request.form.get('min_price', ''),
        'max_price': request.form.get('max_price', ''),
        'bedrooms': request.form.get('bedrooms', ''),
    }
    db = get_db()
    migrate_db()
    db.execute(
        'INSERT INTO saved_searches (user_id, name, filters) VALUES (?, ?, ?)',
        (session['user_id'], name, json.dumps(filters))
    )
    db.commit()
    flash(f'Search "{name}" saved.', 'success')
    return redirect(url_for('client_browse', **{k: v for k, v in filters.items() if v}))


@app.route('/client/saved-search/<int:sid>/delete', methods=['POST'])
@login_required
@role_required('customer')
def client_delete_saved_search(sid):
    db = get_db()
    db.execute('DELETE FROM saved_searches WHERE id = ? AND user_id = ?', (sid, session['user_id']))
    db.commit()
    flash('Saved search removed.', 'info')
    return redirect(url_for('client_browse'))


@app.route('/client/saved-search/<int:sid>')
@login_required
@role_required('customer')
def client_apply_saved_search(sid):
    import json
    db = get_db()
    row = db.execute(
        'SELECT filters FROM saved_searches WHERE id = ? AND user_id = ?',
        (sid, session['user_id'])
    ).fetchone()
    if not row:
        flash('Saved search not found.', 'warning')
        return redirect(url_for('client_browse'))
    filters = json.loads(row['filters'])
    return redirect(url_for('client_browse', **{k: v for k, v in filters.items() if v}))


@app.route('/client/property/<int:prop_id>')
@login_required
@role_required('customer')
def client_property(prop_id):
    db = get_db()
    migrate_db()
    prop = db.execute(
        "SELECT p.*, u.full_name as agent_name FROM properties p LEFT JOIN users u ON p.agent_id = u.id WHERE p.id = ? AND p.status = 'available'",
        (prop_id,)
    ).fetchone()
    if not prop:
        flash('Property not found or unavailable.', 'warning')
        return redirect(url_for('client_browse'))
    photos = [p.strip() for p in (prop['photos'] or '').split(',') if p.strip()]
    currency = get_setting('currency', 'USD')
    return render_template('client_property.html', prop=prop, photos=photos, currency=currency, format_money=format_money)


@app.route('/client/request-viewing/<int:prop_id>', methods=['POST'])
@login_required
@role_required('customer')
def client_request_viewing(prop_id):
    db = get_db()
    prop = db.execute("SELECT id, title, agent_id FROM properties WHERE id = ? AND status = 'available'", (prop_id,)).fetchone()
    if not prop:
        flash('Property not available.', 'danger')
        return redirect(url_for('client_browse'))
    # Find or create client record for this user
    client = db.execute("SELECT id FROM clients WHERE email = ?", (session.get('email'),)).fetchone()
    if not client:
        db.execute(
            "INSERT INTO clients (full_name, email, phone, status, notes) VALUES (?, ?, ?, 'lead', 'Portal customer')",
            (session.get('full_name'), session.get('email'), '')
        )
        db.commit()
        client = db.execute("SELECT id FROM clients WHERE email = ?", (session.get('email'),)).fetchone()
    preferred = request.form.get('preferred_date', '').strip()
    notes = request.form.get('notes', '').strip()
    db.execute(
        "INSERT INTO appointments (client_id, property_id, agent_id, appointment_date, status, notes) VALUES (?, ?, ?, ?, 'scheduled', ?)",
        (client['id'], prop_id, prop['agent_id'], preferred or None, notes or 'Viewing requested via client portal')
    )
    db.commit()
    log_activity('Viewing requested', 'property', prop_id, prop['title'])
    flash('Viewing request submitted. An agent will contact you soon.', 'success')
    return redirect(url_for('client_appointments'))


@app.route('/client/appointments')
@login_required
@role_required('customer')
def client_appointments():
    db = get_db()
    rows = db.execute(
        """SELECT a.*, p.title as property_title, p.city as property_city
           FROM appointments a
           JOIN clients c ON a.client_id = c.id
           LEFT JOIN properties p ON a.property_id = p.id
           WHERE c.email = ?
           ORDER BY a.appointment_date DESC""",
        (session.get('email'),)
    ).fetchall()
    return render_template('client_appointments.html', appointments=rows)


@app.route('/client/profile', methods=['GET', 'POST'])
@login_required
@role_required('customer')
def client_profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        if not full_name:
            flash('Name is required.', 'danger')
            return redirect(url_for('client_profile'))
        if password:
            db.execute('UPDATE users SET full_name=?, phone=?, password=? WHERE id=?',
                       (full_name, phone, generate_password_hash(password), session['user_id']))
        else:
            db.execute('UPDATE users SET full_name=?, phone=? WHERE id=?',
                       (full_name, phone, session['user_id']))
        db.commit()
        session['full_name'] = full_name
        flash('Profile updated.', 'success')
        return redirect(url_for('client_profile'))
    return render_template('client_profile.html', user=user)



@app.route('/client/favorites')
@login_required
@role_required('customer')
def client_favorites():
    db = get_db()
    migrate_db()
    rows = db.execute(
        """SELECT p.* FROM favorites f JOIN properties p ON f.property_id = p.id
           WHERE f.user_id = ? ORDER BY f.created_at DESC""",
        (session['user_id'],)
    ).fetchall()
    currency = get_setting('currency', 'USD')
    return render_template('client_favorites.html', properties=rows, currency=currency, format_money=format_money)


@app.route('/client/favorites/toggle/<int:prop_id>', methods=['POST'])
@login_required
@role_required('customer')
def client_toggle_favorite(prop_id):
    db = get_db()
    migrate_db()
    existing = db.execute(
        "SELECT id FROM favorites WHERE user_id = ? AND property_id = ?",
        (session['user_id'], prop_id)
    ).fetchone()
    if existing:
        db.execute("DELETE FROM favorites WHERE id = ?", (existing['id'],))
        flash('Removed from favorites.', 'success')
    else:
        db.execute(
            "INSERT OR IGNORE INTO favorites (user_id, property_id) VALUES (?, ?)",
            (session['user_id'], prop_id)
        )
        flash('Saved to favorites.', 'success')
    db.commit()
    return redirect(request.referrer or url_for('client_browse'))



@app.route('/client/inquiry/<int:prop_id>', methods=['POST'])
@login_required
@role_required('customer')
def client_inquiry(prop_id):
    db = get_db()
    migrate_db()
    prop = db.execute("SELECT id, title FROM properties WHERE id = ? AND status = 'available'", (prop_id,)).fetchone()
    if not prop:
        flash('Property not found.', 'warning')
        return redirect(url_for('client_browse'))
    message = request.form.get('message', '').strip()
    phone = request.form.get('phone', '').strip() or session.get('email', '')
    if not message:
        flash('Please write a message.', 'danger')
        return redirect(url_for('client_property', prop_id=prop_id))
    db.execute(
        '''INSERT INTO inquiries (property_id, user_id, full_name, email, phone, message)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (prop_id, session['user_id'], session.get('full_name', ''), session.get('email', ''), phone, message)
    )
    db.commit()
    log_activity('Property inquiry', 'property', prop_id, prop['title'])
    flash('Your inquiry was sent. An agent will contact you soon.', 'success')
    return redirect(url_for('client_property', prop_id=prop_id))


@app.route('/admin/inquiries')
@login_required
@role_required('admin')
def admin_inquiries():
    db = get_db()
    migrate_db()
    rows = db.execute('''
        SELECT i.*, p.title as property_title
        FROM inquiries i
        LEFT JOIN properties p ON i.property_id = p.id
        ORDER BY i.created_at DESC
    ''').fetchall()
    return render_template('admin_inquiries.html', inquiries=rows)


@app.route('/admin/inquiries/status/<int:inq_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_inquiry_status(inq_id):
    status = request.form.get('status', 'new')
    if status not in ('new', 'contacted', 'closed'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_inquiries'))
    db = get_db()
    db.execute('UPDATE inquiries SET status = ? WHERE id = ?', (status, inq_id))
    db.commit()
    flash('Inquiry status updated.', 'success')
    return redirect(url_for('admin_inquiries'))


@app.route('/admin/inquiries/delete/<int:inq_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_inquiry(inq_id):
    db = get_db()
    db.execute('DELETE FROM inquiries WHERE id = ?', (inq_id,))
    db.commit()
    flash('Inquiry deleted.', 'info')
    return redirect(url_for('admin_inquiries'))


@app.route('/agent/properties')
@login_required
@role_required('agent')
def agent_properties():
    db = get_db()
    migrate_db()
    agent_id = session['user_id']
    currency = get_setting('currency', 'USD')
    properties = db.execute('''
        SELECT * FROM properties WHERE agent_id = ? ORDER BY created_at DESC
    ''', (agent_id,)).fetchall()
    return render_template('agent_properties.html', properties=properties, currency=currency, format_money=format_money)



if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5001)
