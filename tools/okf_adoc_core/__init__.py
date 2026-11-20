"""Shared implementation for the opt-in OKF AsciiDoc profile."""

from .profile import (
    AttributePlan,
    Concept,
    Finding,
    Header,
    PROFILE,
    attribute_plan,
    detect_profile,
    discover,
    parse_header,
    resolve_target,
    split_frontmatter,
    sync_attributes,
    targets,
)

__all__ = [
    "AttributePlan",
    "Concept",
    "Finding",
    "Header",
    "PROFILE",
    "attribute_plan",
    "detect_profile",
    "discover",
    "parse_header",
    "resolve_target",
    "split_frontmatter",
    "sync_attributes",
    "targets",
]
