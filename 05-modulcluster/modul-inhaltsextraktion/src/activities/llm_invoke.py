# src/activities/llm_invoke.py
"""
Temporal activity for invoking Large Language Models (LLMs).

This module provides a centralized, robust LLM invocation using the Instructor library
for reliable structured output. Instructor handles retries automatically and works
directly with Pydantic models.
"""

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, NotRequired, TypedDict

import instructor
from openai.types.chat import ChatCompletionMessageParam
from prompt_injection.prompt_defense import render_prompt_format, wrap_system_prompt
from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from src.config import get_config
from src.models.llm_client import get_openai_client
from src.models.model_manager import LLMConfig

# --- Type Definitions ---


class LlmInvokeInput(TypedDict):
    """Input structure for the llm_invoke function."""

    llm_config: LLMConfig
    prompt_template: str
    input_dict: dict[str, Any]
    agent_name: str
    system_prompt: NotRequired[str]


# --- Temporal Activity Definition ---


def _import_class(fully_qualified_name: str) -> type:
    """Dynamically import a class from its fully qualified name."""
    module_name, class_name = fully_qualified_name.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_name)
    return getattr(module, class_name)


@dataclass
class LlmInvokeStructuredActivityInput:
    """Activity-level input for the structured LLM invocation."""

    llm_config: dict[str, Any]
    prompt_template: str
    input_dict: dict[str, Any]
    agent_name: str
    output_class_name: str
    system_prompt: str = ""


@activity.defn(name="llm_invoke_structured")
async def _llm_invoke_structured(input: LlmInvokeStructuredActivityInput) -> str:
    """
    LLM invocation using Instructor for reliable structured output.

    Instructor provides:
    - Automatic retries on validation failures
    - Clean Pydantic integration
    - Works with any OpenAI-compatible API

    Returns: JSON string of validated Pydantic model
    """

    # Dynamically import the output class
    output_class = _import_class(input.output_class_name)

    # Get OpenAI client from centralized factory
    model_name = input.llm_config.get("model_name", "summarization")
    openai_client, model = await get_openai_client(model_name)

    activity.logger.debug(f"LLM call: {input.agent_name} ({model})")

    try:
        # Patch with Instructor for structured output
        client = instructor.from_openai(openai_client, mode=instructor.Mode.JSON)

        # Sanitize and format the prompt
        formatted_prompt = render_prompt_format(input.prompt_template, **input.input_dict)

        # Build messages list with optional system prompt
        messages: list[ChatCompletionMessageParam] = []
        if input.system_prompt:
            messages.append({"role": "system", "content": wrap_system_prompt(input.system_prompt)})
        messages.append({"role": "user", "content": formatted_prompt})

        # Call with Instructor - returns validated Pydantic model directly
        result = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_model=output_class,
            temperature=get_config().LLM_STRUCTURED_OUTPUT_TEMPERATURE,
            max_retries=0,  # Let Temporal handle retries
        )
    finally:
        await openai_client.close()

    activity.logger.debug(f"LLM done: {input.agent_name}")

    return json.dumps(result.model_dump())


# --- Workflow-Facing Wrapper ---


async def llm_invoke_structured[TOutput: BaseModel](input: LlmInvokeInput, output_class: type[TOutput]) -> TOutput:
    """
    Workflow wrapper for LLM invocation with structured output.

    Uses Instructor for reliable Pydantic model output with automatic
    retries on validation failures.

    Args:
        input: LLM invocation parameters
        output_class: Pydantic model class for output validation

    Returns:
        Validated Pydantic model instance
    """
    # Get fully qualified class name for dynamic import in activity
    output_class_name = f"{output_class.__module__}.{output_class.__qualname__}"

    # Call the Temporal activity
    result_json = await workflow.execute_activity(
        _llm_invoke_structured,
        LlmInvokeStructuredActivityInput(
            llm_config=input["llm_config"],
            prompt_template=input["prompt_template"],
            input_dict=input["input_dict"],
            agent_name=input["agent_name"],
            output_class_name=output_class_name,
            system_prompt=input.get("system_prompt") or "",
        ),
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            maximum_attempts=get_config().TEMPORAL_LLM_ACTIVITY_MAX_ATTEMPTS,
            initial_interval=timedelta(seconds=10),
            backoff_coefficient=2,
            maximum_interval=timedelta(seconds=60),
        ),
    )

    # Parse and validate result
    result_dict = json.loads(result_json)
    result = output_class.model_validate(result_dict)

    return result


# --- Direct Functions for Activities ---


# TODO: Remove this and instead use temporalio.activity.in_activity() and run it conditionally as an activity
async def llm_invoke_structured_direct[TOutput: BaseModel](
    input: LlmInvokeInput, output_class: type[TOutput]
) -> TOutput:
    """
    Direct LLM invocation with structured output for use within activities.

    Uses Instructor for reliable Pydantic model output. Call this when
    invoking LLM from within other activities (not through workflow).

    For workflow code, use llm_invoke_structured() instead.
    """

    # Get OpenAI client from centralized factory
    model_name = input["llm_config"].get("model_name", "summarization")
    openai_client, model = await get_openai_client(model_name)

    activity.logger.debug(f"LLM call: {input['agent_name']} ({model})")

    try:
        # Patch with Instructor for structured output
        client = instructor.from_openai(openai_client, mode=instructor.Mode.JSON)

        # Sanitize and format the prompt
        formatted_prompt = render_prompt_format(input["prompt_template"], **input["input_dict"])

        # Build messages list with optional system prompt
        system_prompt = input.get("system_prompt") or ""
        messages: list[ChatCompletionMessageParam] = []
        if system_prompt:
            messages.append({"role": "system", "content": wrap_system_prompt(system_prompt)})
        messages.append({"role": "user", "content": formatted_prompt})

        # Call with Instructor
        output = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_model=output_class,
            temperature=get_config().LLM_STRUCTURED_OUTPUT_TEMPERATURE,
            max_retries=0,  # Let Temporal handle retries
        )
    finally:
        await openai_client.close()

    activity.logger.debug(f"LLM done: {input['agent_name']}")

    result = output_class.model_validate(output)

    return result
