import os
from typing import Awaitable, Callable, Iterable, List

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, status
from google.protobuf import json_format
from temporal.payload_codec import LargePayloadCodec
from temporal.s3_payload_storage import S3PayloadStorage
from temporalio.api.common.v1 import Payload, Payloads

from env import ENV

app = FastAPI(title="Temporal Payload Codec Service")

_storage = S3PayloadStorage(
    bucket_name=ENV.TEMPORAL_S3_BUCKET_NAME,
    endpoint_url=ENV.TEMPORAL_S3_ENDPOINT_URL,
    access_key=ENV.TEMPORAL_S3_ACCESS_KEY_ID,
    secret_key=ENV.TEMPORAL_S3_SECRET_ACCESS_KEY,
    region=ENV.TEMPORAL_S3_REGION,
)
_codec = LargePayloadCodec(_storage)


def _cors_headers(request: Request) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
        "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Headers": "content-type,x-namespace",
    }


async def _apply_codec(
    fn: Callable[[Iterable[Payload]], Awaitable[List[Payload]]],
    request: Request,
) -> Response:
    if request.method == "OPTIONS":
        return Response(
            status_code=status.HTTP_204_NO_CONTENT,
            headers=_cors_headers(request),
        )

    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Content-Type must be application/json",
        )

    try:
        payloads = json_format.Parse(await request.body(), Payloads())
    except Exception as exc:  # pragma: no cover - safety for malformed JSON
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payloads JSON",
        ) from exc

    encoded_payloads = Payloads(payloads=await fn(payloads.payloads))
    return Response(
        content=json_format.MessageToJson(encoded_payloads),
        media_type="application/json",
        headers=_cors_headers(request),
    )


@app.api_route("/encode", methods=["POST", "OPTIONS"], tags=["Temporal-Codec"])
async def encode_payloads(request: Request) -> Response:
    # pyrefly:ignore
    return await _apply_codec(_codec.encode, request)


@app.api_route("/decode", methods=["POST", "OPTIONS"], tags=["Temporal-Codec"])
async def decode_payloads(request: Request) -> Response:
    return await _apply_codec(_codec.decode, request)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )
