"""
DocGen-specific tools for document generation.

Provides generate_document and list_templates as LangChain StructuredTools.
Uses fpdf2 for PDF generation and Jinja2 SandboxedEnvironment for template safety.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool


# Template directory
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
DOCUMENTS_DIR = Path(__file__).parent.parent.parent / "data" / "documents"


def _ensure_dirs():
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def _list_templates() -> str:
    """List available document templates."""
    templates = []
    if TEMPLATES_DIR.exists():
        for category_dir in TEMPLATES_DIR.iterdir():
            if category_dir.is_dir():
                for tmpl in category_dir.glob("*.j2"):
                    templates.append({
                        "category": category_dir.name,
                        "name": tmpl.stem.replace(".html", ""),
                        "path": str(tmpl.relative_to(TEMPLATES_DIR)),
                    })

    if not templates:
        return "Nenhum template encontrado."

    lines = ["Templates disponíveis:"]
    for t in templates:
        lines.append(f"- [{t['category']}] {t['name']}")
    return "\n".join(lines)


def _generate_document(
    template_name: str = "default",
    template_category: str = "proposals",
    **variables: Any,
) -> str:
    """Generate a PDF document from a Jinja2 template.

    Args:
        template_name: Name of the template (e.g., "default")
        template_category: Category folder (e.g., "proposals", "reports", "contracts")
        **variables: Template variables to fill in

    Returns:
        Path to the generated PDF file
    """
    _ensure_dirs()

    # Find template
    template_path = TEMPLATES_DIR / template_category / f"{template_name}.html.j2"
    if not template_path.exists():
        # Try without .html extension
        template_path = TEMPLATES_DIR / template_category / f"{template_name}.j2"
    if not template_path.exists():
        return f"Template não encontrado: {template_category}/{template_name}"

    # Render template with Jinja2 SandboxedEnvironment
    try:
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment(autoescape=True)
        template_content = template_path.read_text(encoding="utf-8")
        template = env.from_string(template_content)

        # Add default variables
        variables.setdefault("date", datetime.now().strftime("%d/%m/%Y"))

        rendered_html = template.render(**variables)
    except Exception as e:
        return f"Erro ao renderizar template: {e}"

    # Generate PDF with fpdf2
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Strip HTML tags for plain text PDF
        import re
        # Extract sections from HTML
        text = rendered_html

        # Handle headings
        text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n\n=== \1 ===\n", text, flags=re.DOTALL)
        text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n\n--- \1 ---\n", text, flags=re.DOTALL)
        text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n\1\n", text, flags=re.DOTALL)
        text = re.sub(r"<li>(.*?)</li>", r"  • \1\n", text, flags=re.DOTALL)
        text = re.sub(r"<strong>(.*?)</strong>", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"<hr[^>]*>", "\n" + "-" * 60 + "\n", text)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", "", text)  # Strip remaining tags
        text = re.sub(r"\n{3,}", "\n\n", text)  # Collapse extra newlines
        text = text.strip()

        # Write to PDF
        pdf.set_font("Helvetica", size=12)
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("===") and line.endswith("==="):
                # Title
                title = line.strip("= ").strip()
                pdf.set_font("Helvetica", "B", 16)
                pdf.cell(0, 12, title, ln=True)
                pdf.set_font("Helvetica", size=12)
            elif line.startswith("---") and line.endswith("---"):
                # Section header
                header = line.strip("- ").strip()
                if header and not all(c == "-" for c in header):
                    pdf.set_font("Helvetica", "B", 14)
                    pdf.cell(0, 10, header, ln=True)
                    pdf.set_font("Helvetica", size=12)
                else:
                    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                    pdf.ln(5)
            else:
                # Regular text — encode safely for fpdf2
                safe_line = line.encode("latin-1", errors="replace").decode("latin-1")
                pdf.multi_cell(0, 7, safe_line)

        # Save
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        contact = variables.get("contact_name", "document").replace(" ", "_")
        filename = f"{template_category}_{contact}_{timestamp}.pdf"
        output_path = DOCUMENTS_DIR / filename
        pdf.output(str(output_path))

        return f"Documento gerado: {filename}\nCaminho: {output_path}"

    except ImportError:
        return "fpdf2 não instalado. Execute: pip install fpdf2"
    except Exception as e:
        return f"Erro ao gerar PDF: {e}"


def get_docgen_tools() -> list[StructuredTool]:
    """Get DocGen-specific LangChain tools."""
    return [
        StructuredTool.from_function(
            func=_list_templates,
            name="list_templates",
            description="List available document templates (proposals, contracts, reports)",
        ),
        StructuredTool.from_function(
            func=_generate_document,
            name="generate_document",
            description=(
                "Generate a PDF document from a template. "
                "Parameters: template_name (str), template_category (str: proposals/reports/contracts), "
                "and template variables as keyword args (contact_name, project_scope, pricing, etc.)"
            ),
        ),
    ]
