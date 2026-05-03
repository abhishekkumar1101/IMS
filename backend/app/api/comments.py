"""Threaded comments per incident (collab feature)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Request

from app.models.schemas import CommentIn, CommentOut

router = APIRouter(prefix="/incidents", tags=["comments"])


@router.get("/{incident_id}/comments", response_model=list[CommentOut])
async def list_comments(incident_id: UUID, request: Request) -> list[CommentOut]:
    docs = await request.app.state.mongo.list_comments(incident_id)
    return [
        CommentOut(
            id=str(d["_id"]),
            incident_id=incident_id,
            author=d["author"],
            body=d["body"],
            parent_id=d.get("parent_id"),
            created_at=d["created_at"],
        )
        for d in docs
    ]


@router.post("/{incident_id}/comments", response_model=CommentOut)
async def add_comment(incident_id: UUID, body: CommentIn, request: Request) -> CommentOut:
    doc = {
        "_id": str(uuid4()),
        "incident_id": str(incident_id),
        "author": body.author,
        "body": body.body,
        "parent_id": body.parent_id,
        "created_at": datetime.now(timezone.utc),
    }
    inserted_id = await request.app.state.mongo.insert_comment(doc)
    out = CommentOut(
        id=str(inserted_id),
        incident_id=incident_id,
        author=body.author,
        body=body.body,
        parent_id=body.parent_id,
        created_at=doc["created_at"],
    )
    await request.app.state.incident_hub.broadcast(
        str(incident_id), {"type": "comment_added", "comment": out.model_dump(mode="json")}
    )
    return out
