import json
import boto3
from datetime import datetime, timezone, timedelta
from botocore.client import Config
from botocore.exceptions import ClientError
from configs.settings import settings

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
        self.ensure_bucket_exists(settings.MINIO_BUCKET_PROCESSED)
        self.ensure_lifecycle_policy(settings.MINIO_BUCKET_RAW, days=30)

    def ensure_bucket_exists(self, bucket_name: str) -> None:
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except ClientError:
            self.s3_client.create_bucket(Bucket=bucket_name)

    def ensure_lifecycle_policy(self, bucket_name: str, days: int = 30) -> None:
        try:
            rule = {
                'Rules': [
                    {
                        'ID': f'auto-expire-json-{days}-days',
                        'Status': 'Enabled',
                        'Filter': {'Prefix': ''},
                        'Expiration': {'Days': days}
                    }
                ]
            }
            self.s3_client.put_bucket_lifecycle_configuration(
                Bucket=bucket_name,
                LifecycleConfiguration=rule
            )
        except Exception:
            pass

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

    def read_json(self, bucket_name: str, object_name: str) -> dict:
        resp = self.s3_client.get_object(Bucket=bucket_name, Key=object_name)
        content = resp["Body"].read().decode("utf-8")
        return json.loads(content)

    def list_json_files(self, bucket_name: str = None) -> list:
        if bucket_name is None:
            bucket_name = settings.MINIO_BUCKET_RAW
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name)
            files = []
            for page in pages:
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if key.endswith('.json'):
                        files.append(key)
            return files
        except Exception:
            return []

    def delete_file(self, object_name: str, bucket_name: str = None) -> bool:
        if bucket_name is None:
            bucket_name = settings.MINIO_BUCKET_RAW
        try:
            self.s3_client.delete_object(Bucket=bucket_name, Key=object_name)
            return True
        except Exception:
            return False

    def cleanup_old_json_files(self, days: int = 30, bucket_name: str = None) -> int:
        """Delete JSON files older than `days` days from MinIO bucket."""
        if bucket_name is None:
            bucket_name = settings.MINIO_BUCKET_RAW
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted_count = 0
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket_name):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    last_mod = obj.get('LastModified')
                    if key.endswith('.json') and last_mod and last_mod < cutoff:
                        self.s3_client.delete_object(Bucket=bucket_name, Key=key)
                        deleted_count += 1
            return deleted_count
        except Exception:
            return 0

minio_client = MinIOStorageClient()
