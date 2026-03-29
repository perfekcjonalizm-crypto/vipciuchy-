"""
routes/products.py — CRUD produktów, ulubione
"""
import json
import os
from flask import Blueprint, request, jsonify, session
from db import get_db
from routes.csrf import csrf_required

products_bp = Blueprint("products", __name__, url_prefix="/api/products")

# Filtr spamu — słowa kluczowe zakazane
_SPAM_KEYWORDS = [
    "zarobek","zarabiaj","kliknij link","whatsapp","telegram","przelew z góry",
    "western union","przedpłata","zaliczka poza serwisem","kontakt poza",
    "fake","podróbka","replica","replika","1:1 kopia",
    "bitcoin","kryptowaluta","crypto","nft",
    "xxx","18+","erotyk","escort",
]

def _spam_check(text: str):
    """Zwraca nazwę wykrytego słowa kluczowego lub None."""
    t = text.lower()
    for kw in _SPAM_KEYWORDS:
        if kw in t:
            return kw
    return None


def _prod_dict(row):
    return {
        "id":          row["id"],
        "name":        row["name"],
        "brand":       row["brand"],
        "price":       row["price"],
        "size":        row["size"],
        "condition":   row["condition"],
        "emoji":       row["emoji"],
        "description": row["description"],
        "seller_id":   row["seller_id"],
        "seller":      row["username"]  if "username"  in row.keys() else None,
        "avatar":      row["avatar"]    if "avatar"    in row.keys() else None,
        "images":      json.loads(row["images"] if "images" in row.keys() and row["images"] else "[]"),
        "is_sold":     bool(row["is_sold"]),
        "status":    row["status"]    if "status"    in row.keys() else ("sold" if row["is_sold"] else "available"),
        "is_hidden": bool(row["is_hidden"]) if "is_hidden" in row.keys() else False,
        "category":  row["category"] if "category" in row.keys() else "",
        "created_at":  row["created_at"],
    }


