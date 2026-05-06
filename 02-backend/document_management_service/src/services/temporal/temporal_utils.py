from src.models.schemas.approval_schema import FileDiffResponse
from src.utils.exceptions import WorkflowValidateDiffError


async def validate_user_diff(
    current_diff: FileDiffResponse, user_diff: FileDiffResponse
):
    """Validates user diff."""

    def build_state_map(result: FileDiffResponse) -> dict[str, str]:
        state: dict[str, str] = {}

        def add(identifier: str, category: str):
            if identifier in state:
                raise WorkflowValidateDiffError(
                    f"File {identifier} appears multiple times in diff"
                )
            state[identifier] = category

        for f in result.new:
            add(f.sha, "new")

        for f in result.deleted:
            add(str(f.file_id), "deleted")

        for f in result.changed:
            add(str(f.file_id), "changed")

        for f in result.renamed:
            add(str(f.file_id), "renamed")

        for f in result.unchanged:
            add(str(f.file_id), "unchanged")

        return state

    current_map = build_state_map(current_diff)
    new_map = build_state_map(user_diff)

    # Rule 1: ensure no files were added or removed
    if not set(new_map.keys()).issubset(current_map.keys()):
        raise WorkflowValidateDiffError("Files cannot be added to the diff")

    # Rule 2: enforce allowed transitions
    allowed_moves = {
        ("deleted", "unchanged"),
        ("renamed", "unchanged"),
        ("renamed", "changed"),
        ("renamed", "new"),
    }

    for file_id, new_state in new_map.items():
        old_state = current_map[file_id]

        if old_state == new_state:
            continue

        if (old_state, new_state) not in allowed_moves:
            raise WorkflowValidateDiffError(
                f"Illegal diff modification: {file_id} moved from {old_state} "
                f"to {new_state}"
            )
