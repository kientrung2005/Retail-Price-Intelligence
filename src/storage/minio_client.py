import json
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from src.config.settings import settings

class MinIOStorageClient:
    def __init__(self):
        protocol = "https" if settings.MINIO_SECURE else "http"
        endpoint_url = f"{protocol}://{settings.MINIO_ENDPOINT}"
        
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1"
        )
        self.ensure_bucket_exists(settings.MINIO_BUCKET_RAW)

    def ensure_bucket_exists(self, bucket_name: str) -> None:
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except ClientError:
            self.s3_client.create_bucket(Bucket=bucket_name)

    def upload_json(self, data: dict, object_name: str, bucket_name: str = None) -> str:
        if bucket_name is None:
            bucket_name = settings.MINIO_BUCKET_RAW

        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        
        self.s3_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=json_bytes,
            ContentType="application/json"
        )
        return f"{bucket_name}/{object_name}"

minio_client = MinIOStorageClient()
