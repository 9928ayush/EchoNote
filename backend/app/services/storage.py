from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ..config import settings
from .errors import ServiceError


@lru_cache
def client(public: bool = False):
    s = settings()
    return boto3.client(
        "s3",
        endpoint_url=(s.s3_public_endpoint_url or s.s3_endpoint_url)
        if public
        else s.s3_endpoint_url,
        region_name=s.s3_region,
        aws_access_key_id=s.s3_access_key or None,
        aws_secret_access_key=s.s3_secret_key or None,
        config=Config(
            signature_version="s3v4",
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 2},
            s3={"addressing_style": "path"},
        ),
    )


def upload(path, key: str, mime: str):
    try:
        client().upload_file(str(path), settings().s3_bucket, key, ExtraArgs={"ContentType": mime})
    except (BotoCoreError, ClientError) as exc:
        raise ServiceError("Storage is unavailable. Please upload the file again.", False) from exc


def download(key: str, path):
    try:
        client().download_file(settings().s3_bucket, key, str(path))
    except (BotoCoreError, ClientError) as exc:
        raise ServiceError("The recording could not be read from storage. Please retry.") from exc


def playback(key: str) -> str:
    return client(True).generate_presigned_url(
        "get_object", Params={"Bucket": settings().s3_bucket, "Key": key}, ExpiresIn=3600
    )
