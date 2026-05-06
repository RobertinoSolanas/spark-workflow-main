from collections.abc import Callable

from src.services.workflows.activities.compute_sha_diff import create_sha256_diff
from src.services.workflows.activities.delete_file import delete_file
from src.services.workflows.activities.extract_zip import extract_zip
from src.services.workflows.activities.ingest_file import ingest_file
from src.services.workflows.activities.rename_file import rename_file
from src.services.workflows.activities.update_workflow_status import update_file_status
from src.services.workflows.activities.validate_zip import validate_zip

activities: list[Callable] = [
    create_sha256_diff,
    extract_zip,
    ingest_file,
    delete_file,
    rename_file,
    update_file_status,
    validate_zip,
]
