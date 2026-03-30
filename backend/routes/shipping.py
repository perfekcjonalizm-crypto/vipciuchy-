"""
routes/shipping.py — wybór dostawy, generowanie etykiet, śledzenie
Obsługuje: InPost Paczkomat, InPost Kurier, DPD, Poczta Polska, Orlen Paczka
"""
import os
import json
import logging
import requests
from flask import Blueprint, request, jsonify, session
from db import get_db
from routes.csrf import csrf_required

shipping_bp = Blueprint("shipping", __name__, url_prefix="/api/shipping")
log = logging.getLogger(__name__)

# ── Konfiguracja kurierów ────────────────────────────────────────
CARRIERS = {
    "inpost_paczkomat": {
        "name": "InPost Paczkomat",
        "icon": "📦",
        "desc": "Odbiór z paczkomatu 24/7",
        "requires_point": True,
        "sizes": {
            "A": {"label": "Gabaryt A  (8×38×64 cm, do 25 kg)",  "price": 10.99},
            "B": {"label": "Gabaryt B (19×38×64 cm, do 25 kg)",  "price": 13.99},
            "C": {"label": "Gabaryt C (41×38×64 cm, do 25 kg)",  "price": 16.99},
        },
    },
    "inpost_kurier": {
        "name": "InPost Kurier",
        "icon": "🚚",
        "desc": "Dostawa kurierska do drzwi",
        "requires_point": False,
        "sizes": {
            "small":  {"label": "Do 1 kg",  "price": 14.99},
            "medium": {"label": "Do 5 kg",  "price": 17.99},
            "large":  {"label": "Do 20 kg", "price": 22.99},
        },
    },
    "dpd": {
        "name": "DPD Kurier",
        "icon": "🔴",
        "desc": "Dostawa kurierem DPD",
        "requires_point": False,
        "sizes": {
            "small":  {"label": "Do 1 kg",  "price": 13.99},
            "medium": {"label": "Do 5 kg",  "price": 16.99},
            "large":  {"label": "Do 20 kg", "price": 21.99},
        },
    },
    "poczta": {
        "name": "Poczta Polska",
        "icon": "📮",
        "desc": "Paczka ekonomiczna",
        "requires_point": False,
        "sizes": {
            "small":  {"label": "Do 1 kg",  "price":  8.50},
            "medium": {"label": "Do 5 kg",  "price": 11.50},
            "large":  {"label": "Do 10 kg", "price": 16.50},
        },
    },
    "orlen": {
        "name": "Orlen Paczka",
        "icon": "⛽",
        "desc": "Odbiór na stacji Orlen",
        "requires_point": True,
        "sizes": {
            "small":  {"label": "Mała",    "price":  8.99},
            "medium": {"label": "Średnia", "price": 11.99},
        },
    },
}

TRACKING_STATUS_LABELS = {
    "created":          "Etykieta utworzona",
    "dispatched":       "Nadano",
    "in_transit":       "W drodze",
    "out_for_delivery": "Dostarczana",
    "ready_for_pickup": "Czeka na odbiór",
    "delivered":        "Dostarczono",
    "failed":           "Nieudana próba",
    "return_in_progress": "Zwrot w toku",
    "returned":         "Zwrócono",
}

INPOST_API_BASE        = "https://api-shipx-pl.easypack24.net/v1"
INPOST_PUBLIC_API_BASE = "https://api.inpost.pl/v1"
INPOST_TOKEN           = os.environ.get("INPOST_API_TOKEN", "")
INPOST_ORG_ID          = os.environ.get("INPOST_ORG_ID", "")
INPOST_GEOWIDGET_TOKEN = os.environ.get("INPOST_GEOWIDGET_TOKEN", "")


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL  = "https://overpass.openstreetmap.fr/api/interpreter"
OSM_HEADERS   = {"User-Agent": "VipCiuchy/1.0 (vipciuchy.pl)"}


