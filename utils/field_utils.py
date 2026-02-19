"""Parse and compare field event results (e.g. 17'6" = 17 ft 6 in). Bigger is better."""
import re

# Unicode alternatives for feet (') and inches (") so pasted/copy data still parses
_FEET_CHARS = "'\u2019\u2032\u00b4"   # ASCII apostrophe, right single quote, prime, acute
_INCH_CHARS = '"\u201c\u201d\u2033\u2034'  # ASCII quote, curly left/right, double prime


def _normalize_quotes(s):
    """Replace Unicode feet/inches characters with ASCII ' and \" for parsing."""
    if not s or not isinstance(s, str):
        return s
    for c in _FEET_CHARS:
        if c != "'":
            s = s.replace(c, "'")
    for c in _INCH_CHARS:
        if c != '"':
            s = s.replace(c, '"')
    return s


def _strip_result_suffix(s):
    """Strip trailing letters (e.g. q, w) from result strings for parsing."""
    if not s or not isinstance(s, str):
        return s
    s = s.strip()
    while s and s[-1].isalpha():
        s = s[:-1]
    return s.strip()


def parse_field_result(result_str):
    """
    Parse a field result string into a numeric value for comparison (bigger = better).
    Supports:
      - Feet and inches: 17'6", 17'6, 17' 6" (and Unicode quote variants)
      - Decimal (e.g. meters): 17.5
    Trailing letters (q, w, etc.) are stripped before parsing.
    Returns total inches for ft-in, or the decimal value. Unparseable returns -1 (sorts last).
    """
    if result_str is None or not isinstance(result_str, str):
        return -1.0
    s = _strip_result_suffix(result_str)
    if not s:
        return -1.0
    s = _normalize_quotes(s)
    # Match feet'inches" or feet'inches: e.g. 17'6", 17'6, 17' 6"
    m = re.match(r"(\d+)\s*'\s*(\d+)\s*\"?", s)
    if m:
        feet = int(m.group(1))
        inches = int(m.group(2))
        return float(feet * 12 + inches)
    try:
        return float(s)
    except (ValueError, TypeError):
        return -1.0


def looks_like_field_result(result_str):
    """
    Return True if the result string looks like a feet-inches measurement
    (contains both ' and "), so higher values are better.
    """
    if result_str is None or not isinstance(result_str, str):
        return False
    s = _normalize_quotes(result_str.strip())
    return "'" in s and '"' in s


def all_results_are_field_format(result_strings):
    """
    Return True if the list is non-empty and every string looks like
    a field result (feet-inches with ' and "). Use this to decide
    whether to sort/compare by higher = better.
    """
    if not result_strings:
        return False
    return all(looks_like_field_result(r) for r in result_strings)
