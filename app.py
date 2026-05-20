from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3
import os
import uuid

app = Flask(__name__)
app.secret_key = 'sports_store_secret_2024'

DB_PATH = os.path.join(os.path.dirname(__file__), 'sports_store.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_session_id():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def get_cart_count():
    sid = get_session_id()
    conn = get_db()
    row = conn.execute("SELECT COALESCE(SUM(quantity),0) as cnt FROM Cart WHERE session_id=?", (sid,)).fetchone()
    conn.close()
    return row['cnt']

# ==================== HOME ====================
@app.route('/')
def index():
    conn = get_db()
    featured = conn.execute(
        "SELECT p.*, c.category_name, c.icon FROM Products p JOIN Categories c ON p.category_id=c.category_id WHERE p.is_featured=1 LIMIT 6"
    ).fetchall()
    categories = conn.execute("SELECT * FROM Categories").fetchall()
    stats = {
        'products': conn.execute("SELECT COUNT(*) as n FROM Products").fetchone()['n'],
        'categories': conn.execute("SELECT COUNT(*) as n FROM Categories").fetchone()['n'],
        'orders': conn.execute("SELECT COUNT(*) as n FROM Orders").fetchone()['n'],
    }
    conn.close()
    return render_template('index.html', featured=featured, categories=categories, stats=stats, cart_count=get_cart_count())

# ==================== PRODUCTS ====================
@app.route('/products')
def products():
    conn = get_db()
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    sort = request.args.get('sort', 'name')

    query = "SELECT p.*, c.category_name, c.icon FROM Products p JOIN Categories c ON p.category_id=c.category_id WHERE 1=1"
    params = []
    if search:
        query += " AND (p.product_name LIKE ? OR p.description LIKE ?)"
        params += [f'%{search}%', f'%{search}%']
    if category:
        query += " AND p.category_id=?"
        params.append(category)
    order = {'name': 'p.product_name ASC', 'price_asc': 'p.price ASC', 'price_desc': 'p.price DESC'}.get(sort, 'p.product_name ASC')
    query += f" ORDER BY {order}"

    items = conn.execute(query, params).fetchall()
    categories = conn.execute("SELECT * FROM Categories").fetchall()
    conn.close()
    return render_template('products.html', products=items, categories=categories,
                           search=search, category=category, sort=sort, cart_count=get_cart_count())

# ==================== PRODUCT DETAIL ====================
@app.route('/product/<int:pid>')
def product_detail(pid):
    conn = get_db()
    product = conn.execute(
        "SELECT p.*, c.category_name, c.icon FROM Products p JOIN Categories c ON p.category_id=c.category_id WHERE p.product_id=?", (pid,)
    ).fetchone()
    if not product:
        conn.close()
        return redirect(url_for('products'))
    related = conn.execute(
        "SELECT p.*, c.category_name FROM Products p JOIN Categories c ON p.category_id=c.category_id WHERE p.category_id=? AND p.product_id!=? LIMIT 4",
        (product['category_id'], pid)
    ).fetchall()
    conn.close()
    return render_template('product_detail.html', product=product, related=related, cart_count=get_cart_count())

# ==================== CART ====================
@app.route('/cart')
def cart():
    sid = get_session_id()
    conn = get_db()
    items = conn.execute(
        "SELECT c.cart_id, c.quantity, p.product_id, p.product_name, p.price, p.image_url, p.stock FROM Cart c JOIN Products p ON c.product_id=p.product_id WHERE c.session_id=?", (sid,)
    ).fetchall()
    total = sum(i['price'] * i['quantity'] for i in items)
    conn.close()
    return render_template('cart.html', cart_items=items, total=total, cart_count=get_cart_count())

@app.route('/cart/add/<int:pid>', methods=['POST'])
def cart_add(pid):
    sid = get_session_id()
    qty = int(request.form.get('quantity', 1))
    conn = get_db()
    existing = conn.execute("SELECT * FROM Cart WHERE session_id=? AND product_id=?", (sid, pid)).fetchone()
    if existing:
        conn.execute("UPDATE Cart SET quantity=quantity+? WHERE session_id=? AND product_id=?", (qty, sid, pid))
    else:
        conn.execute("INSERT INTO Cart (session_id, product_id, quantity) VALUES (?,?,?)", (sid, pid, qty))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('cart'))

@app.route('/cart/update/<int:cart_id>', methods=['POST'])
def cart_update(cart_id):
    qty = int(request.form.get('quantity', 1))
    conn = get_db()
    if qty <= 0:
        conn.execute("DELETE FROM Cart WHERE cart_id=?", (cart_id,))
    else:
        conn.execute("UPDATE Cart SET quantity=? WHERE cart_id=?", (qty, cart_id))
    conn.commit()
    conn.close()
    return redirect(url_for('cart'))

