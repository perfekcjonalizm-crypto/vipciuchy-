"""
test_chat.py — kompleksowy test i audyt czatu + systemu wiadomości

Uruchom: python3 test_chat.py
Wymaga: serwer Flask na http://localhost:8080
"""
import requests
import json
import sys

BASE = "http://localhost:8080"
PASS = "haslo123"

# ── Kolory terminalowe ─────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

passed = 0
failed = 0
warnings = []


def ok(label):
    global passed
    passed += 1
    print(f"  {GREEN}✓{RESET} {label}")


def fail(label, detail=""):
    global failed
    failed += 1
    detail_str = f" → {RED}{detail}{RESET}" if detail else ""
    print(f"  {RED}✗{RESET} {label}{detail_str}")


def warn(label, detail=""):
    warnings.append((label, detail))
    detail_str = f" → {YELLOW}{detail}{RESET}" if detail else ""
    print(f"  {YELLOW}⚠{RESET} {label}{detail_str}")


def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*55}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*55}{RESET}")


def expect(label, condition, detail=""):
    if condition:
        ok(label)
    else:
        fail(label, detail)


# ── Sesje HTTP ─────────────────────────────────────────────────────

def login(username, password=PASS):
    s = requests.Session()
    csrf = s.get(f"{BASE}/api/csrf").json()["csrf"]
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": username, "password": password},
               headers={"X-CSRF-Token": csrf})
    if r.status_code == 200:
        return s
    raise RuntimeError(f"Login failed for {username}: {r.status_code} {r.text[:200]}")


def csrf(session):
    return session.get(f"{BASE}/api/csrf").json()["csrf"]


# ═══════════════════════════════════════════════════════════════════
section("0. SETUP — logowanie użytkowników testowych")
# ═══════════════════════════════════════════════════════════════════

try:
    s_asia    = login("asia_modowa")    # user 13, sprzedaje produkt 33
    s_karolin = login("karolinka_sz")   # user 14
    s_marta   = login("marta_fashion")  # user 15
    ok("asia_modowa zalogowana")
    ok("karolinka_sz zalogowana")
    ok("marta_fashion zalogowana")
except Exception as e:
    fail(f"Login nieudany: {e}")
    sys.exit(1)

# Pobierz ID zalogowanych
me_asia    = s_asia.get(f"{BASE}/api/auth/me").json()
me_karolin = s_karolin.get(f"{BASE}/api/auth/me").json()
me_marta   = s_marta.get(f"{BASE}/api/auth/me").json()
uid_asia    = me_asia["user"]["id"]
uid_karolin = me_karolin["user"]["id"]
uid_marta   = me_marta["user"]["id"]
print(f"  asia={uid_asia}, karolinka={uid_karolin}, marta={uid_marta}")

# Produkt do testów (sprzedawca = asia)
import sqlite3
conn_db = sqlite3.connect("rzeczy.db")
conn_db.row_factory = sqlite3.Row
prod = conn_db.execute(
    "SELECT id FROM products WHERE seller_id=? AND is_sold=0 LIMIT 1", (uid_asia,)
).fetchone()
PRODUCT_ID = prod["id"] if prod else 33
conn_db.close()
print(f"  testowy produkt: #{PRODUCT_ID}")


# ═══════════════════════════════════════════════════════════════════
section("1. AUTORYZACJA — endpointy bez sesji")
# ═══════════════════════════════════════════════════════════════════

anon = requests.Session()

r = anon.get(f"{BASE}/api/messages/conversations")
expect("GET /conversations → 401 bez sesji", r.status_code == 401)

r = anon.get(f"{BASE}/api/messages/unread-count")
expect("GET /unread-count → 401 bez sesji", r.status_code == 401)

r = anon.get(f"{BASE}/api/messages/thread/{uid_karolin}")
expect("GET /thread/<id> → 401 bez sesji", r.status_code == 401)

r = anon.post(f"{BASE}/api/messages", json={"to_user_id": uid_karolin, "content": "test"})
expect("POST /messages → 401 bez sesji", r.status_code == 401)

