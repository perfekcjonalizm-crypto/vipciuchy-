"""
seed.py — wypełnia bazę danymi testowymi
Uruchom raz: python3 seed.py
"""
import json
from werkzeug.security import generate_password_hash
from db import get_db, init_db

# Unsplash image URLs per category
IMG = {
    "dress":    "https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=600&q=80",
    "coat":     "https://images.unsplash.com/photo-1539533018447-63fcce2678e3?w=600&q=80",
    "jeans":    "https://images.unsplash.com/photo-1542272604-787c3835535d?w=600&q=80",
    "sneakers": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&q=80",
    "bag":      "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=600&q=80",
    "blouse":   "https://images.unsplash.com/photo-1562157873-818bc0726f68?w=600&q=80",
    "skirt":    "https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?w=600&q=80",
    "sweater":  "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=600&q=80",
    "jacket":   "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=600&q=80",
    "acc":      "https://images.unsplash.com/photo-1611085583191-a3b181a88401?w=600&q=80",
    "boots":    "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=600&q=80",
    "suit":     "https://images.unsplash.com/photo-1594938298603-c8148c4b4a02?w=600&q=80",
}

USERS = [
    {"username": "asia_modowa",   "email": "asia_modowa@rzeczy.local"},
    {"username": "karolinka_sz",  "email": "karolinka_sz@rzeczy.local"},
    {"username": "marta_fashion", "email": "marta_fashion@rzeczy.local"},
    {"username": "joanna_styl",   "email": "joanna_styl@rzeczy.local"},
    {"username": "zuzia_vintage", "email": "zuzia_vintage@rzeczy.local"},
    {"username": "paulina_looks", "email": "paulina_looks@rzeczy.local"},
    {"username": "ela_glam",      "email": "ela_glam@rzeczy.local"},
    {"username": "natka_chic",    "email": "natka_chic@rzeczy.local"},
    {"username": "monika_style",  "email": "monika_style@rzeczy.local"},
    {"username": "ania_secondhand", "email": "ania_secondhand@rzeczy.local"},
    {"username": "basia_trendy",  "email": "basia_trendy@rzeczy.local"},
    {"username": "ola_vintage",   "email": "ola_vintage@rzeczy.local"},
]

