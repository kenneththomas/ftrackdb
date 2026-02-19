"""
OpenRouter API client for LLM-backed test data generation.
Uses full context of current result rows and fills in blank fields with plausible track & field data.
"""
import json
import os
import re
import urllib.request
import urllib.error


OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def _get_api_key():
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    return key or None


def _get_model():
    return os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL


def _call_openrouter(messages: list, model: str, api_key: str) -> str:
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 4096,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_BASE,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "http://localhost/"),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.load(resp)
    choices = out.get("choices") or []
    if not choices:
        raise ValueError("OpenRouter returned no choices")
    content = (choices[0].get("message") or {}).get("content") or ""
    return content.strip()


def _parse_json_from_response(content: str) -> list:
    """Extract a JSON array from LLM response, allowing markdown code blocks."""
    content = content.strip()
    # Strip optional markdown code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if m:
        content = m.group(1).strip()
    return json.loads(content)


def fill_result_blanks(rows: list[dict]) -> list[dict]:
    """
    Given a list of result rows (each with date, athlete, meet, event, result, team),
    send full context to OpenRouter and return the same list with blank fields filled in
    by the LLM with plausible track & field test data.

    Empty or whitespace-only string values are treated as blanks to fill.
    """
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set")

    # Normalize keys to lowercase for consistent handling
    def norm(r):
        return {k.strip().lower(): (v.strip() if isinstance(v, str) else v or "") for k, v in (r or {}).items()}

    normalized = [norm(r) for r in rows]
    field_names = ["date", "athlete", "meet", "event", "result", "team"]

    # Build context description for the model
    lines = []
    for i, row in enumerate(normalized):
        parts = []
        for f in field_names:
            val = (row.get(f) or "").strip()
            if val:
                parts.append(f"{f}: {val}")
            else:
                parts.append(f"{f}: [BLANK]")
        lines.append(f"Row {i + 1}: " + ", ".join(parts))
    context = "\n".join(lines)

    system = (
        "You are a helper that fills in missing fields for track and field race results. "
        "You will be given a list of rows with some fields filled and some marked [BLANK]. "
        "Return a JSON array of objects with exactly these keys: date, athlete, meet, event, result, team. "
        "For each row, keep existing values unchanged and replace only [BLANK] fields with plausible values. "
        "Dates must be YYYY-MM-DD. Events are like 100m, 200m, 800m, 1500m, Mile, 5000m, etc. "
        "Results are times (e.g. 10.45, 1:52.3, 4:32.10) or other valid result formats. "
        "Athlete names: realistic first and last. Meet names: short meet titles. Team: school or club name. "
        "Output only valid JSON, no other text."
    )
    user = (
        "Current result rows (replace [BLANK] with plausible values; keep non-blank values exactly as-is):\n\n"
        + context
    )

    response_text = _call_openrouter(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=_get_model(),
        api_key=api_key,
    )
    filled = _parse_json_from_response(response_text)
    if not isinstance(filled, list):
        raise ValueError("LLM response is not a JSON array")

    # Ensure we have the same number of rows and correct keys
    out = []
    for i, row in enumerate(filled):
        if i >= len(normalized):
            break
        orig = normalized[i]
        item = {}
        for f in field_names:
            if f in row and row[f] is not None and str(row[f]).strip():
                item[f] = str(row[f]).strip()
            elif orig.get(f):
                item[f] = orig.get(f)
            else:
                item[f] = ""
        out.append(item)
    # If LLM returned fewer rows, keep original for the rest
    while len(out) < len(normalized):
        out.append(dict(normalized[len(out)]))
    return out[: len(normalized)]
