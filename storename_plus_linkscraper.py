from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import re
import requests
from bs4 import BeautifulSoup

from datetime import datetime
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

#MODUŁY
from claude_to_csv import process_urls_to_xlsx
from claude_to_csv import get_shop_name_from_url
from claude_to_csv import ctc_get_olx_ads_count
from claude_to_csv import ctc_get_olx_ads_count_selenium

# === KONFIGURACJA ===
#CATEGORY_URL = "https://www.olx.pl/elektronika/sprzet-audio/"
#CATEGORY_URL = "https://www.olx.pl/dom-ogrod/instalacje/"
CATEGORY_URL = "https://www.olx.pl/dla-firm/maszyny-i-urzadzenia/"
MAX_PAGES    = 1

# === INICJALIZACJA WEBDRIVERA ===
def get_webdriver():
    service = Service(ChromeDriverManager().install())
    opts = webdriver.ChromeOptions()
    # opts.add_argument("--headless")  # odkomentuj, by uruchomić w tle
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(service=service, options=opts)

def get_shop_info_improved(listing_url):
    """
    Ulepszona wersja - rozróżnia sklepy premium od zwykłych użytkowników
    """
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')

    driver = webdriver.Chrome(options=chrome_options)

    try:
        print(f"\nŁadowanie strony: {listing_url}")
        driver.get(listing_url)
        time.sleep(5)

        shop_info = {}

        # Najpierw sprawdź czy to sklep premium (ma parametr w URL)
        is_premium_shop = 'olx_shop_premium' in listing_url

        # Metoda 1: Szukaj linku "Więcej od tego ogłoszeniodawcy"
        try:
            # Ten link prowadzi do profilu sprzedawcy
            more_link = driver.find_element(By.PARTIAL_LINK_TEXT, "Więcej od tego ogłoszeniodawcy")
            profile_url = more_link.get_attribute('href')

            if profile_url:
                shop_info['profile_url'] = profile_url
                print(f"  ✓ Link do profilu: {profile_url}")

                #Zmiana: podstawienie funkcji z claude_to_csv
                #get_olx_ads_count nieaktywne
                ads_count = ctc_get_olx_ads_count(profile_url)  # LICZBA OGLOSZEN
                if ads_count is not None:
                    print(f"Liczba ogłoszeń: {ads_count}")
                else:
                    print("Nie udało się pobrać liczby ogłoszeń.")

                # Teraz musimy pobrać nazwę sprzedawcy
                # Nazwa powinna być gdzieś obok tego linku
                parent = more_link.find_element(By.XPATH, "../..")

                # Szukaj nazwy w rodzicu
                name_elements = parent.find_elements(By.CSS_SELECTOR, "h2, h3, h4, strong")
                for elem in name_elements:
                    text = elem.text.strip()
                    if text and text != "Więcej od tego ogłoszeniodawcy" and len(text) < 100:
                        shop_info['name'] = text
                        print(f"  ✓ Nazwa: {text}")
                        break
        except:
            pass

        # Metoda 2: JavaScript - bardziej precyzyjne szukanie (POPRAWIONE)
        if 'profile_url' not in shop_info or 'name' not in shop_info:
            try:
                js_result = driver.execute_script("""
                    // Znajdź sekcję ze sprzedawcą
                    const sections = document.querySelectorAll('section, div[role="region"]');
                    let result = null;

                    for (let section of sections) {
                        // Sprawdź czy sekcja zawiera link do profilu
                        const profileLink = section.querySelector('a[href*="/oferty/uzytkownik/"], a[href*="/sklepy/"], a[href*=".olx.pl/home/"]');
                        if (!profileLink) continue;

                        // Znajdź nazwę - zwykle jest w h2, h3 lub strong w tej samej sekcji
                        const nameElements = section.querySelectorAll('h2, h3, h4, strong, [class*="title"]');

                        for (let elem of nameElements) {
                            const text = elem.textContent.trim();
                            // Pomijamy teksty które są linkami lub za długie
                            if (text && 
                                text !== "Więcej od tego ogłoszeniodawcy" && 
                                text.length > 2 && 
                                text.length < 100 &&
                                !text.includes('Zestaw') &&  // Pomijamy tytuły ogłoszeń
                                !text.includes('LEGO')) {     // Pomijamy tytuły ogłoszeń

                                result = {
                                    name: text,
                                    profileUrl: profileLink.href,
                                    isPremium: profileLink.href.includes('/sklepy/') || profileLink.href.includes('.olx.pl/home/')
                                };
                                break;
                            }
                        }

                        if (result) break;
                    }

                    // Jeśli nie znaleziono nazwy, zwróć przynajmniej link
                    if (!result) {
                        const anyProfileLink = document.querySelector('a[href*="/oferty/uzytkownik/"], a[href*="/sklepy/"], a[href*=".olx.pl/home/"]');
                        if (anyProfileLink) {
                            result = {
                                profileUrl: anyProfileLink.href,
                                isPremium: anyProfileLink.href.includes('/sklepy/') || anyProfileLink.href.includes('.olx.pl/home/')
                            };
                        }
                    }

                    return result;
                """)

                if js_result:
                    shop_info.update(js_result)
                    print(f"  ✓ Dane z JS: {js_result}")
            except Exception as e:
                print(f"  ! Błąd JS (kontynuuję): {str(e)[:100]}...")

        # Metoda 3: Jeśli mamy link do profilu ale nie mamy nazwy, możemy go odwiedzić
        if 'profile_url' in shop_info and 'name' not in shop_info:
            print("  → Odwiedzam profil aby pobrać nazwę...")
            driver.get(shop_info['profile_url'])
            time.sleep(3)

            # Na stronie profilu nazwa jest bardziej widoczna
            try:
                # Dla sklepów
                shop_name = driver.find_element(By.CSS_SELECTOR, "h1, [class*='shop-name'], [class*='seller-name']")
                if shop_name:
                    shop_info['name'] = shop_name.text.strip()
                    print(f"  ✓ Nazwa z profilu: {shop_info['name']}")
            except:
                # Dla zwykłych użytkowników - nazwa może być w tytule strony
                title = driver.title
                if " - " in title:
                    potential_name = title.split(" - ")[0].strip()
                    if len(potential_name) > 2 and len(potential_name) < 50:
                        shop_info['name'] = potential_name
                        print(f"  ✓ Nazwa z tytułu: {shop_info['name']}")

        # Określ typ konta
        if 'profile_url' in shop_info:
            if '/sklepy/' in shop_info['profile_url'] or '.olx.pl/home/' in shop_info['profile_url']:
                shop_info['type'] = 'sklep_premium'
            elif '/oferty/uzytkownik/' in shop_info['profile_url']:
                shop_info['type'] = 'uzytkownik'

        return shop_info

    except Exception as e:
        print(f"Błąd główny: {e}")
        import traceback
        traceback.print_exc()
        return {}
    finally:
        driver.quit()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "pl-PL,pl;q=0.9"
}

