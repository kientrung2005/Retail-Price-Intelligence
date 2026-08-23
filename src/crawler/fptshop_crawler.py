import logging
import re
import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup, NavigableString
from playwright.async_api import async_playwright
from concurrent.futures import ThreadPoolExecutor

from configs.settings import settings
from src.crawler.base_crawler import BaseCrawler
from src.redis.client import redis_client
from src.utils.brand_utils import normalize_brand
from src.utils.url_utils import normalize_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class FptshopCrawler(BaseCrawler):
    BASE_URL = "https://fptshop.com.vn"

    CATEGORY_CONFIG = {
        "mobile": {"url": "https://fptshop.com.vn/dien-thoai"},
        "laptop": {"url": "https://fptshop.com.vn/may-tinh-xach-tay"},
        "tablet": {"url": "https://fptshop.com.vn/may-tinh-bang"},
        "smartwatch": {"url": "https://fptshop.com.vn/smartwatch"},
        "headphone": {"url": "https://fptshop.com.vn/tai-nghe"},
        "speaker": {"url": "https://fptshop.com.vn/loa"},
        "monitor": {"url": "https://fptshop.com.vn/man-hinh"},
        "keyboard": {"url": "https://fptshop.com.vn/phu-kien/ban-phim"},
        "mouse": {"url": "https://fptshop.com.vn/phu-kien/chuot"},
        "powerbank": {"url": "https://fptshop.com.vn/phu-kien/sac-du-phong"},
        "tivi": {"url": "https://fptshop.com.vn/tivi"},
        "air-purifier": {"url": "https://fptshop.com.vn/may-loc-khong-khi"},
        "vacuum": {"url": "https://fptshop.com.vn/robot-hut-bui"},
        "camera": {"url": "https://fptshop.com.vn/camera"},
        "water-purifier": {"url": "https://fptshop.com.vn/may-loc-nuoc"}
    }

    def __init__(self, category: str = "mobile", province: str = "Hà Nội"):
        super().__init__(store_name="FPTShop", category=category, province=province)
        if category not in self.CATEGORY_CONFIG:
            raise ValueError(f"Category '{category}' is not supported by FptshopCrawler")
        self.config = self.CATEGORY_CONFIG[category]

    def _parse_html_catalog(self, html_str: str) -> List[Dict[str, Any]]:
        if not html_str:
            return []

        soup = BeautifulSoup(html_str, "html.parser")
        products = []
        seen_ids = set()

        cards = soup.select("div.cardInfo")
        for ci in cards:
            parent = ci.parent
            h3_elem = ci.find("h3") or parent.find("h3")
            if not h3_elem:
                continue

            product_name = h3_elem.get_text(strip=True)
            if not product_name or len(product_name) <= 3:
                continue

            a_link = ci.find("a", href=True) or parent.find("a", href=True)
            url = a_link["href"] if a_link else ""
            product_url = url if url.startswith("http") else f"{self.BASE_URL}{url}"
            product_id = f"fptshop_{product_url.split('/')[-1]}"

            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            current_price_elem = ci.select_one("p.text-textOnWhitePrimary, .price")
            current_price = current_price_elem.get_text(strip=True) if current_price_elem else "N/A"

            original_price_elem = ci.select_one("span.line-through, .price-old")
            original_price = original_price_elem.get_text(strip=True) if original_price_elem else current_price

            discount_elem = ci.select_one("span.ml-1, span.text-textOnWhiteBrand, .percent")
            discount_percent = discount_elem.get_text(strip=True) if discount_elem else "0%"

            img_elem = parent.select_one("a img, img")
            image_url = "N/A"
            if img_elem:
                image_url = img_elem.get("src") or img_elem.get("data-src") or "N/A"

            card_text = (parent.get_text(separator=" ", strip=True) if parent else product_name).lower()
            if "sắp về" in card_text or "nhận thông tin" in card_text:
                avail = "Coming Soon"
            elif "tạm hết" in card_text or "hết hàng" in card_text or current_price == "N/A":
                avail = "Out of Stock"
            else:
                avail = "In Stock"

            rating = 0.0
            review_count = 0
            rating_el = ci.select_one(".rating, .score")
            if rating_el:
                nums = re.findall(r'[\d.]+', rating_el.get_text())
                if nums:
                    try:
                        val = float(nums[0])
                        if 0 < val <= 5:
                            rating = val
                    except ValueError:
                        pass

            promo_el = parent.select_one("div.mt-auto p, p.line-clamp-2")
            promotions = promo_el.get_text(strip=True) if promo_el else ""

            products.append({
                "product_id": product_id,
                "product_name": product_name,
                "brand": normalize_brand(product_name),
                "category": self.category,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "availability": avail,
                "store_name": "FPTShop",
                "product_url": product_url,
                "image_url": image_url,
                "rating": rating,
                "review_count": review_count,
                "promotions": promotions,
                "crawl_time": datetime.now().isoformat()
            })

        return products

    def _fetch_detail_ratings(self, product: Dict[str, Any]) -> None:
        url = normalize_url(product["product_url"])
        cached = redis_client.get_cached_detail(url)
        if cached:
            product["rating"] = cached.get("rating", 0.0)
            product["review_count"] = cached.get("review_count", 0)
            if cached.get("promotions"):
                product["promotions"] = cached.get("promotions")
            return

        try:
            resp = self.fetch_with_retry(url, retries=2, timeout=8)
            if not resp or resp.status_code != 200:
                return

            soup = BeautifulSoup(resp.text, "html.parser")
            rating = product.get("rating", 0.0)
            review_count = product.get("review_count", 0)
            promotions = product.get("promotions", "")

            promo_list = []
            for block in soup.select("div.bts, div.payment-promotion, div[class*='promotion']"):
                for item in block.select("button, div.flex, p, li"):
                    txt = item.get_text(separator=" ", strip=True)
                    txt = " ".join(txt.split())
                    if 15 < len(txt) < 150 and any(k in txt for k in ["Giảm", "Tặng", "Ưu đãi", "HSSV", "ZaloPay", "Trả góp", "Phiếu mua hàng"]):
                        if txt not in promo_list and not any(txt in p for p in promo_list):
                            promo_list.append(txt)
            if promo_list:
                promotions = " | ".join(promo_list[:3])
                product["promotions"] = promotions

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

            product["rating"] = rating
            product["review_count"] = review_count
            redis_client.set_cached_detail(
                url,
                {"rating": rating, "review_count": review_count, "promotions": promotions},
                expire_seconds=72000
            )
        except Exception:
            pass

    async def _crawl_playwright(self) -> List[Dict[str, Any]]:
        catalog_url = self.config["url"]

        for attempt in range(1, 4):
            logging.info(f"[{self.store_name} PLAYWRIGHT] Starting browser attempt {attempt}/3 for '{self.category}' in {self.province_name}...")
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page(user_agent=self.DEFAULT_USER_AGENT)
                    
                    # Block heavy resources to ensure super fast loading
                    await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())

                    try:
                        await page.goto(catalog_url, wait_until="domcontentloaded", timeout=45000)
                        await page.wait_for_timeout(1500)
                    except Exception as e:
                        logging.warning(f"[{self.store_name} PLAYWRIGHT] Load warning (attempt {attempt}): {e}")

                    for click_idx in range(settings.CRAWLER_MAX_LOAD_MORE):
                        clicked = await page.evaluate("""
                            () => {
                                const btns = Array.from(document.querySelectorAll('button'));
                                const btn = btns.find(b => b.textContent.trim().includes('Xem thêm') || b.textContent.trim().includes('Xem th'));
                                if (btn) { btn.click(); return true; }
                                return false;
                            }
                        """)
                        if not clicked:
                            break
                        await page.wait_for_timeout(1500)

                    html = await page.content()
                    await browser.close()

                products = self._parse_html_catalog(html)
                if products:
                    return products
            except Exception as e:
                logging.warning(f"[{self.store_name} PLAYWRIGHT] Attempt {attempt} error: {e}")
                await asyncio.sleep(2)

        return []

    def crawl(self) -> List[Dict[str, Any]]:
        try:
            resp = self.fetch_with_retry(self.config["url"], retries=3, timeout=12)
            if resp and resp.status_code == 200:
                products = self._parse_html_catalog(resp.text)
                if len(products) >= settings.CRAWLER_MAX_PRODUCTS:
                    logging.info(f"[{self.store_name}] SSR fetched {len(products)} products directly.")
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        list(executor.map(self._fetch_detail_ratings, products))
                    return products
        except Exception as e:
            logging.warning(f"[{self.store_name}] Direct SSR fetch error: {e}")

        products = asyncio.run(self._crawl_playwright())
        products = products[:settings.CRAWLER_MAX_PRODUCTS]
        logging.info(f"[{self.store_name}] Retrieved {len(products)} products. Enriching details concurrently...")

        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(self._fetch_detail_ratings, products))

        return products


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="mobile", help="Category to crawl")
    parser.add_argument("--province", default="Hà Nội", help="Province to crawl")
    args = parser.parse_args()

    crawler = FptshopCrawler(category=args.category, province=args.province)
    crawler.run()
