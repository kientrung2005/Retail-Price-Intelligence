import logging
import re
import math
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup

from configs.settings import settings
from src.crawler.base_crawler import BaseCrawler
from src.redis.client import redis_client
from src.utils.brand_utils import normalize_brand

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class DienmayxanhCrawler(BaseCrawler):
    BASE_URL = "https://www.dienmayxanh.com"

    CATEGORY_CONFIG = {
        "mobile": {"url": "https://www.dienmayxanh.com/dien-thoai", "cate_id": 42},
        "laptop": {"url": "https://www.dienmayxanh.com/laptop", "cate_id": 44},
        "tablet": {"url": "https://www.dienmayxanh.com/may-tinh-bang", "cate_id": 522},
        "smartwatch": {"url": "https://www.dienmayxanh.com/dong-ho-thong-minh", "cate_id": 7077},
        "headphone": {"url": "https://www.dienmayxanh.com/tai-nghe", "cate_id": 54},
        "speaker": {"url": "https://www.dienmayxanh.com/dan-loa-dvd", "cate_id": 2162},
        "monitor": {"url": "https://www.dienmayxanh.com/man-hinh-may-tinh", "cate_id": 5698},
        "keyboard": {"url": "https://www.dienmayxanh.com/ban-phim", "cate_id": 86},
        "mouse": {"url": "https://www.dienmayxanh.com/chuot-may-tinh", "cate_id": 86},
        "powerbank": {"url": "https://www.dienmayxanh.com/sac-dtdd?g=pin-sac-du-phong", "cate_id": 57},
        "tivi": {"url": "https://www.dienmayxanh.com/tivi", "cate_id": 1942},
        "air-purifier": {"url": "https://www.dienmayxanh.com/may-loc-khong-khi", "cate_id": 5005},
        "vacuum": {"url": "https://www.dienmayxanh.com/robot-hut-bui", "cate_id": 7714},
        "camera": {"url": "https://www.dienmayxanh.com/camera-giam-sat", "cate_id": 4728}
    }

    def __init__(self, category: str = "mobile", province: str = "Hà Nội"):
        super().__init__(store_name="DienmayXanh", category=category, province=province)
        if category not in self.CATEGORY_CONFIG:
            raise ValueError(f"Category '{category}' is not supported by DienmayxanhCrawler")
        self.config = self.CATEGORY_CONFIG[category]

        dmx_ids = self.location_info.get("dmx_ids", [])
        self.dmx_province_id = int(dmx_ids[0]) if dmx_ids else 3

    def _parse_html_cards(self, html_str: str, seen_ids: Optional[set] = None) -> List[Dict[str, Any]]:
        if not html_str:
            return []

        soup = BeautifulSoup(html_str, "html.parser")
        products = []
        if seen_ids is None:
            seen_ids = set()

        elements = soup.select("li.item.ajaxed, .listproduct > li.item, ul.listproduct > li, li.item")
        for elem in elements:
            link_elem = elem.select_one("a.main-contain, a[href]")
            if not link_elem:
                continue

            url = link_elem.get("href", "")
            if not url or "javascript:" in url or url == "//":
                continue

            product_url = url if url.startswith("http") else f"{self.BASE_URL}{url}"
            slug = product_url.split('/')[-1].replace('.html', '').split('?')[0]
            if not slug or len(slug) <= 2:
                continue
            product_id = f"dmx_{slug}"
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            title_elem = elem.select_one("p.product-title, h3, .item-title, strong.name")
            product_name = ""
            if title_elem:
                product_name = title_elem.get_text(strip=True)
            if not product_name:
                product_name = link_elem.get("data-name", "")

            if not product_name or len(product_name) <= 2:
                continue

            price_elem = elem.select_one("strong.price, .price, .item-price")
            current_price = "N/A"
            if price_elem:
                current_price = price_elem.get_text(strip=True)
            elif link_elem.get("data-price"):
                try:
                    p_val = float(link_elem.get("data-price"))
                    if p_val > 0:
                        current_price = f"{int(p_val):,}₫".replace(",", ".")
                except ValueError:
                    pass

            old_price_elem = elem.select_one("p.price-old, span.box-price-old, .price-old, .item-price-old")
            original_price = old_price_elem.get_text(strip=True) if old_price_elem else current_price

            percent_elem = elem.select_one("span.percent, .item-discount")
            discount_percent = percent_elem.get_text(strip=True) if percent_elem else "0%"

            img_elem = elem.select_one("img.thumb, img")
            image_url = "N/A"
            if img_elem:
                image_url = img_elem.get("data-src") or img_elem.get("src") or "N/A"

            card_text = (elem.get_text(separator=" ", strip=True) if elem else product_name).lower()
            if "sắp về" in card_text or "nhận thông tin" in card_text or "đặt trước" in card_text:
                avail = "Coming Soon"
            elif "ngừng kinh doanh" in card_text or "tạm hết" in card_text or "hết hàng" in card_text or current_price == "N/A":
                avail = "Out of Stock"
            else:
                avail = "In Stock"

            rating = 0.0
            review_count = 0
            rate_elem = elem.select_one("p.item-rating, .vote-txt, .rating")
            if rate_elem:
                rate_text = rate_elem.get_text(strip=True)
                m = re.search(r'([\d.]+)', rate_text)
                if m:
                    try:
                        val = float(m.group(1))
                        if 0 < val <= 5:
                            rating = val
                    except ValueError:
                        pass
                nums = re.findall(r'\((\d+)\)', rate_text)
                if nums:
                    review_count = int(nums[0])

            promo_el = elem.select_one("p.item-gift, div.item-gift, p.item-promo, .badge-promo, span.lb-tragop")
            promotions = promo_el.get_text(separator=" ", strip=True) if promo_el else ""

            products.append({
                "product_id": product_id,
                "product_name": product_name,
                "brand": normalize_brand(product_name),
                "category": self.category,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "availability": avail,
                "store_name": "DienmayXanh",
                "product_url": product_url,
                "image_url": image_url,
                "rating": rating,
                "review_count": review_count,
                "promotions": promotions,
                "crawl_time": datetime.now().isoformat()
            })

        return products

    def _crawl_ajax(self, cate_id: int, seen_ids: set) -> List[Dict[str, Any]]:
        ajax_headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "vi-VN,vi;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.config["url"],
        }
        ajax_body = "IsParentCate=false&IsShowCompare=true&IsAffiliate=false&prevent=true"
        ajax_url = "https://www.dienmayxanh.com/Category/FilterProductBox"

        products = []
        for pi in range(1, 200):
            if len(products) + len(seen_ids) >= settings.CRAWLER_MAX_PRODUCTS:
                break
            for attempt in range(1, 4):
                try:
                    resp = self.session.post(
                        ajax_url,
                        params={"c": cate_id, "pi": pi},
                        headers=ajax_headers,
                        data=ajax_body,
                        timeout=15
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        html_fragment = data.get("listproducts") or data.get("lstProducts", "")
                        page_products = self._parse_html_cards(html_fragment, seen_ids)
                        if not page_products:
                            logging.info(f"[{self.store_name} AJAX] pi={pi}: empty response, stopping.")
                            return products
                        products.extend(page_products)
                        logging.info(f"[{self.store_name} AJAX] pi={pi}: +{len(page_products)} items | total so far: {len(products)}")
                        break
                except Exception as e:
                    if attempt == 3:
                        logging.warning(f"[{self.store_name} AJAX] pi={pi} attempt {attempt} failed: {e}")
                    time.sleep(1)
            else:
                break

        return products

    def crawl(self) -> List[Dict[str, Any]]:
        url = self.config["url"]
        cate_id = self.config["cate_id"]
        html_headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.dienmayxanh.com"
        }

        self.session.cookies.set("DMX_Location", str(self.dmx_province_id), domain=".dienmayxanh.com")
        self.session.cookies.set("LocationId", str(self.dmx_province_id), domain=".dienmayxanh.com")

        seen_ids: set = set()
        products = []
        for attempt in range(1, 4):
            try:
                logging.info(f"[{self.store_name}] Fetching page 1 HTML: {url} (Attempt {attempt}/3)...")
                resp = self.session.get(url, headers=html_headers, timeout=15)
                if resp and resp.status_code == 200:
                    first_page = self._parse_html_cards(resp.text, seen_ids)
                    products.extend(first_page)
                    logging.info(f"[{self.store_name}] Page 1 HTML: {len(first_page)} items")
                    break
            except Exception as e:
                logging.warning(f"[{self.store_name}] HTML attempt {attempt} error: {e}")
                time.sleep(1)

        ajax_products = self._crawl_ajax(cate_id, seen_ids)
        products.extend(ajax_products)

        logging.info(f"[{self.store_name}] Total {len(products)} products fetched for '{self.category}' in {self.province_name}.")
        return products

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="mobile", help="Category to crawl")
    parser.add_argument("--province", default="Hà Nội", help="Province to crawl")
    args = parser.parse_args()

    crawler = DienmayxanhCrawler(category=args.category, province=args.province)
    crawler.run()
