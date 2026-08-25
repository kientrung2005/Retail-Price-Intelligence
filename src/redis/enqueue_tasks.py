import json
import argparse
from src.redis.client import redis_client
from src.utils.location_utils import get_all_34_locations

BATCH_CONFIG = {
    "1": {
        "name": "Dot 1: mobile, laptop, tablet, smartwatch, tivi",
        "categories": ["mobile", "laptop", "tablet", "smartwatch", "tivi"]
    },
    "2": {
        "name": "Dot 2: headphone, speaker, keyboard, mouse, powerbank",
        "categories": ["headphone", "speaker", "keyboard", "mouse", "powerbank"]
    },
    "3": {
        "name": "Dot 3: monitor, air-purifier, vacuum, camera, water-purifier",
        "categories": ["monitor", "air-purifier", "vacuum", "camera", "water-purifier"]
    }
}

ALL_CATEGORIES = [
    "mobile", "laptop", "tablet", "smartwatch", "tivi",
    "headphone", "speaker", "keyboard", "mouse", "powerbank",
    "monitor", "air-purifier", "vacuum", "camera", "water-purifier"
]

STORES = ["Cellphones", "FPTShop", "DienmayXanh"]
PROVINCES = [loc["short_name"] for loc in get_all_34_locations()]

def main():
    parser = argparse.ArgumentParser(description="Enqueue crawler tasks to Redis in batches or all at once.")
    parser.add_argument("--batch", choices=["1", "2", "3", "all"], default="all", help="Choose batch 1, 2, 3 or all")
    parser.add_argument("--category", type=str, default=None, help="Enqueue a single category")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear existing queue before pushing")
    args = parser.parse_args()

    if not args.no_clear:
        redis_client.client.delete("crawler:queue")

    if args.category:
        selected_categories = [args.category]
        batch_desc = f"Category '{args.category}'"
    elif args.batch == "all":
        selected_categories = ALL_CATEGORIES
        batch_desc = "All 15 categories"
    else:
        selected_categories = BATCH_CONFIG[args.batch]["categories"]
        batch_desc = BATCH_CONFIG[args.batch]["name"]

    tasks = []
    for category in selected_categories:
        for store in STORES:
            for province in PROVINCES:
                tasks.append({"store": store, "category": category, "province": province})

    for task in tasks:
        redis_client.push_queue(json.dumps(task, ensure_ascii=False))

    print(f"Pushed {len(tasks)} tasks ({batch_desc} - {len(selected_categories)} categories x {len(STORES)} stores x {len(PROVINCES)} provinces) to crawler:queue successfully.")

if __name__ == "__main__":
    main()
