import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

with open('static/app.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Find inline handlers
handlers = re.findall(r'(?:onclick|oninput|onchange|onkeydown)="([a-zA-Z0-9_]+)\(', html)
handlers = sorted(set(handlers))

print("=== CHECKING INLINE EVENT HANDLERS ===")
for h in handlers:
    pattern = rf'\b(function\s+{h}|window\.{h}|let\s+{h}|const\s+{h}|var\s+{h}|{h}\s*=)\b'
    if not re.search(pattern, js):
        print(f"  MISSING HANDLER: {h}")

# Find IDs referenced in HTML vs used in JS
html_ids = set(re.findall(r'id="([a-zA-Z0-9_\-]+)"', html))
js_ids = set(re.findall(r"getElementById\(['\"]([a-zA-Z0-9_\-]+)['\"]\)", js))

missing_in_html = js_ids - html_ids
print("\n=== IDs REFERENCED IN JS getElementById BUT MISSING IN index.html ===")
for mid in sorted(missing_in_html):
    print(f"  MISSING ID: {mid}")
