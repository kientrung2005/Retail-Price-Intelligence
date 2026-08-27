import os
import sys
import logging
from datetime import datetime
from pyspark.sql.functions import explode, col, lit, to_timestamp

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
        
    logging.info(f"Found {len(new_files)} new files to load into PostgreSQL.")
    
    spark_config = get_spark_config()
    db_url = spark_config["database"]["jdbc"]
    
    for file_key in new_files:
        s3_path = f"s3a://{settings.MINIO_BUCKET_RAW}/{file_key}"
        logging.info(f"Processing: {s3_path}")
        
        try:
            df = sc.read.option("multiLine", "true").json(s3_path)
            
            if "items" not in df.columns:
                logging.warning(f"File {file_key} does not contain 'items' array. Skipping.")
                continue
                
            exploded_df = df.select(
                col("category"),
                col("crawled_at"),
                lit(file_key).alias("source_file"),
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
            
            # 1. Ghi ra dinh dang Parquet tren MinIO (Silver Layer)
            parquet_path = f"s3a://{settings.MINIO_BUCKET_PROCESSED}/products_parquet"
            flat_df.write \
                .format("parquet") \
                .mode("append") \
                .partitionBy("store_name", "category") \
                .save(parquet_path)

            # 2. Nap vao PostgreSQL Database (Gold Layer)
            flat_df.write \
                .format("jdbc") \
                .option("url", db_url) \
                .option("driver", "org.postgresql.Driver") \
                .option("dbtable", "raw_products") \
                .option("user", settings.POSTGRES_USER) \
                .option("password", settings.POSTGRES_PASSWORD) \
                .mode("append") \
                .save()
                
            redis_client.mark_file_processed(file_key)
            logging.info(f"Successfully loaded and cached: {file_key}")
            
        except Exception as e:
            logging.error(f"Failed to process file {file_key}: {e}")
            
    sc.stop()

if __name__ == "__main__":
    process_files()
