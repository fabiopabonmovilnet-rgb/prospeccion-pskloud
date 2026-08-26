"""
Extract phone numbers from Instagram profiles for existing leads.
Strategy:
1. Check if lead already has IG URL in 'website' field
2. If not, search DDG for site:instagram.com "{nombre}" Merida Venezuela
3. Visit the IG profile with Playwright (headless, public page)
4. Extract phone from meta description + HTML body
5. Update leads.json in place
"""
import json, sys, os, re, time, random

sys.stdout.reconfigure(encoding='utf-8')

try:
    from playwright.sync_api import sync_playwright
except:
    import pip
    pip.main(["install", "playwright"])
    from playwright.sync_api import sync_playwright

try:
    from ddgs import DDGS
except:
    from duckduckgo_search import DDGS

BASE = r"C:\Users\fabio\prospeccion-pskloud\merida"
LEADS_FILE = os.path.join(BASE, "leads.json")

PHONE_VE = re.compile(
    r'(\+?58[\s.-]?\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|\(\d{4}\)\s?\d{3,4}[\s.-]?\d{4}|'
    r'0\d{3}[\s.-]?\d{3,4}[\s.-]?\d{4}|'
    r'\d{4}[\s.-]\d{3,4}[\s.-]\d{4})'
)

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

IG_URL_RE = re.compile(r'instagram\.com/([a-zA-Z0-9_.]+)')

BAD_DOMAINS = {"sentry.io","wixpress.com","google.com","example.com","localhost","schema.org","w3.org","wordpress.org","squarespace.com","wix.com","godaddy.com","facebook.com","instagram.com","twitter.com","linkedin.com","youtube.com","apple.com","microsoft.com","tiktok.com"}

def ok_email(e):
    e = e.lower().strip()
    if len(e) > 80 or len(e) < 6: return False
    p = e.split("@")
    if len(p) != 2: return False
    if p[1] in BAD_DOMAINS: return False
    return True

def es_tel_ve(t):
    d = re.sub(r'[^\d]', '', t)
    if not d: return False
    prefixes = ("0412","0414","0416","0424","0426","0413","0415","0417","0274","0271","0275","0276")
    if len(d) == 11 and d.startswith("0"): return d[:4] in prefixes
    if len(d) == 12 and d.startswith("58"): return d[2:6] in prefixes
    if len(d) == 10 and d.startswith("58"): return d[2:6] in prefixes
    return False

def normalizar_tel(t):
    d = re.sub(r'[^\d]', '', t)
    if d.startswith("0") and len(d) == 11:
        return "+58" + d[1:]
    if d.startswith("58"):
        return "+" + d
    return "+58" + d

def search_ig_profile(nombre, municipio="Merida"):
    """Search DDG for Instagram profile of a business."""
    queries = [
        f'site:instagram.com "{nombre}" {municipio} Venezuela',
        f'site:instagram.com "{nombre}" {municipio}',
        f'instagram "{nombre}" {municipio} email telefono',
    ]
    for q in queries:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(q, region="ve-ve", max_results=10))
            for r in results:
                href = r.get("href", "")
                if "/p/" in href or "/reel/" in href or "/stories/" in href:
                    continue
                m = IG_URL_RE.search(href)
                if m:
                    username = m.group(1)
                    if username not in ("p","reel","stories","explore","accounts","tv"):
                        return f"https://www.instagram.com/{username}/"
        except:
            pass
        time.sleep(random.uniform(2, 4))
    return None

def scrape_ig_profile(page, url):
    """Visit IG profile and extract phone + email from meta tags and HTML."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.uniform(2, 4))
        
        # Get meta description (contains bio text)
        meta_desc = ""
        try:
            el = page.query_selector('meta[name="description"]')
            if el:
                meta_desc = el.get_attribute("content") or ""
        except:
            pass
        
        # Get og:description
        og_desc = ""
        try:
            el = page.query_selector('meta[property="og:description"]')
            if el:
                og_desc = el.get_attribute("content") or ""
        except:
            pass
        
        # Get full HTML body
        html_body = ""
        try:
            html_body = page.content() or ""
        except:
            pass
        
        # Combine all text sources
        all_text = f"{meta_desc} {og_desc} {html_body}"
        
        # Extract phone
        phone = ""
        for t in PHONE_VE.findall(all_text):
            if es_tel_ve(t):
                phone = normalizar_tel(t)
                break
        
        # Extract email
        email = ""
        for e in EMAIL_RE.findall(all_text):
            if ok_email(e):
                email = e.lower().strip()
                break
        
        return phone, email, meta_desc[:200]
    except Exception as ex:
        print(f"    Error scraping {url}: {str(ex)[:80]}")
        return "", "", ""

def main():
    leads = json.load(open(LEADS_FILE, encoding="utf-8"))
    
    # Stats
    total = len(leads)
    sin_telefono = [l for l in leads if not l.get("telefono", "").strip()]
    con_ig = [l for l in leads if "instagram.com" in l.get("website", "")]
    
    print(f"Total leads: {total}")
    print(f"Sin telefono: {len(sin_telefono)}")
    print(f"Con Instagram en website: {len(con_ig)}")
    print()
    
    # Process leads without phone
    updated = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
        )
        page = ctx.new_page()
        
        for i, lead in enumerate(leads):
            if lead.get("telefono", "").strip():
                continue  # Already has phone
            
            nombre = lead.get("nombre", "")
            municipio = lead.get("municipio", "Merida")
            
            # Check if already has IG URL
            website = lead.get("website", "")
            ig_url = ""
            if "instagram.com" in website:
                m = IG_URL_RE.search(website)
                if m:
                    ig_url = f"https://www.instagram.com/{m.group(1)}/"
            
            # Search for IG profile if not found
            if not ig_url:
                print(f"[{i+1}/{total}] Buscando IG: {nombre[:40]}...", end=" ", flush=True)
                ig_url = search_ig_profile(nombre, municipio)
                if ig_url:
                    print(f"→ {ig_url}")
                else:
                    print("→ no encontrado")
                    continue
            else:
                print(f"[{i+1}/{total}] Scraping IG directo: {nombre[:40]}...", end=" ", flush=True)
            
            # Scrape the profile
            phone, email, bio = scrape_ig_profile(page, ig_url)
            
            if phone:
                lead["telefono"] = phone
                updated += 1
                print(f"  ✅ TEL: {phone}")
            elif email and not lead.get("email", "").strip():
                lead["email"] = email
                updated += 1
                print(f"  ✅ EMAIL: {email}")
            else:
                print(f"  ❌ sin datos (bio: {bio[:60]})")
            
            # Save every 10 leads
            if updated > 0 and updated % 10 == 0:
                with open(LEADS_FILE, "w", encoding="utf-8") as f:
                    json.dump(leads, f, ensure_ascii=False, indent=2)
            
            # Rate limit
            time.sleep(random.uniform(3, 6))
        
        browser.close()
    
    # Final save
    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)
    
    # Final stats
    con_tel = sum(1 for l in leads if l.get("telefono", "").strip())
    con_email = sum(1 for l in leads if l.get("email", "").strip())
    print(f"\n{'='*60}")
    print(f"RESULTADO:")
    print(f"  Leads totales: {len(leads)}")
    print(f"  Con telefono: {con_tel}")
    print(f"  Con email: {con_email}")
    print(f"  Actualizados esta sesion: {updated}")

if __name__ == "__main__":
    main()
