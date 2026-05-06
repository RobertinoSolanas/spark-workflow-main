import asyncio
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict
from uuid import UUID

from temporalio import activity

from src.models.db.database import AsyncSessionLocal
from src.models.db.db_models import File
from src.models.db.file_enum import FileTypeEnum
from src.services.files.file_service import FileService
from src.services.storage_provider.storage_provider_base_service import (
    BaseStorageProviderService,
)
from src.services.workflows.activities.activity_models import (
    ComputeShaDiffInput,
    DeleteChange,
    FileChange,
    FileDiffResult,
    NewFile,
    RenameChange,
    SingleFileResult,
    Unchanged,
)
from src.utils.service_utils import (
    create_file_service,
)


class FileEntry(TypedDict):
    bucket_path: str
    file_id: str
    sha256: str


async def get_sha256(
    storage_provider_service: BaseStorageProviderService,
    filepath: str,
    chunk_size: int = 8192 * 4,
) -> str:
    """Retrieve or compute the SHA-256 hash of a single file."""
    meta = await storage_provider_service.get_metadata(
        document_name=filepath,
        keys=["sha256"],
    )
    sha256 = meta.get("sha256")
    if sha256 is None:
        file_stream = await storage_provider_service.download_document_stream(
            document_name=filepath,
            chunk_size=chunk_size,
        )
        sha256 = await storage_provider_service.compute_sha256(
            source=file_stream,
            chunk_size=chunk_size,
        )
    return sha256


async def gather_sha256(
    storage_provider_service: BaseStorageProviderService,
    filepaths: list[str],
    chunk_size: int = 8192 * 4,
) -> list[str]:
    """Fetch or compute SHA-256 hashes for multiple files in parallel."""
    results = await asyncio.gather(
        *[
            get_sha256(
                storage_provider_service=storage_provider_service,
                filepath=f,
                chunk_size=chunk_size,
            )
            for f in filepaths
        ],
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception):
            raise result
    return results  # type: ignore


async def get_renamed(
    source_map: dict[str, str],
    target_map: dict[str, str],
    rename_similarity_threshold: float = 0.65,
    rename_same_dir_only: bool = True,
) -> list[RenameChange]:
    """Identify potential renamed files by matching SHA with filename similarity."""
    sha_to_source = defaultdict(list)
    sha_to_target = defaultdict(list)

    for name, sha in source_map.items():
        sha_to_source[sha].append(name)
    for name, sha in target_map.items():
        sha_to_target[sha].append(name)

    seen = set()

    def filename_similarity(a: str, b: str) -> float:
        from difflib import SequenceMatcher

        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    renamed: list[RenameChange] = []
    for sha, sources in sha_to_source.items():
        targets = sha_to_target.get(sha, [])
        for s in sources:
            for t in targets:
                if s == t:
                    continue
                pair = tuple(sorted([s, t]))
                if pair in seen:
                    continue

                if rename_same_dir_only:
                    if Path(s).parent != Path(t).parent:
                        continue

                if filename_similarity(s, t) < rename_similarity_threshold:
                    continue

                seen.add(pair)
                renamed.append(
                    RenameChange(
                        file_id="",
                        old_name=t,
                        new_name=s,
                        sha=sha,
                    )
                )
    return renamed


def _build_target_info(db_files: Sequence[File]) -> dict[str, FileEntry]:
    """Helper method to build target info."""
    info: dict[str, FileEntry] = {}
    for f in db_files:
        name = f.filename
        if name in info:
            continue
        info[name] = {
            "bucket_path": f.bucket_path,
            "file_id": str(f.id),
            "sha256": "",
        }
    return info


def _build_source_info(extracted: list[SingleFileResult]) -> dict[str, FileEntry]:
    """Helper method to build source info."""
    info: dict[str, FileEntry] = {}
    for f in extracted:
        name = f.filename
        if name in info:
            continue
        if f.bucket_path is None:
            raise ValueError(f"File {name} has no bucket path")

        info[name] = {
            "bucket_path": f.bucket_path,
            "file_id": "",
            "sha256": "",
        }
    return info


@activity.defn
async def create_sha256_diff(
    activity_input: ComputeShaDiffInput,
) -> FileDiffResult:
    """
    Create a file diff between unzipped source files (staging) and existing project
    files.
    """
    async with AsyncSessionLocal() as db:
        service: FileService = await create_file_service(db=db)
        target_files = await service.list_files(
            project_id=UUID(activity_input.project_id),
            file_type=FileTypeEnum.DOCUMENT,
            page_size=None,
        )
        storage_provider_service: BaseStorageProviderService = (
            service.storage_provider_service
        )

    target_info = _build_target_info(target_files)
    source_info = _build_source_info(activity_input.files)

    target_paths = [info["bucket_path"] for info in target_info.values()]
    source_paths = [info["bucket_path"] for info in source_info.values()]

    target_shas, source_shas = await asyncio.gather(
        gather_sha256(storage_provider_service, target_paths),
        gather_sha256(storage_provider_service, source_paths),
    )

    for info, sha in zip(target_info.values(), target_shas, strict=True):
        info["sha256"] = sha
    for info, sha in zip(source_info.values(), source_shas, strict=True):
        info["sha256"] = sha

    source_map = {name: info["sha256"] for name, info in source_info.items()}
    target_map = {name: info["sha256"] for name, info in target_info.items()}

    source_names = set(source_info.keys())
    target_names = set(target_info.keys())

    diff = FileDiffResult()

    renamed_raw = await get_renamed(
        source_map=source_map,
        target_map=target_map,
        rename_similarity_threshold=activity_input.rename_similarity_threshold,
        rename_same_dir_only=activity_input.rename_same_dir_only,
    )

    # Track names already explained by renames
    renamed_source_names = {r.new_name for r in renamed_raw}
    renamed_target_names = {r.old_name for r in renamed_raw}

    # Enrich renames with file_id (from old name)
    diff.renamed = []
    for r in renamed_raw:
        old_info = target_info.get(r.old_name)
        if old_info and old_info["file_id"]:
            diff.renamed.append(
                RenameChange(
                    file_id=old_info["file_id"],
                    old_name=r.old_name,
                    new_name=r.new_name,
                    sha=r.sha,
                )
            )
    diff.renamed.sort(key=lambda r: r.old_name)

    diff.new = [
        NewFile(
            bucket_path=source_info[name]["bucket_path"],
            filename=name,
            sha=source_info[name]["sha256"],
        )
        for name in sorted(source_names - target_names - renamed_source_names)
    ]

    # Deleted = target names not in source AND not explained by rename
    diff.deleted = [
        DeleteChange(
            file_id=target_info[name]["file_id"],
            filename=name,
            sha=target_info[name]["sha256"],
        )
        for name in sorted(target_names - source_names - renamed_target_names)
    ]

    # Unchanged / Changed = same filename AND not renamed
    common_names = (
        (source_names & target_names) - renamed_source_names - renamed_target_names
    )

    for name in sorted(common_names):
        s_sha = source_map[name]
        t_sha = target_map[name]
        bucket_path = source_info[name]["bucket_path"]
        file_id = target_info[name]["file_id"]

        if s_sha == t_sha:
            diff.unchanged.append(Unchanged(file_id=file_id, filename=name, sha=s_sha))
        else:
            diff.changed.append(
                FileChange(
                    file_id=file_id,
                    filename=name,
                    bucket_path=bucket_path,
                    source_sha=s_sha,
                    target_sha=t_sha,
                )
            )

    return diff