def _inpost_points_from_osm(city: str, post_code: str) -> list:
    """Zwraca paczkomaty InPost z OpenStreetMap w promieniu 5 km od szukanej lokalizacji."""
    query = post_code or city
    if not query:
        return []

    # Krok 1: geokodowanie — Nominatim (darmowe, bez klucza)
    try:
        geo = requests.get(
            NOMINATIM_URL,
            params={"q": query, "countrycodes": "pl", "format": "json", "limit": 1},
            headers=OSM_HEADERS, timeout=6
        ).json()
        if not geo:
            log.warning(f"Nominatim: brak wyników dla '{query}'")
            return []
        lat, lon = float(geo[0]["lat"]), float(geo[0]["lon"])
    except Exception as e:
        log.warning(f"Nominatim error: {e}")
        return []

    # Krok 2: Overpass — paczkomaty InPost w promieniu 5 km
    overpass_query = (
        f'[out:json][timeout:10];'
        f'node["amenity"="parcel_locker"]["operator"="InPost"](around:5000,{lat},{lon});'
        f'out 25;'
    )
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": overpass_query},
            headers=OSM_HEADERS, timeout=18
        )
        if not resp.ok:
            log.warning(f"Overpass HTTP {resp.status_code}")
            return []
        elements = resp.json().get("elements", [])
    except Exception as e:
        log.warning(f"Overpass error: {e}")
        return []

    points = []
    for el in elements:
        tags = el.get("tags", {})
        ref  = tags.get("ref", "")
        if not ref:
            continue
        # Adres z tagów OSM lub z URL
        addr_street = tags.get("addr:street", "")
        addr_no     = tags.get("addr:housenumber", "")
        addr_city   = tags.get("addr:city", city or "")
        if addr_street:
            address = f"ul. {addr_street} {addr_no}, {addr_city}".strip(", ")
        else:
            # Wydobądź miasto z URL InPost jeśli brak tagów adresowych
            website = tags.get("website", "")
            address = addr_city or ""
            if website:
                # URL: /paczkomat-{city}-{ref}-{street}-...
                parts = website.rstrip("/").split("/paczkomat-")
                if len(parts) > 1:
                    city_slug = parts[1].split("-")[0].capitalize()
                    address = city_slug if not address else f"{address}"

        points.append({
            "id":     ref,
            "name":   ref,
            "address": address,
            "desc":   tags.get("description", tags.get("opening_hours", "")),
            "status": "Operating",
        })
    return points


def _inpost_headers():
    return {"Authorization": f"Bearer {INPOST_TOKEN}", "Content-Type": "application/json"}


# ── Endpoint: geowidget token (bezpieczne przekazanie do frontu) ─
@shipping_bp.get("/geowidget-token")
def geowidget_token():
    return jsonify({"token": INPOST_GEOWIDGET_TOKEN, "available": bool(INPOST_GEOWIDGET_TOKEN)})


# ── Endpoint: pobierz opcje dostawy ─────────────────────────────
@shipping_bp.get("/options")
def get_options():
    result = []
    for key, c in CARRIERS.items():
        result.append({
            "id":             key,
            "name":           c["name"],
            "icon":           c["icon"],
            "desc":           c["desc"],
            "requires_point": c["requires_point"],
            "sizes":          {sk: sv for sk, sv in c["sizes"].items()},
        })
    return jsonify({"carriers": result})


# ── Endpoint: punkty InPost/Orlen w pobliżu ─────────────────────
@shipping_bp.get("/points")
def get_points():
    carrier   = request.args.get("carrier", "inpost_paczkomat")
    city      = (request.args.get("city", "") or "").strip()
    post_code = (request.args.get("post_code", "") or "").strip()

    if not city and not post_code:
        return jsonify({"error": "Podaj miasto lub kod pocztowy."}), 400

    if carrier == "inpost_paczkomat":
        # 1. Próba ShipX API (wymaga tokenu — dla kont biznesowych)
        if INPOST_TOKEN:
            try:
                resp = requests.get(
                    f"{INPOST_API_BASE}/points",
                    params={"type": "paczkomat", "near_place": city or post_code,
                            "per_page": 20, "fields": "name,address,location_description,status"},
                    headers=_inpost_headers(), timeout=5
                )
                if resp.ok:
                    data = resp.json()
                    points = [
                        {
                            "id":      p["name"],
                            "name":    p["name"],
                            "address": f"{p['address']['line1']}, {p['address']['city']}",
                            "desc":    p.get("location_description", ""),
                            "status":  p.get("status", "Operating"),
                        }
                        for p in data.get("items", [])
                    ]
                    return jsonify({"points": points, "source": "shipx"})
            except Exception as e:
                log.warning(f"InPost ShipX API error: {e}")

        # 2. OpenStreetMap (darmowe, bez klucza) — Nominatim + Overpass
        points = _inpost_points_from_osm(city, post_code)
        if points:
            return jsonify({"points": points, "source": "osm"})

        # 3. Ostateczny fallback — komunikat błędu
        return jsonify({"error": "Nie udało się pobrać listy paczkomatów. Spróbuj ponownie."}), 503

    if carrier == "orlen":
        # Orlen nie ma publicznego API — mock
        label = post_code or city
        mock = [
            {"id": f"ORLEN-{label.upper()}-01", "name": f"Orlen {label} 1",
             "address": f"ul. Naftowa 1, {city or label}", "desc": "Stacja całodobowa", "status": "Operating"},
            {"id": f"ORLEN-{label.upper()}-02", "name": f"Orlen {label} 2",
             "address": f"ul. Benzynowa 3, {city or label}", "desc": "", "status": "Operating"},
        ]
        return jsonify({"points": mock, "source": "mock"})

    return jsonify({"points": []})


