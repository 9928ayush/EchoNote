from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.init_storage import ensure_bucket


def test_existing_bucket_does_not_get_recreated():
    storage = Mock()
    ensure_bucket(storage)
    storage.head_bucket.assert_called_once()
    storage.create_bucket.assert_not_called()


def test_missing_bucket_is_created():
    storage = Mock()
    storage.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
        "HeadBucket",
    )
    ensure_bucket(storage)
    storage.create_bucket.assert_called_once_with(Bucket="echonote")


def test_startup_failure_is_bounded_and_does_not_leak_endpoint():
    storage, wait = Mock(), Mock()
    storage.head_bucket.side_effect = EndpointConnectionError(endpoint_url="secret-endpoint")
    with pytest.raises(RuntimeError, match="Storage initialization failed") as error:
        ensure_bucket(storage, attempts=3, wait=wait)
    assert storage.head_bucket.call_count == 3
    assert wait.call_count == 2
    assert "secret-endpoint" not in str(error.value)
