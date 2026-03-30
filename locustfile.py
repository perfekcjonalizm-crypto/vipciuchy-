"""
Locust load test — VipCiuchy
Realistyczna symulacja 200 użytkowników:
  - Przeglądanie katalogu
  - Rejestracja / logowanie
  - Dodawanie do ulubionych
  - Wystawianie ogłoszenia
  - Wysyłanie wiadomości
  - Przeglądanie zamówień
  - Wyszukiwanie paczkomatów
"""
import random
import string
import json
from locust import HttpUser, task, between, events


# ── Dane testowe ──────────────────────────────────────────────────
PRODUCT_IDS   = [33, 35, 36, 37, 38]
CATEGORIES    = ["tops", "bottoms", "dresses", "shoes", "accessories", ""]
CONDITIONS    = ["Nowe", "Bardzo dobry", "Dobry", "Widoczne ślady użytkowania"]
SIZES         = ["XS", "S", "M", "L", "XL"]
BRANDS        = ["Zara", "H&M", "Reserved", "Mango", "Nike", "Adidas", "Levi's"]
CITIES        = ["Warszawa", "Kraków", "Gdańsk", "Wrocław", "Poznań"]
POST_CODES    = ["00-001", "30-001", "50-001", "60-001", "80-001"]


def _rand_str(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# ── Użytkownik niezalogowany — tylko przegląda ─────────────────
class GuestUser(HttpUser):
    """
    60% ruchu — niezalogowani goście przeglądający oferty.
    """
    weight    = 60
    wait_time = between(2, 5)

    def on_start(self):
        r = self.client.get("/api/csrf", name="/api/csrf")
        try:
            self.csrf = r.json().get("csrf", "")
        except Exception:
            self.csrf = ""

    @task(8)
    def browse_catalog(self):
        params = {"limit": 20, "offset": random.randint(0, 3) * 20}
        if random.random() < 0.4:
            params["category"] = random.choice(CATEGORIES)
        self.client.get("/api/products", params=params, name="/api/products")

    @task(4)
    def view_product_detail(self):
        pid = random.choice(PRODUCT_IDS)
        self.client.get(f"/api/products/{pid}", name="/api/products/:id")

    @task(2)
    def search_paczkomat(self):
        pc = random.choice(POST_CODES)
        self.client.get(
            "/api/shipping/points",
            params={"carrier": "inpost_paczkomat", "post_code": pc},
            name="/api/shipping/points",
        )

    @task(2)
    def load_homepage(self):
        self.client.get("/", name="/ (frontend)")

    @task(1)
    def view_shipping_options(self):
        self.client.get("/api/shipping/options", name="/api/shipping/options")


# ── Użytkownik zalogowany — kupuje i sprzedaje ─────────────────
class LoggedInUser(HttpUser):
    """
    40% ruchu — zarejestrowani użytkownicy wykonujący akcje.
    """
    weight    = 40
    wait_time = between(1, 4)

    def on_start(self):
        """Rejestracja → logowanie przy starcie każdego użytkownika."""
        self.token   = ""
        self.user_id = None
        self.username = f"test_{_rand_str(6)}"
        self.email    = f"{self.username}@loadtest.vipciuchy.pl"
        self.password = "TestPass123!"

        # CSRF
        r = self.client.get("/api/csrf", name="/api/csrf [init]")
        try:
            self.csrf = r.json().get("csrf", "")
        except Exception:
            self.csrf = ""

        # Rejestracja
        self.client.post(
            "/api/auth/register",
            json={
                "username": self.username,
                "email":    self.email,
                "password": self.password,
                "phone":    f"5{random.randint(10000000,99999999)}",
            },
            headers={"X-CSRF-Token": self.csrf},
            name="/api/auth/register [init]",
        )

        # Logowanie
        r = self.client.post(
            "/api/auth/login",
            json={"login": self.email, "password": self.password},
            headers={"X-CSRF-Token": self.csrf},
            name="/api/auth/login [init]",
        )
        try:
            d = r.json()
            self.user_id = d.get("user", {}).get("id")
        except Exception:
            pass

    # ── Przeglądanie ──────────────────────────────────────────
    @task(6)
    def browse_catalog(self):
        params = {"limit": 20}
        if random.random() < 0.5:
            params["category"] = random.choice(CATEGORIES)
        self.client.get("/api/products", params=params, name="/api/products")

    @task(3)
    def view_product(self):
        pid = random.choice(PRODUCT_IDS)
        self.client.get(f"/api/products/{pid}", name="/api/products/:id")

    # ── Ulubione ──────────────────────────────────────────────
    @task(3)
    def toggle_favorite(self):
        pid = random.choice(PRODUCT_IDS)
        self.client.post(
            f"/api/favorites/{pid}",
            headers={"X-CSRF-Token": self.csrf},
            name="/api/favorites/:id (toggle)",
        )

    @task(1)
    def view_favorites(self):
        self.client.get("/api/favorites", name="/api/favorites")

    # ── Sprzedaż — wystawianie ogłoszenia ─────────────────────
    @task(2)
    def post_listing(self):
        payload = {
            "name":        f"Testowe ogłoszenie {_rand_str(4)}",
            "brand":       random.choice(BRANDS),
            "price":       round(random.uniform(15, 350), 2),
            "size":        random.choice(SIZES),
            "condition":   random.choice(CONDITIONS),
            "description": f"Opis produktu loadtest. {_rand_str(20)}",
            "category":    random.choice(CATEGORIES),
            "emoji":       "👗",
            "shipping_methods": json.dumps(["inpost_paczkomat", "dpd"]),
        }
        r = self.client.post(
            "/api/products",
            json=payload,
            headers={"X-CSRF-Token": self.csrf},
            name="/api/products (POST — nowe ogłoszenie)",
        )
        # Usuń wystawione ogłoszenie żeby nie zaśmiecać bazy
        try:
            pid = r.json().get("product", {}).get("id")
            if pid:
                self.client.delete(
                    f"/api/products/{pid}",
                    headers={"X-CSRF-Token": self.csrf},
                    name="/api/products/:id (DELETE)",
                )
        except Exception:
            pass

    # ── Wiadomości ────────────────────────────────────────────
    @task(2)
    def send_message(self):
        pid = random.choice(PRODUCT_IDS)
        self.client.post(
            "/api/messages",
            json={
                "to_user_id": 1,
                "product_id": pid,
                "content":    f"Czy produkt jest dostępny? {_rand_str(5)}",
            },
            headers={"X-CSRF-Token": self.csrf},
            name="/api/messages (POST)",
        )

    @task(1)
    def inbox(self):
        self.client.get("/api/messages", name="/api/messages (inbox)")

    # ── Profil i zamówienia ───────────────────────────────────
    @task(1)
    def view_profile(self):
        self.client.get("/api/auth/me", name="/api/auth/me")

    @task(1)
    def view_orders(self):
        self.client.get("/api/orders", name="/api/orders")

    # ── Wysyłka ───────────────────────────────────────────────
    @task(1)
    def search_paczkomat(self):
        pc = random.choice(POST_CODES)
        self.client.get(
            "/api/shipping/points",
            params={"carrier": "inpost_paczkomat", "post_code": pc},
            name="/api/shipping/points",
        )

    def on_stop(self):
        """Wylogowanie na końcu sesji."""
        self.client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": self.csrf},
            name="/api/auth/logout [cleanup]",
        )
