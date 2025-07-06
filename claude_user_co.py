import requests
from bs4 import BeautifulSoup
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

# Lista URL-i sklepów/stron użytkowników do testów
test_urls = [
    "https://audiblask.olx.pl/home/",
    "https://media-max.olx.pl/home/",
    "https://sprzedazalufelg.olx.pl/home/",
    "https://www.olx.pl/oferty/uzytkownik/2mw85l/",
    "https://brickmarket.olx.pl/home/",
    "https://autoczesci.olx.pl/home/",
    "https://skotniki.olx.pl/home/",
    "https://www.olx.pl/oferty/uzytkownik/2UafH/",
    "https://motozbyt.olx.pl/home/",
    "https://www.olx.pl/oferty/uzytkownik/Yxbr/",
    "https://www.olx.pl/oferty/uzytkownik/1DsEB/",
    "https://www.olx.pl/oferty/uzytkownik/1qlFD/"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9"
}


def get_olx_ads_count_selenium(shop_url):
    """
    Używa Selenium do pobrania liczby ogłoszeń
    """
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')

    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get(shop_url)
        time.sleep(3)

        # Pobierz tekst strony
        page_text = driver.find_element(By.TAG_NAME, "body").text

        # Dla użytkowników - szukaj "Znaleźliśmy X ogłoszeń"
        if "/oferty/uzytkownik/" in shop_url:
            # Najpierw szukaj dokładnego wzorca "Znaleźliśmy X ogłoszeń"
            match = re.search(r'Znaleźliśmy (\d+) ogłoszeń', page_text)
            if match:
                count = int(match.group(1))
                print(f"Znaleziono w tekście: 'Znaleźliśmy {count} ogłoszeń'")
                return count

            # Alternatywny wzorzec
            match = re.search(r'Wszystkie ogłoszenia\s*(\d+)', page_text)
            if match:
                count = int(match.group(1))
                print(f"Znaleziono w tekście: 'Wszystkie ogłoszenia {count}'")
                return count

            # Sprawdź czy jest informacja o braku ogłoszeń
            if any(text in page_text for text in ["Brak ogłoszeń", "Nie ma ogłoszeń", "0 ogłoszeń"]):
                print("Znaleziono informację o braku ogłoszeń")
                return 0

            # Jeśli nic nie znaleziono, policz elementy na stronie
            ad_elements = driver.find_elements(By.CSS_SELECTOR,
                                               '[data-testid="l-card"], .offer-wrapper, [id^="offer-"]')
            actual_count = len(ad_elements)
            print(f"Policzone ogłoszenia na stronie: {actual_count} (może być niepełne z powodu paginacji)")

            # Jeśli jest mało ogłoszeń i nie ma paginacji, zwróć policzoną liczbę
            pagination = driver.find_elements(By.CSS_SELECTOR, '[data-testid="pagination"], .pagination')
            if actual_count > 0 and actual_count < 48 and not pagination:
                return actual_count

        driver.quit()
        return None

    except Exception as e:
        print(f"Błąd Selenium: {e}")
        driver.quit()
        return None


def get_olx_ads_count(shop_url):
    """
    Pobiera liczbę ogłoszeń - wersja hybrydowa
    """
    # Najpierw spróbuj z requests (szybsze)
    resp = requests.get(shop_url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"Błąd pobierania {shop_url}: {resp.status_code}")
        return None

    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # Określ typ strony
    is_user_page = "/oferty/uzytkownik/" in shop_url
    is_shop_page = ".olx.pl/home/" in shop_url

    if is_shop_page:
        # Dla sklepów firmowych
        # Szukaj w różnych elementach
        patterns = [
            (r'(\d+[\s\d]*)\s*ogłoszeń', 'ogłoszeń'),
            (r'(\d+[\s\d]*)\s*ofert', 'ofert'),
            (r'Zobacz wszystkie \((\d+)\)', 'zobacz'),
        ]

        # Sprawdź wszystkie elementy
        for element in soup.find_all(['button', 'a', 'span', 'div', 'h1', 'h2', 'h3']):
            text = element.get_text().strip()

            for pattern, keyword in patterns:
                if keyword in text.lower():
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        count = int(match.group(1).replace(' ', '').replace('\xa0', ''))
                        if 0 < count <= 10000:
                            print(f"Znaleziono w elemencie {element.name}: '{text}' -> {count}")
                            return count

        # Dla media-max i podobnych - szukaj też w atrybutach
        for element in soup.find_all(attrs={'data-count': True}):
            try:
                count = int(element['data-count'])
                if 0 < count <= 10000:
                    print(f"Znaleziono w atrybucie data-count: {count}")
                    return count
            except:
                pass

        # Szukaj w skryptach JavaScript
        for script in soup.find_all('script'):
            if script.string:
                # Szukaj JSON z liczbą ogłoszeń
                matches = re.findall(r'"(?:count|total|adsCount)":\s*(\d+)', script.string)
                for match in matches:
                    count = int(match)
                    if 0 < count <= 10000:
                        print(f"Znaleziono w JavaScript: {count}")
                        return count

    elif is_user_page:
        # Dla użytkowników - użyj Selenium
        print("Strona użytkownika - używam Selenium...")
        return get_olx_ads_count_selenium(shop_url)

    # Jeśli nic nie znaleziono dla sklepu, spróbuj też Selenium
    if is_shop_page:
        print("Nie znaleziono w HTML, próbuję z Selenium...")
        return get_olx_ads_count_selenium(shop_url)

    return None


if __name__ == '__main__':
    for url in test_urls:
        print(f"\n{'=' * 60}")
        print(f"Sprawdzanie URL: {url}")
        count = get_olx_ads_count(url)
        if count is not None:
            print(f"✅ Liczba ogłoszeń: {count}")
        else:
            print(f"❌ Brak danych o liczbie ogłoszeń.")