import logging
import json
import time
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests

from configs.settings import settings
from src.storage.minio_client import minio_client
from src.redis.client import redis_client
from src.utils.brand_utils import normalize_brand
from src.utils.url_utils import normalize_url
from src.utils.location_utils import map_location_to_34, LOCATIONS_34

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class BaseCrawler(ABC):
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(self, store_name: str, category: str, province: str = "Hà Nội"):
        self.store_name = store_name
        self.category = category
        self.location_info = map_location_to_34(province)
        self.province_name = self.location_info["name"]
        self.region = self.location_info["region"]
        self.location_code = self.location_info["code"]

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
        })

    def fetch_with_retry(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Any] = None,
        retries: int = 3,
        timeout: int = 15
    ) -> Optional[requests.Response]:
        delay = 1.0
        req_headers = headers or {}

        for attempt in range(retries):
            try:
                if method.upper() == "POST":
                    response = self.session.post(
                        url,
                        headers=req_headers,
                        data=data,
                        json=json_data,
                        timeout=timeout
                    )
                else:
                    response = self.session.get(
                        url,
                        headers=req_headers,
                        params=data,
                        timeout=timeout
                    )
                response.raise_for_status()
                return response
            except Exception as e:
                logging.warning(f"[{self.store_name} RETRY {attempt + 1}/{retries}] Error requesting {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    logging.error(f"[{self.store_name} ERROR] Max retries exceeded for {url}")
        return None

    def validate_product_item(self, item: Dict[str, Any]) -> bool:
        if not item.get("product_id") or not item.get("product_name"):
            return False
        if len(str(item.get("product_name", "")).strip()) < 2:
            return False
        return True

    def sanitize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        current_price = str(item.get("current_price", "N/A")).strip()
        original_price = str(item.get("original_price", current_price)).strip()

        discount = str(item.get("discount_percent", "0%")).strip()
        if discount and discount not in ("0%", "0", ""):
            if not discount.endswith("%"):
                discount = f"{discount}%"
            if not discount.startswith("-") and discount != "0%":
                discount = f"-{discount}"
        else:
            discount = "0%"

        try:
            rating = round(float(item.get("rating", 0.0)), 1)
            if not (0.0 <= rating <= 5.0):
                rating = 0.0
        except (ValueError, TypeError):
            rating = 0.0

        try:
            review_count = int(item.get("review_count", 0))
            if review_count < 0:
                review_count = 0
        except (ValueError, TypeError):
            review_count = 0

        avail = str(item.get("availability", "In Stock")).strip()
        if avail not in ("In Stock", "Out of Stock", "Coming Soon"):
            avail = "In Stock"

        return {
            "product_id": str(item.get("product_id", "")).strip(),
            "product_name": str(item.get("product_name", "")).strip(),
            "brand": normalize_brand(str(item.get("product_name", "")), fallback_brand=str(item.get("brand", ""))),
            "category": self.category,
            "current_price": current_price if current_price else "N/A",
            "original_price": original_price if original_price else current_price,
            "discount_percent": discount,
            "availability": avail,
            "store_name": self.store_name,
            "location_code": self.location_code,
            "province_name": self.province_name,
            "region": self.region,
            "product_url": normalize_url(str(item.get("product_url", ""))),
            "image_url": str(item.get("image_url", "N/A")),
            "rating": rating,
            "review_count": review_count,
            "promotions": str(item.get("promotions", "")).strip(),
            "crawl_time": item.get("crawl_time") or datetime.now().isoformat()
        }

    def save_to_data_lake(self, products: List[Dict[str, Any]]) -> Optional[str]:
        if not products:
            logging.warning(f"[{self.store_name}] No products to save for category '{self.category}'.")
            return None

        sanitized_products = [self.sanitize_item(p) for p in products if self.validate_product_item(p)]
        logging.info(f"[{self.store_name}] Validated {len(sanitized_products)}/{len(products)} products for '{self.category}' in {self.province_name} ({self.region}).")

        payload = {
            "source": self.store_name.lower().replace(" ", ""),
            "category": self.category,
            "location_code": self.location_code,
            "province_name": self.province_name,
            "region": self.region,
            "total_items": len(sanitized_products),
            "items": sanitized_products,
            "crawled_at": datetime.now().isoformat()
        }

        store_folder = self.store_name.lower().replace(" ", "")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        object_name = f"{store_folder}/{self.category}/{self.location_code.lower()}_data_{timestamp}.json"

        saved_location = minio_client.upload_json(payload, object_name)
        logging.info(f"[{self.store_name}] Successfully uploaded {len(sanitized_products)} items to MinIO: {saved_location}")
        return saved_location

    @abstractmethod
    def crawl(self) -> List[Dict[str, Any]]:
        pass

    def run(self) -> Optional[str]:
        logging.info(f"[{self.store_name}] Starting crawl for '{self.category}' in {self.province_name} ({self.location_code})...")
        start_time = time.time()
        try:
            products = self.crawl()
            duration = round(time.time() - start_time, 2)
            logging.info(f"[{self.store_name}] Crawl completed in {duration}s. Found {len(products)} products.")
            return self.save_to_data_lake(products)
        except Exception as e:
            logging.error(f"[{self.store_name}] Crawl job failed: {e}", exc_info=True)
            return None