# ── Endpoint: utwórz przesyłkę i wygeneruj etykietę ─────────────
@shipping_bp.post("/create")
@csrf_required
def create_shipment():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data     = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    if not order_id:
        return jsonify({"error": "Brakuje order_id."}), 400

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=? AND seller_id=?", (order_id, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Nie znaleziono zamówienia."}), 404

        # Sprawdź czy przesyłka już istnieje
        existing = conn.execute(
            "SELECT * FROM shipments WHERE order_id=?", (order_id,)
        ).fetchone()
        if existing:
            return jsonify({"shipment": _shipment_dict(existing)})

        order_keys   = order.keys()
        carrier      = order["shipping_carrier"]  if "shipping_carrier"   in order_keys else ""
        service      = order["shipping_service"]  if "shipping_service"   in order_keys else ""
        point_id     = order["shipping_point_id"] if "shipping_point_id"  in order_keys else ""
        recipient_js = order["shipping_recipient"] if "shipping_recipient" in order_keys else "{}"
        price        = order["shipping_amount"]   if "shipping_amount"    in order_keys else 0

        if not carrier:
            carrier = data.get("carrier", "inpost_paczkomat")
        if not service:
            service = data.get("service", "A")

        try:
            recipient = json.loads(recipient_js) if recipient_js else {}
        except Exception:
            recipient = {}

        # Dane nadawcy — z profilu sprzedawcy
        seller = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        seller_keys = seller.keys()
        sender = {
            "name":    seller["username"],
            "phone":   seller["phone"]   if "phone"   in seller_keys else "",
            "email":   seller["email"],
            "address": seller["address"] if "address" in seller_keys else "",
            "city":    seller["city"]    if "city"    in seller_keys else "",
            "postal":  seller["postal_code"] if "postal_code" in seller_keys else "",
        }

        tracking_number = ""
        label_url       = ""
        external_id     = ""

        # Próba API InPost
        if carrier == "inpost_paczkomat" and INPOST_TOKEN and INPOST_ORG_ID:
            result = _create_inpost_shipment(sender, recipient, point_id, service)
            if result:
                external_id     = result.get("id", "")
                tracking_number = result.get("tracking_number", "")
                label_url       = result.get("label_url", "")

        # Tryb dev — generuj mock
        if not tracking_number:
            import random, string
            tracking_number = "00" + "".join(random.choices(string.digits, k=20))
            label_url       = f"/api/shipping/mock-label/{order_id}"
            external_id     = f"dev-{order_id}"

        cur = conn.execute(
            """INSERT INTO shipments
               (order_id, carrier, service, sender_name, sender_phone, sender_address,
                recipient_name, recipient_phone, recipient_address, point_id,
                parcel_size, price, external_id, label_url, tracking_number, tracking_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'created')""",
            (order_id, carrier, service,
             sender["name"], sender.get("phone",""),
             f"{sender.get('address','')} {sender.get('city','')} {sender.get('postal','')}".strip(),
             recipient.get("name",""), recipient.get("phone",""),
             recipient.get("address","") or point_id,
             point_id, service, price, external_id, label_url, tracking_number)
        )
        shipment_id = cur.lastrowid

        # Zaktualizuj numer śledzenia w zamówieniu
        conn.execute(
            "UPDATE orders SET tracking_number=? WHERE id=?",
            (tracking_number, order_id)
        )
        conn.commit()

        shipment = conn.execute("SELECT * FROM shipments WHERE id=?", (shipment_id,)).fetchone()
        return jsonify({"shipment": _shipment_dict(shipment)}), 201
    finally:
        conn.close()


