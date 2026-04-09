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


def _parse_json_object_from_response(content: str) -> dict:
    """Extract a JSON object from LLM response, allowing markdown code blocks."""
    content = content.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if m:
        content = m.group(1).strip()
    obj = json.loads(content)
    if isinstance(obj, list) and len(obj) > 0:
        obj = obj[0]
    if not isinstance(obj, dict):
        raise ValueError("LLM response is not a JSON object")
    return obj


def generate_board_post(prompt: str) -> dict:
    """
    Ask the LLM to generate a single Reddit-style board post from the user's prompt.
    Returns a dict with keys: author_display_name, content.
    """
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set")
    system = (
        "You are a forum poster. The user will give you a topic or instruction. "
        "Write a short Reddit-style post (a few sentences). Also invent a plausible username for the author. "
        "Return a single JSON object with exactly these keys: author_display_name, content. "
        "author_display_name should be a short username (e.g. run_fan_42). content is the post body. "
        "Output only valid JSON, no other text."
    )
    response_text = _call_openrouter(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        model=_get_model(),
        api_key=api_key,
    )
    obj = _parse_json_object_from_response(response_text)
    author = obj.get("author_display_name") or obj.get("author") or "Anonymous"
    content = obj.get("content") or ""
    if not isinstance(author, str):
        author = str(author)
    if not isinstance(content, str):
        content = str(content)
    return {"author_display_name": author.strip(), "content": content.strip()}


def fill_result_blanks(rows: list[dict], suggestions: str | None = None) -> list[dict]:
    """
    Given a list of result rows (each with date, athlete, meet, event, result, team),
    send full context to OpenRouter and return the same list with blank fields filled in
    by the LLM with plausible track & field test data.

    Empty or whitespace-only string values are treated as blanks to fill.
    If suggestions is provided, the LLM is instructed to follow those preferences
    (e.g. "pick d3 teams in NY", "fill results with 400m times between 47.00 and 49.26").
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
    if suggestions:
        user += "\n\nUser preferences (follow these when filling blanks): " + suggestions

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


def generate_bulk_results(seed_results: list[dict], count: int, event: str, suggestions: str | None = None, gender: str | None = None) -> list[dict]:
    """
    Generate bulk synthetic track & field results for a given event, seeded from
    existing meet results.  Returns a list of dicts with keys: athlete, result, team.

    seed_results: list of {'athlete', 'result', 'team', ...} already in the meet.
    count:        number of new results to generate.
    event:        e.g. "100m".
    suggestions:  optional free-text steering from the user.
    gender:       optional gender preference: 'male', 'female', or None for any.
    """
    import urllib.request as _urlreq
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set")

    # --- build context from seeds ---
    seed_lines = []
    seed_teams = set()
    for sr in seed_results:
        ath = (sr.get('athlete') or '').strip()
        res = (sr.get('result') or '').strip()
        team = (sr.get('team') or '').strip()
        if ath and res:
            seed_lines.append(f"{ath} ({team}): {res}")
            if team:
                seed_teams.add(team)

    context_block = "\n".join(seed_lines) if seed_lines else "(no seed results)"
    teams_hint = ", ".join(sorted(seed_teams)) if seed_teams else "N/A"

    # --- try to fetch name candidates from Namey (best-effort) ---
    name_candidates = []
    try:
        params = f"count={count + 5}&with_surname=true&frequency=all"
        if gender in ('male', 'female'):
            params += f"&type={gender}"
        req = _urlreq.Request(f"https://namey.muffinlabs.com/name.json?{params}", method="GET")
        with _urlreq.urlopen(req, timeout=10) as resp:
            name_candidates = json.load(resp) or []
    except Exception:
        pass

    name_pool = ", ".join(name_candidates) if name_candidates else "generate plausible names yourself"
    
    gender_rule = ""
    if gender in ('male', 'female'):
        gender_rule = f"- All new athletes should be {gender}.\n"

    system = (
        f"You are a track & field results generator. The user wants {count} plausible NEW results "
        f"for the {event} event at a meet that already has the results listed below.\n\n"
        f"Existing results (seed):\n{context_block}\n\n"
        f"Teams already in this meet: {teams_hint}\n\n"
        f"Name pool (available for new athletes): {name_pool}\n\n"
        "Rules:\n"
        f"{gender_rule}"
        f"- Generate exactly {count} new results.\n"
        "- New athletes should be either (a) names from the name pool above or (b) brand new plausible names you invent.\n"
        "- A mix of athletes: roughly half from teams already at the meet, half from new plausible team names.\n"
        "- Results should be SLOWER / WEAKER than the existing seed results above (these are the bottom half of the field).\n"
        "- For timed events (100m, 200m, 400m, 800m, 1500m, Mile, 5000m, etc.) — slower times.\n"
        "- For field events (Long Jump, High Jump, Shot Put, etc.) — shorter / lower marks.\n"
        "- Use realistic result formats: times like 11.42, 1:58.3, 4:42.15; or field marks like 18'7.5\", 5'10\".\n"
        "- Do NOT duplicate any existing athlete name from the seed results.\n"
        "- Return a JSON array of objects with exactly these keys: athlete, result, team. No other keys.\n"
        "Output only valid JSON, no other text."
    )
    user_msg = (
        f"Generate {count} additional results for {event}. "
        f"The seed athletes already have times shown above. "
        f"Make the new athletes competitive but definitely ranked below the existing ones."
    )
    if suggestions:
        user_msg += f"\n\nUser steering instructions (follow these): {suggestions}"

    response_text = _call_openrouter(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        model=_get_model(),
        api_key=api_key,
    )
    raw = _parse_json_from_response(response_text)
    if not isinstance(raw, list):
        raise ValueError("LLM response is not a JSON array")

    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        out.append({
            'athlete': str(row.get('athlete', '')).strip(),
            'result': str(row.get('result', '')).strip(),
            'team': str(row.get('team', '')).strip(),
        })
    return out[:count]
