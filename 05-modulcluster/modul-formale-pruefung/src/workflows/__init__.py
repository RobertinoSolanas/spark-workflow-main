from src.workflows.inhaltsverzeichnis_finder import (
    InhaltsverzeichnisFinderWorkflow,
)
from src.workflows.inhaltsverzeichnis_matching import (
    InhaltsverzeichnisMatchingWorkflow,
)
from src.workflows.llm_matching import LLMMatchingWorkflow

workflows = [
    LLMMatchingWorkflow,
    InhaltsverzeichnisFinderWorkflow,
    InhaltsverzeichnisMatchingWorkflow,
]
