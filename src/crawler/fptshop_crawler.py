import logging
import time
import re
import asyncio
from datetime import datetime
import requests
from bs4 import BeautifulSoup, NavigableString
from playwright.async_api import async_playwright
from concurrent.futures import ThreadPoolExecutor
from src.redis.client import redis_client
from src.storage.minio_client import minio_client
from src.utils.brand_utils import normalize_brand
from src.utils.url_utils import normalize_url
from src.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class FptshopCrawler:
    BASE_URL = "https://fptshop.com.vn"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    CATEGORY_MAP = {
        "mobile": "https://fptshop.com.vn/dien-thoai",
        "laptop": "https://fptshop.com.vn/may-tinh-xach-tay",
        "tablet": "https://fptshop.com.vn/may-tinh-bang",
        "smartwatch": "https://fptshop.com.vn/smartwatch",
        "headphone": "https://fptshop.com.vn/tai-nghe",
        "speaker": "https://fptshop.com.vn/loa",
        "monitor": "https://fptshop.com.vn/man-hinh",
        "keyboard": "https://fptshop.com.vn/phu-kien/ban-phim",
        "mouse": "https://fptshop.com.vn/phu-kien/chuot",
        "powerbank": "https://fptshop.com.vn/phu-kien/sac-du-phong"
    }

    def __init__(self, category: str = "mobile"):
        if category not in self.CATEGORY_MAP:
            raise ValueError(f"Category {category} is not supported by FptshopCrawler")
        self.category = category
        self.catalog_url = self.CATEGORY_MAP[category]

    def fetch_with_retry(self, url: str, retries: int = 3) -> str:
        delay = 1.0
        for attempt in range(retries):
            try:
                response = requests.get(url, headers={"User-Agent": self.USER_AGENT}, timeout=15)
                response.raise_for_status()
                return response.text
            except Exception as e:
                logging.warning(f"[RETRY] Fetch attempt {attempt+1} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    logging.error(f"[ERROR] Failed to fetch {url} after max attempts.")
        return ""

    def get_availability(self, name: str) -> str:
        name_lower = name.lower()
        if "sắp về hàng" in name_lower or "sắp về" in name_lower:
            return "Coming Soon"
        elif "tạm hết hàng" in name_lower or "hết hàng" in name_lower:
            return "Out of Stock"
        return "In Stock"

    async def load_catalog(self) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=self.USER_AGENT)
            
            for attempt in range(3):
                try:
                    await page.goto(self.catalog_url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(2000)
                    break
                except Exception as e:
                    logging.warning(f"[RETRY] Catalog load attempt {attempt+1} failed: {e}")
                    if attempt == 2:
                        await browser.close()
                        return ""
                    await asyncio.sleep(2)

            for click_idx in range(settings.CRAWLER_MAX_LOAD_MORE):
                unique_count = await page.evaluate("""() => {
                    const cards = document.querySelectorAll('div.cardInfo');
                    const urls = new Set();
                    cards.forEach(card => {
                        const a = card.querySelector('a[href]') || card.parentElement.querySelector('a[href]');
                        if (a && a.getAttribute('href')) {
                            urls.add(a.getAttribute('href'));
                        }
                    });
                    return urls.size;
                }""")
                if unique_count >= settings.CRAWLER_MAX_PRODUCTS:
                    break

                clicked = await page.evaluate("""
                    () => {
                        const btns = Array.from(document.querySelectorAll('button'));
                        const btn = btns.find(b => b.textContent.trim().includes('Xem th\u00eam'));
                        if (btn) { btn.click(); return true; }
                        return false;
                    }
                """)
                if not clicked:
                    break
                await page.wait_for_timeout(2000)

            html = await page.content()
            await browser.close()
            return html

    def parse_catalog(self, html: str) -> list:
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        products = []
        seen_ids = set()

        for ci in soup.find_all("div", class_="cardInfo"):
            parent = ci.parent
            h3_elem = ci.find("h3")
            if not h3_elem:
                continue

            product_name = h3_elem.get_text(strip=True)
            a_link = ci.find("a", href=True) or parent.find("a", href=True)
            url = a_link["href"] if a_link else ""
            product_url = url if url.startswith("http") else f"{self.BASE_URL}{url}"

            if not product_name or len(product_name) <= 3:
                continue

            product_id = "fptshop_" + product_url.split("/")[-1]
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            current_price_elem = ci.select_one("p.text-textOnWhitePrimary")
            current_price = current_price_elem.get_text(strip=True) if current_price_elem else "N/A"

            original_price_elem = ci.select_one("span.line-through")
            original_price = original_price_elem.get_text(strip=True) if original_price_elem else current_price

            discount_elem = ci.select_one("span.ml-1, span.text-textOnWhiteBrand")
            discount_percent = discount_elem.get_text(strip=True) if discount_elem else "0%"

            img_elem = parent.select_one("a img")
            image_url = "N/A"
            if img_elem:
                image_url = img_elem.get("src") or img_elem.get("data-src") or "N/A"

            products.append({
                "product_id": product_id,
                "product_name": product_name,
                "brand": normalize_brand(product_name),
                "category": self.category,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "availability": self.get_availability(product_name),
                "store_name": "FPTShop",
                "product_url": product_url,
                "image_url": image_url,
                "crawl_time": datetime.now().isoformat()
            })

        return products[:100]

    def fetch_detail_with_retry(self, product_url: str, retries: int = 3, need_discount: bool = True) -> dict:
        html = self.fetch_with_retry(product_url, retries=retries)
        if not html:
            return {"rating": 0.0, "review_count": 0}

        soup = BeautifulSoup(html, "html.parser")
        rating = 0.0
        review_count = 0

        count_elem = soup.find(string=lambda s: s and "lượt đánh giá" in s)
        if count_elem:
            raw_text = count_elem.parent.get_text(strip=True)
            k_match = re.search(r'([\d]+[,.]?[\d]*)k', raw_text, re.IGNORECASE)
            if k_match:
                review_count = int(float(k_match.group(1).replace(",", ".")) * 1000)
            else:
                nums = re.findall(r'\d+', raw_text)
                if nums:
                    review_count = int(nums[0])

            rating_div = count_elem.parent.find_previous_sibling("div")
            if rating_div:
                for child in rating_div.children:
                    if isinstance(child, NavigableString):
                        text = child.strip()
                        try:
                            val = float(text.replace(",", "."))
                            if 0 < val <= 5:
                                rating = val
                                break
                        except ValueError:
                            continue

        discount_percent = None
        if need_discount:
            line_through = soup.select_one("span.line-through, [class*='line-through']")
            if line_through:
                sibling = line_through.find_next_sibling("span")
                if sibling and "%" in sibling.get_text():
                    discount_percent = sibling.get_text(strip=True)
            if not discount_percent:
                for sp in soup.find_all("span"):
                    text = sp.get_text(strip=True)
                    if text.endswith("%") and len(text) <= 5 and re.match(r'^\d+%$', text):
                        discount_percent = text
                        break
            if discount_percent:
                cleaned_pct = discount_percent.replace("-", "").strip()
                discount_percent = f"-{cleaned_pct}"

        return {"rating": rating, "review_count": review_count, "discount_percent": discount_percent}

    def process_product(self, product, i, total):
        url = normalize_url(product["product_url"])
        cached = redis_client.get_cached_detail(url)
        need_discount = product.get("discount_percent") in ("0%", "0", "", None)

        if cached:
            product["rating"] = cached["rating"]
            product["review_count"] = cached["review_count"]
            if need_discount and cached.get("discount_percent"):
                product["discount_percent"] = cached["discount_percent"]
            logging.info(f"[DETAIL-CACHE] ({i}/{total}) {product['product_name']} → rating={cached['rating']}, reviews={cached['review_count']}")
        else:
            detail = self.fetch_detail_with_retry(url, need_discount=need_discount)
            product["rating"] = detail["rating"]
            product["review_count"] = detail["review_count"]
            if need_discount and detail.get("discount_percent"):
                product["discount_percent"] = detail["discount_percent"]
            redis_client.set_cached_detail(url, detail, expire_seconds=72000)
            logging.info(f"[DETAIL-FETCH] ({i}/{total}) {product['product_name']} → rating={detail['rating']}, reviews={detail['review_count']}")
            time.sleep(0.1)

    def run(self):
        html = asyncio.run(self.load_catalog())
        if not html:
            logging.error("[ALERT] 0 products catalog loaded for FPTShop.")
            return None

        products = self.parse_catalog(html)
        if not products:
            logging.error("[ALERT] 0 products parsed for FPTShop.")
            return None

        products = products[:settings.CRAWLER_MAX_PRODUCTS]
        logging.info(f"[PARSED] Found {len(products)} products in {self.category}. Fetching detail pages concurrently...")

        futures = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            for i, product in enumerate(products, 1):
                futures.append(executor.submit(self.process_product, product, i, len(products)))
            for f in futures:
                f.result()

        raw_payload = {
            "source": "fptshop",
            "category": self.category,
            "total_items": len(products),
            "items": products,
            "crawled_at": datetime.now().isoformat()
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        object_name = f"fptshop/{self.category}/data_{timestamp}.json"
        saved_location = minio_client.upload_json(raw_payload, object_name)
        logging.info(f"[MINIO] Uploaded to: {saved_location}")
        return saved_location


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="mobile", help="Category to crawl")
    args = parser.parse_args()

    crawler = FptshopCrawler(category=args.category)
    crawler.run()
