import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import CURRENT_PROJECT_DIR, FILES_INDEX_PATH, MAX_UPLOAD_SIZE, METADATA_PATH, UPLOAD_DIR
from .metadata import build_metadata
from .scanner import scan_project
from .utils import ensure_workspace, is_relative_to, reset_directory, write_json


async def save_upload(file: UploadFile) -> Path:
    ensure_workspace()
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file.")

    destination = UPLOAD_DIR / "uploaded.zip"
    size = 0
    with destination.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE:
                raise HTTPException(status_code=413, detail="ZIP file is larger than 50 MB.")
            handle.write(chunk)
    return destination


def extract_zip(zip_path: Path) -> str:
    reset_directory(CURRENT_PROJECT_DIR)
    project_name = zip_path.stem

    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = [name for name in archive.namelist() if name and not name.endswith("/")]
            if not names:
                raise HTTPException(status_code=400, detail="The ZIP file is empty.")

            common_root = names[0].split("/", 1)[0] if "/" in names[0] else ""
            if common_root and all(name.startswith(common_root + "/") for name in names):
                project_name = common_root

            for member in archive.infolist():
                if member.is_dir():
                    continue
                target = CURRENT_PROJECT_DIR / member.filename
                if not is_relative_to(target, CURRENT_PROJECT_DIR):
                    raise HTTPException(status_code=400, detail="ZIP contains an unsafe file path.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as dest:
                    dest.write(source.read())
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid ZIP archive.") from exc

    return project_name


async def ingest_upload(file: UploadFile) -> dict:
    zip_path = await save_upload(file)
    project_name = extract_zip(zip_path)
    entries = scan_project(CURRENT_PROJECT_DIR)
    metadata = build_metadata(entries, project_name)

    write_json(FILES_INDEX_PATH, entries)
    write_json(METADATA_PATH, metadata)

    return {
        "message": f"Indexed {len(entries)} files from {project_name}.",
        "files_indexed": len(entries),
        "project_name": project_name,
    }
