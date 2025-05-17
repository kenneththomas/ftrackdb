import markdown
from markupsafe import Markup

def markdown_to_html(text):
    if not text:
        return ""
    # You can add options to markdown.markdown() if needed.
    return Markup(markdown.markdown(text)) 