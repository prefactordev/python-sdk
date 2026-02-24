"""Base response models for Prefactor API."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Generic API response wrapper.

    Attributes:
        status: Response status (always "success" for successful requests)
        details: Detailed response data
    """

    status: str
    details: T


class ApiError(BaseModel):
    """API error response.

    Attributes:
        status: Response status (always "error")
        code: Error code
        message: Human-readable error message
    """

    status: str = "error"
    code: str
    message: str


class DetailedApiError(ApiError):
    """API error with detailed validation errors.

    Attributes:
        errors: Map of field names to error messages
    """

    errors: dict[str, Any]


class PaginationOutput(BaseModel):
    """Pagination information.

    Attributes:
        item_count: Total number of items
        item_end: Index of last item in page (one-based)
        item_start: Index of first item in page (one-based)
        next_page_offset: Offset of next page (null if last page)
        page_count: Total number of pages
        page_index: Index of current page (one-based)
        page_offset: Offset of first item (zero-based)
        page_size: Number of items per page
        previous_page_offset: Offset of previous page (null if first page)
    """

    item_count: int
    item_end: int
    item_start: int
    next_page_offset: int | None
    page_count: int
    page_index: int
    page_offset: int
    page_size: int
    previous_page_offset: int | None


class Sorting(BaseModel):
    """Sorting information.

    Attributes:
        field: Field to sort by
        direction: Sort direction (asc or desc)
    """

    field: str
    direction: str


class ListResponse(BaseModel, Generic[T]):
    """Generic list response wrapper.

    Attributes:
        status: Response status (always "success")
        summaries: List of items
        pagination: Pagination information
        sorting: Sorting information
    """

    status: str
    summaries: list[T]
    pagination: PaginationOutput | None
    sorting: Sorting | None
