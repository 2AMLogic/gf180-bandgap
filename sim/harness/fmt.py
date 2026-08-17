"""Human-readable scalar formatting for records, reports and CLI summaries.

``None`` -> ``"n/a"``; a ``float`` outside the ``[1e-3, 1e5)`` magnitude
range uses scientific notation (``precision``, default ``"6e"``), otherwise
``.6g``; anything else is ``str(value)``. This was a byte-identical private
copy in two callers, plus a near-identical third that wants a more compact
``"4e"`` precision for its summaries (issue #171); this module is the single
implementation.
"""

from __future__ import annotations


def _fmt(value, *, precision: str = "6e") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if value != 0 and (abs(value) < 1e-3 or abs(value) >= 1e5):
            return f"{value:.{precision}}"
        return f"{value:.6g}"
    return str(value)
