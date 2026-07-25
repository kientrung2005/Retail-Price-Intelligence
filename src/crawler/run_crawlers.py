import json
import time
import subprocess
import sys
import logging
from concurrent.futures import ThreadPoolExecutor
from src.redis.client import redis_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CRAWLER_MAP = {
    "Cellphones": "src.crawler.cellphones_crawler",
    "FPTShop": "src.crawler.fptshop_crawler",
    "DienmayXanh": "src.crawler.dienmayxanh_crawler"
}

def run_crawler_process(store_name, module_path, category):
    logging.info(f"STARTING TASK: {store_name} | CATEGORY: {category}")
    cmd = [sys.executable, "-m", module_path, "--category", category]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                msg = f"[{store_name}-{category}] {output.strip()}\n"
                sys.stdout.buffer.write(msg.encode(sys.stdout.encoding or "utf-8", errors="replace"))
                sys.stdout.flush()
        rc = process.poll()
        if rc == 0:
            logging.info(f"SUCCESS TASK: {store_name} | CATEGORY: {category}")
        else:
            logging.error(f"FAILED TASK (Exit Code {rc}): {store_name} | CATEGORY: {category}")
    except Exception as e:
        logging.error(f"ERROR executing crawler for {store_name} {category}: {e}")

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
            module_path = CRAWLER_MAP.get(store)
            if module_path:
                run_crawler_process(store, module_path, category)
                time.sleep(3)
            else:
                logging.error(f"Unknown store: {store}")
        except Exception as e:
            logging.error(f"Worker-{worker_id} error: {e}")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3, help="Number of concurrent workers")
    args = parser.parse_args()

    q_len = redis_client.get_queue_length("crawler:queue")
    if q_len == 0:
        logging.warning("Queue is empty! Populating with default tasks...")
        subprocess.run([sys.executable, "-m", "src.redis.enqueue_tasks"])
        q_len = redis_client.get_queue_length("crawler:queue")

    logging.info(f"Starting {args.workers} concurrent workers to process {q_len} tasks...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(worker_loop, i) for i in range(1, args.workers + 1)]
        for f in futures:
            f.result()
    logging.info("All tasks processed.")

if __name__ == "__main__":
    main()
