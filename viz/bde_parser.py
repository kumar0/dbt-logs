"""BDE name parser for Step Function execution names.

Extracts Business Data Entity (BDE) names from execution names by stripping
the trailing ``_{numeric_timestamp}_{uuid}`` suffix.
"""

import re

_BDE_RE = re.compile(
    r"^(.+)_(\d+)_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}.*)$"
)


def extract_bde_name(execution_name: str) -> str:
    """Extract BDE name from a Step Function execution name.

    Pattern: ``{bde_name}_{numeric_timestamp}_{uuid}``

    Returns the BDE name portion on match, or the full input string if the
    pattern doesn't match (including empty strings).
    """
    if not execution_name:
        return execution_name
    m = _BDE_RE.match(execution_name)
    return m.group(1) if m else execution_name
