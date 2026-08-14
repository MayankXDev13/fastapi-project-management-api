"""Schema foundation: the response schema IS the ORM→API mapper.

`APIResponse` opts every row-mapping response into Pydantic's
`from_attributes`, so routes return `Schema.model_validate(orm_obj)` and no
field-by-field copying exists anywhere. `Page[T]` is the only pagination
envelope. `build_entity` merges path/actor extras (which always win) with
request-body fields (None → model defaults) when constructing model rows.
"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from sqlmodel import SQLModel

T = TypeVar("T")
M = TypeVar("M", bound=SQLModel)


class APIResponse(BaseModel):
    """Base class for every response that maps 1:1 onto a table row."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def build_entity(
    model: type[M],
    body: BaseModel,
    *,
    exclude: frozenset[str] = frozenset(),
    **extras: Any,
) -> M:
    """Construct a model row from a request body plus path/actor extras.

    Extras always win over body fields; body fields left unset (None) fall
    back to the model's column defaults. `exclude` drops body fields that do
    not exist on the model (e.g. a still-sent redundant path param).
    """
    fields = {
        k: v
        for k, v in body.model_dump(exclude_unset=True).items()
        if k not in exclude
    }
    fields.update(extras)
    return model(**fields)