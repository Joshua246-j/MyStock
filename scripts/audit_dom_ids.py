import re
from pathlib import Path

js_text = Path("static/app.js").read_text(encoding="utf-8")
html_text = Path("static/index.html").read_text(encoding="utf-8")

# 1. Missing DOM IDs
js_ids = set(re.findall(r"getElementById\(['\"]([a-zA-Z0-9_\-]+)['\"]", js_text))
html_ids = set(re.findall(r"id=['\"]([a-zA-Z0-9_\-]+)['\"]", html_text))
print("Missing IDs referenced in JS:", sorted(js_ids - html_ids))

# 2. Query selectors that might be missing
qs = set(re.findall(r"querySelector(?:All)?\(['\"]([#\.][a-zA-Z0-9_\-]+)['\"]", js_text))
print("Selectors used in JS:", sorted(qs))

# 3. API calls made in JS
api_calls = set(re.findall(r"['\"`](/api/[a-zA-Z0-9_\-/\${}]+)", js_text))
print("\nAPI calls in JS:")
for c in sorted(api_calls):
    print(" ", c)
