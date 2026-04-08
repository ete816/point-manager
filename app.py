from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = 'points-app-secret-key-2024'

# 絶対パスで DB を指定（どこから起動しても同じ場所に保存される）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'points.db')

CATEGORIES = {
    'point_site': 'ポイントサイト',
    'mile':       'マイル',
    'credit_card': 'クレカ',
}


# ── DB ──────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sites (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            url          TEXT    DEFAULT '',
            category     TEXT    NOT NULL DEFAULT 'point_site',
            points       INTEGER DEFAULT 0,
            expiry_date  TEXT,
            login_id     TEXT    DEFAULT '',
            notes        TEXT    DEFAULT '',
            created_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
            updated_at   TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 既存DBへのマイグレーション（login_id列がなければ追加）
    cols = [row[1] for row in conn.execute('PRAGMA table_info(sites)').fetchall()]
    if 'login_id' not in cols:
        conn.execute("ALTER TABLE sites ADD COLUMN login_id TEXT DEFAULT ''")
    conn.commit()
    conn.close()


# ── helpers ──────────────────────────────────────────────────────────────────

def expiry_info(expiry_date_str):
    """Return (days_left, status_class) or (None, None)."""
    if not expiry_date_str:
        return None, None
    try:
        expiry = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
        days_left = (expiry - date.today()).days
        if days_left < 0:
            status = 'expired'
        elif days_left <= 30:
            status = 'danger'
        elif days_left <= 60:
            status = 'warning'
        else:
            status = 'ok'
        return days_left, status
    except ValueError:
        return None, None


def enrich(rows):
    """Add days_left / status / category_label to each row dict."""
    result = []
    for row in rows:
        d = dict(row)
        d['days_left'], d['status'] = expiry_info(d.get('expiry_date'))
        d['category_label'] = CATEGORIES.get(d['category'], d['category'])
        result.append(d)
    return result


# ── routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    conn = get_db()
    all_sites = enrich(conn.execute(
        'SELECT * FROM sites ORDER BY expiry_date ASC NULLS LAST'
    ).fetchall())
    conn.close()

    # 警告対象（60日以内 + 期限切れ）
    warnings = [s for s in all_sites
                if s['status'] in ('expired', 'danger', 'warning')]
    warnings.sort(key=lambda s: (s['days_left'] is None, s['days_left']))

    # カテゴリ別件数
    cat_counts = {k: 0 for k in CATEGORIES}
    for s in all_sites:
        if s['category'] in cat_counts:
            cat_counts[s['category']] += 1

    return render_template('dashboard.html',
                           warnings=warnings,
                           all_sites=all_sites,
                           cat_counts=cat_counts,
                           categories=CATEGORIES,
                           total=len(all_sites))


@app.route('/sites')
def site_list():
    cat_filter = request.args.get('category', '')
    conn = get_db()
    if cat_filter and cat_filter in CATEGORIES:
        rows = conn.execute(
            'SELECT * FROM sites WHERE category=? ORDER BY name ASC', (cat_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT * FROM sites ORDER BY category, name ASC'
        ).fetchall()
    conn.close()

    return render_template('sites.html',
                           sites=enrich(rows),
                           categories=CATEGORIES,
                           current_category=cat_filter)


@app.route('/sites/add', methods=['GET', 'POST'])
def add_site():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('サービス名は必須です。', 'danger')
            return render_template('site_form.html',
                                   action='add', form=request.form,
                                   categories=CATEGORIES)

        conn = get_db()
        conn.execute(
            '''INSERT INTO sites (name, url, category, points, expiry_date, login_id, notes)
               VALUES (?,?,?,?,?,?,?)''',
            (
                name,
                request.form.get('url', '').strip(),
                request.form.get('category', 'point_site'),
                int(request.form.get('points') or 0),
                request.form.get('expiry_date') or None,
                request.form.get('login_id', '').strip(),
                request.form.get('notes', '').strip(),
            )
        )
        conn.commit()
        conn.close()
        flash(f'「{name}」を登録しました。', 'success')
        return redirect(url_for('site_list'))

    return render_template('site_form.html',
                           action='add', form={}, categories=CATEGORIES)


@app.route('/sites/<int:site_id>/edit', methods=['GET', 'POST'])
def edit_site(site_id):
    conn = get_db()
    site = conn.execute('SELECT * FROM sites WHERE id=?', (site_id,)).fetchone()
    if not site:
        conn.close()
        flash('サイトが見つかりません。', 'danger')
        return redirect(url_for('site_list'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('サービス名は必須です。', 'danger')
            conn.close()
            return render_template('site_form.html',
                                   action='edit', site=dict(site),
                                   form=request.form, categories=CATEGORIES)

        conn.execute(
            '''UPDATE sites
               SET name=?, url=?, category=?, points=?, expiry_date=?,
                   login_id=?, notes=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (
                name,
                request.form.get('url', '').strip(),
                request.form.get('category', 'point_site'),
                int(request.form.get('points') or 0),
                request.form.get('expiry_date') or None,
                request.form.get('login_id', '').strip(),
                request.form.get('notes', '').strip(),
                site_id,
            )
        )
        conn.commit()
        conn.close()
        flash(f'「{name}」を更新しました。', 'success')
        return redirect(url_for('site_list'))

    conn.close()
    return render_template('site_form.html',
                           action='edit', site=dict(site),
                           form=dict(site), categories=CATEGORIES)


@app.route('/sites/<int:site_id>/delete', methods=['POST'])
def delete_site(site_id):
    conn = get_db()
    site = conn.execute('SELECT name FROM sites WHERE id=?', (site_id,)).fetchone()
    if site:
        conn.execute('DELETE FROM sites WHERE id=?', (site_id,))
        conn.commit()
        flash(f'「{site["name"]}」を削除しました。', 'info')
    conn.close()
    return redirect(url_for('site_list'))


# PythonAnywhere などから import されたときも DB を初期化する
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
