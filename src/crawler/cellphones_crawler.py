import logging
import time
import re
import asyncio
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from concurrent.futures import ThreadPoolExecutor
from src.redis.client import redis_client
from src.storage.minio_client import minio_client
from src.utils.brand_utils import normalize_brand
from src.utils.url_utils import normalize_url
from src.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class CellphonesCrawler:
    BASE_URL = "https://cellphones.com.vn"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    CATEGORY_MAP = {
        "mobile": "https://cellphones.com.vn/mobile.html",
        "laptop": "https://cellphones.com.vn/laptop.html",
        "tablet": "https://cellphones.com.vn/tablet.html",
        "smartwatch": "https://cellphones.com.vn/do-choi-cong-nghe.html",
        "headphone": "https://cellphones.com.vn/thiet-bi-am-thanh/tai-nghe.html",
        "speaker": "https://cellphones.com.vn/thiet-bi-am-thanh/loa.html",
        "monitor": "https://cellphones.com.vn/man-hinh.html",
        "keyboard": "https://cellphones.com.vn/phu-kien/chuot-ban-phim-may-tinh/ban-phim.html",
        "mouse": "https://cellphones.com.vn/phu-kien/chuot-ban-phim-may-tinh/chuot.html",
        "powerbank": "https://cellphones.com.vn/phu-kien/pin-du-phong.html"
    }

    def __init__(self, category: str = "mobile"):
        if category not in self.CATEGORY_MAP:
            raise ValueError(f"Category {category} is not supported by CellphonesCrawler")
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
            context = await browser.new_context(
                user_agent=self.USER_AGENT,
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()
            for attempt in range(3):
                try:
                    await page.goto(self.catalog_url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(7000)
                    await page.evaluate("window.scrollTo(0, 1200);")
                    try:
                        await page.wait_for_selector("div.product-info-container, div.product-item", timeout=8000)
                    except Exception:
                        await page.wait_for_timeout(3000)
                    break
                except Exception as e:
                    logging.warning(f"[RETRY] Catalog load attempt {attempt+1} failed: {e}")
                    if attempt == 2:
                        await browser.close()
                        return ""
                    await asyncio.sleep(2)
            for click_idx in range(settings.CRAWLER_MAX_LOAD_MORE):
                try:
                    unique_count = await page.evaluate("""() => {
                        const v1 = document.querySelectorAll('div.product-info-container');
                        const v2 = document.querySelectorAll('div.product-item');
                        const dominant = v1.length >= v2.length ? v1 : v2;
                        const links = new Set();
                        dominant.forEach(el => {
                            const a = el.querySelector('a[href]');
                            if (a && a.getAttribute('href')) {
                                links.add(a.getAttribute('href'));
                            }
                        });
                        return links.size;
                    }""")
                    if unique_count >= settings.CRAWLER_MAX_PRODUCTS:
                        break
                    selector = "a.btn-show-more, .show-more-btn, [data-slot='button']:has-text('Xem thêm'), span:has-text('Xem thêm')"
                    see_more = await page.query_selector(selector)
                    if not see_more:
                        await page.wait_for_timeout(2000)
                        see_more = await page.query_selector(selector)
                        if not see_more:
                            break
                    try:
                        await see_more.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    if not await see_more.is_visible():
                        is_vis = False
                        for _ in range(4):
                            await page.wait_for_timeout(1000)
                            if await see_more.is_visible():
                                is_vis = True
                                break
                        if not is_vis:
                            break
                    try:
                        total_before = await page.evaluate("document.querySelectorAll('div.product-info-container, div.product-item').length")
                        await see_more.click(timeout=4000)
                        expanded = False
                        for _ in range(16):
                            await page.wait_for_timeout(500)
                            v1_check = await page.query_selector_all("div.product-info-container")
                            v2_check = await page.query_selector_all("div.product-item")
                            if len(v1_check) + len(v2_check) > total_before:
                                expanded = True
                                break
                        if not expanded:
                            break
                    except Exception:
                        try:
                            await page.evaluate("""() => {
                                const elements = document.querySelectorAll('[role="dialog"], [data-slot="dialog-overlay"], [id^="radix-"], .cpsui\\\\:fixed');
                                elements.forEach(el => el.remove());
                                document.body.style.pointerEvents = 'auto';
                                document.body.style.overflow = 'auto';
                            }""")
                        except Exception:
                            pass
                        await page.wait_for_timeout(3000)
                        continue
                except Exception:
                    await page.wait_for_timeout(3000)
                    continue
            html = ""
            for attempt in range(3):
                try:
                    html = await page.content()
                    break
                except Exception as e:
                    if "navigating" in str(e).lower() or "navigation" in str(e).lower():
                        await page.wait_for_timeout(2000)
                    else:
                        if attempt == 2:
                            raise e
            await browser.close()
            return html


    def parse_catalog(self, html: str) -> list:
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        products = []
        seen_ids = set()

        elements = soup.select("div.product-info-container, div.product-item")

        for elem in elements:
            if "product-item" in elem.get("class", []) and "product-info-container" not in elem.get("class", []):
                link_elem = elem.select_one("a[href]")
            else:
                link_elem = elem.select_one("a.product__link, a[href$='.html']")

            if not link_elem or not link_elem.get("href"):
                continue

            title_elem = elem.select_one("div.product__name, h3.product__name, p.product__name")
            price_elem = elem.select_one("p.product__price--show, span.product__price--show, p.text-primary-600, p[class*='text-primary-600'], p.sm\\:text-medium")
            through_elem = elem.select_one("p.product__price--through, span.product__price--through, p.text-gray-300, p.line-through, p[class*='line-through']")
            percent_elem = elem.select_one("p.product__price--percent-detail span, span.product__price--percent-detail span, div[style*='discount-badge'] span")
            img_elem = elem.select_one("img.product__img, img[src], img[data-src]")

            if not title_elem:
                if img_elem and img_elem.get("alt"):
                    product_name = img_elem["alt"].strip()
                else:
                    continue
            else:
                product_name = title_elem.get_text(strip=True)

            url = link_elem["href"]
            product_url = url if url.startswith("http") else f"{self.BASE_URL}{url}"

            if not product_name or len(product_name) <= 3:
                continue

            product_id = "cellphones_" + product_url.split("/")[-1].replace(".html", "")
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            current_price = price_elem.get_text(strip=True) if price_elem else "N/A"
            original_price = through_elem.get_text(strip=True) if through_elem else current_price
            
            discount_percent = "0%"
            if percent_elem:
                discount_percent = percent_elem.get_text(strip=True)
                if not discount_percent.endswith("%"):
                    discount_percent = f"{discount_percent}%"

            if img_elem:
                image_url = img_elem.get("src") or img_elem.get("data-src") or "N/A"
            else:
                image_url = "N/A"

            products.append({
                "product_id": product_id,
                "product_name": product_name,
                "brand": normalize_brand(product_name),
                "category": self.category,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "availability": self.get_availability(product_name),
                "store_name": "Cellphones",
                "product_url": product_url,
                "image_url": image_url,
                "crawl_time": datetime.now().isoformat()
            })

        return products[:100]

    def fetch_detail_with_retry(self, product_url: str, retries: int = 3) -> dict:
        html = self.fetch_with_retry(product_url, retries=retries)
        if not html:
            return {"rating": 0.0, "review_count": 0}

        soup = BeautifulSoup(html, "html.parser")
        rating = 0.0
        review_count = 0

        box = soup.select_one("div.box-rating")
        if box:
            spans = box.find_all("span")
            for s in spans:
                text = s.get_text(strip=True)
                if "đánh giá" in text or "review" in text.lower():
                    k_match = re.search(r'([\d]+[,.]?[\d]*)k', text, re.IGNORECASE)
                    if k_match:
                        review_count = int(float(k_match.group(1).replace(",", ".")) * 1000)
                    else:
                        nums = re.findall(r'\d+', text)
                        if nums:
                            review_count = int(nums[0])
                else:
                    try:
                        rating = float(text)
                    except ValueError:
                        pass

            if rating == 0.0:
                all_text = box.get_text(separator=" ", strip=True)
                nums = re.findall(r'[\d.]+', all_text)
                float_nums = [float(n) for n in nums if float(n) <= 5.0]
                if float_nums:
                    rating = float_nums[0]

        return {"rating": rating, "review_count": review_count}

    def process_product(self, product, i, total):
        url = normalize_url(product["product_url"])
        cached = redis_client.get_cached_detail(url)
        if cached:
            product["rating"] = cached["rating"]
            product["review_count"] = cached["review_count"]
            logging.info(f"[DETAIL-CACHE] ({i}/{total}) {product['product_name']} → rating={cached['rating']}, reviews={cached['review_count']}")
        else:
            detail = self.fetch_detail_with_retry(url)
            product["rating"] = detail["rating"]
            product["review_count"] = detail["review_count"]
            redis_client.set_cached_detail(url, detail, expire_seconds=72000)
            logging.info(f"[DETAIL-FETCH] ({i}/{total}) {product['product_name']} → rating={detail['rating']}, reviews={detail['review_count']}")
            time.sleep(0.1)

    def run(self):
        html = asyncio.run(self.load_catalog())
        if not html:
            logging.error("[ALERT] 0 products catalog loaded for Cellphones.")
            return None

        products = self.parse_catalog(html)
        if not products:
            logging.error("[ALERT] 0 products parsed for Cellphones.")
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
            "source": "cellphones",
            "category": self.category,
            "total_items": len(products),
            "items": products,
            "crawled_at": datetime.now().isoformat()
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        object_name = f"cellphones/{self.category}/data_{timestamp}.json"
        saved_location = minio_client.upload_json(raw_payload, object_name)
        logging.info(f"[MINIO] Uploaded to: {saved_location}")
        return saved_location


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="mobile", help="Category to crawl")
    args = parser.parse_args()

    crawler = CellphonesCrawler(category=args.category)
    crawler.run()
