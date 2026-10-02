"""Create the local private bucket without depending on a separate mc image."""

import logging
import time

from botocore.exceptions import BotoCoreError, ClientError

from .config import settings
from .logging_config import configure_logging
from .services.storage import client

log = logging.getLogger(__name__)


def ensure_bucket(storage_client=None, attempts: int = 20, wait=time.sleep):
    s = settings()
    storage_client = storage_client or client()
    for attempt in range(attempts):
        try:
            try:
                storage_client.head_bucket(Bucket=s.s3_bucket)
            except ClientError as exc:
                status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if status != 404:
                    raise
                parameters = {"Bucket": s.s3_bucket}
                if s.s3_region != "us-east-1":
                    parameters["CreateBucketConfiguration"] = {"LocationConstraint": s.s3_region}
                try:
                    storage_client.create_bucket(**parameters)
                except ClientError as create_error:
                    if (
                        create_error.response.get("Error", {}).get("Code")
                        != "BucketAlreadyOwnedByYou"
                    ):
                        raise
            log.info("storage_bucket_ready")
            return
        except (BotoCoreError, ClientError):
            log.warning("waiting_for_storage")
            if attempt == attempts - 1:
                raise RuntimeError(
                    "Storage initialization failed. Check storage startup and credentials."
                ) from None
            wait(3)


if __name__ == "__main__":
    configure_logging()
    ensure_bucket()
