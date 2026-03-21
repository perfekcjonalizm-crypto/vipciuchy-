# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a single-file SPA prototype of a Polish second-hand fashion marketplace called **"Rzeczy z Drugiej Ręki"** (Things from Second Hand). Everything — HTML structure, CSS, and JavaScript — lives in `wymien-i-kup.html`.

There is no build system, package manager, or test framework. Open the file directly in a browser to run it.

## Architecture

### Routing
Client-side navigation is handled by `goTo(p)`, which shows/hides `<div id="page-*">` sections. Routes: `home`, `product`, `chat`, `logowanie`, `rejestracja`, `sprzedaj`, `faq`, `kontakt`, `cennik`, `regulamin`, `jak-sprzedawac`.

### State
Global JS variables hold runtime state:
- `_currentProduct` — index of the selected product from `PRODS[]`
- `_blikTimer` / `_blikSeconds` — BLIK payment countdown (120s)
- `ri` — auto-reply index for the mock chat
- `_tt` — toast notification timer

### Data
Mock product data is hardcoded in the `PRODS` array (8 items). Each product has: `name`, `brand`, `price`, `size`, `condition`, `emoji`, `seller`, `avatar`, `desc`.

### Payment Flow
Modal-based multi-step wizard (`openPayM()` → `goPayStep(step)`). Supports BLIK (6-digit code with 2-min timer), card, Google Pay, Apple Pay — all simulated. Platform fee constant: `PLATFORM_FEE_PCT = 0.05` (5%).

### Key Utilities
- `goTo(p)` — page router
- `openProd(i)` — product detail page
- `openPayM(i)` — open payment modal
- `sendMsg()` — chat with simulated auto-replies
- `showToast(m)` — non-blocking toast notification
- `esc(s)` — HTML-escapes chat input (XSS prevention)
- `togFav(e, b)` — toggle favourite state

### Design System (CSS Variables)
Defined at `:root` — teal primary, coral accent, 6-level gray scale, 4-level shadow/radius scale. Fonts: **Syne** (headings) + **Plus Jakarta Sans** (body), loaded from Google Fonts.

### Animations
Product cards use staggered CSS animations (`animation-delay: calc(var(--i) * 0.03s)`). Scroll-triggered fade-ins use `IntersectionObserver`.

---

## Golden Rules — obowiązują bezwzględnie

### 1. Responsywność — absolutna podstawa
- Mobile-first: najpierw mały ekran (320px), potem skaluj w górę
- Żadnych stałych szerokości w px dla layoutów — tylko `%`, `vw`, `rem`, breakpointy
- Elementy dotykowe: minimum **44×44px** obszaru klikalności
- Weryfikacja przed oddaniem: iPhone SE (375px), tablet poziomo, ultrawide (2560px)
- `overflow-x: hidden` na `html, body` — nigdy nie pozwalamy na poziomy scroll

### 2. SEO — fundament architektury
- Unikalny `<title>` (50–60 znaków) i `<meta description>` (150–160 znaków) na każdej stronie
- Dokładnie jeden `<h1>` na stronę, logiczna hierarchia nagłówków
- Obrazy zawsze z opisowym `alt` (nie "zdjęcie", "img")
- Dane strukturalne JSON-LD dla strony głównej i kontaktu
- Core Web Vitals: LCP < 2.5s, CLS < 0.1, FID < 100ms

### 3. Bezpieczeństwo — zero kompromisów
- Sekrety wyłącznie w `.env` — nigdy w kodzie źródłowym
- Każdy endpoint autoryzowany przed jakąkolwiek operacją
- Hasła: bcrypt min. 12 rund, nigdy logowane, nigdy zwracane w response
- Walidacja każdego wejścia serwerowego — klient zawsze może kłamać
- Rate limiting na formularzach i logowaniu
- Security headers: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, CSP

### 4. Jakość kodu — poziom senior engineer
- Każda linijka kodu pisana tak, jakby czytał ją senior engineer z 15-letnim doświadczeniem
- Zero skrótów "na szybko" — brzydkie rozwiązanie = brak rozwiązania
- Komentarze tam gdzie logika jest nieoczywista, nie wszędzie
- Żadnych hacków na teraz — jeśli brzydkie, robimy porządnie lub zgłaszamy dług techniczny
- Każda decyzja: "Czy pokazałbym to w rozmowie technicznej?" Jeśli "nie" lub "może" — wróć i zrób lepiej

### 5. Proaktywność i dociekliwość
- Do niejednoznacznych wymagań — pytanie PRZED napisaniem kodu
- Propozycje w formacie: **co to jest → dlaczego warto → co to oznacza w praktyce**
- Lepsze rozwiązanie niż proszone? Mówić wprost z uzasadnieniem
- Ryzyka i pułapki wskazywać zanim w nie wpadniemy

### 6. Kontekst projektu
Ten projekt jest elementem CV wysyłanego do dużej firmy technologicznej. Rekruterzy i senior engineerzy będą go oglądać z lupą. Perfekcja nie jest przesadą — jest wymogiem.
