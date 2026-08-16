#!/usr/bin/env python3
"""
Daily horoscope generator — calls Gemini for all 12 signs, saves to horoscopes.json,
and writes per-sign static HTML pages to napi-horoszkop/{sign}/index.html.
Cron: 0 5 * * * /home/domelaci/projects/automate/horoszkop/venv/bin/python /home/domelaci/projects/automate/horoszkop/generate.py
"""
import base64
import json
import logging
import os
import re
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR   = Path(__file__).parent
DATA_FILE  = BASE_DIR / "horoscopes.json"
KEEP_DAYS  = 30

load_dotenv(BASE_DIR / ".env")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = os.environ.get("GITHUB_REPO", "")
SITE_URL       = os.environ.get("SITE_URL", "https://maihori.hu")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SIGNS = [
    ("kos",      "Kos",      "♈", "márc. 21. – ápr. 19.",  "tűz"),
    ("bika",     "Bika",     "♉", "ápr. 20. – máj. 20.",   "föld"),
    ("ikrek",    "Ikrek",    "♊", "máj. 21. – jún. 20.",   "levegő"),
    ("rak",      "Rák",      "♋", "jún. 21. – júl. 22.",   "víz"),
    ("oroszlan", "Oroszlán", "♌", "júl. 23. – aug. 22.",   "tűz"),
    ("szuz",     "Szűz",     "♍", "aug. 23. – szept. 22.", "föld"),
    ("merleg",   "Mérleg",   "♎", "szept. 23. – okt. 22.", "levegő"),
    ("skorpio",  "Skorpió",  "♏", "okt. 23. – nov. 21.",   "víz"),
    ("nyilas",   "Nyilas",   "♐", "nov. 22. – dec. 21.",   "tűz"),
    ("bak",      "Bak",      "♑", "dec. 22. – jan. 19.",   "föld"),
    ("vizonto",  "Vízöntő",  "♒", "jan. 20. – febr. 18.",  "levegő"),
    ("halak",    "Halak",    "♓", "febr. 19. – márc. 20.", "víz"),
]

ELEMENT_COLORS = {"tűz": "#ef4444", "föld": "#22c55e", "levegő": "#eab308", "víz": "#3b82f6"}

