import os

# Create directories
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("static/js/components", exist_ok=True)

# index.html
html = """<!DOCTYPE html>
<html lang="en" class="antialiased light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>StockAI - Premium Terminal</title>
    <link href="https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <script src="https://cdn.tailwindcss.com?plugins=typography"></script>
    <script src="/static/js/tailwind.config.js"></script>
    
    <link rel="stylesheet" href="/static/css/styles.css">
    
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body class="h-screen w-full flex overflow-hidden selection:bg-apple-blue selection:text-white">

    <!-- Left Sidebar -->
    <aside class="w-20 md:w-64 glass-sidebar flex flex-col z-30 shrink-0 transition-all duration-300 relative">
        <div class="h-20 flex items-center justify-center md:justify-start md:px-6 border-b border-black/5 dark:border-white/5">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-apple-blue to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/30">
                <i data-lucide="activity" class="w-5 h-5 text-white"></i>
            </div>
            <span class="text-xl font-bold tracking-tight ml-3 hidden md:block text-transparent bg-clip-text bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300">StockAI</span>
        </div>
        
        <div class="flex-1 overflow-y-auto py-6 px-3 md:px-4 space-y-2" id="sidebar-nav">
            <!-- Nav components injected here -->
        </div>

        <div class="p-4 border-t border-black/5 dark:border-white/5 bg-black/5 dark:bg-white/5 hidden md:block" id="system-status">
            <!-- System Status injected here -->
        </div>
    </aside>

    <!-- Main Content Area -->
    <main class="flex-1 flex flex-col min-w-0 relative h-full">
        <!-- Header -->
        <header class="h-20 glass-panel border-b-0 border-x-0 rounded-none flex items-center px-6 shrink-0 z-20 justify-between">
            <div class="relative w-full max-w-xl group">
                <div class="absolute inset-y-0 left-4 flex items-center pointer-events-none">
                    <i data-lucide="search" class="w-5 h-5 text-apple-gray group-focus-within:text-apple-blue transition-colors"></i>
                </div>
                <input type="text" id="symbol-input" 
                       class="w-full bg-black/5 dark:bg-white/5 border border-transparent rounded-2xl pl-12 pr-4 py-3 text-base focus:outline-none input-glow transition-all backdrop-blur-md"
                       placeholder="Search symbols, indices, or ask a question...">
                <div id="search-feedback" class="hidden absolute top-full left-0 w-full mt-2 bg-white dark:bg-[#1C1C1E] rounded-xl shadow-xl border border-black/10 dark:border-white/10 p-2 z-50"></div>
            </div>
            <div class="flex items-center gap-4 ml-4">
                <button class="w-10 h-10 rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center hover:bg-black/10 transition-colors">
                    <i data-lucide="bell" class="w-5 h-5 opacity-70"></i>
                </button>
            </div>
        </header>

        <!-- Dynamic Layout Area -->
        <div class="flex-1 flex overflow-hidden relative">
            <div class="flex-1 overflow-y-auto px-6 py-8 md:px-10 scroll-smooth pb-32" id="dashboard-view">
                <!-- Content injected here -->
            </div>
            
            <div id="chat-panel" class="w-full md:w-[450px] glass-sidebar flex flex-col shrink-0 z-20 shadow-[-10px_0_30px_rgba(0,0,0,0.05)] transform transition-transform duration-300 md:translate-x-0 absolute md:relative right-0 h-full border-l border-black/10 dark:border-white/10 hidden md:flex">
                <!-- Chat injected here -->
            </div>
            
            <button id="mobile-chat-toggle" class="md:hidden fixed bottom-6 right-6 w-14 h-14 rounded-full bg-apple-blue text-white shadow-xl flex items-center justify-center z-40 hover:scale-105 transition-transform">
                <i data-lucide="message-square" class="w-6 h-6"></i>
            </button>
        </div>
    </main>

    <!-- Modals -->
    <div id="modal-container"></div>
    
    <div id="global-loading" class="fixed inset-0 bg-black/20 backdrop-blur-sm flex items-center justify-center z-50 opacity-0 pointer-events-none transition-opacity duration-300">
        <div class="glass-panel p-6 rounded-2xl flex flex-col items-center shadow-2xl">
            <div class="w-8 h-8 border-4 border-apple-blue border-t-transparent rounded-full animate-spin mb-3"></div>
            <span class="text-sm font-semibold">Processing...</span>
        </div>
    </div>

    <!-- Scripts -->
    <script type="module" src="/static/js/app.js"></script>
</body>
</html>
"""

# css/styles.css
css = """
:root {
    --glass-bg: rgba(255, 255, 255, 0.55);
    --glass-border: rgba(255, 255, 255, 0.3);
    --glass-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
    --sidebar-bg: rgba(242, 242, 247, 0.65);
    --text-main: #1C1C1E;
    --text-muted: #8E8E93;
    --accent: #0A84FF;
}

@media (prefers-color-scheme: dark) {
    :root {
        --glass-bg: rgba(28, 28, 30, 0.55);
        --glass-border: rgba(255, 255, 255, 0.1);
        --sidebar-bg: rgba(0, 0, 0, 0.65);
        --text-main: #F2F2F7;
        --text-muted: #98989D;
    }
    html { background-color: #000; }
}

body {
    background-color: #F2F2F7;
    color: var(--text-main);
    font-family: -apple-system, "SF Pro Display", Inter, system-ui, sans-serif;
}

@media (prefers-color-scheme: dark) {
    body { background-color: #000; }
}

.glass-panel {
    background: var(--glass-bg);
    backdrop-filter: blur(24px) saturate(180%);
    -webkit-backdrop-filter: blur(24px) saturate(180%);
    border: 1px solid var(--glass-border);
    box-shadow: var(--glass-shadow);
}

.glass-sidebar {
    background: var(--sidebar-bg);
    backdrop-filter: blur(40px);
    -webkit-backdrop-filter: blur(40px);
    border-right: 1px solid var(--glass-border);
}

.input-glow:focus-within {
    box-shadow: 0 0 0 4px rgba(10, 132, 255, 0.15);
    border-color: var(--accent);
}

.chart-period-btn {
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-muted);
    transition: all 0.2s ease;
}
.chart-period-btn.active {
    background: var(--glass-border);
    color: var(--text-main);
    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
}

.nav-item { transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.nav-item:hover { background: rgba(0, 0, 0, 0.05); }
@media (prefers-color-scheme: dark) { .nav-item:hover { background: rgba(255, 255, 255, 0.08); } }
.nav-item.active { background: var(--accent); color: white; }

/* Custom Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(142, 142, 147, 0.3); border-radius: 10px; }

/* Numeric typography */
.tabular-nums { font-variant-numeric: tabular-nums; }
"""

# js/tailwind.config.js
tw_config = """
tailwind.config = {
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                apple: { blue: '#0A84FF', green: '#30D158', red: '#FF453A', gray: '#8E8E93' }
            }
        }
    }
}
"""

with open("static/index.html", "w") as f: f.write(html)
with open("static/css/styles.css", "w") as f: f.write(css)
with open("static/js/tailwind.config.js", "w") as f: f.write(tw_config)