@products_bp.get("")
def list_products():
    q         = request.args.get("q", "").strip()
    category  = request.args.get("category", "").strip()
    sort      = request.args.get("sort", "newest")
    seller_id = request.args.get("seller_id", "").strip()
    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except (TypeError, ValueError):
        return jsonify({"error": "Nieprawidłowe parametry paginacji."}), 400
    offset    = (page - 1) * per_page

    sql  = """SELECT p.*, u.username, u.avatar
              FROM products p
              LEFT JOIN users u ON u.id = p.seller_id
              WHERE p.is_sold = 0 AND p.is_hidden = 0"""
    args = []

    if q:
        sql  += " AND (p.name LIKE ? OR p.brand LIKE ? OR p.description LIKE ?)"
        like  = f"%{q}%"
        args += [like, like, like]

    if seller_id:
        try:
            args += [int(seller_id)]
        except (TypeError, ValueError):
            return jsonify({"error": "Nieprawidłowy seller_id."}), 400
        sql  += " AND p.seller_id = ?"

    size         = request.args.get("size", "").strip()
    cond_filter  = request.args.get("cond", "").strip()
    min_price    = request.args.get("min_price", "")
    max_price    = request.args.get("max_price", "")
    brand_filter = request.args.get("brand", "").strip()
    city_filter  = request.args.get("city", "").strip()

    if size:
        sql  += " AND p.size = ?"
        args += [size]
    if cond_filter:
        sql  += " AND p.condition LIKE ?"
        args += [f"%{cond_filter}%"]
    if min_price:
        try: sql += " AND p.price >= ?"; args += [float(min_price)]
        except (TypeError, ValueError): pass
    if max_price:
        try: sql += " AND p.price <= ?"; args += [float(max_price)]
        except (TypeError, ValueError): pass
    if brand_filter:
        sql  += " AND p.brand LIKE ?"
        args += [f"%{brand_filter}%"]
    if city_filter:
        sql  += " AND u.city LIKE ?"
        args += [f"%{city_filter}%"]
    if category and category != 'wszystko':
        CATEGORY_KEYWORDS = {
            'sukienki':  ['sukienk'],
            'spodnie':   ['spodnie','jeansy','leggins','leginsy'],
            'bluzki':    ['bluzk','koszul','top ','shirt'],
            'kurtki':    ['kurt','płaszcz','kurtka','kożuch'],
            'buty':      ['but','sneaker','tenisom','kozak','sandał','obcas'],
            'torebki':   ['torebk','torb','plecak'],
            'bizuteria': ['kolczyk','naszyjnik','bransolet','pierścion','biżuteri'],
            'akcesoria': ['szalik','czapk','pasek','rękawic','okulary','kapelusz'],
            'dziecko':   ['dziecko','dziecięc','niemowl','chłopiec','dziewczynk'],
            'sport':     ['sport','biegani','yoga','siłowni','treningow'],
        }
        kw_list = CATEGORY_KEYWORDS.get(category, [category])
        kw_conditions = ' OR '.join(['(p.name LIKE ? OR p.description LIKE ?)'] * len(kw_list))
        sql  += f" AND (p.category=? OR {kw_conditions})"
        args += [category]
        for kw in kw_list:
            args += [f"%{kw}%", f"%{kw}%"]

    order_map = {
        "newest":     "p.created_at DESC",
        "oldest":     "p.created_at ASC",
        "price_asc":  "p.price ASC",
        "price_desc": "p.price DESC",
    }
    sql += f" ORDER BY {order_map.get(sort, 'p.created_at DESC')}"
    sql += " LIMIT ? OFFSET ?"
    args += [per_page, offset]

    conn = get_db()
    try:
        rows = conn.execute(sql, args).fetchall()
        # Count query mirrors all filters (strip ORDER BY / LIMIT / OFFSET)
        count_sql  = """SELECT COUNT(*) FROM products p
                        LEFT JOIN users u ON u.id = p.seller_id
                        WHERE p.is_sold = 0 AND p.is_hidden = 0"""
        count_args = []
        if q:
            count_sql  += " AND (p.name LIKE ? OR p.brand LIKE ? OR p.description LIKE ?)"
            count_args += [f"%{q}%", f"%{q}%", f"%{q}%"]
        if seller_id:
            count_sql  += " AND p.seller_id = ?"
            count_args += [int(seller_id)]
        if size:
            count_sql  += " AND p.size = ?"
            count_args += [size]
        if cond_filter:
            count_sql  += " AND p.condition LIKE ?"
            count_args += [f"%{cond_filter}%"]
        if min_price:
            try: count_sql += " AND p.price >= ?"; count_args += [float(min_price)]
            except (TypeError, ValueError): pass
        if max_price:
            try: count_sql += " AND p.price <= ?"; count_args += [float(max_price)]
            except (TypeError, ValueError): pass
        if brand_filter:
            count_sql  += " AND p.brand LIKE ?"
            count_args += [f"%{brand_filter}%"]
        if city_filter:
            count_sql  += " AND u.city LIKE ?"
            count_args += [f"%{city_filter}%"]
        if category and category != 'wszystko':
            CATEGORY_KEYWORDS = {
                'sukienki':  ['sukienk'],
                'spodnie':   ['spodnie','jeansy','leggins','leginsy'],
                'bluzki':    ['bluzk','koszul','top ','shirt'],
                'kurtki':    ['kurt','płaszcz','kurtka','kożuch'],
                'buty':      ['but','sneaker','tenisom','kozak','sandał','obcas'],
                'torebki':   ['torebk','torb','plecak'],
                'bizuteria': ['kolczyk','naszyjnik','bransolet','pierścion','biżuteri'],
                'akcesoria': ['szalik','czapk','pasek','rękawic','okulary','kapelusz'],
                'dziecko':   ['dziecko','dziecięc','niemowl','chłopiec','dziewczynk'],
                'sport':     ['sport','biegani','yoga','siłowni','treningow'],
            }
            kw_list = CATEGORY_KEYWORDS.get(category, [category])
            conditions = ' OR '.join(['(p.name LIKE ? OR p.description LIKE ?)'] * len(kw_list))
            count_sql  += f" AND ({conditions})"
            for kw in kw_list:
                count_args += [f"%{kw}%", f"%{kw}%"]
        total = conn.execute(count_sql, count_args).fetchone()[0]
        return jsonify({
            "products": [_prod_dict(r) for r in rows],
            "total":    total,
            "page":     page,
            "pages":    (total + per_page - 1) // per_page,
        })
    finally:
        conn.close()


@products_bp.get("/mine")
def my_products():
    """Własne ogłoszenia zalogowanego użytkownika — wszystkie statusy."""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 50))))
    except (TypeError, ValueError):
        return jsonify({"error": "Nieprawidłowe parametry."}), 400
    offset = (page - 1) * per_page

    status_filter = request.args.get("status", "")

    sql  = """SELECT p.*, u.username, u.avatar
              FROM products p LEFT JOIN users u ON u.id=p.seller_id
              WHERE p.seller_id=?"""
    args = [uid]
    if status_filter:
        sql  += " AND p.status=?"
        args += [status_filter]
    sql  += " ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
    args += [per_page, offset]

    conn = get_db()
    try:
        rows  = conn.execute(sql, args).fetchall()
        count_sql  = "SELECT COUNT(*) FROM products WHERE seller_id=?"
        count_args = [uid]
        if status_filter:
            count_sql  += " AND status=?"
            count_args += [status_filter]
        total = conn.execute(count_sql, count_args).fetchone()[0]
        return jsonify({
            "products": [_prod_dict(r) for r in rows],
            "total": total,
            "page": page,
            "pages": (total + per_page - 1) // per_page,
        })
    finally:
        conn.close()


