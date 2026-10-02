# Build the same pinned community release from the official source repository.
# This avoids depending on MinIO's unavailable prebuilt registry images.
FROM golang:1.25-bookworm AS build
ARG MINIO_RELEASE=RELEASE.2025-04-22T22-12-26Z
RUN git clone --depth 1 --branch "$MINIO_RELEASE" https://github.com/minio/minio.git /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -o /out/minio .

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home storage \
    && mkdir /data && chown storage:storage /data
COPY --from=build /out/minio /usr/local/bin/minio
USER storage
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
