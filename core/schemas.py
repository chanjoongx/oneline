"""Load and validate against the shared JSON Schemas in shared/schemas.

This binds core to the contract: planner, retriever, selector, and kb outputs
are validated against the same schema files the other modules code against.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from .config import SCHEMA_DIR

SCHEMA_FILES = {
    "plan": "plan.schema.json",
    "candidate": "candidate.schema.json",
    "judge_scores": "judge_scores.schema.json",
    "selection": "selection.schema.json",
    "lesson": "lesson.schema.json",
    "retrieved_lessons": "retrieved_lessons.schema.json",
}


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    """Load a named schema from shared/schemas. Cached."""
    filename = SCHEMA_FILES.get(name)
    if not filename:
        raise KeyError(f"unknown schema: {name}. known: {sorted(SCHEMA_FILES)}")
    with open(SCHEMA_DIR / filename, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(name))


def validate(obj: Any, name: str) -> None:
    """Raise jsonschema.ValidationError if obj does not match the named schema."""
    _validator(name).validate(obj)


def is_valid(obj: Any, name: str) -> bool:
    """Return True if obj matches the named schema."""
    return _validator(name).is_valid(obj)


def validate_curator_output(obj: Any) -> None:
    """Validate a curator output against the curator_output subschema of lesson.

    The curator emits this 9-field subset; the core write helper enriches it into
    a full stored Lesson.
    """
    lesson = load_schema("lesson")
    subschema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": lesson["$defs"],
        "$ref": "#/$defs/curator_output",
    }
    Draft202012Validator(subschema).validate(obj)