@products_bp.get("/<int:pid>")
def get_product(pid):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT p.*, u.username, u.avatar FROM products p LEFT JOIN users u ON u.id=p.seller_id WHERE p.id=?",
            (pid,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Nie znaleziono produktu."}), 404
        return jsonify({"product": _prod_dict(row)})
    finally:
        conn.close()


@products_bp.post("")
@csrf_required
def create_product():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data = request.get_json(silent=True) or {}
    name  = (data.get("name")  or "").strip()
    brand = (data.get("brand") or "").strip()
    price = data.get("price")
    size  = (data.get("size")  or "—").strip()
    cond  = (data.get("condition") or "Dobry").strip()
    emoji  = (data.get("emoji") or "👗").strip()
    desc   = (data.get("description") or "").strip()
    images   = json.dumps(data.get("images") or [])
    category = (data.get("category") or "").strip()[:50]

    if not name or not brand:
        return jsonify({"error": "Nazwa i marka są wymagane."}), 400
    try:
        price = float(price)
        if price <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Cena musi być liczbą większą od 0."}), 400

    # Filtr spamu
    combined = f"{name} {desc}"
    kw = _spam_check(combined)
    if kw:
        return jsonify({"error": f"Oferta zawiera niedozwolone treści: '{kw}'."}), 400

    conn = get_db()
    try:
        # Ogranicz: max 10 aktywnych ofert na użytkownika
        active_count = conn.execute(
            "SELECT COUNT(*) FROM products WHERE seller_id=? AND is_sold=0", (uid,)
        ).fetchone()[0]
        if active_count >= 20:
            return jsonify({"error": "Możesz mieć maksymalnie 20 aktywnych ofert."}), 400

        cur = conn.execute(
            "INSERT INTO products (name,brand,price,size,condition,emoji,description,images,seller_id,status,is_hidden,category) VALUES (?,?,?,?,?,?,?,?,?,'available',0,?)",
            (name, brand, price, size, cond, emoji, desc, images, uid, category)
        )
        conn.commit()
        new_id = cur.lastrowid
        row = conn.execute(
            "SELECT p.*, u.username, u.avatar FROM products p LEFT JOIN users u ON u.id=p.seller_id WHERE p.id=?",
            (new_id,)
        ).fetchone()
        return jsonify({"product": _prod_dict(row)}), 201
    finally:
        conn.close()


@products_bp.patch("/<int:pid>/status")
@csrf_required
def change_status(pid):
    """Zmień status ogłoszenia: available / reserved / sold"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data   = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in ("available", "reserved", "sold"):
        return jsonify({"error": "Nieprawidłowy status. Dozwolone: available, reserved, sold"}), 400

    conn = get_db()
    try:
        prod = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not prod:
            return jsonify({"error": "Nie znaleziono produktu."}), 404
        if prod["seller_id"] != uid:
            return jsonify({"error": "Brak uprawnień."}), 403

        is_sold = 1 if status == "sold" else 0
        conn.execute("UPDATE products SET status=?, is_sold=? WHERE id=?", (status, is_sold, pid))
        conn.commit()
        return jsonify({"ok": True, "status": status, "is_sold": bool(is_sold)})
    finally:
        conn.close()


@products_bp.patch("/<int:pid>/visibility")
@csrf_required
def toggle_visibility(pid):
    """Ukryj / pokaż ogłoszenie."""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        prod = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not prod:
            return jsonify({"error": "Nie znaleziono produktu."}), 404
        if prod["seller_id"] != uid:
            return jsonify({"error": "Brak uprawnień."}), 403

        new_hidden = 0 if (prod["is_hidden"] if "is_hidden" in prod.keys() else 0) else 1
        conn.execute("UPDATE products SET is_hidden=? WHERE id=?", (new_hidden, pid))
        conn.commit()
        return jsonify({"ok": True, "is_hidden": bool(new_hidden)})
    finally:
        conn.close()


@products_bp.delete("/<int:pid>")
@csrf_required
def delete_product(pid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        prod = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not prod:
            return jsonify({"error": "Nie znaleziono produktu."}), 404
        if prod["seller_id"] != uid:
            return jsonify({"error": "Brak uprawnień — możesz usuwać tylko swoje ogłoszenia."}), 403

        # Usuń powiązane zdjęcia z dysku
        try:
            images = json.loads(prod["images"] or "[]")
            for img_url in images:
                # img_url wygląda jak /uploads/xxx.jpg
                filename = os.path.basename(img_url)
                upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
                filepath = os.path.join(upload_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
        except Exception:
            pass  # Nie przerywaj usuwania produktu z powodu błędu pliku

        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@products_bp.put("/<int:pid>")
@csrf_required
def update_product(pid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        prod = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not prod:
            return jsonify({"error": "Nie znaleziono produktu."}), 404
        if prod["seller_id"] != uid:
            return jsonify({"error": "Brak uprawnień."}), 403

        data  = request.get_json(silent=True) or {}
        name  = (data.get("name")  or prod["name"]).strip()
        brand = (data.get("brand") or prod["brand"]).strip()
        price = data.get("price", prod["price"])
        size  = (data.get("size")  or prod["size"]).strip()
        cond  = (data.get("condition") or prod["condition"]).strip()
        desc  = (data.get("description") or prod["description"] or "").strip()
        emoji = (data.get("emoji") or prod["emoji"] or "👗").strip()
        images = json.dumps(data.get("images")) if "images" in data else prod["images"]
        category = (data.get("category") or (prod["category"] if "category" in prod.keys() else "") or "").strip()[:50]

        try:
            price = float(price)
            if price <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Cena musi być liczbą większą od 0."}), 400

        conn.execute(
            "UPDATE products SET name=?, brand=?, price=?, size=?, condition=?, description=?, emoji=?, images=?, category=? WHERE id=?",
            (name, brand, price, size, cond, desc, emoji, images, category, pid)
        )
        conn.commit()
        row = conn.execute(
            "SELECT p.*, u.username, u.avatar FROM products p LEFT JOIN users u ON u.id=p.seller_id WHERE p.id=?",
            (pid,)
        ).fetchone()
        return jsonify({"product": _prod_dict(row)})
    finally:
        conn.close()


@products_bp.post("/<int:pid>/favorite")
@csrf_required
def toggle_favorite(pid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM favorites WHERE user_id=? AND product_id=?", (uid, pid)
        ).fetchone()
        if exists:
            conn.execute("DELETE FROM favorites WHERE user_id=? AND product_id=?", (uid, pid))
            conn.commit()
            return jsonify({"favorited": False})
        else:
            conn.execute("INSERT INTO favorites (user_id, product_id) VALUES (?,?)", (uid, pid))
            conn.commit()
            return jsonify({"favorited": True})
    finally:
        conn.close()


@products_bp.get("/favorites")
def my_favorites():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT p.*, u.username, u.avatar FROM favorites f
               JOIN products p ON p.id = f.product_id
               LEFT JOIN users u ON u.id = p.seller_id
               WHERE f.user_id = ? AND p.is_sold = 0""",
            (uid,)
        ).fetchall()
        return jsonify({"products": [_prod_dict(r) for r in rows]})
    finally:
        conn.close()


