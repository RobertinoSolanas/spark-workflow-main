from src.services.activities.results import (
    _send_fvp_results,
    _send_plausibility_results,
    _send_toc_matching_results,
)
from src.services.workflows.fvp import (
    FVPWorkflow,
    get_project_files,
    get_template_document_types,
)
from src.services.workflows.fvp_workflow import IsolatedFVPWorkflow

workflows = [
    IsolatedFVPWorkflow,
    FVPWorkflow,
]
activities = [
    _send_fvp_results,
    _send_plausibility_results,
    get_project_files,
    get_template_document_types,
    _send_toc_matching_results,
]
