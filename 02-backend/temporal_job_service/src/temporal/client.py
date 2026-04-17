from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from src.config.settings import settings

_temporal_client: Client | None = None


async def get_temporal_client() -> Client:
    global _temporal_client

    if _temporal_client is None:
        _temporal_client = await Client.connect(
            target_host=settings.TEMPORAL_ADDRESS,
            namespace=settings.TEMPORAL_NAMESPACE,
            data_converter=pydantic_data_converter,
        )
    return _temporal_client
