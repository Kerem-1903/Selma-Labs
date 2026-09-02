from google.cloud import storage
import typing
import asyncio
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.storage_reference import StorageReference

class GCSStorageAdapter(StoragePort):
    def __init__(self, bucket_name: str, credentials_path: str = None):
        if credentials_path:
            self.client = storage.Client.from_service_account_json(credentials_path)
        else:
            self.client = storage.Client()

        self.bucket = self.client.bucket(bucket_name)

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        """Persist data via the async interface by bridging to threaded sync."""
        def _save_sync():
            blob = self.bucket.blob(key)
            blob.upload_from_string(data, content_type=content_type)
            return len(data)

        size = await asyncio.to_thread(_save_sync)
        return StorageReference(key=key, path=f"gs://{self.bucket.name}/{key}", size_bytes=size)

    async def load(self, key: str) -> bytes:
        blob = self.bucket.blob(key)
        return await asyncio.to_thread(blob.download_as_bytes)

    async def exists(self, key: str) -> bool:
        blob = self.bucket.blob(key)
        return await asyncio.to_thread(blob.exists)

    def upload_file(self, file_stream: typing.BinaryIO, destination_path: str, content_type: str = "video/mp4") -> str:
        blob = self.bucket.blob(destination_path)
        # For large files, chunk_size tuning is memory friendly
        blob.chunk_size = 5 * 1024 * 1024 # 5 MB chunks
        blob.upload_from_file(file_stream, content_type=content_type)
        return f"gs://{self.bucket.name}/{destination_path}"

    def download_file(self, source_path: str, local_destination: str) -> bool:
        # source_path might be a GS URI, let's normalize it to just the key if needed
        key = source_path
        if key.startswith(f"gs://{self.bucket.name}/"):
            key = key[len(f"gs://{self.bucket.name}/"):]

        blob = self.bucket.blob(key)
        blob.download_to_filename(local_destination)
        return True

    def delete_file(self, file_path: str) -> bool:
        key = file_path
        if key.startswith(f"gs://{self.bucket.name}/"):
            key = key[len(f"gs://{self.bucket.name}/"):]

        blob = self.bucket.blob(key)
        blob.delete()
        return True
