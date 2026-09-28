import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "media_upload", Path(__file__).resolve().parents[1] / "media_upload.py",
)
uploads = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uploads)


class Field:
    def __init__(self, name, value, filename=None):
        self.name, self.value, self.filename = name, value, filename
        self.chunks = iter(value) if filename else None

    async def text(self):
        return self.value

    async def read_chunk(self, size):
        value = next(self.chunks, b"")
        if isinstance(value, Exception):
            raise value
        return value


async def reader(chunks, checksum=None):
    yield Field("file", chunks, "media.mp4")
    yield Field("asset_id", "asset-1")
    if checksum:
        yield Field("sha256", checksum)


class UploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_and_keeps_existing_inputs_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = await uploads.store_upload(reader([b"one", b"two"]), root, lambda name, _: name)
            second = await uploads.store_upload(reader([b"changed"]), root, lambda name, _: name)
            self.assertNotEqual(first["relativePath"], second["relativePath"])
            self.assertEqual((root / first["relativePath"]).read_bytes(), b"onetwo")
            self.assertEqual(first["sha256"], hashlib.sha256(b"onetwo").hexdigest())
            self.assertEqual(first["size"], 6)
            self.assertEqual(list((root / "shotmill/.incoming").iterdir()), [])

    async def test_disconnect_and_checksum_mismatch_leave_no_partial_file(self):
        for chunks, checksum, error in (([b"partial", OSError("disconnected")], None, OSError),
                                       ([b"content"], "0" * 64, ValueError)):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.assertRaises(error):
                    await uploads.store_upload(reader(chunks, checksum), root, lambda name, _: name)
                self.assertFalse(any(path.is_file() for path in root.rglob("*")))

    async def test_corrupt_existing_blob_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = await uploads.store_upload(reader([b"original"]), root, lambda name, _: name)
            target = root / item["relativePath"]
            target.write_bytes(b"damaged")
            with self.assertRaisesRegex(ValueError, "damaged"):
                await uploads.store_upload(reader([b"original"]), root, lambda name, _: name)
            self.assertEqual(target.read_bytes(), b"damaged")


if __name__ == "__main__":
    unittest.main()
