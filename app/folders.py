import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import Folder, Material, User
from app.schemas import FolderCreate, FolderResponse

logger = logging.getLogger("case-ims.folders")

router = APIRouter(prefix="/folders", tags=["Folders"])


def _folder_response(f: Folder, db: Session) -> dict:
    mat_count = db.query(Material).filter(Material.folder_id == f.id).count()
    children = db.query(Folder).filter(Folder.parent_folder_id == f.id).all()
    return {
        "id": f.id, "case_id": f.case_id, "name": f.name,
        "path": f.path, "source_type": f.source_type,
        "parent_folder_id": f.parent_folder_id,
        "is_watched": f.is_watched, "material_count": mat_count,
        "child_count": len(children),
        "created_at": f.created_at,
    }


def _build_tree(folders: list, db: Session) -> list:
    """Build nested folder tree from flat list."""
    by_id = {f.id: {**_folder_response(f, db), "children": []} for f in folders}
    roots = []
    for f in folders:
        node = by_id[f.id]
        if f.parent_folder_id and f.parent_folder_id in by_id:
            by_id[f.parent_folder_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.get("/")
def list_folders(
    case_id: Optional[int] = None,
    parent_id: Optional[int] = None,
    tree: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Folder)
    if case_id is not None:
        query = query.filter(Folder.case_id == case_id)
    if parent_id is not None:
        query = query.filter(Folder.parent_folder_id == parent_id)
    elif not tree:
        # By default show root-level folders only
        query = query.filter(Folder.parent_folder_id.is_(None))

    folders = query.order_by(Folder.name).all()

    if tree and case_id is not None:
        # Return full tree for case
        all_folders = db.query(Folder).filter(Folder.case_id == case_id).order_by(Folder.name).all()
        return {"folders": _build_tree(all_folders, db)}

    return {"folders": [_folder_response(f, db) for f in folders]}


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_folder(
    data: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check parent exists if specified
    if data.parent_folder_id:
        parent = db.query(Folder).filter(Folder.id == data.parent_folder_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        if parent.case_id != data.case_id:
            raise HTTPException(status_code=400, detail="Parent folder must be in the same case")

    folder = Folder(
        case_id=data.case_id, name=data.name, path=data.path,
        gdrive_id=data.gdrive_id, source_type=data.source_type,
        parent_folder_id=data.parent_folder_id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return _folder_response(folder, db)


@router.get("/{folder_id}")
def get_folder(folder_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    resp = _folder_response(folder, db)

    # Include children
    children = db.query(Folder).filter(Folder.parent_folder_id == folder_id).order_by(Folder.name).all()
    resp["children"] = [_folder_response(c, db) for c in children]

    # Include materials
    materials = db.query(Material).filter(Material.folder_id == folder_id).order_by(Material.upload_date.desc()).all()
    resp["materials"] = [
        {
            "id": m.id, "filename": m.filename, "file_type": m.file_type,
            "file_size": m.file_size, "upload_date": m.upload_date,
            "extraction_status": m.extraction_status,
        }
        for m in materials
    ]

    return resp


@router.put("/{folder_id}")
def update_folder(
    folder_id: int,
    name: Optional[str] = None,
    parent_folder_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if name is not None:
        folder.name = name
    if parent_folder_id is not None:
        if parent_folder_id == folder_id:
            raise HTTPException(status_code=400, detail="Cannot set folder as its own parent")
        folder.parent_folder_id = parent_folder_id if parent_folder_id > 0 else None
    db.commit()
    db.refresh(folder)
    return _folder_response(folder, db)


@router.delete("/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Materials in this folder will have folder_id set to NULL (ondelete=SET NULL)
    db.delete(folder)
    db.commit()
    return {"detail": "Folder deleted"}
