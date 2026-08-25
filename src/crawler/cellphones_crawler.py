import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

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
        "smartwatch": {"url": "https://cellphones.com.vn/dong-ho-thong-minh.html"},
        "headphone": {"url": "https://cellphones.com.vn/thiet-bi-am-thanh/tai-nghe.html"},
        "speaker": {"url": "https://cellphones.com.vn/thiet-bi-am-thanh/loa.html"},
        "monitor": {"url": "https://cellphones.com.vn/man-hinh.html"},
        "keyboard": {"url": "https://cellphones.com.vn/phu-kien/chuot-ban-phim-may-tinh/ban-phim.html"},
        "mouse": {"url": "https://cellphones.com.vn/phu-kien/chuot-ban-phim-may-tinh/chuot.html"},
        "powerbank": {"url": "https://cellphones.com.vn/phu-kien/pin-du-phong.html"},
        "tivi": {"url": "https://cellphones.com.vn/tivi.html"},
        "air-purifier": {"url": "https://cellphones.com.vn/nha-thong-minh/may-loc-khong-khi.html"},
        "vacuum": {"url": "https://cellphones.com.vn/nha-thong-minh/may-hut-bui.html"},
        "camera": {"url": "https://cellphones.com.vn/phu-kien/camera.html"},
        "water-purifier": {"url": "https://cellphones.com.vn/do-gia-dung/may-loc-nuoc.html"}
    }

    def __init__(self, category: str = "mobile", province: str = "Hà Nội"):
        super().__init__(store_name="CellphoneS", category=category, province=province)
        if category not in self.CATEGORY_CONFIG:
            raise ValueError(f"Category '{category}' is not supported by CellphonesCrawler")
        self.config = self.CATEGORY_CONFIG[category]
        
        cps_ids = self.location_info.get("cps_ids", [])
        self.cps_province_id = int(cps_ids[0]) if cps_ids else 30

    def _resolve_cate_id(self) -> Optional[str]:
        cache_key = f"cache:cate_id:cellphones:{self.category}"
        cached_id = redis_client.client.get(cache_key)
        if cached_id:
            return cached_id

        url = self.config["url"]
        try:
            resp = self.fetch_with_retry(url, timeout=12)
            if resp and resp.status_code == 200:
                match = re.search(r'categories:\s*\["(\d+)"\]|["\']category_id["\']\s*:\s*["\']?(\d+)|["\']categoryId["\']\s*:\s*["\']?(\d+)', resp.text)
                if match:
                    cate_id = match.group(1) or match.group(2) or match.group(3)
                    redis_client.client.setex(cache_key, 604800, str(cate_id))
                    logging.info(f"[{self.store_name} GraphQL] Dynamically resolved CateID for '{self.category}': {cate_id}")
                    return cate_id
        except Exception as e:
            logging.warning(f"[{self.store_name} GraphQL] Dynamic CateID discovery failed for {url}: {e}")

        FALLBACK_IDS = {
            "mobile": "3", "laptop": "864", "tablet": "4", "smartwatch": "1056",
            "headphone": "265", "speaker": "73", "monitor": "784",
            "keyboard": "872", "mouse": "871", "powerbank": "122",
            "tivi": "1036", "air-purifier": "1058", "vacuum": "1059",
            "camera": "857", "water-purifier": "1182"
        }
        return FALLBACK_IDS.get(self.category)

    def _crawl_graphql(self, cate_id: str) -> List[Dict[str, Any]]:
        query = """
        query GetProductsByCateId($cate: String!, $page: Int!, $size: Int!, $prov: Int!) {
            products(
                filter: {
                    static: {
                        categories: [$cate],
                        province_id: $prov,
                        stock: { from: 0 }
                    }
                },
                page: $page,
                size: $size,
                sort: [{ view: desc }]
            ) {
                general {
                    product_id
                    name
                    sku
                    manufacturer
                    url_path
                    review {
                        total_count
                        average_rating
                    }
                }
                filterable {
                    price
                    special_price
                    stock
                    promotion_information
                    thumbnail
                }
            }
        }
        """

        products = []
        max_pages = max(1, settings.CRAWLER_MAX_PRODUCTS // 50)

        for page_idx in range(1, max_pages + 1):
            variables = {
                "cate": cate_id,
                "page": page_idx,
                "size": 50,
                "prov": self.cps_province_id
            }

            items = []
            for attempt in range(1, 4):
                try:
                    response = self.session.post(
                        self.GRAPHQL_URL,
                        json={"query": query, "variables": variables},
                        timeout=15
                    )
                    if response.status_code == 200:
                        data = response.json()
                        items = data.get("data", {}).get("products", [])
                        break
                except Exception as e:
                    if attempt == 3:
                        logging.warning(f"[{self.store_name} GraphQL] Page {page_idx} attempt {attempt} failed: {e}")
                    time.sleep(1)

            if not items:
                break

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

            logging.info(f"[{self.store_name} GraphQL] Page {page_idx}: Fetched {len(items)} items for '{self.category}' in {self.province_name}.")
            if len(products) >= settings.CRAWLER_MAX_PRODUCTS:
                break

        return products

    def crawl(self) -> List[Dict[str, Any]]:
        cate_id = self._resolve_cate_id()
        if not cate_id:
            logging.error(f"[{self.store_name} GraphQL] Could not resolve Category ID for '{self.category}'.")
            return []

        products = self._crawl_graphql(cate_id)
        logging.info(f"[{self.store_name} GraphQL] Total {len(products)} products fetched successfully for '{self.category}' (CateID {cate_id}).")
        return products


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="mobile", help="Category to crawl")
    parser.add_argument("--province", default="Hà Nội", help="Province to crawl")
    args = parser.parse_args()

    crawler = CellphonesCrawler(category=args.category, province=args.province)
    crawler.run()
