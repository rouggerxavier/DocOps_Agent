from typing import List
from fastapi import APIRouter
from docops.api.schemas import DocItem
from docops.tools.doc_tools import tool_list_docs

router = APIRouter()


@router.get("/docs", response_model=List[DocItem])
async def list_docs() -> List[DocItem]:
    """List all documents currently indexed in the vector store."""
    docs = tool_list_docs()
    return [DocItem(**d) for d in docs]
