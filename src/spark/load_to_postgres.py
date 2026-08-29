import os
import sys
import logging
import time
from datetime import datetime
from pyspark.sql.functions import explode, col, lit, to_timestamp, input_file_name

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from configs.settings import settings
from src.storage.minio_client import minio_client
from src.redis.client import redis_client
from src.spark.spark_connect import sc, get_spark_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def process_files():
    logging.info("Scanning MinIO bucket for raw retail data...")
    all_files = minio_client.list_json_files()
    
    if not all_files:
        logging.info("No JSON files found in MinIO bucket.")
        return

    new_files = [f for f in all_files if not redis_client.is_file_processed(f)]
    
    if not new_files:
        logging.info("All files are already processed. No new data to load.")
        return
        
    logging.info(f"Found {len(new_files)} files to transform via PySpark and load into Data Lake / PostgreSQL.")
    
    spark_config = get_spark_config()
    db_url = spark_config["database"]["jdbc"]
    parquet_path = f"s3a://{settings.MINIO_BUCKET_PROCESSED}/products_parquet"

    batches = {}
    for f in new_files:
        parts = f.split("/")
        if len(parts) >= 2:
            key = (parts[0], parts[1])
            batches.setdefault(key, []).append(f)

    total_batches = len(batches)
    total_records_processed = 0
    start_all = time.time()

    logging.info(f"Grouped into {total_batches} category-store batches for high-performance distributed transformation.")

    batch_idx = 0
    for (store, category), file_list in batches.items():
        batch_idx += 1
        s3_paths = [f"s3a://{settings.MINIO_BUCKET_RAW}/{f}" for f in file_list]
        start_batch = time.time()

        try:
            df = sc.read.option("multiLine", "true").json(s3_paths)
            
            if "items" not in df.columns:
                logging.warning(f"[{batch_idx}/{total_batches}] Batch {store}/{category} has no 'items' array. Skipping.")
                continue

            exploded_df = df.select(
                col("category"),
                col("crawled_at"),
                input_file_name().alias("source_file"),
                explode(col("items")).alias("item")
            )

            flat_df = exploded_df.select(
                col("item.product_id").alias("product_id"),
                col("item.product_name").alias("product_name"),
                col("item.brand").alias("brand"),
                col("category"),
                col("item.current_price").alias("current_price"),
                col("item.original_price").alias("original_price"),
                col("item.discount_percent").alias("discount_percent"),
                col("item.availability").alias("availability"),
                col("item.store_name").alias("store_name"),
                col("item.location_code").alias("location_code"),
                col("item.province_name").alias("province_name"),
                col("item.region").alias("region"),
                col("item.product_url").alias("product_url"),
                col("item.image_url").alias("image_url"),
                col("item.rating").cast("double").alias("rating"),
                col("item.review_count").cast("int").alias("review_count"),
                col("item.promotions").alias("promotions"),
                to_timestamp(col("item.crawl_time")).alias("crawl_time"),
                col("source_file")
            )

            record_count = flat_df.count()

            flat_df.write \
                .format("parquet") \
                .mode("append") \
                .partitionBy("store_name", "category") \
                .save(parquet_path)

            flat_df.write \
                .format("jdbc") \
                .option("url", db_url) \
                .option("driver", "org.postgresql.Driver") \
                .option("dbtable", "raw_products") \
                .option("user", settings.POSTGRES_USER) \
                .option("password", settings.POSTGRES_PASSWORD) \
                .mode("append") \
                .save()

            for f in file_list:
                redis_client.mark_file_processed(f)

            total_records_processed += record_count
            dur_batch = round(time.time() - start_batch, 2)
            logging.info(f"[{batch_idx}/{total_batches}] SUCCESS: {store.upper():<12} | {category:<15} ({len(file_list)} files) -> {record_count:,} records in {dur_batch}s")

        except Exception as e:
            logging.error(f"[{batch_idx}/{total_batches}] ERROR on {store}/{category}: {e}")

    total_duration = round(time.time() - start_all, 1)
    logging.info("=" * 80)
    logging.info(f"ETL COMPLETE: Processed {total_records_processed:,} records across {len(new_files)} files in {total_duration}s")
    logging.info("=" * 80)

    sc.stop()

if __name__ == "__main__":
    process_files()
