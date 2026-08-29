import logging
import re
import time
import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from configs.settings import settings
from src.crawler.base_crawler import BaseCrawler
from src.redis.client import redis_client
from src.utils.brand_utils import normalize_brand

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class CellphonesCrawler(BaseCrawler):
    BASE_URL = "https://cellphones.com.vn"
    GRAPHQL_URL = "https://api.cellphones.com.vn/v2/graphql/query"

    CATEGORY_CONFIG = {
        "mobile": {"url": "https://cellphones.com.vn/mobile.html"},
        "laptop": {"url": "https://cellphones.com.vn/laptop.html"},
        "tablet": {"url": "https://cellphones.com.vn/tablet.html"},
        "smartwatch": {"url": "https://cellphones.com.vn/do-choi-cong-nghe.html"},
        "headphone": {"url": "https://cellphones.com.vn/thiet-bi-am-thanh/tai-nghe.html"},
        "speaker": {"url": "https://cellphones.com.vn/thiet-bi-am-thanh/loa.html"},
        "monitor": {"url": "https://cellphones.com.vn/man-hinh.html"},
        "keyboard": {"url": "https://cellphones.com.vn/phu-kien/chuot-ban-phim-may-tinh/ban-phim.html"},
        "mouse": {"url": "https://cellphones.com.vn/phu-kien/chuot-ban-phim-may-tinh/chuot.html"},
        "powerbank": {"url": "https://cellphones.com.vn/phu-kien/pin-du-phong.html"},
        "tivi": {"url": "https://cellphones.com.vn/tivi.html"},
        "air-purifier": {"url": "https://cellphones.com.vn/nha-thong-minh/may-loc-khong-khi.html"},
        "vacuum": {"url": "https://cellphones.com.vn/nha-thong-minh/may-hut-bui.html"},
        "camera": {"url": "https://cellphones.com.vn/phu-kien/camera.html"}
    }

    def __init__(self, category: str = "mobile", province: str = "Hà Nội"):
        super().__init__(store_name="CellphoneS", category=category, province=province)
        if category not in self.CATEGORY_CONFIG:
            raise ValueError(f"Category '{category}' is not supported by CellphonesCrawler")
        self.config = self.CATEGORY_CONFIG[category]
        
        cps_ids = self.location_info.get("cps_ids", [])
        self.cps_province_id = int(cps_ids[0]) if cps_ids else 30

    FALLBACK_IDS = {
        "mobile": "3",
        "laptop": "380",
        "tablet": "4",
        "smartwatch": "610",
        "headphone": "265",
        "speaker": "73",
        "monitor": "784",
        "keyboard": "739",
        "mouse": "664",
        "powerbank": "122",
        "tivi": "1124",
        "air-purifier": "727",
        "vacuum": "748",
        "camera": "667"
    }

    def _resolve_cate_id(self) -> Optional[str]:
        return self.FALLBACK_IDS.get(self.category)

    def _parse_graphql_items(self, items: list, seen_ids: set) -> List[Dict[str, Any]]:
        products = []
        for it in items:
            gen = it.get("general", {})
            filt = it.get("filterable", {})
            name = gen.get("name", "").strip()
            if not name:
                continue

            raw_special = filt.get("special_price") or filt.get("price") or 0
            raw_price = filt.get("price") or raw_special or 0

            current_price = f"{int(raw_special):,}₫".replace(",", ".") if raw_special > 0 else "N/A"
            original_price = f"{int(raw_price):,}₫".replace(",", ".") if raw_price > 0 else current_price

            discount = "0%"
            if raw_price > raw_special > 0:
                pct = round((1 - (raw_special / raw_price)) * 100)
                discount = f"-{pct}%"

            name_lower = name.lower()
            stock = filt.get("stock", 0)
            if "sắp về" in name_lower or "đặt trước" in name_lower or "nhận thông tin" in name_lower:
                avail = "Coming Soon"
            elif stock <= 0 or current_price == "N/A":
                avail = "Out of Stock"
            else:
                avail = "In Stock"

            url_path = gen.get("url_path", "")
            if url_path.startswith("http"):
                product_url = url_path
            else:
                clean_path = url_path.lstrip("/")
                product_url = f"{self.BASE_URL}/{clean_path}" if clean_path else self.config["url"]

            slug = product_url.split("/")[-1].replace(".html", "")
            product_id = f"cellphones_{gen.get('product_id') or slug}"
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            img = filt.get("thumbnail", "")
            if img and not img.startswith("http"):
                image_url = f"https://cdn2.cellphones.com.vn/insecure/rs:fill:358:358/q:90/plain/{img.lstrip('/')}"
            else:
                image_url = img or "N/A"

            raw_promo = filt.get("promotion_information", "")
            clean_promo = BeautifulSoup(raw_promo, "html.parser").get_text(separator=" ", strip=True) if raw_promo else ""

            review = gen.get("review") or {}
            rating = float(review.get("average_rating") or 0.0)
            review_count = int(review.get("total_count") or 0)

            products.append({
                "product_id": product_id,
                "product_name": name,
                "brand": normalize_brand(name, fallback_brand=gen.get("manufacturer", "")),
                "category": self.category,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount,
                "availability": avail,
                "store_name": "CellphoneS",
                "product_url": product_url,
                "image_url": image_url,
                "rating": rating,
                "review_count": review_count,
                "promotions": clean_promo,
                "crawl_time": datetime.now().isoformat()
            })
        return products

    async def _crawl_playwright(self) -> List[Dict[str, Any]]:
        catalog_url = self.config["url"]
        seen_ids: set = set()
        all_items: list = []

        for attempt in range(1, 4):
            logging.info(f"[{self.store_name} PLAYWRIGHT] Attempt {attempt}/3 for '{self.category}' in {self.province_name}...")
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    context = await browser.new_context(
                        user_agent=self.DEFAULT_USER_AGENT,
                        extra_http_headers={"Accept-Language": "vi-VN,vi;q=0.9"}
                    )
                    page = await context.new_page()

                    await page.route("**/*", lambda route: route.abort()
                        if route.request.resource_type in ["image", "media", "font"]
                        else route.continue_())

                    async def handle_response(response):
                        if "graphql" in response.url and response.status == 200:
                            try:
                                body = await response.json()
                                prods = body.get("data", {}).get("products", [])
                                if prods:
                                    all_items.extend(prods)
                                    logging.info(f"[{self.store_name} PLAYWRIGHT] Intercepted {len(prods)} items | total raw: {len(all_items)}")
                            except Exception:
                                pass

                    page.on("response", handle_response)

                    try:
                        await page.goto(catalog_url, wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(3500)
                    except Exception as e:
                        logging.warning(f"[{self.store_name} PLAYWRIGHT] Page load warning: {e}")

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    await page.wait_for_timeout(1000)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)

                    for click_idx in range(settings.CRAWLER_MAX_LOAD_MORE):
                        clicked = await page.evaluate("""
                            () => {
                                const btn = document.querySelector('a.btn-show-more, button.btn-show-more, .button__show-more-product, a[class*="show-more"]');
                                if (btn) { btn.click(); return true; }
                                return false;
                            }
                        """)
                        if not clicked:
                            break
                        await page.wait_for_timeout(1500)

                    await browser.close()

                products = self._parse_graphql_items(all_items, seen_ids)
                if products:
                    logging.info(f"[{self.store_name} PLAYWRIGHT] Done: {len(products)} unique products (from {len(all_items)} raw items).")
                    return products

            except Exception as e:
                logging.warning(f"[{self.store_name} PLAYWRIGHT] Attempt {attempt} error: {e}")
                all_items.clear()
                await asyncio.sleep(2)

        return []

    def crawl(self) -> List[Dict[str, Any]]:
        products = asyncio.run(self._crawl_playwright())
        logging.info(f"[{self.store_name}] Total {len(products)} products for '{self.category}' in {self.province_name}.")
        return products

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="mobile", help="Category to crawl")
    parser.add_argument("--province", default="Hà Nội", help="Province to crawl")
    args = parser.parse_args()

    crawler = CellphonesCrawler(category=args.category, province=args.province)
    crawler.run()
