"""
CRM Router - Contact management, timeline, memories, relationship graph.

Endpoints:
- GET /crm/contacts — List contacts with search/filter
- GET /crm/contacts/{phone} — Contact detail + timeline
- GET /crm/contacts/{phone}/timeline — All interactions chronologically
- GET /crm/contacts/{phone}/memories — LanceDB memories
- GET /crm/contacts/{phone}/graph — Relationship graph data
- POST /crm/contacts — Create contact
- PUT /crm/contacts/{phone} — Update contact
- POST /crm/contacts/import — Import from Z-API
"""

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

_agent_path = str(Path(__file__).parent.parent.parent.parent / "shadow" / "agent")
if _agent_path not in sys.path:
    sys.path.insert(0, _agent_path)

router = APIRouter(prefix="/crm", tags=["crm"])


def _get_storage():
    from storage import Storage
    return Storage()


@router.get("/contacts")
def list_contacts(
    search: str | None = None,
    tag: str | None = None,
    limit: int = Query(50, le=500),
) -> dict[str, Any]:
    """List contacts with optional search and tag filter."""
    storage = _get_storage()
    contacts = storage.list_contacts(limit=limit)

    results = []
    for c in contacts:
        entry = {
            "phone": c.phone if hasattr(c, "phone") else str(c),
            "name": getattr(c, "name", ""),
            "aliases": getattr(c, "aliases", []),
            "relationship_type": getattr(c, "relationship_type", ""),
            "updated_at": getattr(c, "updated_at", ""),
        }
        # Apply search filter
        if search:
            search_lower = search.lower()
            name = (entry.get("name") or "").lower()
            phone = (entry.get("phone") or "").lower()
            if search_lower not in name and search_lower not in phone:
                continue
        results.append(entry)

    return {"contacts": results, "total": len(results)}


@router.get("/contacts/{phone}")
def get_contact(phone: str) -> dict[str, Any]:
    """Get contact detail."""
    storage = _get_storage()
    contact = storage.get_contact(phone)
    if not contact:
        return {"error": "Contact not found", "phone": phone}

    return {
        "phone": getattr(contact, "phone", phone),
        "name": getattr(contact, "name", ""),
        "aliases": getattr(contact, "aliases", []),
        "relationship_type": getattr(contact, "relationship_type", ""),
        "notes": getattr(contact, "notes", ""),
        "created_at": getattr(contact, "created_at", ""),
        "updated_at": getattr(contact, "updated_at", ""),
    }


@router.get("/contacts/{phone}/timeline")
def get_contact_timeline(phone: str, limit: int = 50) -> dict[str, Any]:
    """Get chronological timeline of all interactions with a contact."""
    storage = _get_storage()
    timeline = []

    # Tasks linked to this contact
    try:
        tasks = storage.list_tasks(limit=limit)
        for t in tasks:
            if phone in (getattr(t, "title", "") + getattr(t, "description", "")):
                timeline.append({
                    "type": "task",
                    "title": t.title,
                    "status": t.status,
                    "date": getattr(t, "due_at", "") or getattr(t, "created_at", ""),
                })
    except Exception:
        pass

    # Appointments
    try:
        appointments = storage.list_appointments(limit=limit)
        for a in appointments:
            if phone in (getattr(a, "title", "") + getattr(a, "description", "")):
                timeline.append({
                    "type": "appointment",
                    "title": a.title,
                    "date": a.scheduled_at,
                })
    except Exception:
        pass

    # Sort by date (most recent first)
    timeline.sort(key=lambda x: x.get("date", ""), reverse=True)

    return {"phone": phone, "timeline": timeline[:limit]}


@router.get("/contacts/{phone}/memories")
def get_contact_memories(phone: str, limit: int = 20) -> dict[str, Any]:
    """Get LanceDB memories for a contact."""
    try:
        from contact_memory import ContactMemory
        memory = ContactMemory()
        mems = memory.recall(query="", owner_id="", contact_phone=phone, top_k=limit)
        return {"phone": phone, "memories": mems}
    except Exception as e:
        return {"phone": phone, "memories": [], "error": str(e)[:200]}


@router.get("/contacts/{phone}/graph")
def get_contact_graph(phone: str) -> dict[str, Any]:
    """Get relationship graph data for React Flow visualization."""
    storage = _get_storage()

    nodes = []
    edges = []

    # Central node: the contact
    contact = storage.get_contact(phone)
    contact_name = getattr(contact, "name", phone) if contact else phone
    nodes.append({
        "id": phone,
        "label": contact_name,
        "type": "contact",
    })

    # Connected contacts (from tasks, appointments)
    try:
        contacts = storage.list_contacts(limit=20)
        for c in contacts:
            c_phone = getattr(c, "phone", "")
            if c_phone and c_phone != phone:
                nodes.append({
                    "id": c_phone,
                    "label": getattr(c, "name", c_phone),
                    "type": "contact",
                })
    except Exception:
        pass

    return {"nodes": nodes, "edges": edges}


@router.post("/contacts/import")
def import_contacts_from_zapi() -> dict[str, Any]:
    """Trigger Z-API contact import (async background task)."""
    # TODO: Trigger Collector agent to import contacts
    return {"status": "queued", "message": "Contact import will run in background"}
