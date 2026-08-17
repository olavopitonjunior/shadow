"""
Documents Router - Generated documents and template management.

Endpoints:
- GET /documents — List generated documents
- GET /documents/{id} — Document detail + preview
- GET /documents/{id}/download — Download PDF
- POST /documents/{id}/resend — Resend via WhatsApp
- GET /templates — List Jinja2 templates
- POST /templates — Upload new template
"""

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

_agent_path = str(Path(__file__).parent.parent.parent.parent / "shadow" / "agent")
if _agent_path not in sys.path:
    sys.path.insert(0, _agent_path)

router = APIRouter(prefix="/documents", tags=["documents"])

DOCS_DIR = Path(_agent_path) / "data" / "documents"
TEMPLATES_DIR = Path(_agent_path) / "templates"


@router.get("")
def list_documents(doc_type: str | None = None, limit: int = 50) -> dict[str, Any]:
    """List generated documents."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    documents = []
    for f in sorted(DOCS_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        stat = f.stat()
        documents.append({
            "id": f.stem,
            "filename": f.name,
            "size_bytes": stat.st_size,
            "created_at": stat.st_mtime,
            "type": "pdf",
        })

    # Also check for HTML docs
    for f in sorted(DOCS_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        stat = f.stat()
        documents.append({
            "id": f.stem,
            "filename": f.name,
            "size_bytes": stat.st_size,
            "created_at": stat.st_mtime,
            "type": "html",
        })

    return {"documents": documents[:limit], "total": len(documents)}


@router.get("/{doc_id}")
def get_document(doc_id: str) -> dict[str, Any]:
    """Get document detail and preview content."""
    pdf_path = DOCS_DIR / f"{doc_id}.pdf"
    html_path = DOCS_DIR / f"{doc_id}.html"

    if pdf_path.exists():
        return {
            "id": doc_id,
            "filename": pdf_path.name,
            "type": "pdf",
            "size_bytes": pdf_path.stat().st_size,
            "preview_url": f"/documents/{doc_id}/download",
        }

    if html_path.exists():
        content = html_path.read_text(encoding="utf-8")
        return {
            "id": doc_id,
            "filename": html_path.name,
            "type": "html",
            "size_bytes": html_path.stat().st_size,
            "content": content[:5000],
        }

    return {"error": "Document not found", "id": doc_id}


@router.get("/{doc_id}/download")
def download_document(doc_id: str):
    """Download document file."""
    pdf_path = DOCS_DIR / f"{doc_id}.pdf"
    if pdf_path.exists():
        return FileResponse(str(pdf_path), media_type="application/pdf", filename=pdf_path.name)

    html_path = DOCS_DIR / f"{doc_id}.html"
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html", filename=html_path.name)

    return {"error": "Document not found"}


@router.get("/templates/list")
def list_templates() -> dict[str, Any]:
    """List available Jinja2 templates."""
    templates = []

    for category_dir in TEMPLATES_DIR.iterdir():
        if category_dir.is_dir():
            for f in category_dir.glob("*.j2"):
                templates.append({
                    "name": f.stem,
                    "category": category_dir.name,
                    "path": str(f.relative_to(TEMPLATES_DIR)),
                    "size_bytes": f.stat().st_size,
                })

    return {"templates": templates, "total": len(templates)}


@router.get("/templates/{category}/{name}")
def get_template(category: str, name: str) -> dict[str, Any]:
    """Get template content for preview."""
    template_path = TEMPLATES_DIR / category / f"{name}.html.j2"
    if not template_path.exists():
        template_path = TEMPLATES_DIR / category / f"{name}.j2"

    if not template_path.exists():
        return {"error": "Template not found"}

    content = template_path.read_text(encoding="utf-8")

    # Extract variable names from template
    import re
    variables = list(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", content)))

    return {
        "name": name,
        "category": category,
        "content": content,
        "variables": variables,
    }
