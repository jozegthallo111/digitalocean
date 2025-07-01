import os
import time
import csv
import random
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("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")
SERPAPI_API_KEY = os.getenv("0a7c2fc610f1e0b9fcf241cb43f4cb2b2984ac911f0af69775adade602223cc6")

START_URL = "https://www.pricecharting.com/category/yugioh-cards"
WAIT_TIMEOUT = 25
MAX_RETRIES = 3
REQUEST_DELAY = (2, 5)
SAVE_EVERY = 25
CSV_FILE_PATH = "yugioh_cards.csv"
PREVIOUS_CSV_PATH = "yugioh_cards_previous.csv"
BLOGS_OUTPUT_DIR = "blogs"
IMAGES_DIR = "blog_images"
MIN_OPENAI_CALLS = 15
MIN_SERPAPI_CALLS = 10

os.makedirs(BLOGS_OUTPUT_DIR, exist_ok=True)

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
    return webdriver.Chrome(service=service, options=options)

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
    urls = [link.get_attribute("href") for link in set_links if "yugioh" in link.get_attribute("href").lower()]
    return list(set(urls))

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
            return list({link.get_attribute("href") for link in card_links})
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {set_url}: {str(e)}")
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
            prices = [elem.text.strip() for elem in driver.find_elements(By.CSS_SELECTOR, "span.price.js-price")]
            volumes = [elem.text.replace("volume:", "").strip() for elem in driver.find_elements(By.CSS_SELECTOR, "td.js-show-tab")]

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
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {card_url}: {str(e)}")
            time.sleep(5)
    return None

def load_scraped_data(csv_path=CSV_FILE_PATH):
    if not os.path.exists(csv_path):
        return {}
    with open(csv_path, newline='', encoding='utf-8') as f:
        return {row["Card URL"]: row for row in csv.DictReader(f)}

def save_scraped_data(data, filename=CSV_FILE_PATH):
    if not data:
        return
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

def compare_price_changes(old_data, new_data):
    changes = []
    for card in new_data:
        url = card["Card URL"]
        old_card = old_data.get(url)
        if not old_card:
            changes.append({**card, "Price Change": "New Card"})
            continue
        diffs = []
        for field in ["Raw Price", "Grade 7", "Grade 8", "Grade 9", "Grade 9.5", "PSA 10"]:
            try:
                old_val = float(old_card[field].replace("$", "").replace(",", ""))
                new_val = float(card[field].replace("$", "").replace(",", ""))
                diffs.append(f"{field}: {new_val - old_val:+.2f}")
            except:
                diffs.append(f"{field}: N/A")
        changes.append({**card, "Price Change": "; ".join(diffs)})
    return changes

def generate_blog_content(cards, blog_num, timestamp):
    import openai
    openai.api_key = OPENAI_API_KEY
    prompt_cards = "\n".join(
        [f"{i+1}. {c['Name']} - Current Price: {c['Raw Price']} - Change: {c['Price Change']}" for i, c in enumerate(cards)]
    )
    prompt = (
        f"Write a Yu-Gi-Oh! card market update blog post #{blog_num} for {timestamp.strftime('%Y-%m-%d')}\n"
        f"Cards:\n{prompt_cards}\n"
        "Include rarity insights and collector tips."
    )
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=700,
        temperature=0.7,
    )
    return response['choices'][0]['message']['content'].strip()

def main():
    driver = create_driver()
    all_data = []
    try:
        old_data_dict = load_scraped_data(CSV_FILE_PATH)
        set_urls = get_all_set_urls(driver)

        for set_url in set_urls:
            card_urls = get_card_urls_from_set(driver, set_url)
            if not card_urls:
                continue
            for card_url in tqdm(card_urls, desc=f"Scraping {set_url.split('/')[-1]}", unit="card"):
                card_data = scrape_card_data(driver, card_url)
                if card_data:
                    all_data.append(card_data)
                time.sleep(random.uniform(*REQUEST_DELAY))

        save_scraped_data(all_data)
        changes = compare_price_changes(old_data_dict, all_data)

        cards_per_blog = max(1, len(changes) // 5)
        for i in range(5):
            start = i * cards_per_blog
            end = start + cards_per_blog if i < 4 else len(changes)
            blog_cards = changes[start:end]
            content = generate_blog_content(blog_cards, i+1, datetime.now())
            with open(f"{BLOGS_OUTPUT_DIR}/yugioh_blog_{i+1}.md", "w", encoding="utf-8") as f:
                f.write(content)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
