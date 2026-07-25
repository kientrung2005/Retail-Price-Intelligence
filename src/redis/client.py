import redis
import json
from typing import Optional
from src.config.settings import settings

class RedisClient:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )

    def is_visited(self, url: str, run_id: str) -> bool:
        return bool(self.client.sismember(f"crawler:visited:{run_id}", url))

    def mark_visited(self, url: str, run_id: str, ttl_seconds: int = 21600) -> None:
        key = f"crawler:visited:{run_id}"
        self.client.sadd(key, url)
        self.client.expire(key, ttl_seconds)

    def push_queue(self, item: str, queue_name: str = "crawler:queue") -> None:
        self.client.lpush(queue_name, item)

    def pop_queue(self, queue_name: str = "crawler:queue", timeout: int = 5) -> Optional[str]:
        result = self.client.brpop(queue_name, timeout=timeout)
        if result:
            return result[1]
        return None

    def get_queue_length(self, queue_name: str = "crawler:queue") -> int:
        return self.client.llen(queue_name)

    def ping(self) -> bool:
        return self.client.ping()

    def get_cached_detail(self, url: str) -> Optional[dict]:
        data = self.client.get(f"cache:detail:{url}")
        if data:
            try:
                return json.loads(data)
            except:
                pass
        return None

    def set_cached_detail(self, url: str, detail_data: dict, expire_seconds: int = 43200) -> None:
        self.client.setex(f"cache:detail:{url}", expire_seconds, json.dumps(detail_data))

redis_client = RedisClient()