@app.route('/cart/remove/<int:cart_id>')
def cart_remove(cart_id):
    conn = get_db()
    conn.execute("DELETE FROM Cart WHERE cart_id=?", (cart_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    sid = get_session_id()
    conn = get_db()
    if request.method == 'POST':
        items = conn.execute(
            "SELECT c.quantity, p.price FROM Cart c JOIN Products p ON c.product_id=p.product_id WHERE c.session_id=?", (sid,)
        ).fetchall()
        total = sum(i['price'] * i['quantity'] for i in items)
        conn.execute(
            "INSERT INTO Orders (user_id, order_date, total_price, status) VALUES (?,date('now'),?,'pending')",
            (1, total)
        )
        conn.execute("DELETE FROM Cart WHERE session_id=?", (sid,))
        conn.commit()
        conn.close()
        flash('สั่งซื้อสำเร็จ! ขอบคุณที่ใช้บริการ 🎉', 'success')
        return redirect(url_for('index'))
    items = conn.execute(
        "SELECT c.cart_id, c.quantity, p.product_name, p.price, p.image_url FROM Cart c JOIN Products p ON c.product_id=p.product_id WHERE c.session_id=?", (sid,)
    ).fetchall()
    total = sum(i['price'] * i['quantity'] for i in items)
    conn.close()
    return render_template('checkout.html', cart_items=items, total=total, cart_count=get_cart_count())

# ==================== ADMIN ====================
@app.route('/admin')
def admin():
    conn = get_db()
    products = conn.execute(
        "SELECT p.*, c.category_name FROM Products p JOIN Categories c ON p.category_id=c.category_id ORDER BY p.product_id"
    ).fetchall()
    orders = conn.execute(
        "SELECT o.*, u.name as user_name FROM Orders o LEFT JOIN Users u ON o.user_id=u.user_id ORDER BY o.order_date DESC"
    ).fetchall()
    stats = {
        'total_products': conn.execute("SELECT COUNT(*) as n FROM Products").fetchone()['n'],
        'total_orders': conn.execute("SELECT COUNT(*) as n FROM Orders").fetchone()['n'],
        'revenue': conn.execute("SELECT COALESCE(SUM(total_price),0) as s FROM Orders WHERE status='paid'").fetchone()['s'],
        'pending': conn.execute("SELECT COUNT(*) as n FROM Orders WHERE status='pending'").fetchone()['n'],
    }
    categories = conn.execute("SELECT * FROM Categories").fetchall()
    conn.close()
    return render_template('admin.html', products=products, orders=orders, stats=stats, categories=categories, cart_count=get_cart_count())

@app.route('/admin/product/add', methods=['POST'])
def admin_add_product():
    conn = get_db()
    conn.execute(
        "INSERT INTO Products (product_name, price, original_price, stock, category_id, description, image_url, is_featured) VALUES (?,?,?,?,?,?,?,?)",
        (request.form['name'], request.form['price'], request.form.get('original_price') or None,
         request.form['stock'], request.form['category_id'], request.form.get('description',''),
         request.form.get('image_url',''), 1 if request.form.get('featured') else 0)
    )
    conn.commit()
    conn.close()
    flash('เพิ่มสินค้าสำเร็จ!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/product/edit/<int:pid>', methods=['GET', 'POST'])
def admin_edit_product(pid):
    conn = get_db()
    if request.method == 'POST':
        conn.execute(
            "UPDATE Products SET product_name=?, price=?, original_price=?, stock=?, category_id=?, description=?, image_url=?, is_featured=? WHERE product_id=?",
            (request.form['name'], request.form['price'], request.form.get('original_price') or None,
             request.form['stock'], request.form['category_id'], request.form.get('description',''),
             request.form.get('image_url',''), 1 if request.form.get('featured') else 0, pid)
        )
        conn.commit()
        conn.close()
        flash('อัปเดตสินค้าสำเร็จ! ✅', 'success')
        return redirect(url_for('admin'))
    product = conn.execute("SELECT * FROM Products WHERE product_id=?", (pid,)).fetchone()
    categories = conn.execute("SELECT * FROM Categories").fetchall()
    conn.close()
    if not product:
        return redirect(url_for('admin'))
    return render_template('edit_product.html', product=product, categories=categories, cart_count=get_cart_count())

@app.route('/admin/product/delete/<int:pid>')
def admin_delete_product(pid):
    conn = get_db()
    conn.execute("DELETE FROM Products WHERE product_id=?", (pid,))
    conn.commit()
    conn.close()
    flash('ลบสินค้าสำเร็จ!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/order/status/<int:oid>', methods=['POST'])
def admin_update_order(oid):
    conn = get_db()
    conn.execute("UPDATE Orders SET status=? WHERE order_id=?", (request.form['status'], oid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

# ==================== API ====================
@app.route('/api/cart/count')
def api_cart_count():
    return jsonify({'count': get_cart_count()})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
