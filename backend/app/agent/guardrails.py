"""
Input guardrails: sanitization, prompt injection detection, file validation.
"""
import re
import os
from pathlib import Path
from typing import Optional
import bleach
from app.observability.logging_config import get_logger

logger = get_logger(__name__)

MAX_TITLE_LENGTH = 500
MAX_DESCRIPTION_LENGTH = 10_000
MAX_FILE_SIZE_MB = 10
ALLOWED_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ALLOWED_LOG_TYPES = {".txt", ".log", ".json", ".csv"}

INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above)\s+instructions",
    r"you\s+are\s+now\s+a",
    r"disregard\s+(your|all)",
    r"system\s*prompt",
    r"jailbreak",
    r"act\s+as\s+(if|a|an)",
    r"do\s+anything\s+now",
    r"dan\s*mode",
    r"<\s*script",
    r"javascript:",
    r"\beval\s*\(",
    r"__import__",
    r"os\.system",
    r"subprocess",
]

_injection_re = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def sanitize_text(text: str) -> str:
    """Strip HTML and control characters from text input."""
    clean = bleach.clean(text, tags=[], strip=True)
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", clean)
    return clean.strip()


def detect_injection_heuristic(text: str) -> Optional[str]:
    """Fast regex-based injection detection before calling the LLM."""
    match = _injection_re.search(text)
    if match:
        return f"Potential prompt injection pattern detected: '{match.group()}'"
    return None


def validate_file(file_path: str) -> tuple[bool, str]:
    """Validate an uploaded file for type and size."""
    path = Path(file_path)
    if not path.exists():
        return False, "File does not exist"

    suffix = path.suffix.lower()
    allowed = ALLOWED_IMAGE_TYPES | ALLOWED_LOG_TYPES
    if suffix not in allowed:
        return False, f"File type {suffix} not allowed"

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return False, f"File too large ({size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB limit)"

    return True, "ok"


def run_guardrails(
    title: str,
    description: str,
    reporter_email: str,
    attachment_paths: list[str],
) -> tuple[bool, str, str, str]:
    """
    Run all input guardrails.
    Returns: (passed, reason, clean_title, clean_description)
    """
    # Length checks
    if len(title.strip()) < 5:
        return False, "Title too short", title, description
    if len(title) > MAX_TITLE_LENGTH:
        return False, "Title exceeds maximum length", title, description
    if len(description) > MAX_DESCRIPTION_LENGTH:
        return False, "Description exceeds maximum length", title, description

    # Email basic validation
    if not re.match(r"[^@]+@[^@]+\.[^@]+", reporter_email):
        return False, "Invalid reporter email", title, description

    # Sanitize
    clean_title = sanitize_text(title)
    clean_description = sanitize_text(description)

    # Injection heuristic check on both fields
    combined = f"{clean_title} {clean_description}"
    injection_issue = detect_injection_heuristic(combined)
    if injection_issue:
        logger.warning(f"Guardrail blocked injection attempt: {injection_issue}")
        return False, injection_issue, clean_title, clean_description

    # Validate files
    for path in attachment_paths:
        valid, reason = validate_file(path)
        if not valid:
            return False, f"Invalid attachment: {reason}", clean_title, clean_description

    return True, "ok", clean_title, clean_description
