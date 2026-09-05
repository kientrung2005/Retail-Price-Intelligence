import logging
from src.database.postgresql_connect import PostgresConnect
from configs.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def create_tables():
    logging.info("Initializing PostgreSQL raw_products table...")
    
    with PostgresConnect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB
    ) as db:
        create_table_query = """
        CREATE TABLE IF NOT EXISTS raw_products (
            id                  BIGSERIAL PRIMARY KEY,
            product_id          VARCHAR(255) NOT NULL,
            product_name        TEXT NOT NULL,
            brand               VARCHAR(100),
            category            VARCHAR(50),
            current_price       VARCHAR(50),
            original_price      VARCHAR(50),
            discount_percent    VARCHAR(20),
            availability        VARCHAR(50),
            store_name          VARCHAR(50),
            location_code       VARCHAR(50),
            province_name       VARCHAR(150),
            region              VARCHAR(50),
            product_url         TEXT,
            image_url           TEXT,
            rating              NUMERIC,
            review_count        INTEGER,
            promotions          TEXT,
            crawl_time          TIMESTAMP,
            source_file         TEXT,
            loaded_at           TIMESTAMP DEFAULT now()
        );
        """
        db.cursor.execute(create_table_query)
        
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_raw_products_product_id ON raw_products(product_id);",
            "CREATE INDEX IF NOT EXISTS idx_raw_products_crawl_time ON raw_products(crawl_time);",
            "CREATE INDEX IF NOT EXISTS idx_raw_products_location ON raw_products(location_code);",
            "CREATE INDEX IF NOT EXISTS idx_raw_products_pid_time ON raw_products(product_id, crawl_time DESC);",
            "CREATE INDEX IF NOT EXISTS idx_raw_products_pid_loc_time ON raw_products(product_id, location_code, crawl_time DESC);",
            "CREATE INDEX IF NOT EXISTS idx_raw_products_category ON raw_products(category);"
        ]
        for idx in indexes:
            db.cursor.execute(idx)
        
        logging.info("Table raw_products initialized successfully with location, promotion columns and composite indexes.")

if __name__ == "__main__":
    create_tables()
