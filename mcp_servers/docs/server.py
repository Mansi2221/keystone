"""Document Store MCP Server — search and retrieve documents.

Read tools: search_documents, get_document, semantic_search
Write tools: none

Vector retrieval pre-filters by access groups inside the SQL query.
"""

import logging

from sqlalchemy import select, text

from company.models import Document
from company.principal import Principal
from company.rls import rls_session
from mcp_servers.base import access_denied, tool_result

logger = logging.getLogger(__name__)


def search_documents(
    principal: Principal,
    query: str = "",
    doc_type: str = "",
    department: str = "",
    limit: int = 20,
) -> dict:
    """Search documents by title, type, or department. Filtered by RLS."""
    with rls_session(principal) as session:
        stmt = select(Document)
        if query:
            stmt = stmt.where((Document.title.ilike(f"%{query}%")) | (Document.content.ilike(f"%{query}%")))
        if doc_type:
            stmt = stmt.where(Document.doc_type == doc_type)
        if department:
            stmt = stmt.where(Document.department.ilike(f"%{department}%"))

        stmt = stmt.order_by(Document.updated_at.desc()).limit(limit)
        results = session.execute(stmt).scalars().all()

        return tool_result(
            [
                {
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "doc_type": d.doc_type,
                    "department": d.department,
                    "version": d.version,
                    "owner_id": d.owner_id,
                    "access_groups": d.access_groups,
                    "updated_at": d.updated_at.isoformat(),
                }
                for d in results
            ]
        )


def get_document(principal: Principal, doc_id: str) -> dict:
    """Get full document content by ID. Filtered by RLS."""
    with rls_session(principal) as session:
        stmt = select(Document).where(Document.doc_id == doc_id)
        doc = session.execute(stmt).scalar_one_or_none()

        if not doc:
            return access_denied("document", "Document not found or access denied.")

        return tool_result(
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "content": doc.content,
                "doc_type": doc.doc_type,
                "department": doc.department,
                "version": doc.version,
                "owner_id": doc.owner_id,
                "access_groups": doc.access_groups,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
                "is_duplicate": doc.is_duplicate,
                "is_stale": doc.is_stale,
            }
        )


def semantic_search(
    principal: Principal,
    query_embedding: list[float],
    limit: int = 10,
) -> dict:
    """Semantic search across document chunks using vector similarity.

    IMPORTANT: Pre-filters by access groups before similarity ranking.
    This ensures restricted documents are never returned to unauthorized users,
    even if they are semantically similar to the query.
    """
    from company.config import settings

    with rls_session(principal) as session:
        # Build groups array for the pre-filter
        groups = principal.groups

        # RETRIEVAL_PREFILTER: add explicit access-group filter
        # The RLS policy on document_chunks provides a second layer,
        # but we add an explicit pre-filter for defense in depth.
        if settings.protection_enabled("retrieval_prefilter"):
            where_clause = """WHERE
                (dc.access_groups && :groups::text[]
                 OR :role = 'executive'
                )"""
        else:
            where_clause = ""

        stmt = text(f"""
            SELECT
                dc.id,
                dc.document_id,
                dc.chunk_index,
                dc.content,
                d.doc_id,
                d.title,
                d.doc_type,
                d.department,
                1 - (dc.embedding <=> :embedding::vector) AS similarity
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            {where_clause}
            ORDER BY dc.embedding <=> :embedding::vector
            LIMIT :limit
        """)

        results = session.execute(
            stmt,
            {
                "embedding": str(query_embedding),
                "groups": groups,
                "role": principal.role,
                "limit": limit,
            },
        ).fetchall()

        return tool_result(
            [
                {
                    "chunk_id": r.id,
                    "doc_id": r.doc_id,
                    "title": r.title,
                    "doc_type": r.doc_type,
                    "department": r.department,
                    "content": r.content,
                    "similarity": float(r.similarity) if r.similarity else 0.0,
                }
                for r in results
            ]
        )


TOOLS = {
    "docs_search": {
        "function": search_documents,
        "description": "Search documents by title, type, or department",
        "parameters": {
            "query": {"type": "string", "description": "Search term"},
            "doc_type": {"type": "string", "description": "Filter: policy, contract, wiki, board_minutes"},
            "department": {"type": "string", "description": "Filter by department"},
            "limit": {"type": "integer"},
        },
    },
    "docs_get": {
        "function": get_document,
        "description": "Get full document content by ID",
        "parameters": {
            "doc_id": {"type": "string", "required": True},
        },
    },
    "docs_semantic_search": {
        "function": semantic_search,
        "description": "Semantic search across documents using vector similarity (pre-filtered by access)",
        "parameters": {
            "query_embedding": {"type": "array", "required": True, "description": "Query embedding vector"},
            "limit": {"type": "integer"},
        },
    },
}
