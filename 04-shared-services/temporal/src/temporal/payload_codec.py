from collections.abc import Iterable, Sequence

from temporalio.api.common.v1 import Payload
from temporalio.converter import PayloadCodec

from .s3_payload_storage import S3PayloadStorage

MAX_PAYLOAD_SIZE = 1024 * 100  # 100 KB


class LargePayloadCodec(PayloadCodec):
    def __init__(self, storage: S3PayloadStorage):
        self.storage = storage

    async def encode(self, payloads: Sequence[Payload]) -> list[Payload]:
        encoded_payloads = []
        for p in payloads:
            payload_bytes = p.SerializeToString()
            if p.ByteSize() > MAX_PAYLOAD_SIZE:
                key = await self.storage.put(payload_bytes)
                encoded_payloads.append(
                    Payload(
                        metadata={
                            "encoding": b"binary/s3-reference",
                            "s3-key": key.encode("utf-8"),
                        },
                        data=b"",
                    )
                )
            else:
                encoded_payloads.append(p)

        return encoded_payloads

    async def decode(self, payloads: Iterable[Payload]) -> list[Payload]:
        decoded_payloads = []
        for p in payloads:
            if p.metadata.get("encoding", b"").decode() != "binary/s3-reference":
                decoded_payloads.append(p)
                continue

            key = p.metadata.get("s3-key").decode("utf-8")

            payload_data = await self.storage.get(key)
            decoded_payloads.append(Payload.FromString(payload_data))

        return decoded_payloads