# ── Endpoint: pobierz etykietę ───────────────────────────────────
@shipping_bp.get("/<int:sid>/label")
def get_label(sid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        shipment = conn.execute(
            """SELECT s.* FROM shipments s
               JOIN orders o ON o.id = s.order_id
               WHERE s.id=? AND o.seller_id=?""",
            (sid, uid)
        ).fetchone()
        if not shipment:
            return jsonify({"error": "Nie znaleziono przesyłki."}), 404

        # Jeśli mamy prawdziwy URL etykiety InPost
        if INPOST_TOKEN and shipment["external_id"] and not shipment["external_id"].startswith("dev-"):
            try:
                resp = requests.get(
                    f"{INPOST_API_BASE}/shipments/{shipment['external_id']}/label",
                    headers={**_inpost_headers(), "Accept": "application/pdf"},
                    timeout=10
                )
                if resp.ok:
                    from flask import Response
                    return Response(
                        resp.content,
                        mimetype="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename=etykieta_{shipment['tracking_number']}.pdf"}
                    )
            except Exception as e:
                log.warning(f"InPost label fetch error: {e}")

        # Dev mode — zwróć mock HTML jako "etykietę"
        order_id = shipment["order_id"]
        label_html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>body{{font-family:sans-serif;padding:20px;max-width:400px;margin:0 auto;border:3px solid #000;margin-top:20px}}
h2{{text-align:center;border-bottom:2px solid #000;padding-bottom:10px}}
.field{{margin:8px 0}}.label{{font-size:.75rem;color:#666;text-transform:uppercase}}.value{{font-size:1rem;font-weight:700}}
.barcode{{text-align:center;font-size:1.5rem;letter-spacing:4px;padding:15px;background:#f5f5f5;border:1px solid #ccc;margin:15px 0}}
.carrier{{text-align:center;font-size:2rem;margin:10px 0}}
</style></head><body>
<h2>📦 ETYKIETA WYSYŁKOWA</h2>
<div class="carrier">{CARRIERS.get(shipment['carrier'],{}).get('icon','📦')} {CARRIERS.get(shipment['carrier'],{}).get('name','Kurier')}</div>
<div class="field"><div class="label">Numer przesyłki</div><div class="value">{shipment['tracking_number']}</div></div>
<div class="barcode">{shipment['tracking_number']}</div>
<div class="field"><div class="label">Nadawca</div><div class="value">{shipment['sender_name']}<br>{shipment['sender_address']}</div></div>
<div class="field"><div class="label">Odbiorca</div><div class="value">{shipment['recipient_name'] or 'Kupujący'}<br>{shipment['recipient_address'] or shipment['point_id'] or '—'}</div></div>
<div class="field"><div class="label">Gabaryt</div><div class="value">{shipment['parcel_size']}</div></div>
<p style="font-size:.7rem;color:#aaa;text-align:center;margin-top:20px">Etykieta wygenerowana przez Rzeczy z Drugiej Ręki (DEV MODE)</p>
</body></html>"""
        from flask import Response
        return Response(label_html, mimetype="text/html",
                        headers={"Content-Disposition": f"inline; filename=etykieta_{shipment['tracking_number']}.html"})
    finally:
        conn.close()


# ── Endpoint: śledź przesyłkę ────────────────────────────────────
@shipping_bp.get("/track/<tracking_number>")
def track_shipment(tracking_number):
    if not tracking_number:
        return jsonify({"error": "Podaj numer śledzenia."}), 400

    # Próba InPost tracking API (publiczne, bez auth)
    try:
        resp = requests.get(
            f"{INPOST_API_BASE}/tracking/{tracking_number}",
            timeout=5
        )
        if resp.ok:
            data   = resp.json()
            status = _map_inpost_status(data.get("status", ""))
            events = [
                {
                    "status":      _map_inpost_status(e.get("status", "")),
                    "description": e.get("description", ""),
                    "datetime":    e.get("datetime", ""),
                }
                for e in data.get("tracking_details", [])
            ]
            return jsonify({
                "tracking_number": tracking_number,
                "status":          status,
                "status_label":    TRACKING_STATUS_LABELS.get(status, status),
                "events":          events,
                "source":          "inpost",
            })
    except Exception:
        pass

    # Szukaj w lokalnej bazie
    conn = get_db()
    try:
        shipment = conn.execute(
            "SELECT * FROM shipments WHERE tracking_number=?", (tracking_number,)
        ).fetchone()
        if shipment:
            status = shipment["tracking_status"]
            try:
                events = json.loads(shipment["tracking_events"] or "[]")
            except Exception:
                events = []
            return jsonify({
                "tracking_number": tracking_number,
                "status":          status,
                "status_label":    TRACKING_STATUS_LABELS.get(status, status),
                "events":          events,
                "source":          "local",
            })
        return jsonify({"error": "Nie znaleziono przesyłki."}), 404
    finally:
        conn.close()


# ── Endpoint: szczegóły przesyłki zamówienia ─────────────────────
@shipping_bp.get("/order/<int:order_id>")
def shipment_by_order(order_id):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=? AND (buyer_id=? OR seller_id=?)",
            (order_id, uid, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Brak dostępu."}), 403

        shipment = conn.execute(
            "SELECT * FROM shipments WHERE order_id=?", (order_id,)
        ).fetchone()
        if not shipment:
            return jsonify({"shipment": None})
        return jsonify({"shipment": _shipment_dict(shipment)})
    finally:
        conn.close()


# ── Mock label endpoint ──────────────────────────────────────────
@shipping_bp.get("/mock-label/<int:order_id>")
def mock_label(order_id):
    conn = get_db()
    try:
        shipment = conn.execute("SELECT * FROM shipments WHERE order_id=?", (order_id,)).fetchone()
        if not shipment:
            return jsonify({"error": "Brak etykiety."}), 404
        from flask import redirect
        return redirect(f"/api/shipping/{shipment['id']}/label")
    finally:
        conn.close()


# ── InPost helper ─────────────────────────────────────────────────
def _create_inpost_shipment(sender, recipient, point_id, size):
    try:
        payload = {
            "receiver": {
                "name":    recipient.get("name", "Kupujący"),
                "phone":   recipient.get("phone", ""),
                "email":   recipient.get("email", ""),
                "address": {"line1": recipient.get("address",""), "city": recipient.get("city",""), "post_code": recipient.get("postal",""), "country_code": "PL"},
            },
            "sender": {
                "name":    sender.get("name",""),
                "phone":   sender.get("phone",""),
                "email":   sender.get("email",""),
                "address": {"line1": sender.get("address",""), "city": sender.get("city",""), "post_code": sender.get("postal",""), "country_code": "PL"},
            },
            "parcels": [{"template": size or "A"}],
            "service":  "inpost_locker_standard",
            "custom_attributes": {"target_point": point_id},
        }
        resp = requests.post(
            f"{INPOST_API_BASE}/organizations/{INPOST_ORG_ID}/shipments",
            headers=_inpost_headers(),
            json=payload,
            timeout=10
        )
        if resp.ok:
            data = resp.json()
            return {
                "id":              data.get("id",""),
                "tracking_number": data.get("tracking_number",""),
                "label_url":       f"/api/shipping/{data.get('id','')}/label",
            }
    except Exception as e:
        log.error(f"InPost create shipment error: {e}")
    return None


def _map_inpost_status(raw):
    mapping = {
        "created":              "created",
        "offers_prepared":      "created",
        "offer_selected":       "created",
        "confirmed":            "created",
        "dispatched_by_sender_to_pok": "dispatched",
        "dispatched_by_sender": "dispatched",
        "collected_from_sender":"dispatched",
        "taken_by_courier":     "in_transit",
        "adopted_at_sorting_point": "in_transit",
        "sent_from_sorting_point":  "in_transit",
        "adopted_at_source_branch": "in_transit",
        "out_for_delivery":     "out_for_delivery",
        "ready_for_pickup":     "ready_for_pickup",
        "pickup_reminder_sent": "ready_for_pickup",
        "delivered":            "delivered",
        "pickup_time_expired":  "failed",
        "avizo":                "failed",
        "not_delivered":        "failed",
        "return_in_progress":   "return_in_progress",
        "returned_to_sender":   "returned",
    }
    return mapping.get(raw, "in_transit")


def _shipment_dict(row):
    keys = row.keys()
    def g(k, d=""):
        return row[k] if k in keys else d
    return {
        "id":               row["id"],
        "order_id":         row["order_id"],
        "carrier":          row["carrier"],
        "service":          g("service"),
        "sender_name":      g("sender_name"),
        "sender_address":   g("sender_address"),
        "recipient_name":   g("recipient_name"),
        "recipient_address":g("recipient_address"),
        "point_id":         g("point_id"),
        "parcel_size":      g("parcel_size"),
        "price":            g("price", 0),
        "external_id":      g("external_id"),
        "label_url":        g("label_url"),
        "tracking_number":  g("tracking_number"),
        "tracking_status":  g("tracking_status","created"),
        "tracking_events":  json.loads(g("tracking_events","[]") or "[]"),
        "tracking_updated_at": g("tracking_updated_at"),
        "created_at":       row["created_at"],
    }
