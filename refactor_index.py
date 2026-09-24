import re
import os

with open('static/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract CSS
style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
if style_match:
    css_content = style_match.group(1)
    with open('static/index.css', 'w', encoding='utf-8') as f:
        f.write(css_content)
    content = content.replace(style_match.group(0), '<link rel="stylesheet" href="/static/index.css">')

# Extract JS
script_match = re.search(r'<script>\s*// Init Icons(.*?)<\/script>', content, re.DOTALL)
if script_match:
    js_content = '// Init Icons' + script_match.group(1)
    
    with open('static/app.js', 'w', encoding='utf-8') as f:
        f.write(js_content)
    
    content = content.replace(script_match.group(0), '<script src="/static/app.js"></script>')

# Replace Chart.js CDN with Lightweight charts
content = content.replace('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>', '<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>')

# Make mainChart a div instead of canvas for lightweight charts
content = content.replace('<canvas id="mainChart"></canvas>', '<div id="mainChart" style="width:100%;height:100%;"></div>')

with open('static/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