@products_bp.get("/seller/<int:uid>")
def seller_profile(uid):
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE id=?", (uid,)
        ).fetchone()
        if not user:
            return jsonify({"error": "Nie znaleziono użytkownika."}), 404
        count = conn.execute(
            "SELECT COUNT(*) FROM products WHERE seller_id=? AND is_sold=0", (uid,)
        ).fetchone()[0]
        sold  = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE seller_id=?", (uid,)
        ).fetchone()[0]
        rating = conn.execute(
            "SELECT AVG(rating), COUNT(*) FROM reviews WHERE reviewed_id=?", (uid,)
        ).fetchone()
        avg_rating   = round(rating[0], 1) if rating[0] else None
        rating_count = rating[1]
        return jsonify({
            "user": {
                "id":         user["id"],
                "username":   user["username"],
                "avatar":     user["avatar"],
                "created_at": user["created_at"],
                "active_listings": count,
                "sold_count":      sold,
                "bio":          user["bio"]         if "bio"         in user.keys() else '',
                "city":         user["city"]        if "city"        in user.keys() else '',
                "avatar_url":   user["avatar_url"]  if "avatar_url"  in user.keys() else '',
                "avg_rating":   avg_rating,
                "rating_count": rating_count,
            }
        })
    finally:
        conn.close()