#Nieaktywne na rzecz ctc_get_olx_ads_count
# def get_olx_ads_count(shop_url):
#     """
#     Pobiera liczbę ogłoszeń ze strony OLX - dla kont firmowych (*.olx.pl/home)
#     oraz profili użytkowników (/oferty/uzytkownik/...).
#     """
#     resp = requests.get(shop_url, headers=HEADERS)
#     if resp.status_code != 200:
#         print(f"Błąd pobierania {shop_url}: {resp.status_code}")
#         return None
#     html = resp.text
#     soup = BeautifulSoup(html, 'html.parser')
#
#     # 1) Spróbuj znaleźć element nagłówkowy z liczbą ogłoszeń
#     # dla firm: najczęściej pojawia się jako: "123 ogłoszeń" lub w przycisku
#     text_candidates = list(soup.stripped_strings)
#     for text in text_candidates:
#         # wzorzec: liczba + "ogłoszeń"
#         m = re.search(r"(\d+[\s\d]*)\s*ogłoszeń", text)
#         if m:
#             return int(m.group(1).replace(' ', ''))
#         # wzorzec: liczba + "ofert"
#         m2 = re.search(r"(\d+[\s\d]*)\s*ofert", text)
#         if m2:
#             return int(m2.group(1).replace(' ', ''))
#
#     # 2) Dla stron użytkowników: treść "Ogłoszenia użytkownika (123)"
#     m3 = re.search(r"Ogłoszenia użytkownika\s*\((\d+)\)", html)
#     if m3:
#         return int(m3.group(1))
#
#     # 3) Fallback: regex na całości HTML, łapiemy pierwsze wystąpienie
#     m4 = re.search(r"(\d+[\s\d]*)\s*(ogłoszeń|ofert)", html)
#     if m4:
#         return int(m4.group(1).replace(' ', ''))
#
#     print(f"Nie znaleziono liczby ogłoszeń dla: {shop_url}")
#     return None