SYSTEM_PROMPT = """Magyar napi horoszkóp-generátor vagy. Stílusjegyek:
- Meleg, bátorító, mégis kissé titokzatos hangvétel
- Minden jegyhez 150-200 szó, folyó szöveg (nem felsorolás)
- Érintsd meg: általános energia, kapcsolatok, munka, egészség — de NE jelöld külön feliratokkal
- Konkrét, mégis általánosan érvényes: „Ma érdemes visszalépni egy lépést" > „Sok minden fog történni veled"
- Kerüld: „A csillagok azt sugallják", „A bolygók állása szerint", „A Holygó"
- Helyes magyar helyesírás, köznyelvi stílus"""

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{sign_name} napi horoszkóp – {date_hu} | Maihori</title>
<meta name="description" content="{sign_name} horoszkóp {date_hu}: {snippet}">
<meta name="google-site-verification" content="PASTE_GSC_CODE_HERE">
<link rel="canonical" href="{site_url}/napi-horoszkop/{sign_id}/">
<meta property="og:title" content="{sign_name} napi horoszkóp – {date_hu}">
<meta property="og:description" content="{snippet}">
<meta property="og:url" content="{site_url}/napi-horoszkop/{sign_id}/">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{sign_name} napi horoszkóp – {date_hu}">
<meta name="twitter:description" content="{snippet}">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{sign_name} napi horoszkóp – {date_hu}",
  "description": "{snippet}",
  "url": "{site_url}/napi-horoszkop/{sign_id}/",
  "datePublished": "{date_iso}",
  "dateModified": "{date_iso}",
  "publisher": {{"@type": "Organization", "name": "Maihori"}}
}}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','G-XXXXXXXXXX');</script>
<style>
:root{{--bg:#09071a;--surface:#120f28;--accent:#8b5cf6;--text:#e2e0f0;--muted:#9490b5}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh;padding:0 1rem}}
a{{color:var(--accent);text-decoration:none}}
a:hover{{text-decoration:underline}}
header{{text-align:center;padding:2rem 0 1rem}}
header a{{color:var(--muted);font-size:.9rem}}
header a:hover{{color:var(--text)}}
.sign-hero{{text-align:center;padding:2rem 0}}
.sign-symbol{{font-size:4rem;display:block;margin-bottom:.5rem}}
h1{{font-family:'Playfair Display',serif;font-size:clamp(1.8rem,4vw,2.8rem);margin-bottom:.5rem}}
.date-label{{color:var(--muted);font-size:.95rem;margin-bottom:.5rem}}
.element-badge{{display:inline-block;padding:.25rem .75rem;border-radius:99px;font-size:.8rem;font-weight:500;margin-top:.5rem}}
.horoscope-text{{max-width:680px;margin:2rem auto;background:var(--surface);border-radius:1rem;padding:2rem;font-size:1.05rem;line-height:1.8;border:1px solid rgba(139,92,246,.15)}}
.signs-nav{{max-width:900px;margin:2rem auto;text-align:center}}
.signs-nav h2{{font-family:'Playfair Display',serif;font-size:1.1rem;color:var(--muted);margin-bottom:1rem}}
.signs-grid{{display:flex;flex-wrap:wrap;gap:.5rem;justify-content:center}}
.sign-chip{{background:var(--surface);border:1px solid rgba(139,92,246,.2);border-radius:99px;padding:.35rem .9rem;font-size:.85rem;transition:border-color .2s,color .2s}}
.sign-chip:hover{{border-color:var(--accent);color:var(--accent);text-decoration:none}}
.sign-chip.active{{border-color:var(--accent);color:var(--accent);background:rgba(139,92,246,.1)}}
footer{{text-align:center;color:var(--muted);font-size:.8rem;padding:3rem 0 2rem}}
</style>
</head>
<body>
<header>
  <a href="{site_url}/">← Vissza a főoldalra</a>
</header>
<main>
  <div class="sign-hero">
    <span class="sign-symbol">{symbol}</span>
    <h1>{sign_name} napi horoszkóp</h1>
    <div class="date-label">{date_hu}</div>
    <span class="element-badge" style="background:{el_color}22;color:{el_color}">{element} jegy</span>
    <div class="date-label" style="margin-top:.5rem">{date_range}</div>
  </div>
  <div class="horoscope-text">{text}</div>
  <nav class="signs-nav">
    <h2>Más jegyek horoszkópja</h2>
    <div class="signs-grid">
{sign_chips}
    </div>
  </nav>
</main>
<footer>© {year} Maihori · Napi horoszkóp magyarul</footer>
</body>
</html>"""


def hu_date(d: date) -> str:
    months = ["január","február","március","április","május","június",
               "július","augusztus","szeptember","október","november","december"]
    return f"{d.year}. {months[d.month - 1]} {d.day}."


def call_gemini(prompt: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta"
        f"/models/gemini-flash-lite-latest:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 4096},
    }
    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def generate_all_signs(today: str) -> dict:
    sign_list = "\n".join(f'  "{s[0]}": "<{s[1]} szöveg>"' for s in SIGNS)
    prompt = f"""Ma {today} van. Írj napi horoszkópot mind a 12 jegyre.

Válaszolj CSAK érvényes JSON-ban, más szöveg nélkül:
{{
{sign_list}
}}"""
    raw = call_gemini(prompt)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    return json.loads(raw)


def load_data() -> list:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def save_data(data: list) -> None:
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_sign_pages(today: str, signs_data: dict) -> list:
    today_date = date.fromisoformat(today)
    date_hu = hu_date(today_date)
    written = []

    for sid, sname, symbol, date_range, element in SIGNS:
        text = signs_data.get(sid, "")
        snippet = text[:200].rstrip() + ("…" if len(text) > 200 else "")
        snippet_esc = snippet.replace('"', '&quot;')
        text_esc = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        active_chips = "\n".join(
            f'      <a href="{SITE_URL}/napi-horoszkop/{s[0]}/" '
            f'class="sign-chip{" active" if s[0] == sid else ""}" '
            f'title="{s[1]} horoszkóp">{s[2]} {s[1]}</a>'
            for s in SIGNS
        )

        el_color = ELEMENT_COLORS.get(element, "#8b5cf6")
        html = HTML_TEMPLATE.format(
            sign_id=sid, sign_name=sname, symbol=symbol,
            date_range=date_range, element=element, el_color=el_color,
            date_hu=date_hu, date_iso=today,
            snippet=snippet_esc, text=text_esc,
            site_url=SITE_URL, year=today_date.year,
            sign_chips=active_chips,
        )
        out = BASE_DIR / "napi-horoszkop" / sid / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        written.append(out)
        log.info("Wrote %s", out)

    return written


def write_sitemap(today: str) -> None:
    entries = [
        f'  <url><loc>{SITE_URL}/</loc><lastmod>{today}</lastmod>'
        f'<changefreq>daily</changefreq><priority>1.0</priority></url>'
    ]
    for sid, *_ in SIGNS:
        entries.append(
            f'  <url><loc>{SITE_URL}/napi-horoszkop/{sid}/</loc>'
            f'<lastmod>{today}</lastmod>'
            f'<changefreq>daily</changefreq><priority>0.9</priority></url>'
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries) + "\n"
        '</urlset>\n'
    )
    (BASE_DIR / "sitemap.xml").write_text(xml, encoding="utf-8")


def push_to_github(files: dict) -> None:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    for path, content_bytes in files.items():
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        sha = None
        r = requests.get(api_url, headers=headers, timeout=15)
        if r.status_code == 200:
            sha = r.json()["sha"]
        payload = {
            "message": f"chore: napi horoszkóp {date.today().isoformat()}",
            "content": base64.b64encode(content_bytes).decode(),
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha
        r = requests.put(api_url, headers=headers, json=payload, timeout=15)
        if r.status_code in (200, 201):
            log.info("GitHub push OK: %s", path)
        else:
            log.error("GitHub push FAILED %s: %s %s", path, r.status_code, r.text[:200])


def main() -> None:
    if not GEMINI_API_KEY:
        raise SystemExit("Missing GEMINI_API_KEY in .env")

    today = date.today().isoformat()
    data  = load_data()

    if any(d["date"] == today for d in data):
        log.info("Már elkészült a mai horoszkóp — sign pages újraírása.")
        today_entry = next(d for d in data if d["date"] == today)
        sign_pages = write_sign_pages(today, today_entry)
        write_sitemap(today)
        push_to_github({
            "sitemap.xml": (BASE_DIR / "sitemap.xml").read_bytes(),
            **{str(p.relative_to(BASE_DIR)): p.read_bytes() for p in sign_pages},
        })
        return

    log.info("Horoszkóp generálása: %s", today)
    signs = generate_all_signs(today)

    data.insert(0, {"date": today, **signs})
    data = data[:KEEP_DAYS]
    save_data(data)

    sign_pages = write_sign_pages(today, signs)
    write_sitemap(today)

    push_to_github({
        "horoscopes.json": DATA_FILE.read_bytes(),
        "sitemap.xml": (BASE_DIR / "sitemap.xml").read_bytes(),
        **{str(p.relative_to(BASE_DIR)): p.read_bytes() for p in sign_pages},
    })

    log.info("Kész.")


if __name__ == "__main__":
    main()