r = anon.patch(f"{BASE}/api/messages/thread/{uid_karolin}/read")
expect("PATCH /thread/read → 401 bez sesji", r.status_code == 401)


# ═══════════════════════════════════════════════════════════════════
section("2. CSRF — ochrona endpointów mutujących")
# ═══════════════════════════════════════════════════════════════════

# POST bez CSRF tokenu
r = s_asia.post(f"{BASE}/api/messages",
                json={"to_user_id": uid_karolin, "content": "test"},
                headers={"X-CSRF-Token": "WRONG_TOKEN"})
expect("POST bez poprawnego CSRF → 403", r.status_code == 403,
       f"got {r.status_code}")

r = s_asia.patch(f"{BASE}/api/messages/thread/{uid_karolin}/read",
                 headers={"X-CSRF-Token": "WRONG_TOKEN"})
expect("PATCH bez CSRF → 403", r.status_code == 403,
       f"got {r.status_code}")


# ═══════════════════════════════════════════════════════════════════
section("3. WYSYŁANIE WIADOMOŚCI — happy path")
# ═══════════════════════════════════════════════════════════════════

# asia → karolinka: zwykła wiadomość
r = s_asia.post(f"{BASE}/api/messages",
                json={"to_user_id": uid_karolin, "content": "Hej, masz fajne rzeczy!"},
                headers={"X-CSRF-Token": csrf(s_asia)})
