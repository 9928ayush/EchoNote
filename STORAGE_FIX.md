# Local storage startup fix

The original Compose setup references prebuilt MinIO images that cannot currently be pulled in the user's environment. This patch builds the pinned community server release from the official MinIO GitHub source repository instead. Bucket initialization uses the existing backend's Boto3 S3 client; it no longer needs a separate MinIO mc image.

Extract this archive directly into the existing EchoNote project root, replacing docker-compose.yml. It contains no .env file and preserves your credentials.

Run:

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps -a
```

The first storage build downloads the official Go builder image, MinIO source and Go dependencies, then compiles the server. It will take longer than pulling a prebuilt server. No local Go installation is required. The release pin is the same release originally used for the local storage service. Production Compose uses your managed S3-compatible storage and is unaffected.

Source: https://github.com/minio/minio

The patch's bucket setup tests cover existing buckets, missing bucket creation and bounded startup failures. The Compose structure and required dependency order were checked. The full Docker/Go build could not be executed in the authoring environment because Docker is unavailable; this patch is not claimed to have completed a container integration run.
