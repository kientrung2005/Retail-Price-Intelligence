import logging
import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from src.redis.client import redis_client
from src.storage.minio_client import minio_client
from src.utils.brand_utils import normalize_brand
from src.utils.url_utils import normalize_url
from src.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class DienmayxanhCrawler:
    BASE_URL = "https://www.dienmayxanh.com"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    CATEGORY_MAP = {
        "mobile": "https://www.dienmayxanh.com/dien-thoai-smartphone",
        "laptop": "https://www.dienmayxanh.com/laptop",
        "tablet": "https://www.dienmayxanh.com/may-tinh-bang",
        "smartwatch": "https://www.dienmayxanh.com/dong-ho-thong-minh",
        "headphone": "https://www.dienmayxanh.com/tai-nghe",
        "speaker": "https://www.dienmayxanh.com/loa-laptop-pc",
        "monitor": "https://www.dienmayxanh.com/man-hinh-may-tinh",
        "keyboard": "https://www.dienmayxanh.com/ban-phim-chuot",
        "mouse": "https://www.dienmayxanh.com/chuot-may-tinh",
        "powerbank": "https://www.dienmayxanh.com/sac-du-phong"
    }

    def __init__(self, category: str = "mobile"):
        if category not in self.CATEGORY_MAP:
            raise ValueError(f"Category {category} is not supported by DienmayxanhCrawler")
        self.category = category
        self.catalog_url = self.CATEGORY_MAP[category]

    def get_availability(self, status_text: str) -> str:
        s = status_text.lower()
        if "sắp về" in s:
            return "Coming Soon"
        elif "hết hàng" in s or "tạm hết" in s:
            return "Out of Stock"
        return "In Stock"

    async def load_catalog(self, page) -> list:
        logging.info(f"[PLAYWRIGHT] Loading DMX {self.category} catalog: {self.catalog_url}")
        
        for attempt in range(3):
            try:
                await page.goto(self.catalog_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                break
            except Exception as e:
                logging.warning(f"[RETRY] Catalog load attempt {attempt+1} failed: {e}")
                if attempt == 2:
                    logging.error("[ERROR] Failed to load catalog after max attempts.")
                    return []
                await asyncio.sleep(2)

        for click_idx in range(settings.CRAWLER_MAX_LOAD_MORE):
            see_more = await page.query_selector("div.view-more a")
            if not see_more:
                await page.wait_for_timeout(2000)
                see_more = await page.query_selector("div.view-more a")
                if not see_more:
                    break

            if not await see_more.is_visible():
                is_vis = False
                for _ in range(4):
                    await page.wait_for_timeout(1000)
                    if await see_more.is_visible():
                        is_vis = True
                        break
                if not is_vis:
                    break

            unique_count = await page.evaluate("""() => {
                const cards = document.querySelectorAll('ul.listproduct li.item a.main-contain');
                const urls = new Set();
                cards.forEach(a => {
                    if (a.getAttribute('href')) {
                        urls.add(a.getAttribute('href'));
                    }
                });
                return urls.size;
            }""")
            if unique_count >= settings.CRAWLER_MAX_PRODUCTS:
                logging.info(f"[PLAYWRIGHT] Already loaded {unique_count} unique items. Stopping.")
                break
                
            await see_more.click()
            await page.wait_for_timeout(1500)
            remain_el = await page.query_selector("span.remain")
            remain_count = int(await remain_el.inner_text()) if remain_el else 0
            logging.info(f"[PLAYWRIGHT] Click {click_idx + 1}: loaded={unique_count}, remaining={remain_count}")
            if remain_count == 0:
                break

        items = await page.query_selector_all("ul.listproduct li.item")
        products = []
        seen_ids = set()

        for item in items:
            a = await item.query_selector("a.main-contain")
            if not a:
                continue

            product_name = (await a.get_attribute("data-name") or "").strip()
            if not product_name or len(product_name) <= 3:
                title_el = await item.query_selector("p.product-title")
                product_name = (await title_el.inner_text()).strip() if title_el else ""
                if not product_name:
                    continue

            href = await a.get_attribute("href") or ""
            product_id_raw = await item.get_attribute("data-id") or ""
            dedup_key = product_id_raw or href
            if dedup_key and dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)

            product_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

            data_price = await item.get_attribute("data-price") or ""
            price_el = await item.query_selector("strong.price")
            current_price = (await price_el.inner_text()).strip() if price_el else (f"{float(data_price):,.0f}₫" if data_price else "N/A")

            old_el = await item.query_selector("p.price-old")
            original_price = (await old_el.inner_text()).strip() if old_el else current_price

            pct_el = await item.query_selector("span.percent")
            discount_percent = (await pct_el.inner_text()).strip() if pct_el else "0%"

            status_el = await item.query_selector("p.item-txt-online")
            status_text = (await status_el.inner_text()).strip() if status_el else ""

            img_el = await item.query_selector("img")
            image_url = "N/A"
            if img_el:
                image_url = await img_el.get_attribute("data-src") or await img_el.get_attribute("src") or "N/A"

            data_brand = await a.get_attribute("data-brand") or ""
            brand = normalize_brand(product_name, fallback_brand=data_brand)

            products.append({
                "product_id": f"dmx_{product_id_raw}" if product_id_raw else f"dmx_{href.split('/')[-1]}",
                "product_name": product_name,
                "brand": brand,
                "category": self.category,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "availability": self.get_availability(status_text),
                "store_name": "DienmayXanh",
                "product_url": product_url,
                "image_url": image_url,
                "rating": 0.0,
                "review_count": 0,
                "crawl_time": datetime.now().isoformat()
            })

        return products

    async def fetch_detail_with_retry(self, page, product_url: str, retries: int = 3) -> dict:
        delay = 1.0
        for attempt in range(retries):
            try:
                await page.goto(product_url, wait_until="domcontentloaded", timeout=20000)
                await page.evaluate("window.scrollTo(0, 1800);")
                await page.wait_for_timeout(2500)

                rating = 0.0
                review_count = 0

                review_el = await page.query_selector(".point-alltimerate, .point-satisfied")
                if review_el:
                    review_text = (await review_el.inner_text()).strip().lower()
                    review_text = review_text.replace(",", ".")
                    match = re.search(r'([\d.]+)\s*k', review_text)
                    if match:
                        review_count = int(float(match.group(1)) * 1000)
                    else:
                        nums = re.findall(r'\d+', review_text)
                        if nums:
                            review_count = int(nums[0])

                if review_count > 0:
                    rating_el = await page.query_selector(".point-average-score")
                    if rating_el:
                        try:
                            rating = float((await rating_el.inner_text()).strip().replace(",", "."))
                        except ValueError:
                            pass
                else:
                    rating = 0.0

                return {"rating": rating, "review_count": review_count}
            except Exception as e:
                logging.warning(f"[RETRY] Attempt {attempt+1} failed for {product_url}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logging.error(f"[ERROR] Max retries reached for {product_url}")
        return {"rating": 0.0, "review_count": 0}

    async def process_product(self, context, sem, product, i, total):
        async with sem:
            page = await context.new_page()
            try:
                url = normalize_url(product["product_url"])
                cached = redis_client.get_cached_detail(url)
                if cached:
                    product["rating"] = cached["rating"]
                    product["review_count"] = cached["review_count"]
                    logging.info(f"[DETAIL-CACHE] ({i}/{total}) {product['product_name']} → rating={cached['rating']}, reviews={cached['review_count']}")
                else:
                    detail = await self.fetch_detail_with_retry(page, url)
                    product["rating"] = detail["rating"]
                    product["review_count"] = detail["review_count"]
                    redis_client.set_cached_detail(url, detail, expire_seconds=72000)
                    logging.info(f"[DETAIL-FETCH] ({i}/{total}) {product['product_name']} → rating={detail['rating']}, reviews={detail['review_count']}")
            finally:
                await page.close()

    async def crawl_all(self) -> list:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=self.USER_AGENT)
            
            page = await context.new_page()
            try:
                products = await self.load_catalog(page)
            finally:
                await page.close()

            if not products:
                logging.warning("[WARN] No products found in catalog parsing!")
                await browser.close()
                return []

            products = products[:settings.CRAWLER_MAX_PRODUCTS]
            logging.info(f"[PARSED] Found {len(products)} products in {self.category}. Fetching detail pages concurrently...")

            sem = asyncio.Semaphore(3)
            tasks = []
            for i, product in enumerate(products, 1):
                tasks.append(self.process_product(context, sem, product, i, len(products)))

            await asyncio.gather(*tasks)
            await browser.close()
            return products

    def run(self):
        products = asyncio.run(self.crawl_all())
        if not products:
            logging.error("[ALERT] 0 products parsed. Possible site change or blocker.")
            return None

        raw_payload = {
            "source": "dienmayxanh",
            "category": self.category,
            "total_items": len(products),
            "items": products,
            "crawled_at": datetime.now().isoformat()
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        object_name = f"dienmayxanh/{self.category}/data_{timestamp}.json"
        saved_location = minio_client.upload_json(raw_payload, object_name)
        logging.info(f"[MINIO] Uploaded to: {saved_location}")
        return saved_location


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="mobile", help="Category to crawl")
    args = parser.parse_args()

    crawler = DienmayxanhCrawler(category=args.category)
    crawler.run()
