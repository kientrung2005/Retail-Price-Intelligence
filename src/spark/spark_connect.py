from typing import Optional, List, Dict
from pyspark.sql import SparkSession
from configs.settings import settings

def get_spark_config():
    jdbc_url = f"jdbc:postgresql://{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    
    spark_bucket_conf = {
        "spark.hadoop.fs.s3a.endpoint": f"http://{settings.MINIO_ENDPOINT}",
        "spark.hadoop.fs.s3a.access.key": settings.MINIO_ACCESS_KEY,
        "spark.hadoop.fs.s3a.secret.key": settings.MINIO_SECRET_KEY,
        "spark.hadoop.fs.s3a.path.style.access": "true",
        "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
        "spark.hadoop.fs.s3a.fast.upload": "true",
        "spark.hadoop.fs.s3a.fast.upload.buffer": "bytebuffer",
        "spark.hadoop.fs.s3a.multipart.size": "10485760",
    }

    return {
        "database": {
            "jdbc": jdbc_url,
            "config": {
                "host": settings.POSTGRES_HOST,
                "port": settings.POSTGRES_PORT,
                "user": settings.POSTGRES_USER,
                "password": settings.POSTGRES_PASSWORD,
                "database": settings.POSTGRES_DB,
                "driver": "org.postgresql.Driver"
            }
        },
        "s3": spark_bucket_conf
    }

class SparkConnect:
    def __init__(
            self,
            app_name: str,
            master_url: str,
            executor_memory: Optional[str] = "4g",
            executor_cores: Optional[int] = 2,
            driver_memory: Optional[str] = "2g",
            num_executors: Optional[int] = 1,
            jar_packages: Optional[List[str]] = None,
            spark_conf: Optional[Dict[str, str]] = None,
            log_level: str = "WARN"
    ):
        self.app_name = app_name
        self.spark = self.create_spark_session(
            master_url,
            executor_memory,
            executor_cores,
            driver_memory,
            num_executors,
            jar_packages,
            spark_conf,
            log_level
        )

    def create_spark_session(
            self,
            master_url: str,
            executor_memory: Optional[str] = "4g",
            executor_cores: Optional[int] = 2,
            driver_memory: Optional[str] = "2g",
            num_executors: Optional[int] = 1,
            jar_packages: Optional[List[str]] = None,
            spark_conf: Optional[Dict[str, str]] = None,
            log_level: str = "WARN"
    ) -> SparkSession:

        builder = SparkSession.builder \
            .appName(self.app_name) \
            .master(master_url)

        if executor_memory:
            builder.config("spark.executor.memory", executor_memory)
        if executor_cores:
            builder.config("spark.executor.cores", executor_cores)
        if driver_memory:
            builder.config("spark.driver.memory", driver_memory)
        if num_executors:
            builder.config("spark.executor.instances", num_executors)
        if jar_packages:
            jar_packages_url = ",".join([jar_package for jar_package in jar_packages])
            builder.config("spark.jars.packages", jar_packages_url)
        if spark_conf:
            for key, value in spark_conf.items():
                builder.config(key, value)

        spark = builder.getOrCreate()
        spark.sparkContext.setLogLevel(log_level)

        return spark

    def stop(self):
        if self.spark:
            self.spark.stop()
            print("-------Stop Spark Session--------")

    def __getattr__(self, name):
        """Forward all methods/attributes to SparkSession instance (e.g. read, sql)"""
        return getattr(self.spark, name)

def create_spark_connect():
    spark_config = get_spark_config()

    jars = ["org.postgresql:postgresql:42.6.2",
            "org.apache.hadoop:hadoop-aws:3.3.4",
            "com.amazonaws:aws-java-sdk-bundle:1.12.540"
    ]

    spark_connect = SparkConnect(
        app_name="retail-price-intelligence",
        master_url="local[*]",
        executor_memory="2g",
        executor_cores=1,
        driver_memory="1g",
        num_executors=1,
        jar_packages=jars,
        spark_conf=spark_config["s3"],
        log_level="WARN"
    )

    return spark_connect

sc = create_spark_connect()
