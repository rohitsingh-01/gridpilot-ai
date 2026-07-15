"""Generalized semantic search tools against ChromaDB collections."""
from __future__ import annotations

from typing import List, Optional
import asyncio

from agents.site_intelligence.interfaces import ToolContext, SearchChunk
from agents.site_intelligence.models import SearchRequest
from agents.site_intelligence.tools.decorators import tool_wrapper


@tool_wrapper(required_permissions=["read:semantic"])
async def semantic_search(
    context: ToolContext,
    request: SearchRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> List[SearchChunk]:
    """Execute generalized semantic search against a target ChromaDB collection (regulatory or environmental)."""
    # Call abstract semantic_service search method
    chunks = await context.semantic_service.search(
        collection=request.collection,
        query=request.query,
        limit=request.limit
    )
    return chunks
