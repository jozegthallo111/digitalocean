import os
import time
import random
import csv
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, InvalidSessionIdException
from webdriver_manager.chrome import ChromeDriverManager

# Your API keys (embedded as per your request)
OPENAI_API_KEY = "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"
SERPAPI_API_KEY = "0a7c2fc610f1e0b9fcf241cb43f4cb2b2984ac911f0af69775adade602223cc6"

START_URL = "https://www.pricecharting.com/category/pokemon-cards"
WAIT_TIMEOUT = 25
MAX_RETRIES = 3
REQUEST_DELAY = (2, 5)
CSV_FILE_PATH = "pokemon_cards.csv"


def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def slow_scroll(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_attempts = 0
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2.5, 4.0))
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            scroll_attempts += 1
            if scroll_attempts > 2:
                break
        else:
            scroll_attempts = 0
            last_height = new_height


def get_all_set_urls(driver):
    driver.get(START_URL)
    time.sleep(random.uniform(*REQUEST_DELAY))
    WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/console/']"))
    )
    slow_scroll(driver)
    set_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/console/']")

    urls = []
    for link in set_links:
        url = link.get_attribute("href")
        name = link.text.strip().lower()
        if "pokemon" in url.lower() or "pokemon" in name:
            urls.append(url)
    urls = list(set(urls))
    print(f"Found {len(urls)} Pokémon sets")
    return urls


def get_card_urls_from_set(driver, set_url):
    for attempt in range(MAX_RETRIES):
        try:
            driver.get(set_url)
            time.sleep(random.uniform(*REQUEST_DELAY))
            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "td.title a"))
            )
            slow_scroll(driver)
            card_links = driver.find_elements(By.CSS_SELECTOR, "td.title a")
            urls = list({link.get_attribute("href") for link in card_links if link.get_attribute("href")})
            print(f"Found {len(urls)} cards in set {set_url.split('/')[-1]}")
            return urls
        except InvalidSessionIdException:
            print("Invalid session detected during set URL fetch. Recreating driver...")
            driver.quit()
            driver = create_driver()
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {set_url}: {str(e)}")
            if attempt == MAX_RETRIES - 1:
                return []
            time.sleep(5)
    return []


def scrape_card_data(driver, card_url):
    for attempt in range(MAX_RETRIES):
        try:
            driver.get(card_url)
            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1#product_name"))
            )
            name = driver.find_element(By.CSS_SELECTOR, "h1#product_name").text.strip()

            prices = []
            volumes = []

            price_elements = driver.find_elements(By.CSS_SELECTOR, "span.price.js-price")
            for elem in price_elements:
                prices.append(elem.text.strip())

            volume_elements = driver.find_elements(By.CSS_SELECTOR, "td.js-show-tab")
            for elem in volume_elements:
                volumes.append(elem.text.replace("volume:", "").strip())

            rarity = "N/A"
            model_number = "N/A"
            img_url = "N/A"

            try:
                rarity = driver.find_element(By.CSS_SELECTOR, "td.details[itemprop='description']").text.strip()
            except NoSuchElementException:
                pass

            try:
                model_number = driver.find_element(By.CSS_SELECTOR, "td.details[itemprop='model-number']").text.strip()
            except NoSuchElementException:
                pass

            try:
                img = driver.find_element(By.CSS_SELECTOR, "img[src*='1600.jpg']")
                img_url = img.get_attribute("src")
            except NoSuchElementException:
                pass

            while len(prices) < 6:
                prices.append("N/A")
            while len(volumes) < 6:
                volumes.append("N/A")

            return {
                "Name": name,
                "Raw Price": prices[0],
                "Raw Volume": volumes[0],
                "Grade 7": prices[1],
                "Grade 7 Volume": volumes[1],
                "Grade 8": prices[2],
                "Grade 8 Volume": volumes[2],
                "Grade 9": prices[3],
                "Grade 9 Volume": volumes[3],
                "Grade 9.5": prices[4],
                "Grade 9.5 Volume": volumes[4],
                "PSA 10": prices[5],
                "PSA 10 Volume": volumes[5],
                "Rarity": rarity,
                "Model Number": model_number,
                "Image URL": img_url,
                "Card URL": card_url,
            }

        except InvalidSessionIdException:
            print("Invalid session detected during card scrape. Recreating driver...")
            driver.quit()
            driver = create_driver()
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {card_url}: {str(e)}")
            if attempt == MAX_RETRIES - 1:
                return None
            time.sleep(5)
    return None


def load_scraped_data(csv_path=CSV_FILE_PATH):
    scraped = {}
    if os.path.exists(csv_path):
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("Card URL", "").strip()
                if url:
                    scraped[url] = row
    return scraped


def save_scraped_data_batch(data_batch, filename=CSV_FILE_PATH, write_header=False):
    if not data_batch:
        return
    mode = 'a'
    with open(filename, mode, newline='', encoding='utf-8') as f:
        keys = data_batch[0].keys()
        writer = csv.DictWriter(f, fieldnames=keys)
        if write_header:
            writer.writeheader()
        writer.writerows(data_batch)
    print(f"Saved {len(data_batch)} cards to {filename}")


def compare_price_changes(old_data, new_data):
    changes = []
    for card in new_data:
        url = card["Card URL"]
        old_card = old_data.get(url)
        if not old_card:
            changes.append({**card, "Price Change": "New Card"})
            continue

        price_fields = ["Raw Price", "Grade 7", "Grade 8", "Grade 9", "Grade 9.5", "PSA 10"]
        diffs = []
        for field in price_fields:
            old_price_str = old_card.get(field, "N/A").replace("$", "").replace(",", "")
            new_price_str = card.get(field, "N/A").replace("$", "").replace(",", "")
            try:
                old_price = float(old_price_str)
            except:
                old_price = None
            try:
                new_price = float(new_price_str)
            except:
                new_price = None
            if old_price is not None and new_price is not None:
                diff = new_price - old_price
                diffs.append(f"{field}: {diff:+.2f}")
            else:
                diffs.append(f"{field}: N/A")

        changes.append({**card, "Price Change": "; ".join(diffs)})
    return changes


def main():
    driver = create_driver()
    scraped_data = load_scraped_data()
    all_sets = get_all_set_urls(driver)
    random.shuffle(all_sets)

    write_header = not os.path.exists(CSV_FILE_PATH)
    for set_url in all_sets:
        card_urls = get_card_urls_from_set(driver, set_url)
        batch = []
        for card_url in card_urls:
            if card_url in scraped_data:
                print(f"Already scraped {card_url}, skipping.")
                continue
            card_data = scrape_card_data(driver, card_url)
            if card_data:
                batch.append(card_data)
                scraped_data[card_url] = card_data
                time.sleep(random.uniform(*REQUEST_DELAY))
        if batch:
            save_scraped_data_batch(batch, write_header=write_header)
            write_header = False

    driver.quit()


if __name__ == "__main__":
    main()