PRODS = [
    # ── Sukienki ────────────────────────────────────────────────
    {
        "name": "Sukienka w kwiaty midi", "brand": "Zara", "price": 89, "size": "S",
        "cond": "Nowe z metką", "emoji": "👗", "seller": "asia_modowa",
        "img": IMG["dress"],
        "desc": "Piękna sukienka w kwiaty. Stan idealny, noszona tylko raz. 100% wiskoza, długość midi, dekolt V. Idealna na wesela i przyjęcia.",
    },
    {
        "name": "Sukienka satynowa czarna", "brand": "Mango", "price": 119, "size": "M",
        "cond": "Nowe bez metki", "emoji": "👗", "seller": "karolinka_sz",
        "img": IMG["dress"],
        "desc": "Elegancka sukienka satynowa, czarna, długość midi. Zamek z tyłu. Materiał: 100% poliester z satynowym wykończeniem. Obwód biustu 88 cm, talia 72 cm.",
    },
    {
        "name": "Sukienka letnia boho", "brand": "H&M", "price": 55, "size": "XS",
        "cond": "Dobry stan", "emoji": "👗", "seller": "zuzia_vintage",
        "img": IMG["dress"],
        "desc": "Zwiewna sukienka boho na lato. Bawełna 100%, wzór paisley. Rozmiar XS, długość do kolan. Kilkukrotnie prana, bez uszkodzeń.",
    },
    {
        "name": "Sukienka dżinsowa mini", "brand": "Reserved", "price": 69, "size": "S",
        "cond": "Dobry stan", "emoji": "👗", "seller": "ola_vintage",
        "img": IMG["dress"],
        "desc": "Sukienka mini z dżinsu, zapinana na guziki. Stan bardzo dobry. Rozmiar S, obwód biustu 84 cm. Prosta, klasyczna forma.",
    },

    # ── Płaszcze ────────────────────────────────────────────────
    {
        "name": "Płaszcz wełniany camel", "brand": "Reserved", "price": 145, "size": "M",
        "cond": "Dobry stan", "emoji": "🧥", "seller": "karolinka_sz",
        "img": IMG["coat"],
        "desc": "Klasyczny płaszcz camel. Wełna 60%, poliester 40%. Idealny na jesień i wiosnę. Długość do kolan, dwa guziki, kieszenie.",
    },
    {
        "name": "Płaszcz oversize szary", "brand": "Massimo Dutti", "price": 220, "size": "L",
        "cond": "Nowe z metką", "emoji": "🧥", "seller": "paulina_looks",
        "img": IMG["coat"],
        "desc": "Elegancki płaszcz oversize w kolorze szarym. Wełna 80%, kaszmir 20%. Noszon tylko raz na pokazie. Rozmiar L, długość 110 cm.",
    },
    {
        "name": "Trencz beżowy klasyczny", "brand": "Zara", "price": 175, "size": "M",
        "cond": "Dobry stan", "emoji": "🧥", "seller": "marta_fashion",
        "img": IMG["coat"],
        "desc": "Klasyczny trencz beżowy z paskiem. Poliester 65%, bawełna 35%. Długość midi, podpinka na zimę. Stan bardzo dobry.",
    },

    # ── Jeansy / Spodnie ────────────────────────────────────────
    {
        "name": "Jeansy 501 high waist", "brand": "Levi's", "price": 110, "size": "XS",
        "cond": "Używane", "emoji": "👖", "seller": "zuzia_vintage",
        "img": IMG["jeans"],
        "desc": "Kultowe Levi's 501, rozmiar 24/30. Drobne ślady użytkowania. Szeroka nogawka, wysoki stan, kolor indygo.",
    },
    {
        "name": "Spodnie palazzo czarne", "brand": "Arket", "price": 130, "size": "36",
        "cond": "Nowe bez metki", "emoji": "👖", "seller": "monika_style",
        "img": IMG["jeans"],
        "desc": "Spodnie palazzo z szerokimi nogawkami. 100% wiskoza, kolor czarny. Rozmiar 36, długość 104 cm. Idealne do biura.",
    },
    {
        "name": "Jeansy skinny fit niebieskie", "brand": "Pull&Bear", "price": 65, "size": "38",
        "cond": "Dobry stan", "emoji": "👖", "seller": "basia_trendy",
        "img": IMG["jeans"],
        "desc": "Jeansy skinny fit, kolor jasnoniebieski. Rozmiar 38. Elastan 2%, bawełna 98%. Kilkukrotnie prane, bez dziur.",
    },

    # ── Buty ────────────────────────────────────────────────────
    {
        "name": "Air Force 1 białe", "brand": "Nike", "price": 220, "size": "38",
        "cond": "Nowe z metką", "emoji": "👟", "seller": "marta_fashion",
        "img": IMG["sneakers"],
        "desc": "Nike Air Force 1 białe. Zakupione miesiąc temu, noszone tylko raz. Rozmiar 38, pudełko oryginalne.",
    },
    {
        "name": "Kozaki skórzane brązowe", "brand": "Ecco", "price": 285, "size": "37",
        "cond": "Dobry stan", "emoji": "👢", "seller": "joanna_styl",
        "img": IMG["boots"],
        "desc": "Kozaki ze skóry naturalnej, kolor brązowy. Obcas 4 cm, zamek z boku. Rozmiar 37. Stan bardzo dobry — noszone sezon.",
    },
    {
        "name": "Sneakersy Stan Smith", "brand": "Adidas", "price": 165, "size": "39",
        "cond": "Nowe bez metki", "emoji": "👟", "seller": "ania_secondhand",
        "img": IMG["sneakers"],
        "desc": "Adidas Stan Smith białe z zielonymi detalami. Rozmiar 39. Noszone dwa razy, stan idealny. Brak pudełka.",
    },
    {
        "name": "Szpilki czarne klasyczne", "brand": "Steve Madden", "price": 95, "size": "37",
        "cond": "Dobry stan", "emoji": "👠", "seller": "ela_glam",
        "img": IMG["boots"],
        "desc": "Szpilki czarne lakierowane, obcas 9 cm. Rozmiar 37. Skóra ekologiczna. Użyte kilka razy na imprezy.",
    },

    # ── Torebki ─────────────────────────────────────────────────
    {
        "name": "Torebka crossbody beżowa", "brand": "H&M", "price": 55, "size": "—",
        "cond": "Dobry stan", "emoji": "👜", "seller": "joanna_styl",
        "img": IMG["bag"],
        "desc": "Torebka crossbody beż. 22x16x6 cm. Pasek regulowany, zamek. Bez śladów użytkowania.",
    },
    {
        "name": "Torebka skórzana czarna", "brand": "Coach", "price": 350, "size": "—",
        "cond": "Dobry stan", "emoji": "👜", "seller": "paulina_looks",
        "img": IMG["bag"],
        "desc": "Torebka ze skóry naturalnej Coach, kolor czarny. Złote okucia, podwójny uchwyt. Wymiary 28x20x10 cm. Kupiona za 1200 zł.",
    },
    {
        "name": "Plecak mini różowy", "brand": "Fjällräven", "price": 140, "size": "—",
        "cond": "Dobry stan", "emoji": "🎒", "seller": "basia_trendy",
        "img": IMG["bag"],
        "desc": "Mini plecak Fjällräven Kanken w kolorze różowym. Pojemność 16L. Używany przez sezon, bez uszkodzeń.",
    },

    # ── Bluzki ──────────────────────────────────────────────────
    {
        "name": "Bluzka jedwabna pudrowa", "brand": "Mango", "price": 75, "size": "M",
        "cond": "Nowe bez metki", "emoji": "👔", "seller": "natka_chic",
        "img": IMG["blouse"],
        "desc": "Bluzka pudrowy róż, 100% wiskoza z połyskiem. Rozmiar M, obwód biustu 88 cm. Luźny krój, krótki rękaw.",
    },
    {
        "name": "Koszula lniana biała", "brand": "Arket", "price": 98, "size": "S",
        "cond": "Nowe z metką", "emoji": "👔", "seller": "monika_style",
        "img": IMG["blouse"],
        "desc": "Koszula z 100% lnu w kolorze białym. Rozmiar S. Luźny oversizowy krój, guziki perłowe. Metka nieodcięta.",
    },
    {
        "name": "Top prążkowany zielony", "brand": "COS", "price": 59, "size": "XS",
        "cond": "Dobry stan", "emoji": "👕", "seller": "ola_vintage",
        "img": IMG["blouse"],
        "desc": "Top prążkowany w kolorze butelkowej zieleni. Bawełna 95%, elastan 5%. Rozmiar XS. Noszony kilka razy.",
    },

    # ── Spódnice ────────────────────────────────────────────────
    {
        "name": "Spódnica midi plisowana", "brand": "Zara", "price": 85, "size": "S",
        "cond": "Nowe z metką", "emoji": "👗", "seller": "asia_modowa",
        "img": IMG["skirt"],
        "desc": "Spódnica midi plisowana w kolorze beżu. Poliester satynowy. Rozmiar S, długość 80 cm. Gumka w talii.",
    },
    {
        "name": "Spódnica mini jeansowa", "brand": "Weekday", "price": 72, "size": "36",
        "cond": "Dobry stan", "emoji": "👗", "seller": "ania_secondhand",
        "img": IMG["skirt"],
        "desc": "Spódnica mini z dżinsu, kolor jasnoniebeski. Rozmiar 36. Zapinana na guziki z przodu. Stan bardzo dobry.",
    },

    # ── Swetry ──────────────────────────────────────────────────
    {
        "name": "Sweter merino ecru", "brand": "Massimo Dutti", "price": 130, "size": "L",
        "cond": "Nowe z metką", "emoji": "🧶", "seller": "paulina_looks",
        "img": IMG["sweater"],
        "desc": "Sweter merino ecru. Miękki, nieswędzący. Idealny do biura. Skład: 100% wełna merino.",
    },
    {
        "name": "Sweter warkocz kremowy", "brand": "Reserved", "price": 89, "size": "M",
        "cond": "Dobry stan", "emoji": "🧶", "seller": "karolinka_sz",
        "img": IMG["sweater"],
        "desc": "Sweter z warkoczowym splotem w kolorze kremowym. Akryl 60%, wełna 40%. Rozmiar M. Prany ręcznie, bez mechacenia.",
    },
    {
        "name": "Kardigan oversize zielony", "brand": "Zara", "price": 105, "size": "L",
        "cond": "Nowe bez metki", "emoji": "🧶", "seller": "natka_chic",
        "img": IMG["sweater"],
        "desc": "Kardigan oversize w kolorze butelkowej zieleni. Długi, z kieszeniami. Rozmiar L. Zakupiony 2 miesiące temu.",
    },

    # ── Kurtki ──────────────────────────────────────────────────
    {
        "name": "Kurtka skórzana czarna", "brand": "Zara", "price": 195, "size": "S",
        "cond": "Dobry stan", "emoji": "🧥", "seller": "marta_fashion",
        "img": IMG["jacket"],
        "desc": "Kurtka ze skóry ekologicznej, czarna, moto style. Klamry z boku, zamek metalowy. Rozmiar S. Stan bardzo dobry.",
    },
    {
        "name": "Puchówka krótka różowa", "brand": "Sinsay", "price": 79, "size": "M",
        "cond": "Używane", "emoji": "🧥", "seller": "basia_trendy",
        "img": IMG["jacket"],
        "desc": "Krótka puchówka w kolorze pudrowego różu. Wypełnienie: 80% puch, 20% pierze. Rozmiar M. Sezon użytkowania.",
    },

    # ── Biżuteria i akcesoria ────────────────────────────────────
    {
        "name": "Kolczyki złote koła", "brand": "Bijou Brigitte", "price": 25, "size": "—",
        "cond": "Dobry stan", "emoji": "💍", "seller": "ela_glam",
        "img": IMG["acc"],
        "desc": "Kolczyki złote koła, średnica 5 cm. Lekkie i wygodne, zapięcie angielskie. Używane kilka razy.",
    },
    {
        "name": "Naszyjnik perłowy vintage", "brand": "Vintage", "price": 45, "size": "—",
        "cond": "Dobry stan", "emoji": "📿", "seller": "ola_vintage",
        "img": IMG["acc"],
        "desc": "Naszyjnik perłowy z lat 80. Sztuczne perły, kolor kremowy. Długość 48 cm, zapięcie złote. Stan bardzo dobry.",
    },
    {
        "name": "Zegarek damski srebrny", "brand": "Daniel Wellington", "price": 175, "size": "—",
        "cond": "Dobry stan", "emoji": "⌚", "seller": "monika_style",
        "img": IMG["acc"],
        "desc": "Zegarek Daniel Wellington Petite, koperta 28 mm, tarcza biała, bransoleta srebrna. Z pudełkiem. Stan bardzo dobry.",
    },

    # ── Garnitury / Kombinezony ──────────────────────────────────
    {
        "name": "Garnitur damski granatowy", "brand": "Reserved", "price": 245, "size": "38",
        "cond": "Nowe z metką", "emoji": "👔", "seller": "joanna_styl",
        "img": IMG["suit"],
        "desc": "Komplet: marynarka + spodnie, kolor granat. Wełna 55%, poliester 45%. Rozmiar 38. Perfekcyjny do biura.",
    },
    {
        "name": "Kombinezon sztruksowy brązowy", "brand": "Mango", "price": 135, "size": "S",
        "cond": "Dobry stan", "emoji": "👗", "seller": "ania_secondhand",
        "img": IMG["suit"],
        "desc": "Kombinezon sztruksowy w kolorze czekoladowego brązu. Bawełna 98%, elastan 2%. Rozmiar S, długie nogawki.",
    },
]

