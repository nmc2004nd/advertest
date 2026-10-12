# MinIO cho bản triển khai (deploy/railway/README.md): cùng image đã pin với docker/compose.yaml.
# Volume gắn ở /data. Bucket tạo bằng deploy/railway/create-buckets.sh.
FROM cgr.dev/chainguard/minio@sha256:6a1d0b45c8669726bba580ced0bfa4cb9fdeed1ed636dfabd81d1577beb6937b
EXPOSE 9000
CMD ["server", "/data", "--address", ":9000", "--console-address", ":9001"]
