import json
import time
import subprocess
import sys
import logging
from concurrent.futures import ThreadPoolExecutor
from src.redis.client import redis_client
from src.storage.minio_client import minio_client
from src.utils.location_utils import get_all_34_locations

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CRAWLER_MAP = {
    "Cellphones": "src.crawler.cellphones_crawler",
    "FPTShop": "src.crawler.fptshop_crawler",
    "DienmayXanh": "src.crawler.dienmayxanh_crawler"
}

STORES = ["Cellphones", "FPTShop", "DienmayXanh"]
ALL_CATEGORIES = [
    "mobile", "laptop", "tablet", "smartwatch", "tivi",
    "headphone", "speaker", "keyboard", "mouse", "powerbank",
    "monitor", "air-purifier", "vacuum", "camera"
]

def run_crawler_process(store_name, module_path, category, province="Hà Nội"):
    logging.info(f"STARTING TASK: {store_name} | CATEGORY: {category} | PROVINCE: {province}")
    cmd = [sys.executable, "-m", module_path, "--category", category, "--province", province]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                msg = f"[{store_name}-{category}-{province}] {output.strip()}\n"
                sys.stdout.buffer.write(msg.encode(sys.stdout.encoding or "utf-8", errors="replace"))
                sys.stdout.flush()
        rc = process.poll()
        if rc == 0:
            logging.info(f"SUCCESS TASK: {store_name} | CATEGORY: {category} | PROVINCE: {province}")
        else:
            logging.error(f"FAILED TASK (Exit Code {rc}): {store_name} | CATEGORY: {category} | PROVINCE: {province}")
    except Exception as e:
        logging.error(f"ERROR executing crawler for {store_name} {category} {province}: {e}")

def worker_loop(worker_id):
    logging.info(f"Worker-{worker_id} started.")
    while True:
        task_str = redis_client.pop_queue("crawler:queue", timeout=5)
        if not task_str:
            logging.info(f"Worker-{worker_id}: Queue is empty. Exiting.")
            break
        try:
            task = json.loads(task_str)
            store = task["store"]
            category = task["category"]
            province = task.get("province", "Hà Nội")
            module_path = CRAWLER_MAP.get(store)
            if module_path:
                run_crawler_process(store, module_path, category, province)
                time.sleep(1)
            else:
                logging.error(f"Unknown store: {store}")
        except Exception as e:
            logging.error(f"Worker-{worker_id} error: {e}")

def check_and_enqueue_missing(target_categories=None) -> int:
    existing_files = minio_client.list_json_files()
    existing_keys = set()
    for f in existing_files:
        parts = f.split("/")
        if len(parts) >= 3:
            store = parts[0].lower()
            cat = parts[1].lower()
            file_name = parts[2]
            loc_code = file_name.split("_data_")[0].lower() if "_data_" in file_name else file_name.split("_")[0].lower()
            existing_keys.add((store, cat, loc_code))

    locations = get_all_34_locations()
    missing_tasks = []
    cats_to_check = target_categories if target_categories else ALL_CATEGORIES

    for store in STORES:
        for cat in cats_to_check:
            for loc in locations:
                loc_code = loc["code"].lower()
                key = (store.lower(), cat.lower(), loc_code)
                if key not in existing_keys:
                    missing_tasks.append({
                        "store": store,
                        "category": cat,
                        "province": loc["name"]
                    })

    if missing_tasks:
        for task in missing_tasks:
            redis_client.push_queue(json.dumps(task, ensure_ascii=False))
        logging.info(f"[AUTO-RECONCILIATION] Found {len(missing_tasks)} missing tasks for active categories ({len(cats_to_check)} cates). Auto-enqueued to Redis!")
        return len(missing_tasks)

    logging.info(f"[AUTO-RECONCILIATION] 100% COMPLETE! All tasks for {len(cats_to_check)} active categories exist in MinIO Data Lake.")
    return 0

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=10, help="Number of concurrent workers")
    parser.add_argument("--batch", choices=["1", "2", "3", "all"], default=None, help="Auto populate batch if queue empty")
    args = parser.parse_args()

    q_len = redis_client.get_queue_length("crawler:queue")
    if q_len == 0:
        batch_arg = ["--batch", args.batch] if args.batch else []
        logging.warning(f"Queue is empty! Populating with tasks ({args.batch or 'all'})...")
        subprocess.run([sys.executable, "-m", "src.redis.enqueue_tasks"] + batch_arg)
        q_len = redis_client.get_queue_length("crawler:queue")

    active_categories = set()
    try:
        raw_items = redis_client.client.lrange("crawler:queue", 0, -1)
        for item in raw_items:
            try:
                t = json.loads(item)
                if "category" in t:
                    active_categories.add(t["category"])
            except Exception:
                pass
    except Exception:
        pass

    target_cats = list(active_categories) if active_categories else ALL_CATEGORIES
    logging.info(f"Target categories for this crawl session: {target_cats}")

    logging.info(f"Starting {args.workers} concurrent workers to process {q_len} tasks...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(worker_loop, i) for i in range(1, args.workers + 1)]
        for f in futures:
            f.result()

    for round_idx in range(1, 3):
        missing_count = check_and_enqueue_missing(target_categories=target_cats)
        if missing_count == 0:
            break
        logging.info(f"=== [AUTO-BACKFILL ROUND {round_idx}] Starting {args.workers} workers to crawl {missing_count} missing tasks ===")
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(worker_loop, i) for i in range(1, args.workers + 1)]
            for f in futures:
                f.result()

    final_missing = check_and_enqueue_missing(target_categories=target_cats)
    if final_missing == 0:
        logging.info(f"SUCCESS: ALL DATA LAKE FILES FOR {len(target_cats)} CATEGORIES ARE 100% CRAWLED & STORED IN MINIO!")
    else:
        logging.warning(f"Crawling finished. {final_missing} tasks could not be retrieved.")

if __name__ == "__main__":
    main()