DEFAULT_PASSWORD = "haslo123"


def seed():
    init_db()
    conn = get_db()
    cur = conn.cursor()

    count = cur.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count > 0:
        print("[seed] Baza już zawiera dane — pomijam.")
        conn.close()
        return

    print("[seed] Tworzę użytkowników testowych...")
    sellers = {}
    for u in USERS:
        uname = u["username"]
        email = u["email"]
        pw_hash = generate_password_hash(DEFAULT_PASSWORD, method='pbkdf2:sha256')
        avatar = uname[0].upper()
        cur.execute(
            """INSERT OR IGNORE INTO users
               (username, email, password_hash, avatar, is_active, email_verified, phone_verified)
               VALUES (?,?,?,?,1,1,1)""",
            (uname, email, pw_hash, avatar)
        )
    conn.commit()
    for u in USERS:
        uname = u["username"]
        user = cur.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
        if user:
            sellers[uname] = user["id"]

    print("[seed] Dodaję produkty testowe...")
    for prod in PRODS:
        seller_id = sellers.get(prod["seller"])
        if not seller_id:
            continue
        # Store image URL directly as the images JSON array
        images_json = json.dumps([prod["img"]])
        cur.execute(
            """INSERT INTO products (name, brand, price, size, condition, emoji, description, images, seller_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (prod["name"], prod["brand"], prod["price"], prod["size"],
             prod["cond"], prod["emoji"], prod["desc"], images_json, seller_id)
        )

    conn.commit()
    conn.close()
    print(f"[seed] Gotowe! {len(PRODS)} produktów, {len(USERS)} sprzedawców.")
    print(f"[seed] Hasło testowe dla każdego: {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    seed()
