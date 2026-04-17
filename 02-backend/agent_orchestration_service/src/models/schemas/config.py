from pydantic import ConfigDict
from pydantic.alias_generators import to_camel


class CamelConfig:
    """Shared config for camelCase aliases and ORM mode."""

    model_config = ConfigDict(
        alias_generator=to_camel, from_attributes=True, populate_by_name=True
    )
