"""Auto-enrichment service for trace metadata.

Detects language, framework, and computes a depth score based on how much
context a trace provides. Richer traces rank higher in search (levels of
processing effect from cognitive neuroscience).
"""

import re
from typing import Optional


# Code fence language detection: ```python, ```js, etc.
_FENCE_RE = re.compile(r"```(\w+)")

# Language detection via import/require patterns
_LANGUAGE_PATTERNS: dict[str, list[re.Pattern]] = {
    "python": [
        re.compile(r"\bimport\s+\w+", re.MULTILINE),
        re.compile(r"\bfrom\s+\w+\s+import\b", re.MULTILINE),
        re.compile(r"\bdef\s+\w+\s*\(", re.MULTILINE),
    ],
    "javascript": [
        re.compile(r"\bconst\s+\w+\s*=\s*require\(", re.MULTILINE),
        re.compile(r"\bimport\s+.*\s+from\s+['\"]", re.MULTILINE),
    ],
    "typescript": [
        re.compile(r"\binterface\s+\w+\s*\{", re.MULTILINE),
        re.compile(r":\s*(string|number|boolean|any)\b", re.MULTILINE),
    ],
    "rust": [
        re.compile(r"\buse\s+\w+::", re.MULTILINE),
        re.compile(r"\bfn\s+\w+\s*\(", re.MULTILINE),
    ],
    "go": [
        re.compile(r'\bimport\s+\(', re.MULTILINE),
        re.compile(r"\bfunc\s+\w+\s*\(", re.MULTILINE),
    ],
}

# Framework detection via import/usage patterns
_FRAMEWORK_PATTERNS: dict[str, list[re.Pattern]] = {
    "fastapi": [re.compile(r"\bfrom\s+fastapi\b|\bimport\s+fastapi\b", re.MULTILINE)],
    "django": [re.compile(r"\bfrom\s+django\b|\bimport\s+django\b", re.MULTILINE)],
    "flask": [re.compile(r"\bfrom\s+flask\b|\bimport\s+flask\b", re.MULTILINE)],
    "react": [re.compile(r"\bimport\s+.*\bfrom\s+['\"]react['\"]", re.MULTILINE)],
    "vue": [re.compile(r"\bimport\s+.*\bfrom\s+['\"]vue['\"]", re.MULTILINE)],
    "next": [re.compile(r"\bfrom\s+['\"]next/", re.MULTILINE)],
    "express": [re.compile(r"\brequire\(['\"]express['\"]\)", re.MULTILINE)],
    "sqlalchemy": [re.compile(r"\bfrom\s+sqlalchemy\b|\bimport\s+sqlalchemy\b", re.MULTILINE)],
    "docker": [re.compile(r"\bFROM\s+\S+|\bDockerfile\b", re.MULTILINE)],
    "kubernetes": [re.compile(r"\bapiVersion:\s+\S+|\bkind:\s+(Deployment|Service|Pod)\b", re.MULTILINE)],
    "terraform": [re.compile(r"\bresource\s+\"", re.MULTILINE)],
    "postgres": [re.compile(r"\bCREATE\s+TABLE\b|\bSELECT\s+.*\bFROM\b", re.MULTILINE | re.IGNORECASE)],
}

# Version patterns: ==1.2.3, @^1.2.3, :1.2.3, etc.
_VERSION_RE = re.compile(r"[=@:^~]\d+\.\d+(?:\.\d+)?")


def detect_language(solution_text: str) -> Optional[str]:
    """Detect the primary programming language from solution text.

    Checks code fences first (most reliable), then falls back to
    import/syntax pattern matching.
    """
    # Check code fences first
    fences = _FENCE_RE.findall(solution_text)
    if fences:
        lang = fences[0].lower()
        # Normalize common aliases
        aliases = {"js": "javascript", "ts": "typescript", "py": "python", "rb": "ruby", "rs": "rust"}
        return aliases.get(lang, lang)

    # Fall back to pattern matching
    for lang, patterns in _LANGUAGE_PATTERNS.items():
        if any(p.search(solution_text) for p in patterns):
            return lang

    return None


def detect_framework(solution_text: str) -> Optional[str]:
    """Detect the primary framework from solution text via import patterns."""
    for framework, patterns in _FRAMEWORK_PATTERNS.items():
        if any(p.search(solution_text) for p in patterns):
            return framework
    return None


def compute_depth_score(metadata: Optional[dict], solution_text: str) -> int:
    """Compute encoding depth score (0-4).

    Higher depth = richer context = more useful trace.
    Based on levels-of-processing effect: deeper encoding → better retrieval.

    +1 has error_message in metadata
    +1 has language AND (framework OR versions)
    +1 solution_text > 200 chars
    +1 has specific library versions
    """
    score = 0
    meta = metadata or {}

    # +1 for error context (deeper encoding of the problem)
    if meta.get("error_message"):
        score += 1

    # +1 for language + framework/versions (multi-modal encoding)
    has_lang = bool(meta.get("language"))
    has_framework = bool(meta.get("framework"))
    has_versions = bool(meta.get("versions"))
    if has_lang and (has_framework or has_versions):
        score += 1

    # +1 for substantial solution (elaborative encoding)
    if len(solution_text) > 200:
        score += 1

    # +1 for specific library versions (precise encoding)
    if _VERSION_RE.search(solution_text):
        score += 1

    return score


def compute_somatic_intensity(metadata: Optional[dict]) -> float:
    """Compute initial somatic intensity from detection metadata (0.0-1.0).

    Damasio-inspired: how intensely was this knowledge learned?
    Higher intensity = harder-won knowledge = higher retrieval priority.

    Detection metadata keys (set by skill stop hook):
    - detection_pattern: str — which pattern triggered contribution
    - error_count: int — errors encountered during resolution
    - time_to_resolution_minutes: float — time invested
    - iteration_count: int — edit iterations on the same files
    """
    meta = metadata or {}
    pattern = meta.get("detection_pattern", "")

    # Base intensity from pattern type
    PATTERN_BASE = {
        "error_resolution": 0.6,
        "security_hardening": 0.8,
        "approach_reversal": 0.5,
        "prediction_error": 0.7,
        "dependency_resolution": 0.4,
        "test_fix_cycle": 0.4,
        "migration_pattern": 0.5,
        "user_correction": 0.5,
        "infra_discovery": 0.4,
        "research_then_implement": 0.3,
        "config_discovery": 0.3,
        "cross_file_breadth": 0.2,
    }
    intensity = PATTERN_BASE.get(pattern, 0.2)

    # Amplify by effort signals
    errors = meta.get("error_count", 0)
    if isinstance(errors, (int, float)):
        intensity += min(0.2, errors * 0.03)

    time_min = meta.get("time_to_resolution_minutes", 0)
    if isinstance(time_min, (int, float)):
        intensity += min(0.15, time_min * 0.005)

    iterations = meta.get("iteration_count", 0)
    if isinstance(iterations, (int, float)):
        intensity += min(0.1, iterations * 0.01)

    return min(1.0, intensity)


def auto_enrich_metadata(metadata: Optional[dict], solution_text: str) -> dict:
    """Auto-detect language, framework, and versions from solution text.

    Only fills in fields that aren't already set — respects explicit metadata
    from the contributor.
    """
    enriched = dict(metadata) if metadata else {}

    if not enriched.get("language"):
        lang = detect_language(solution_text)
        if lang:
            enriched["language"] = lang

    if not enriched.get("framework"):
        framework = detect_framework(solution_text)
        if framework:
            enriched["framework"] = framework

    return enriched
