"""S3-compatible object storage provider."""

from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import StorageSettings
from src.providers.base import MissingProviderDependencyError


@dataclass(frozen=True, slots=True)
class S3CompatibleStorageProvider:
    """S3-compatible provider for S3, R2, B2, and MinIO endpoints.

    Example:
        `S3CompatibleStorageProvider(settings).exists("x")`
    """

    settings: StorageSettings

    def put_bytes(
        self,
        path: str,
        data: bytes,
        content_type: str | None = None,
    ) -> str:
        """Store bytes through the optional boto3 SDK."""
        args = _put_object_args(self.settings.bucket_name, path, data, content_type)
        self._client().put_object(**args)
        return self._uri(path)

    def get_bytes(self, path: str) -> bytes:
        """Read bytes through the optional boto3 SDK."""
        response = self._client().get_object(Bucket=self.settings.bucket_name, Key=path)
        return response["Body"].read()

    def exists(self, path: str) -> bool:
        """Return whether the remote object exists."""
        try:
            self._client().head_object(Bucket=self.settings.bucket_name, Key=path)
        except Exception:
            return False
        return True

    def list(self, prefix: str) -> list[str]:
        """List remote keys below a prefix."""
        response = self._client().list_objects_v2(
            Bucket=self.settings.bucket_name,
            Prefix=prefix,
        )
        return [item["Key"] for item in response.get("Contents", [])]

    def delete(self, path: str) -> None:
        """Delete a remote object."""
        self._client().delete_object(Bucket=self.settings.bucket_name, Key=path)

    def presign_read(self, path: str, expires_seconds: int) -> str:
        """Return a temporary remote read URL."""
        return self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.settings.bucket_name, "Key": path},
            ExpiresIn=expires_seconds,
        )

    def _client(self) -> object:
        boto3 = _boto3_module()
        return boto3.client(
            "s3",
            endpoint_url=self.settings.endpoint_url or None,
            aws_access_key_id=self.settings.access_key_id,
            aws_secret_access_key=self.settings.secret_access_key,
            region_name=self.settings.region_name or None,
        )

    def _uri(self, path: str) -> str:
        return f"{self.settings.provider}://{self.settings.bucket_name}/{path}"


def _put_object_args(
    bucket_name: str,
    path: str,
    data: bytes,
    content_type: str | None,
) -> dict[str, object]:
    args: dict[str, object] = {"Bucket": bucket_name, "Key": path, "Body": data}
    if content_type:
        args["ContentType"] = content_type
    return args


def _boto3_module() -> object:
    try:
        import boto3
    except ImportError as exc:
        raise MissingProviderDependencyError(
            "boto3 is required by S3-compatible storage; expected installed module"
        ) from exc
    return boto3
