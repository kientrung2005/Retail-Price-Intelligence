import json
from src.redis.client import redis_client

CATEGORIES = [
    "mobile",
    "laptop",
    "tablet",
    "smartwatch",
    "headphone",
    "speaker",
    "monitor",
    "keyboard",
    "mouse",
    "powerbank"
]

STORES = ["Cellphones", "FPTShop", "DienmayXanh"]

def main():
    redis_client.client.delete("crawler:queue")
    tasks = []
    for category in CATEGORIES:
        for store in STORES:
            tasks.append({"store": store, "category": category})
            
    count = 0
    for task in tasks:
        redis_client.push_queue(json.dumps(task))
        count += 1
    print(f"Pushed {count} tasks to crawler:queue successfully.")

if __name__ == "__main__":
    main()
