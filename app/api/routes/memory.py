"""REST API routes for persistent user memory management."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.services.memory import MemoryService

router = APIRouter(prefix="/memory", tags=["Memory"])


class MemoryCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=2000)
    category: str = Field(default="preference", max_length=50)


@router.get("")
def list_user_memories(category: str | None = None, db: Session = Depends(get_db)):
    """Retrieve all stored user preferences and memory entries."""
    service = MemoryService(db)
    return {"memories": service.list_memories(category=category)}


@router.post("")
def set_user_memory(req: MemoryCreateRequest, db: Session = Depends(get_db)):
    """Create or update a persistent user memory item."""
    service = MemoryService(db)
    try:
        record = service.set_memory(key=req.key, value=req.value, category=req.category)
        return {"success": True, "memory": record}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{memory_id}")
def delete_user_memory(memory_id: int, db: Session = Depends(get_db)):
    """Delete a persistent user memory item by ID."""
    service = MemoryService(db)
    deleted = service.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory item not found.")
    return {"deleted": True, "memory_id": memory_id}
