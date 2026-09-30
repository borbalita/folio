from app.retrieval.documents.formatting import format_passages_for_agent
from app.retrieval.documents.queries import DocumentSearchFilters
from app.retrieval.documents.retriever import DocumentPassage, DocumentRetriever
from app.retrieval.email.formatting import format_email_passages
from app.retrieval.email.queries import EmailSearchFilters
from app.retrieval.email.retriever import EmailPassage, EmailRetriever

__all__ = [
    "DocumentPassage",
    "DocumentRetriever",
    "DocumentSearchFilters",
    "EmailPassage",
    "EmailRetriever",
    "EmailSearchFilters",
    "format_email_passages",
    "format_passages_for_agent",
]