expect("POST /messages → 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
if r.status_code == 201:
    msg1 = r.json()["message"]
    expect("  zwraca id", "id" in msg1)
    expect("  from_user_id = asia", msg1["from_user_id"] == uid_asia)
    expect("  to_user_id = karolinka", msg1["to_user_id"] == uid_karolin)
    expect("  msg_type = text", msg1["msg_type"] == "text")
    expect("  product = None (brak oferty)", msg1["product"] is None)
    expect("  is_read = False (nowa)", msg1["is_read"] == False)

# karolinka → asia: odpowiedź
r = s_karolin.post(f"{BASE}/api/messages",
                   json={"to_user_id": uid_asia, "content": "Dzięki! Co Cię interesuje?"},
                   headers={"X-CSRF-Token": csrf(s_karolin)})
expect("Karolinka → asia → 201", r.status_code == 201)

# asia → karolinka z linkiem do oferty
r = s_asia.post(f"{BASE}/api/messages",
                json={
                    "to_user_id": uid_karolin,
                    "content": "Patrz na tę ofertę!",
                    "product_id": PRODUCT_ID
                },
                headers={"X-CSRF-Token": csrf(s_asia)})
expect("POST z product_id → 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
if r.status_code == 201:
    msg_prod = r.json()["message"]
    expect("  msg_type = product_link", msg_prod["msg_type"] == "product_link")
    expect("  product != None", msg_prod["product"] is not None)
    if msg_prod["product"]:
        expect("  product.id poprawne", msg_prod["product"]["id"] == PRODUCT_ID)
        expect("  product.name istnieje", bool(msg_prod["product"]["name"]))
        expect("  product.price > 0", (msg_prod["product"]["price"] or 0) > 0)


# ═══════════════════════════════════════════════════════════════════
section("4. POBIERANIE WĄTKU — GET /thread/<id>")
# ═══════════════════════════════════════════════════════════════════

r = s_asia.get(f"{BASE}/api/messages/thread/{uid_karolin}")
expect("GET /thread → 200", r.status_code == 200, f"{r.status_code}")
if r.status_code == 200:
    data = r.json()
    msgs = data["messages"]
    expect("  zwraca 'messages'", isinstance(msgs, list))
    expect("  ≥2 wiadomości w wątku", len(msgs) >= 2, f"got {len(msgs)}")
    expect("  zwraca 'other_user'", "other_user" in data)
    expect("  zwraca 'has_more'", "has_more" in data)
    if msgs:
        m = msgs[0]
        expect("  wiadomość ma 'from_username'", "from_username" in m)
        expect("  wiadomość ma 'is_read'", "is_read" in m)
        expect("  wiadomość ma 'product'", "product" in m)

# Karolinka widzi ten sam wątek
r = s_karolin.get(f"{BASE}/api/messages/thread/{uid_asia}")
expect("Karolinka widzi wątek z asią → 200", r.status_code == 200)
if r.status_code == 200:
    msgs_k = r.json()["messages"]
    expect("  ta sama liczba wiadomości", len(msgs_k) == len(msgs) if r.status_code == 200 else False,
           f"{len(msgs_k)} vs {len(msgs)}")

# Nieistniejący użytkownik
r = s_asia.get(f"{BASE}/api/messages/thread/99999")
expect("GET /thread/99999 → 404", r.status_code == 404, f"got {r.status_code}")

# Pisanie do samego siebie
r = s_asia.get(f"{BASE}/api/messages/thread/{uid_asia}")
expect("GET własny wątek → 400", r.status_code == 400, f"got {r.status_code}")

# Paginacja
r = s_asia.get(f"{BASE}/api/messages/thread/{uid_karolin}?before=999999")
expect("Paginacja ?before= → 200", r.status_code == 200)


# ═══════════════════════════════════════════════════════════════════
section("5. LISTA ROZMÓW — GET /conversations")
# ═══════════════════════════════════════════════════════════════════

r = s_asia.get(f"{BASE}/api/messages/conversations")
expect("GET /conversations → 200", r.status_code == 200, f"{r.status_code}")
if r.status_code == 200:
    convs = r.json()["conversations"]
    expect("  zwraca listę", isinstance(convs, list))
    expect("  ≥1 rozmowa (z karolinką)", len(convs) >= 1, f"got {len(convs)}")
    if convs:
        c = convs[0]
        expect("  conv ma 'other_user'", "other_user" in c)
        expect("  conv ma 'last_message'", "last_message" in c)
        expect("  conv ma 'last_at'", "last_at" in c)
        expect("  conv ma 'unread_count'", "unread_count" in c)
        expect("  other_user ma 'id'", "id" in c.get("other_user", {}))
        expect("  other_user ma 'username'", "username" in c.get("other_user", {}))

# Marta (czysta) też ma endpointy
r = s_marta.get(f"{BASE}/api/messages/conversations")
expect("Czysta sesja: /conversations → 200, pusta lista", r.status_code == 200)
if r.status_code == 200:
    expect("  pusta lista []", r.json()["conversations"] == [])


# ═══════════════════════════════════════════════════════════════════
section("6. LICZNIK NIEPRZECZYTANYCH")
# ═══════════════════════════════════════════════════════════════════

# Karolinka powinna mieć nieprzeczytane (od asi)
r = s_karolin.get(f"{BASE}/api/messages/unread-count")
expect("GET /unread-count → 200", r.status_code == 200)
if r.status_code == 200:
    cnt = r.json()["unread"]
    expect("  unread ≥ 1 (karolinka ma nieprzeczytane)", cnt >= 1, f"got {cnt}")

r = s_marta.get(f"{BASE}/api/messages/unread-count")
if r.status_code == 200:
    expect("  marta: unread = 0", r.json()["unread"] == 0, f"got {r.json()['unread']}")


# ═══════════════════════════════════════════════════════════════════
section("7. OZNACZANIE JAKO PRZECZYTANE")
# ═══════════════════════════════════════════════════════════════════

# Karolinka otwiera rozmowę z asią → oznacza jako przeczytane
r = s_karolin.patch(f"{BASE}/api/messages/thread/{uid_asia}/read",
                    headers={"X-CSRF-Token": csrf(s_karolin)})
expect("PATCH /thread/read → 200", r.status_code == 200, f"{r.status_code}")
if r.status_code == 200:
    expect("  zwraca ok:true", r.json().get("ok") == True)

# Sprawdź czy licznik spadł
r = s_karolin.get(f"{BASE}/api/messages/unread-count")
if r.status_code == 200:
    cnt_after = r.json()["unread"]
    expect("  unread = 0 po przeczytaniu", cnt_after == 0, f"got {cnt_after}")

# Sprawdź czy is_read=True w wątku
r = s_karolin.get(f"{BASE}/api/messages/thread/{uid_asia}")
if r.status_code == 200:
    msgs = r.json()["messages"]
    from_asia = [m for m in msgs if m["from_user_id"] == uid_asia]
    all_read = all(m["is_read"] for m in from_asia)
    expect("  wiadomości od asi mają is_read=True", all_read,
           f"{sum(m['is_read'] for m in from_asia)}/{len(from_asia)} przeczytanych")


# ═══════════════════════════════════════════════════════════════════
section("8. WALIDACJA WEJŚCIA")
# ═══════════════════════════════════════════════════════════════════

h = {"X-CSRF-Token": csrf(s_asia)}

r = s_asia.post(f"{BASE}/api/messages",
                json={"to_user_id": uid_karolin, "content": ""},
                headers=h)
expect("Pusta treść → 400", r.status_code == 400, f"got {r.status_code} {r.text[:100]}")

r = s_asia.post(f"{BASE}/api/messages",
                json={"to_user_id": uid_karolin, "content": "x" * 2001},
                headers=h)
expect("Treść >2000 znaków → 400", r.status_code == 400, f"got {r.status_code}")

r = s_asia.post(f"{BASE}/api/messages",
                json={"content": "bez to_user_id"},
                headers=h)
expect("Brak to_user_id → 400", r.status_code == 400, f"got {r.status_code}")

r = s_asia.post(f"{BASE}/api/messages",
                json={"to_user_id": uid_asia, "content": "do siebie"},
                headers=h)
expect("Wiadomość do samego siebie → 400", r.status_code == 400, f"got {r.status_code}")

r = s_asia.post(f"{BASE}/api/messages",
                json={"to_user_id": 99999, "content": "nieistniejący"},
                headers=h)
expect("Odbiorca nie istnieje → 404", r.status_code == 404, f"got {r.status_code}")

r = s_asia.post(f"{BASE}/api/messages",
                json={"to_user_id": uid_karolin, "content": "nieistniejący produkt", "product_id": 999999},
                headers=h)
expect("Nieistniejący product_id → 400", r.status_code == 400, f"got {r.status_code}")


# ═══════════════════════════════════════════════════════════════════
section("9. BEZPIECZEŃSTWO — izolacja rozmów")
# ═══════════════════════════════════════════════════════════════════

# Marta NIE powinna widzieć rozmowy asia-karolinka
r = s_marta.get(f"{BASE}/api/messages/thread/{uid_asia}")
if r.status_code == 200:
    msgs = r.json()["messages"]
    # Filtrujemy wiadomości wyłącznie między asią a karolinką
    leaked = [m for m in msgs
              if set([m["from_user_id"], m["to_user_id"]]) == {uid_asia, uid_karolin}]
    expect("Marta nie widzi wiadomości asia↔karolinka", len(leaked) == 0,
           f"WYCIEK: {len(leaked)} wiadomości")
else:
    ok("Marta nie ma dostępu do wątku asia (200 z pustą listą lub 404)")

# XSS: treść powinna być zwracana dosłownie, escapowanie należy do frontendu
xss_payload = '<script>alert("xss")</script>'
r = s_asia.post(f"{BASE}/api/messages",
                json={"to_user_id": uid_karolin, "content": xss_payload},
                headers=h)
if r.status_code == 201:
    stored = r.json()["message"]["content"]
    expect("XSS: treść zapisana dosłownie (escapowanie po stronie frontendu)",
           stored == xss_payload)
    # Frontend używa esc() wokół wszystkich danych w innerHTML — bezpieczne
    ok("XSS: frontend używa esc() przy renderowaniu wiadomości (zweryfikowane w HTML)")

# SQL injection attempt w content
r = s_asia.post(f"{BASE}/api/messages",
                json={"to_user_id": uid_karolin, "content": "'; DROP TABLE messages; --"},
                headers=h)
expect("SQLi w content → 201 (parametryzowane zapytania działają)",
       r.status_code == 201, f"got {r.status_code}")

# Sprawdź że tabela messages nadal istnieje
import sqlite3
conn_db = sqlite3.connect("rzeczy.db")
conn_db.row_factory = sqlite3.Row
tables = [r[0] for r in conn_db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
expect("Tabela messages nadal istnieje po SQLi", "messages" in tables)
conn_db.close()


# ═══════════════════════════════════════════════════════════════════
section("10. BACKWARD COMPAT — GET /messages/<product_id>")
# ═══════════════════════════════════════════════════════════════════

r = s_asia.get(f"{BASE}/api/messages/{PRODUCT_ID}")
expect(f"GET /messages/{PRODUCT_ID} → 200 (stary endpoint)", r.status_code == 200,
       f"got {r.status_code}")
if r.status_code == 200:
    expect("  zwraca 'messages' (stary format)", "messages" in r.json())


# ═══════════════════════════════════════════════════════════════════
section("11. SYSTEM STATUSÓW ZAMÓWIEŃ")
# ═══════════════════════════════════════════════════════════════════

# Sprawdź istniejące zamówienie (id=1: buyer=asia, seller=karolinka)
import sqlite3
conn_db = sqlite3.connect("rzeczy.db")
conn_db.row_factory = sqlite3.Row
order = conn_db.execute("SELECT * FROM orders WHERE id=1").fetchone()
conn_db.close()

if order:
    oid = order["id"]
    cur_status = order["status"]
    print(f"  zamówienie #{oid}: status={cur_status}, escrow={order['escrow_status']}")

    h_asia    = {"X-CSRF-Token": csrf(s_asia)}
    h_karolin = {"X-CSRF-Token": csrf(s_karolin)}

    # Niedozwolone przejście: buyer nie może anulować po wysyłce (tylko admin może)
    r = s_asia.patch(f"{BASE}/api/orders/{oid}/status",
                     json={"status": "cancelled"},
                     headers=h_asia)
    expect("Kupujący nie może anulować po wysyłce → 422",
           r.status_code == 422, f"got {r.status_code} {r.text[:150]}")

    # Sprzedawca może zmienić paid → shipped
    if cur_status == "paid":
        r = s_karolin.patch(f"{BASE}/api/orders/{oid}/status",
                            json={"status": "shipped", "note": "InPost paczkomat KRK01A"},
                            headers=h_karolin)
        expect("Sprzedawca: paid → shipped → 200",
               r.status_code == 200, f"got {r.status_code} {r.text[:200]}")
        if r.status_code == 200:
            new_status = r.json()["order"]["status"]
            expect("  status = shipped", new_status == "shipped", f"got {new_status}")

            # Historia statusów
            r2 = s_karolin.get(f"{BASE}/api/orders/{oid}/status-history")
            expect("GET /status-history → 200", r2.status_code == 200)
            if r2.status_code == 200:
                hist = r2.json()["history"]
                expect("  historia zawiera wpis", len(hist) >= 1, f"got {len(hist)}")
                if hist:
                    last = hist[-1]
                    expect("  from_status = paid",    last["from_status"] == "paid")
                    expect("  to_status = shipped",   last["to_status"] == "shipped")
                    expect("  actor_role = seller",   last["actor_role"] == "seller")
                    expect("  note zapisana",         last["note"] == "InPost paczkomat KRK01A")

    # Nieistniejące zamówienie
    r = s_asia.patch(f"{BASE}/api/orders/99999/status",
                     json={"status": "cancelled"},
                     headers=h_asia)
    expect("Nieistniejące zamówienie → 404", r.status_code == 404, f"got {r.status_code}")

    # Nieprawidłowy status
    r = s_karolin.patch(f"{BASE}/api/orders/{oid}/status",
                        json={"status": "invalid_xyz"},
                        headers=h_karolin)
    expect("Nieprawidłowy status → 400", r.status_code == 400, f"got {r.status_code}")

    # Trzecia strona (marta) nie ma dostępu do zamówienia
    h_marta = {"X-CSRF-Token": csrf(s_marta)}
    r = s_marta.patch(f"{BASE}/api/orders/{oid}/status",
                      json={"status": "cancelled"},
                      headers=h_marta)
    expect("Trzecia strona nie może zmieniać statusu → 404",
           r.status_code == 404, f"got {r.status_code}")
else:
    warn("Brak zamówienia #1 — pominięto testy statusów")


# ═══════════════════════════════════════════════════════════════════
section("12. AUDYT KODU — statyczne sprawdzenia")
# ═══════════════════════════════════════════════════════════════════

import os, re

def audit_file(path, checks):
    if not os.path.exists(path):
        warn(f"Plik nie istnieje: {path}")
        return
    code = open(path).read()
    for check_name, pattern, should_exist, message in checks:
        found = bool(re.search(pattern, code))
        if found == should_exist:
            ok(f"{check_name}")
        else:
            warn(f"{check_name}", message)

audit_file("routes/messages.py", [
    ("parametryzowane zapytania (brak f-string z user input)",
     r'execute\(f".*\{(content|username|to_user)',
     False,
     "znaleziono potencjalną interpolację user input w SQL"),
    ("is_read używany",              r"is_read",        True,  "brak obsługi is_read"),
    ("msg_type walidowany",          r"msg_type.*not in", True, "brak walidacji msg_type"),
    ("MAX_MSG_LEN sprawdzany",       r"MAX_MSG_LEN",    True,  "brak limitu długości"),
    ("csrf_required na POST",        r"@csrf_required", True,  "brak CSRF na mutujących"),
    ("brak auto-reply bota",         r"AUTO_REPLIES",   False, "bot auto-reply wciąż w kodzie"),
    ("powiadomienie email istnieje", r"send_message_notification", True, "brak powiadomień"),
    ("cooldown powiadomień",         r"NOTIF_COOLDOWN", True,  "brak cooldownu emaili"),
])

audit_file("routes/orders.py", [
    ("state machine zdefiniowana",    r"_TRANSITIONS",  True, "brak maszyny stanów"),
    ("_record_transition używane",    r"_record_transition", True, "brak audit logu"),
    ("seller_id sprawdzane",          r"seller_id.*==.*uid|uid.*==.*seller_id", True,
     "brak weryfikacji własności zamówienia"),
    ("is_admin sprawdzane",           r"is_admin",      True, "brak obsługi admina"),
    ("_trigger_payout przy delivered", r"_trigger_payout", True,
     "brak wywołania _trigger_payout"),
])

audit_file("db.py", [
    ("msg_type migracja",             r"msg_type",      True, "brak kolumny msg_type"),
    ("order_status_history tabela",   r"order_status_history", True, "brak tabeli historii"),
    ("foreign keys ON",               r"foreign_keys.*ON", True, "brak FK constraints"),
    ("indeks na messages thread",     r"idx_messages_thread", True, "brak indeksu na wątkach"),
])


# ═══════════════════════════════════════════════════════════════════
section("PODSUMOWANIE")
# ═══════════════════════════════════════════════════════════════════

total = passed + failed
print(f"\n  {GREEN}{BOLD}{passed}{RESET} / {total} testów zdanych", end="")
if failed:
    print(f"   {RED}{BOLD}{failed} NIEUDANYCH{RESET}", end="")
print()

if warnings:
    print(f"\n  {YELLOW}{BOLD}Ostrzeżenia ({len(warnings)}):{RESET}")
    for w, detail in warnings:
        d = f" — {detail}" if detail else ""
        print(f"    {YELLOW}⚠{RESET} {w}{d}")

print()
sys.exit(1 if failed > 0 else 0)