# === ETAP 1: ZBIERANIE LINKÓW DO OGŁOSZEŃ ===
def extract_ad_links(driver, category_url, max_pages):
    ad_links = set()
    for page in range(1, max_pages + 1):
        page_url = f"{category_url}?page={page}"
        print(f"🔍 Scraping: {page_url}")
        driver.get(page_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//a[contains(@href, '/d/oferta/')]")
            )
        )
        elements = driver.find_elements(
            By.XPATH, "//a[contains(@href, '/d/oferta/')]")
        for el in elements:
            href = el.get_attribute('href')
            if href:
                ad_links.add(href.split('?')[0])
        time.sleep(1)
    print(f"⚡ Found {len(ad_links)} unique ads")
    return list(ad_links)


def extract_store_urls(driver, ad_links):
    store_urls = set()

    for ad in ad_links:
        print(f"🔗 Opening ad: {ad}")

        # get_shop_info_improved otworzy swoją własną przeglądarkę
        shop_info = get_shop_info_improved(ad)

        # Użyj danych które znalazła funkcja!
        if shop_info and 'profile_url' in shop_info:
            store_urls.add(shop_info['profile_url'])

        print(f"   Typ: {shop_info.get('type', 'nieznany')}")

        # Usuń stary kod który nic nie znajduje
        # elems = driver.find_elements...

        time.sleep(1)

    print(f"⚡ Found {len(store_urls)} unique stores")
    return list(store_urls)

# === GŁÓWNA FUNKCJA ===
def main():
    driver = get_webdriver()
    try:
        ad_links   = extract_ad_links(driver, CATEGORY_URL, MAX_PAGES)
        store_urls = extract_store_urls(driver, ad_links)
        print("\n📋 Store URLs:")
        for url in store_urls:
            print(url)
            #process_urls_to_xlsx(store_urls, output_filename="linkscraper1.xlsx")

    finally:
        driver.quit()

    # Upewnij się, że masz zainstalowane wymagane pakiety
    try:
        import pandas
        import openpyxl
    except ImportError:
        print("Instaluję wymagane pakiety...")
        import subprocess

        subprocess.check_call(["pip", "install", "pandas", "openpyxl"])

# Generuj nazwę pliku z datą i czasem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"olx_sellers_{timestamp}.xlsx"

    print(f"DEBUG: Przekazuję {len(store_urls)} URL-i do process_urls_to_xlsx")
    if store_urls:
        print(f"DEBUG: Przykładowy URL: {store_urls[0]}")
    else:
        print("DEBUG: Lista store_urls jest pusta!")
    # Przetwórz URL-e i zapisz do XLSX
    process_urls_to_xlsx(store_urls, output_file)

if __name__ == '__main__':
    main()
