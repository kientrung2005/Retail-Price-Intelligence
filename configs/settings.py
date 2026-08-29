import os

class Settings:
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))

    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minio_admin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minio_password")
    MINIO_BUCKET_RAW: str = os.getenv("MINIO_BUCKET_RAW", "raw-retail-data")
    MINIO_BUCKET_PROCESSED: str = os.getenv("MINIO_BUCKET_PROCESSED", "processed-retail-data")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", 5432))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "retail_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "retail_password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "retail_dw")

    CRAWLER_MAX_PRODUCTS: int = int(os.getenv("CRAWLER_MAX_PRODUCTS", 10000))
    CRAWLER_MAX_LOAD_MORE: int = int(os.getenv("CRAWLER_MAX_LOAD_MORE", 30))

settings = Settings()
