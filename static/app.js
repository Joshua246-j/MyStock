// Init Icons
        lucide.createIcons();

        let currentSymbol = null;
        let activeDatasetId = Number(localStorage.getItem('stockrag.datasetId')) || null;
        let mainChartInstance = null;
        const comparisonCharts = new Map();
        let compareResizeObserver = null;
        const popularSymbols = ['RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS','ICICIBANK.NS','SBIN.NS','BHARTIARTL.NS','ITC.NS','LT.NS','BAJFINANCE.NS','KOTAKBANK.NS','MARUTI.NS','TATAMOTORS.NS','SUNPHARMA.NS','AXISBANK.NS','HINDUNILVR.NS','AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','SPY','QQQ','^NSEI','^BSESN'];
        let chartMode = 'line';
        let chartResizeObserver = null;
        let chatSessionId = localStorage.getItem('stockrag.sessionId') || null;
        let chatRestoreGeneration = 0;
        let selectedDocumentIds = JSON.parse(localStorage.getItem('stockrag.documentIds') || '[]');
        let knownDocuments = [];
        let currentSettings = {};

        const EXTRA_SETTINGS = [
            ['response_detail','Response detail','select',['concise','balanced','detailed']],
            ['default_chat_mode','Default chat mode','select',['auto','market','documents','general']],
            ['max_retrieved_documents','Max retrieved passages','number'],
            ['max_output_tokens','Maximum answer tokens','number'],
            ['web_research_enabled','Enable web research','checkbox'],
            ['automatic_news_retrieval','Retrieve news automatically','checkbox'],
            ['automatic_technical_analysis','Retrieve technicals automatically','checkbox'],
            ['automatic_fundamental_analysis','Retrieve fundamentals automatically','checkbox'],
            ['default_market_exchange','Default exchange','select',['US','IN','UK','CA','AU']],
            ['default_chart_period','Default chart period','select',['1mo','3mo','6mo','1y','2y','5y']],
            ['default_chart_interval','Default chart interval','select',['1d','1wk','1mo']],
            ['theme','Theme','select',['light','dark']],
            ['ui_density','Interface density','select',['comfortable','compact']],
            ['show_advanced_metrics','Show advanced metrics','checkbox'],
            ['show_data_sources','Show data sources','checkbox'],
            ['cache_ttl','Cache lifetime (seconds)','number'],
            ['request_timeout','Request timeout (seconds)','number']
        ];

        function applyTheme(theme, density = currentSettings.ui_density) {
            document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
            document.documentElement.dataset.density = density === 'compact' ? 'compact' : 'comfortable';
            document.documentElement.dataset.advanced = currentSettings.show_advanced_metrics === false ? 'false' : 'true';
        }

        function renderSettingsControls(data) {
            const root = document.getElementById('advanced-settings-controls');
            root.innerHTML = EXTRA_SETTINGS.map(([key,label,type,options]) => {
                const value = data[key];
                if (type === 'checkbox') return `<label class="flex min-h-11 items-center justify-between gap-3 text-sm"><span>${label}</span><input data-setting="${key}" type="checkbox" ${value ? 'checked' : ''}></label>`;
                const control = type === 'select'
                    ? `<select data-setting="${key}" class="w-full rounded-xl border border-black/10 bg-white/70 px-3 py-2.5 text-sm dark:bg-black/20">${options.map(option=>`<option value="${option}" ${value===option?'selected':''}>${option}</option>`).join('')}</select>`
                    : `<input data-setting="${key}" type="number" min="1" value="${Number(value)||1}" class="w-full rounded-xl border border-black/10 bg-white/70 px-3 py-2.5 text-sm dark:bg-black/20">`;
                return `<label class="block text-xs font-semibold text-apple-gray">${label}${control}</label>`;
            }).join('');
        }

        // Auto-resize chat textarea
        const tx = document.getElementById('chat-input');
        tx.addEventListener("input", function() {
            this.style.height = "52px";
            this.style.height = Math.min(this.scrollHeight, 150) + "px";
        });

        // Mobile chat toggle
        function toggleChatMobile() {
            const panel = document.getElementById('chat-panel');
            if (!panel.classList.contains('mobile-open')) {
                panel.classList.remove('hidden');
                panel.classList.add('mobile-open');
            } else {
                panel.classList.remove('mobile-open');
                panel.classList.add('hidden');
            }
        }

        // Navigation UI
        function focusSearch() {
            document.getElementById('symbol-input').focus();
        }
        function showView(view) {
            if (view !== 'dashboard') return;
            document.getElementById('dashboard-view').scrollTo({top:0, behavior:'smooth'});
            document.querySelectorAll('.nav-item').forEach(button => button.classList.toggle('active', button.getAttribute('onclick') === "showView('dashboard')"));
        }
        function focusChat() {
            if (window.innerWidth < 1024) toggleChatMobile();
            setTimeout(() => document.getElementById('chat-input').focus(), 300);
        }

        // Tabs
        function switchTab(tabId) {
            document.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => {
                c.classList.add('hidden');
                c.classList.remove('block');
            });
            
            document.querySelectorAll('.tab-btn').forEach(button => {
                if (button.getAttribute('onclick') === `switchTab('${tabId}')`) button.classList.add('active');
            });
            const target = document.getElementById('tab-' + tabId);
            target.classList.remove('hidden');
            target.classList.add('block');
        }

        // Modals
        function toggleModal(modalId) {
            const m = document.getElementById(modalId);
            const contentId = modalId.replace('-modal', '-content');
            const c = document.getElementById(contentId);
            const isHidden = m.classList.contains('pointer-events-none');
            
            if (isHidden) {
                if (modalId === 'settings-modal') fetchSettings();
                if (modalId === 'docs-modal') loadDocuments();
                m.classList.remove('pointer-events-none', 'opacity-0');
                c.classList.remove('scale-95');
            } else {
                m.classList.add('opacity-0');
                c.classList.add('scale-95');
                setTimeout(() => m.classList.add('pointer-events-none'), 300);
            }
        }

        async function fetchSettings() {
            try {
                const res = await fetch('/api/settings');
                if (!res.ok) throw new Error('Settings unavailable');
                const data = await res.json();
                currentSettings = data;
                await refreshModels(data.ai_model ?? 'gemma3:4b');
                document.getElementById('set-temp').value = data.temperature ?? 0.2;
                document.getElementById('set-ctx').value = data.context_size ?? 4096;
                document.getElementById('set-cite').checked = data.citation_visibility !== false;
                renderSettingsControls(data);
                applyTheme(data.theme, data.ui_density);
            } catch (e) { console.warn("Failed to load settings", e); }
        }

        async function refreshModels(configuredModel) {
            const settingsSelect = document.getElementById('set-model');
            const chatSelect = document.getElementById('chat-model-select');
            const selected = configuredModel || settingsSelect.value;
            for (const select of [settingsSelect, chatSelect]) select.replaceChildren();
            try {
                const response = await fetch('/api/models');
                const result = await response.json();
                const models = result.available ? result.models : [];
                for (const select of [settingsSelect, chatSelect]) {
                    if (selected && !models.includes(selected)) {
                        const option = document.createElement('option');
                        option.value = selected;
                        option.textContent = `${selected} — ${result.available ? 'not installed' : 'Ollama unavailable'}`;
                        option.disabled = true;
                        select.append(option);
                    }
                    for (const name of models) {
                        const option = document.createElement('option');
                        option.value = name;
                        option.textContent = name;
                        select.append(option);
                    }
                    select.value = selected;
                    select.title = result.available ? (models.length ? 'Installed local models' : 'No local models installed') : (result.error || 'Local Ollama unavailable');
                }
                const quickStatus = document.getElementById('chat-model-status');
                quickStatus.textContent = result.available ? (models.length ? 'Local model' : 'No models installed') : 'Ollama unavailable';
                chatSelect.disabled = !result.available || !models.length;
                const help = document.getElementById('model-help');
                if (help) help.textContent = !result.available
                    ? `Ollama is unavailable. Start it locally, then install a model. Example: ollama pull qwen2.5:1.5b. ${result.error || ''}`
                    : !models.length
                        ? 'Ollama is running, but no generation models are installed. Install one, for example: ollama pull qwen2.5:1.5b.'
                        : 'Choose an installed local Ollama model. Every model uses the same StockRAG retrieval, calculations, citation rules, and answer structure.';
            } catch (_) {
                for (const select of [settingsSelect, chatSelect]) {
                    const option = document.createElement('option');
                    option.value = selected;
                    option.textContent = `${selected} — model list unavailable`;
                    option.disabled = true;
                    select.append(option);
                    select.disabled = true;
                }
                document.getElementById('chat-model-status').textContent = 'Model list unavailable';
            }
        }

        async function switchChatModel(model) {
            const select = document.getElementById('chat-model-select');
            const status = document.getElementById('chat-model-status');
            const previous = currentSettings.ai_model || document.getElementById('set-model').value;
            if (!model || model === previous) return;
            select.disabled = true;
            status.textContent = 'Switching…';
            try {
                const response = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ai_model:model})});
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail?.message || data.detail || data.error?.message || 'Model switch failed');
                currentSettings = {...currentSettings, ...data};
                document.getElementById('set-model').value = model;
                select.value = model;
                status.textContent = 'Active for next reply';
            } catch (error) {
                select.value = previous;
                status.textContent = `Switch failed: ${error.message}`;
            } finally {
                select.disabled = false;
            }
        }

        function setupComparisonSelectors() {
            document.querySelectorAll('.compare-symbol').forEach((select, index) => {
                select.innerHTML = popularSymbols.map(symbol => `<option value="${symbol}">${symbol}</option>`).join('');
                select.value = ['RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS'][index];
            });
        }

        async function loadComparisons() {
            const period = document.getElementById('compare-period').value;
            const note = document.getElementById('comparison-note');
            if (compareResizeObserver) compareResizeObserver.disconnect();
            for (const chart of comparisonCharts.values()) chart.remove();
            comparisonCharts.clear();
            const jobs = [...document.querySelectorAll('.compare-symbol')].map(async (select, index) => {
                const symbol = select.value;
                const container = document.getElementById(`compare-chart-${index}`);
                container.textContent = 'Loading historical prices…';
                document.getElementById(`compare-source-${index}`).textContent = '';
                try {
                    const response = await fetch(`/api/stocks/${encodeURIComponent(symbol)}/history?period=${period}&interval=1d`);
                    const result = await response.json();
                    if (!response.ok || !result.success || !result.data?.length) throw new Error(result.error?.message || 'Provider returned no price history');
                    const rows = result.data.filter(row => Number(row.Close) > 0);
                    if (!rows.length) throw new Error('No usable closing prices');
                    const base = Number(rows[0].Close);
                    const chart = LightweightCharts.createChart(container, {
                        width: container.clientWidth || 300, height: 144,
                        layout: {background:{type:'solid',color:'transparent'},textColor:'#777780'},
                        grid:{vertLines:{visible:false},horzLines:{color:'rgba(0,0,0,.06)'}},
                        rightPriceScale:{visible:false}, timeScale:{borderVisible:false},
                    });
                    const series = chart.addLineSeries({color:['#0A84FF','#8B5CF6','#F59E0B','#14B8A6'][index],lineWidth:2,priceFormat:{type:'custom',formatter:value=>`${value.toFixed(1)}`} });
                    series.setData(rows.map(row => ({time:String(row.Date).slice(0,10),value:Number((Number(row.Close)/base*100).toFixed(2))})));
                    chart.timeScale().fitContent();
                    comparisonCharts.set(index, chart);
                    document.getElementById(`compare-source-${index}`).textContent = `${result.source || 'Unknown source'} · ${result.data_status || 'freshness unknown'} · last bar ${result.last_bar_at || rows[rows.length-1].Date || 'unknown'}`;
                } catch (error) {
                    const message = document.createElement('span');
                    message.className = 'text-xs text-apple-gray';
                    message.textContent = `${symbol}: ${error.message}. `;
                    const retry = document.createElement('button');
                    retry.className = 'min-h-11 px-2 text-apple-blue';
                    retry.textContent = 'Retry';
                    retry.addEventListener('click', loadComparisons, {once:true});
                    container.replaceChildren(message,retry);
                }
            });
            await Promise.all(jobs);
            compareResizeObserver = new ResizeObserver(entries => entries.forEach(entry => {
                const index = Number(entry.target.id.split('-').at(-1));
                comparisonCharts.get(index)?.applyOptions({width:Math.floor(entry.contentRect.width)});
            }));
            document.querySelectorAll('[id^="compare-chart-"]').forEach(el => compareResizeObserver.observe(el));
            note.textContent = 'Panels show provider-backed historical prices rebased to 100. Quotes may be delayed or freshness-unverified; this is not a real-time consolidated feed.';
        }

        function escapeHtml(value) {
            return String(value ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
        }

        async function loadDocuments() {
            const container = document.getElementById('document-list');
            try {
                const res = await fetch('/api/documents');
                if (!res.ok) throw new Error('Document list unavailable');
                const {documents} = await res.json();
                knownDocuments = documents;
                const pdfs = documents.filter(doc => doc.type === 'pdf');
                container.innerHTML = documents.length ? documents.map(doc => `<label class="flex min-h-11 items-center gap-3 rounded-xl px-2 hover:bg-black/5 dark:hover:bg-white/5"><input type="checkbox" class="h-4 w-4 accent-[var(--accent)]" ${doc.type === 'pdf' ? `data-document-id="${doc.id}" ${selectedDocumentIds.includes(doc.id) ? 'checked' : ''}` : doc.type === 'dataset' ? `data-dataset-id="${doc.id}" ${activeDatasetId === doc.id ? 'checked' : ''}` : 'disabled'} ${doc.status !== 'completed' ? 'disabled' : ''}><span class="min-w-0 flex-1 truncate">${escapeHtml(doc.filename)}</span><span class="text-xs ${doc.status === 'completed' ? 'text-apple-green' : doc.status === 'failed' ? 'text-apple-red' : 'text-apple-gray'}">${escapeHtml(doc.status)}</span></label>`).join('') : '<p class="text-apple-gray">No uploaded documents yet.</p>';
                container.querySelectorAll('[data-document-id]').forEach(input => input.addEventListener('change', () => {
                    const id = Number(input.dataset.documentId);
                    selectedDocumentIds = input.checked ? [...new Set([...selectedDocumentIds,id])] : selectedDocumentIds.filter(item => item !== id);
                    localStorage.setItem('stockrag.documentIds', JSON.stringify(selectedDocumentIds));
                }));
                container.querySelectorAll('[data-dataset-id]').forEach(input => input.addEventListener('change', () => {
                    activeDatasetId = input.checked ? Number(input.dataset.datasetId) : null;
                    if (activeDatasetId) localStorage.setItem('stockrag.datasetId', String(activeDatasetId));
                    else localStorage.removeItem('stockrag.datasetId');
                    container.querySelectorAll('[data-dataset-id]').forEach(other => { if (other !== input) other.checked = false; });
                }));
                renderChatAttachments();
            } catch (error) {
                container.innerHTML = `<p class="text-apple-red">${escapeHtml(error.message)} <button class="underline" onclick="loadDocuments()">Retry</button></p>`;
            }
        }

        async function saveSettings() {
            showLoading(true);
            try {
                const settings = {
                    ai_model: document.getElementById('set-model').value.trim(),
                    temperature: parseFloat(document.getElementById('set-temp').value),
                    context_size: parseInt(document.getElementById('set-ctx').value),
                    citation_visibility: document.getElementById('set-cite').checked
                };
                document.querySelectorAll('[data-setting]').forEach(control => {
                    const {setting} = control.dataset;
                    settings[setting] = control.type === 'checkbox' ? control.checked : control.type === 'number' ? Number(control.value) : control.value;
                });
                const res = await fetch('/api/settings', {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(settings)
                });
                if (!res.ok) throw new Error('Settings could not be saved');
                currentSettings = await res.json();
                applyTheme(currentSettings.theme, currentSettings.ui_density);
                toggleModal('settings-modal');
                checkHealth();
            } catch (e) {
                console.error(e);
                alert(e.message || "Failed to save settings");
            }
            showLoading(false);
        }

        function showLoading(show) {
            const el = document.getElementById('global-loading');
            if (show) {
                el.classList.remove('opacity-0', 'pointer-events-none');
            } else {
                el.classList.add('opacity-0', 'pointer-events-none');
            }
        }

        // Formatters
        function formatNumber(num) {
            if (num === null || num === undefined) return 'N/A';
            if (num >= 1e12) return (num / 1e12).toFixed(2) + 'T';
            if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
            if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
            return num.toLocaleString();
        }

        function renderMetricsCard(key, val) {
            let displayVal = val;
            if (typeof val === 'number') {
                displayVal = Number.isInteger(val) ? val.toLocaleString() : val.toFixed(2);
            }
            const cleanKey = key.replace(/([A-Z])/g, ' $1').replace(/_/g, ' ').trim();
            const title = cleanKey.charAt(0).toUpperCase() + cleanKey.slice(1);
            
            return `
                <div class="metric-card">
                    <div class="text-[10px] font-bold uppercase tracking-widest text-apple-gray mb-1.5">${title}</div>
                    <div class="text-xl font-bold tracking-tight">${displayVal}</div>
                </div>
            `;
        }

        function simulateSearch(symbol) {
            document.getElementById('symbol-input').value = symbol;
            handleSearch();
        }

        // Main Search Logic
        async function handleSearch() {
            const inputEl = document.getElementById('symbol-input');
            const input = inputEl.value.trim();
            if (!input) return;

            // Natural language detection (if long or has spaces) -> send to chat
            if (input.includes(' ') || input.length > 10) {
                if (window.innerWidth < 1024) toggleChatMobile();
                document.getElementById('chat-input').value = input;
                inputEl.value = '';
                sendChatMessage();
                return;
            }

            let symbol = input.toUpperCase();
            const exchangeSuffix = {IN:'.NS',UK:'.L',CA:'.TO',AU:'.AX'}[currentSettings.default_market_exchange];
            if (exchangeSuffix && !symbol.includes('.') && !symbol.includes('-')) symbol += exchangeSuffix;
            inputEl.blur(); // dismiss keyboard

            let resolution;
            try {
                const resolveResponse = await fetch(`/api/symbols/resolve/${encodeURIComponent(symbol)}`);
                resolution = await resolveResponse.json();
                if (!resolveResponse.ok) throw new Error(resolution.error?.message || 'Invalid symbol format');
                symbol = resolution.resolved_symbol;
            } catch (error) {
                currentSymbol = null;
                document.getElementById('empty-state').classList.add('hidden');
                document.getElementById('stock-view').classList.remove('hidden');
                document.getElementById('stock-symbol').textContent = input.toUpperCase();
                document.getElementById('stock-name').textContent = `${error.message}. Enter a valid ticker symbol and retry.`;
                document.getElementById('stock-price').textContent = '—';
                document.getElementById('stock-status').classList.add('hidden');
                document.getElementById('basic-metrics').replaceChildren();
                renderRetryState('mainChart', 'Resolve a valid ticker before loading its chart.', () => handleSearch());
                document.getElementById('quote-retry').classList.remove('hidden');
                return;
            }
            
            document.getElementById('empty-state').classList.add('hidden');
            document.getElementById('stock-view').classList.remove('hidden');
            
            document.getElementById('stock-symbol').textContent = symbol;
            document.getElementById('stock-name').textContent = `Loading ${resolution.exchange} market data…`;
            document.getElementById('quote-retry').classList.add('hidden');
            document.getElementById('stock-status').classList.add('hidden');
            document.getElementById('stock-price').textContent = '—';
            currentSymbol = symbol;
            loadComparisons();

            // Reset UI
            document.getElementById('basic-metrics').innerHTML = '<div class="col-span-4 text-center py-10 opacity-50"><div class="loading-dot inline-block w-2 h-2 bg-black dark:bg-white rounded-full mx-1"></div><div class="loading-dot inline-block w-2 h-2 bg-black dark:bg-white rounded-full mx-1" style="animation-delay: 0.2s"></div><div class="loading-dot inline-block w-2 h-2 bg-black dark:bg-white rounded-full mx-1" style="animation-delay: 0.4s"></div></div>';
            if (mainChartInstance) mainChartInstance.remove();
            if (chartResizeObserver) chartResizeObserver.disconnect();
            document.getElementById('news-badge').textContent = '0';

            try {
                // Fetch basic data in parallel
                const [profileRes, quoteRes, newsRes] = await Promise.all([
                    fetch(`/api/stocks/${symbol}`),
                    fetch(`/api/stocks/${symbol}/quote`),
                    fetch(`/api/stocks/${symbol}/news`)
                ]);
                
                if (!quoteRes.ok) {
                    const failure = await quoteRes.json().catch(() => ({}));
                    const message = failure.error?.message || failure.detail || `No quote is available for ${symbol}.`;
                    document.getElementById('stock-name').textContent = `${message} Check the ticker or retry when providers recover.`;
                    document.getElementById('basic-metrics').innerHTML = '';
                    const status = document.getElementById('stock-status');
                    status.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-gray-500/10 text-apple-gray uppercase';
                    status.textContent = 'MARKET DATA UNAVAILABLE';
                    document.getElementById('stock-price').textContent = '—';
                    renderRetryState('mainChart', 'Price history is unavailable from configured providers.', () => loadChartData(currentSettings.default_chart_period || '1mo'));
                    renderRetryState('technical-metrics', 'Technical metrics need available historical prices.', () => handleSearch());
                    renderRetryState('fundamental-metrics', 'Fundamentals are unavailable from configured providers.', () => handleSearch());
                    renderRetryState('news-container', 'News is unavailable from configured providers.', () => handleSearch());
                    document.getElementById('quote-retry').classList.remove('hidden');
                    return;
                }
                document.getElementById('quote-retry').classList.add('hidden');
                if (profileRes.ok) {
                    const profile = await profileRes.json();
                    document.getElementById('stock-name').textContent = profile.name || symbol;
                } else document.getElementById('stock-name').textContent = `${symbol} · company profile unavailable`;
                
                if (quoteRes.ok) {
                    const quote = await quoteRes.json();
                    if (quote.success !== false) {
                        const price = Number(quote.price);
                        document.getElementById('stock-price').textContent = `${quote.currency || ''} ${price.toFixed(2)}`.trim();
                        
                        const changeEl = document.getElementById('stock-change');
                        const iconEl = document.getElementById('stock-trend-icon');
                        const containerEl = document.getElementById('stock-change-container');
                        
                        const isUp = Number(quote.change) >= 0;
                        const hasChange = quote.change !== null && quote.change !== undefined && quote.change_percent !== null && quote.change_percent !== undefined;
                        changeEl.textContent = hasChange ? `${isUp ? '+' : ''}${Number(quote.change).toFixed(2)} (${isUp ? '+' : ''}${Number(quote.change_percent).toFixed(2)}%)` : 'Change unavailable';
                        
                        containerEl.className = `text-xl font-semibold mt-2 flex items-center md:justify-end gap-1.5 transition-colors ${hasChange ? (isUp ? 'text-apple-green' : 'text-apple-red') : 'text-apple-gray'}`;
                        iconEl.setAttribute('data-lucide', isUp ? 'trending-up' : 'trending-down');
                        lucide.createIcons();

                        document.getElementById('stock-exchange').textContent = quote.exchange || 'MKT';
                        document.getElementById('quote-data-source').textContent = `${quote.source || 'Provider unknown'} · ${quote.data_status || quote.status || 'freshness unknown'} · retrieved ${quote.retrieved_at || 'time unavailable'}`;
                        
                        const statusBadge = document.getElementById('stock-status');
                        statusBadge.classList.remove('hidden');
                        if (['CACHED','DELAYED','DELAYED_OR_UNVERIFIED','DELAYED_OR_END_OF_DAY','UNVERIFIED_FRESHNESS'].includes(quote.status)) {
                            statusBadge.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-orange-500/10 text-orange-500 uppercase';
                            statusBadge.textContent = quote.status.replaceAll('_',' ');
                        } else {
                            statusBadge.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-gray-500/10 text-apple-gray uppercase';
                            statusBadge.textContent = quote.status || 'STATUS UNKNOWN';
                        }
                        
                        document.getElementById('basic-metrics').innerHTML = 
                            renderMetricsCard('Volume', quote.volume) +
                            renderMetricsCard('Market Cap', formatNumber(quote.market_cap)) +
                            renderMetricsCard('Prev Close', quote.previous_close) +
                            renderMetricsCard('Open', quote.open);
                    } else {
                        document.getElementById('stock-name').textContent = 'Symbol not found';
                        document.getElementById('basic-metrics').innerHTML = '';
                    }
                }

                // Load initial chart
                loadChartData(currentSettings.default_chart_period || '1mo');
                loadComparisons();

                // News
                if (newsRes.ok) {
                    const news = await newsRes.json();
                    const container = document.getElementById('news-container');
                    if (news.news && news.news.length > 0) {
                        document.getElementById('news-badge').textContent = news.news.length > 9 ? '9+' : news.news.length;
                        container.innerHTML = news.news.slice(0, 10).map(item => {
                            let href = '#';
                            try { const candidate = new URL(item.url); if (['https:','http:'].includes(candidate.protocol)) href = candidate.href; } catch (_) {}
                            return `
                            <a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" class="glass-panel p-5 rounded-2xl hover:border-apple-blue transition-all group block">
                                <h4 class="text-sm font-bold mb-2 group-hover:text-apple-blue transition-colors line-clamp-2">${escapeHtml(item.title)}</h4>
                                <div class="text-xs text-apple-gray flex items-center gap-2 mt-auto">
                                    <i data-lucide="newspaper" class="w-3 h-3"></i>
                                    ${escapeHtml(item.publisher)} • ${item.published_at ? new Date(item.published_at).toLocaleDateString() : 'Date unavailable'}
                                </div>
                            </a>
                        `}).join('');
                        lucide.createIcons();
                    } else if (news.success === false) {
                        renderRetryState('news-container', news.error || 'News is unavailable from current providers.', () => handleSearch());
                    } else {
                        container.innerHTML = '<div class="col-span-2 text-center py-10 text-apple-gray">No recent news available.</div>';
                    }
                } else renderRetryState('news-container', 'News is unavailable from the current provider.', () => handleSearch());

                // Async fetch tech/fund to not block UI
                fetch(`/api/stocks/${symbol}/technical`).then(r=>r.json()).then(tech => {
                    if (tech.metrics) {
                        let html =
                            Object.entries(tech.metrics).filter(([_, v]) => v != null)
                                  .map(([k, v]) => renderMetricsCard(k, v)).join('');
                        if (tech.scenario_estimate) {
                            const forecast = tech.scenario_estimate;
                            html += `<div class="metric-card col-span-full"><h4 class="text-sm font-bold">${escapeHtml(forecast.horizon_trading_days)}-session statistical scenario range</h4><p class="mt-2 text-xs text-apple-gray">Central estimate ${escapeHtml(Number(forecast.central_estimate).toFixed(2))}; 80% scenario interval ${escapeHtml(Number(forecast.lower_80_percent).toFixed(2))}–${escapeHtml(Number(forecast.upper_80_percent).toFixed(2))}. Historical drift and volatility model; not a validated forecast. Baseline holdout MAE: ${forecast.persistence_baseline_holdout_mae == null ? 'unavailable' : escapeHtml(Number(forecast.persistence_baseline_holdout_mae).toFixed(2))}.</p><p class="mt-1 text-xs text-apple-gray">${escapeHtml(forecast.limitations)}</p></div>`;
                        }
                        document.getElementById('technical-metrics').innerHTML = html;
                    } else renderRetryState('technical-metrics', 'Technical data is unavailable.', () => handleSearch());
                }).catch(() => renderRetryState('technical-metrics', 'Technical data is unavailable.', () => handleSearch()));
                fetch(`/api/stocks/${symbol}/fundamentals`).then(r=>r.json()).then(fund => {
                    if (fund.metrics) {
                        document.getElementById('fundamental-metrics').innerHTML = 
                            Object.entries(fund.metrics).filter(([_, v]) => v != null)
                                  .map(([k, v]) => renderMetricsCard(k, v)).join('');
                    } else renderRetryState('fundamental-metrics', 'Fundamentals are unavailable from the current provider.', () => handleSearch());
                }).catch(() => renderRetryState('fundamental-metrics', 'Fundamentals are unavailable.', () => handleSearch()));

            } catch (error) {
                console.error("Fetch error:", error);
            }
        }

        // Charting
        async function loadChartData(period) {
            if (!currentSymbol) return;
            
            // Update UI buttons
            document.querySelectorAll('.chart-period-btn').forEach(b => b.classList.toggle('active', b.getAttribute('onclick')?.includes(`'${period}'`)));
            
            const loader = document.getElementById('chart-loading');
            loader.classList.remove('hidden');

            try {
                const interval = currentSettings.default_chart_interval || '1d';
                const res = await fetch(`/api/stocks/${currentSymbol}/history?period=${encodeURIComponent(period)}&interval=${encodeURIComponent(interval)}`);
                if (!res.ok) throw new Error('Chart request failed');
                const data = await res.json();
                
                if (data.success && data.data && data.data.length > 0) {
                    document.getElementById('chart-source-status').textContent = `${data.source || 'Provider unknown'} · ${data.data_status || 'historical data'} · last bar ${data.last_bar_at || data.data.at(-1)?.Date || 'unknown'}`;
                    renderChart(data.data);
                } else renderRetryState('mainChart', 'Chart data unavailable.', () => loadChartData(period));
            } catch (e) {
                console.warn("Chart data request failed:", e.message);
                document.getElementById('chart-source-status').textContent = 'Provider unavailable';
                renderRetryState('mainChart', 'Chart data unavailable from configured providers.', () => loadChartData(period));
            }
            loader.classList.add('hidden');
        }

        function renderChart(historyData) {
            
            // Initialize new lightweight chart
            const chartContainer = document.getElementById('mainChart');
            if (mainChartInstance) mainChartInstance.remove();
            if (chartResizeObserver) chartResizeObserver.disconnect();
            chartContainer.innerHTML = '';
            mainChartInstance = LightweightCharts.createChart(chartContainer, {
                layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8E8E93' },
                grid: { vertLines: { color: 'rgba(0,0,0,0.05)' }, horzLines: { color: 'rgba(0,0,0,0.05)' } },
                rightPriceScale: { borderVisible: false },
                timeScale: { borderVisible: false }
            });
            const series = chartMode === 'candlestick'
                ? mainChartInstance.addCandlestickSeries({ upColor:'#30D158', downColor:'#FF453A', borderVisible:false, wickUpColor:'#30D158', wickDownColor:'#FF453A' })
                : mainChartInstance.addLineSeries({ color: '#0A84FF', lineWidth: 2 });
            
            // map history data
            const cData = historyData.map(d => {
                const dateField = d.Date || d.Datetime;
                const time = dateField.includes(' ') ? Math.floor(new Date(dateField).getTime() / 1000) : dateField.slice(0,10);
                return chartMode === 'candlestick'
                    ? {time, open:Number(d.Open), high:Number(d.High), low:Number(d.Low), close:Number(d.Close)}
                    : {time, value:Number(d.Close)};
            }).sort((a, b) => typeof a.time === 'string' ? a.time.localeCompare(b.time) : a.time - b.time);
            
            series.setData(cData);
            mainChartInstance.timeScale().fitContent();
            chartResizeObserver = new ResizeObserver(entries => {
                const {width,height} = entries[0].contentRect;
                mainChartInstance?.applyOptions({width:Math.floor(width),height:Math.floor(height)});
            });
            chartResizeObserver.observe(chartContainer);
            
            document.getElementById('chart-loading').classList.add('hidden');
        }

        // Chat functionality
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const msg = input.value.trim();
            if (!msg) return;

            appendChat('user', msg);
            renderChatAttachments();
            input.value = '';
            input.style.height = '52px';
            
            const typingId = 'typing-' + Date.now();
            appendChat('assistant', '<p role="status" class="m-0 text-apple-gray"><span class="inline-flex gap-1 align-middle mr-2"><i class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></i><i class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></i><i class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></i></span>Checking relevant sources and preparing the analysis…</p>', null, typingId);

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: msg,
                        symbol: currentSymbol,
                        dataset_id: activeDatasetId,
                        document_ids: selectedDocumentIds,
                        session_id: chatSessionId,
                        mode: currentSettings.default_chat_mode || 'auto'
                    })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error?.message || 'The request failed. Please retry.');
                if (data.session_id) {
                    chatSessionId = data.session_id;
                    localStorage.setItem('stockrag.sessionId', chatSessionId);
                }
                document.getElementById(typingId).remove();
                appendChat('assistant', data.answer, currentSettings.citation_visibility === false || currentSettings.show_data_sources === false ? null : data.citations, null, data.data_status, {
                    model: data.model, timestamp: data.data_timestamp, retrieval: data.retrieval,
                    sourcesUnverified: data.sources_unverified, formatUnverified: data.format_unverified,
                    numericValidation: data.numeric_validation
                });
                
            } catch (err) {
                document.getElementById(typingId)?.remove();
                appendChat('assistant', `The analysis service could not produce a reply. ${err.message || 'Check the local AI service and retry.'}`, null, null, 'SERVICE_ERROR');
                const retry = document.createElement('button');
                retry.className = 'mt-2 min-h-11 rounded-xl px-3 font-semibold text-apple-blue hover:bg-black/5';
                retry.textContent = 'Retry question';
                retry.addEventListener('click', () => { input.value = msg; sendChatMessage(); }, {once:true});
                document.getElementById('chat-messages').lastElementChild?.append(retry);
            }
        }

        function appendChat(role, content, citations = null, id = null, status = null, meta = null) {
            const container = document.getElementById('chat-messages');
            if (role === 'assistant' && (currentSettings.citation_visibility === false || currentSettings.show_data_sources === false)) content = content.replace(/\n## Sources[\s\S]*$/i, '');
            
            let bubbleHtml = '';
            if (role === 'user') {
                bubbleHtml = `
                    <div class="flex flex-col gap-1 items-end ml-auto max-w-[95%] animate-slide-up" ${id ? `id="${id}"` : ''}>
                        <div class="chat-bubble-user px-5 py-3 text-sm font-medium">
                            ${content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
                        </div>
                    </div>
                `;
            } else {
                // Parse markdown
                const isHtmlContent = content.includes('<div') || content.includes('<span');
                const parsedContent = isHtmlContent ? content : DOMPurify.sanitize(marked.parse(content));
                
                let extraHtml = '';
                if (status === 'SERVICE_ERROR') {
                    extraHtml += '<div role="status" class="mt-3 inline-block px-2 py-1 rounded-md text-[10px] font-bold tracking-widest bg-orange-500/10 text-orange-700 uppercase">⚠️ Service failure · no AI answer generated</div>';
                } else if (status && status !== 'LIVE' && status !== 'NOT_REQUESTED') {
                    extraHtml += `<div class="mt-3 inline-block px-2 py-1 rounded-md text-[10px] font-bold tracking-widest bg-orange-500/10 text-orange-500 uppercase">⚠️ ${status} DATA</div>`;
                }
                
                if (citations && citations.length > 0) {
                    extraHtml += `
                        <div class="mt-4 pt-3 border-t border-black/5 dark:border-white/5 text-[11px] text-apple-gray">
                            <div class="font-bold mb-2 flex items-center gap-1.5 uppercase tracking-wider"><i data-lucide="link-2" class="w-3 h-3"></i> Sources utilized</div>
                            <ul class="list-disc pl-4 space-y-1">
                                ${citations.map(c => `<li>${String(c).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</li>`).join('')}
                            </ul>
                        </div>
                    `;
                }
                if (meta) {
                    const warnings = [];
                    if (meta.sourcesUnverified) warnings.push('Source format could not be verified');
                    if (meta.formatUnverified) warnings.push('Required answer sections could not be verified');
                    if (meta.numericValidation && !['passed','repaired','not_applicable'].includes(meta.numericValidation)) warnings.push('Check numeric values against the cited evidence');
                    const time = meta.timestamp ? new Date(meta.timestamp).toLocaleString() : 'time unavailable';
                    extraHtml += `<div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-black/5 pt-2 text-[10px] text-apple-gray dark:border-white/10"><span>${escapeHtml(meta.model || 'Model unavailable')}</span><span>Data checked ${escapeHtml(time)}</span>${meta.retrieval?.mode ? `<span>${escapeHtml(meta.retrieval.mode)} retrieval</span>` : ''}${warnings.map(warning => `<span class="text-amber-700 dark:text-amber-300">${escapeHtml(warning)}</span>`).join('')}</div>`;
                }

                bubbleHtml = `
                    <div class="flex gap-3 items-end max-w-[95%] animate-slide-up" ${id ? `id="${id}"` : ''}>
                        <div class="w-6 h-6 rounded-full bg-gradient-to-tr from-blue-600 to-purple-500 flex-shrink-0 mb-1 flex items-center justify-center">
                            <i data-lucide="sparkles" class="w-3 h-3 text-white"></i>
                        </div>
                        <div class="chat-bubble-ai p-5 text-sm prose prose-sm dark:prose-invert prose-p:leading-relaxed prose-a:text-apple-blue w-full">
                            ${parsedContent}
                            ${extraHtml}
                        </div>
                    </div>
                `;
            }
            
            container.insertAdjacentHTML('beforeend', bubbleHtml);
            lucide.createIcons();
            
            setTimeout(() => {
                container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
            }, 100);
        }

        function setChartStyle(style) {
            chartMode = style === 'candlestick' ? 'candlestick' : 'line';
            document.querySelectorAll('.chart-style-btn').forEach(button => {
                const active = button.textContent.toLowerCase() === (chartMode === 'candlestick' ? 'candles' : 'line');
                button.classList.toggle('active', active);
                button.setAttribute('aria-pressed', String(active));
            });
            if (currentSymbol) loadChartData(currentSettings.default_chart_period || '1mo');
        }

        async function restoreChatSession() {
            if (!chatSessionId) return;
            const requestedSession = chatSessionId;
            const generation = ++chatRestoreGeneration;
            try {
                const res = await fetch(`/api/chat/sessions/${encodeURIComponent(requestedSession)}`);
                if (!res.ok) throw new Error('Saved conversation unavailable');
                const data = await res.json();
                if (generation !== chatRestoreGeneration || requestedSession !== chatSessionId) return;
                const container = document.getElementById('chat-messages');
                container.innerHTML = '';
                data.messages.forEach(message => {
                    const legacyFailure = message.role === 'assistant' && /^(?:Error:\s*Could not connect to Ollama|AI response unavailable:|Analysis failed before a response could be generated\.)/i.test(message.content);
                    if (legacyFailure) {
                        appendChat('assistant', `The analysis service did not generate a reply. ${message.content.replace(/^Error:\s*/i, '')}`, null, null, 'SERVICE_ERROR');
                    } else appendChat(message.role, message.content);
                });
            } catch (_) {
                if (generation !== chatRestoreGeneration) return;
                localStorage.removeItem('stockrag.sessionId');
                chatSessionId = null;
            }
        }

        function renderRetryState(containerId, message, retry) {
            if (containerId === 'mainChart') {
                if (mainChartInstance) mainChartInstance.remove();
                mainChartInstance = null;
                if (chartResizeObserver) chartResizeObserver.disconnect();
            }
            const container = document.getElementById(containerId);
            const text = document.createElement('p');
            text.className = 'text-apple-gray py-6';
            text.textContent = message;
            const button = document.createElement('button');
            button.className = 'ml-2 min-h-11 rounded-xl px-3 font-semibold text-apple-blue hover:bg-black/5';
            button.textContent = 'Retry';
            button.addEventListener('click', retry, {once:true});
            container.replaceChildren(text, button);
        }

        function resetChatSession() {
            chatRestoreGeneration++;
            chatSessionId = null;
            localStorage.removeItem('stockrag.sessionId');
            document.getElementById('chat-messages').innerHTML = '';
            appendChat('assistant', 'New conversation. Ask a question about market data or your indexed documents.');
        }

        function renderChatAttachments() {
            const root = document.getElementById('chat-attachments');
            if (!root) return;
            const chips = selectedDocumentIds.map(id => {
                const doc = knownDocuments.find(item => Number(item.id) === Number(id));
                const name = doc?.filename || `PDF ${Number(id)}`;
                return `<button type="button" data-remove-document="${Number(id)}" class="inline-flex min-h-9 max-w-full items-center gap-2 rounded-full border border-black/10 bg-white/70 px-3 text-xs dark:bg-white/10" title="Remove ${escapeHtml(name)} from chat scope"><span class="max-w-48 truncate">${escapeHtml(name)}</span><span aria-hidden="true">×</span></button>`;
            });
            if (activeDatasetId) {
                const doc = knownDocuments.find(item => Number(item.id) === Number(activeDatasetId));
                const name = doc?.filename || `Dataset ${Number(activeDatasetId)}`;
                chips.push(`<button type="button" data-remove-dataset class="inline-flex min-h-9 max-w-full items-center gap-2 rounded-full border border-black/10 bg-white/70 px-3 text-xs dark:bg-white/10" title="Remove ${escapeHtml(name)} from chat scope"><span class="max-w-48 truncate">${escapeHtml(name)}</span><span aria-hidden="true">×</span></button>`);
            }
            root.innerHTML = chips.join('');
            root.querySelectorAll('[data-remove-document]').forEach(button => button.addEventListener('click', () => {
                const id = Number(button.dataset.removeDocument);
                selectedDocumentIds = selectedDocumentIds.filter(value => Number(value) !== id);
                localStorage.setItem('stockrag.documentIds', JSON.stringify(selectedDocumentIds));
                renderChatAttachments(); loadDocuments();
            }));
            root.querySelector('[data-remove-dataset]')?.addEventListener('click', () => {
                activeDatasetId = null; localStorage.removeItem('stockrag.datasetId'); renderChatAttachments(); loadDocuments();
            });
        }

        // RAG Upload & Crawl
        async function uploadFile() { return uploadSelectedFile(document.getElementById('file-upload'), false); }
        async function uploadChatFile() { return uploadSelectedFile(document.getElementById('chat-file-upload'), true); }

        async function uploadSelectedFile(input, fromChat) {
            const file = input.files[0];
            if(!file) return;

            const isPdf = file.name.toLowerCase().endsWith('.pdf');
            const type = isPdf ? 'pdf' : 'dataset';
            const status = document.getElementById('upload-status');
            const attachments = document.getElementById('chat-attachments');
            
            if (!fromChat) {
                status.classList.remove('hidden');
                status.className = 'text-sm font-bold p-3 rounded-xl bg-orange-500/10 text-orange-500 flex items-center justify-center gap-2 mt-4';
                status.textContent = `Processing ${file.name}...`;
            } else {
                attachments.textContent = `Processing ${file.name}…`;
                attachments.setAttribute('role','status');
            }
            
            const fd = new FormData();
            fd.append('file', file);
            
            try {
                const res = await fetch(`/api/upload/${type}`, { method: 'POST', body: fd });
                const data = await res.json();
                if (res.ok) {
                    if (!fromChat) {
                        status.className = 'text-sm font-bold p-3 rounded-xl bg-green-500/10 text-green-500 flex items-center justify-center gap-2 mt-4';
                        status.textContent = 'Upload processed successfully.';
                    }
                    if(type === 'dataset') {
                        activeDatasetId = data.document_id;
                        localStorage.setItem('stockrag.datasetId', String(activeDatasetId));
                    } else {
                        selectedDocumentIds = [...new Set([...selectedDocumentIds, Number(data.document_id)])];
                        localStorage.setItem('stockrag.documentIds', JSON.stringify(selectedDocumentIds));
                    }
                    await loadDocuments();
                    renderChatAttachments();
                    lucide.createIcons();
                    if (!fromChat) setTimeout(() => toggleModal('docs-modal'), 2000);
                } else {
                    throw new Error(data.error?.message || data.detail || 'Upload failed');
                }
            } catch (e) {
                if (!fromChat) {
                    status.className = 'text-sm font-bold p-3 rounded-xl bg-red-500/10 text-red-500 flex items-center justify-center gap-2 mt-4';
                    status.textContent = `Upload failed: ${e.message}`;
                } else attachments.textContent = `Upload failed: ${e.message}`;
            } finally {
                input.value = '';
            }
        }

        async function crawlUrl() {
            const input = document.getElementById('crawl-url');
            const url = input.value.trim();
            if(!url) return;
            
            const status = document.getElementById('upload-status');
            status.classList.remove('hidden');
            status.className = 'text-sm font-bold p-3 rounded-xl bg-blue-500/10 text-blue-500 flex items-center justify-center gap-2 mt-4';
            status.innerHTML = `<div class="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div> Crawling and indexing...`;

            try {
                const res = await fetch('/api/crawl', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });
                if(res.ok) {
                    status.className = 'text-sm font-bold p-3 rounded-xl bg-green-500/10 text-green-500 flex items-center justify-center gap-2 mt-4';
                    status.textContent = 'Web page indexed successfully.';
                    await loadDocuments();
                    input.value = '';
                    lucide.createIcons();
                    setTimeout(() => toggleModal('docs-modal'), 2000);
                } else {
                    const error = await res.json().catch(()=>({}));
                    throw new Error(error.error?.message || error.detail || 'Research request failed');
                }
            } catch (e) {
                status.className = 'text-sm font-bold p-3 rounded-xl bg-red-500/10 text-red-500 flex items-center justify-center gap-2 mt-4';
                status.textContent = `Research failed: ${e.message}`;
            }
        }

        // System Health
        async function checkHealth() {
            try {
                const res = await fetch('/api/health');
                if (!res.ok) throw new Error('Health check failed');
                const data = await res.json();
                const apiDot = document.getElementById('status-api');
                const aiDot = document.getElementById('status-ollama');
                const setDot = (element, ok, label) => {
                    element.style.background = ok ? '#0a84ff' : '#f59e0b';
                    element.title = label;
                    element.setAttribute('aria-label', label);
                };
                setDot(apiDot, data.market_data?.status === 'available', `Market data: ${data.market_data?.provider || data.market_data?.status || 'unknown'}`);
                setDot(aiDot, data.ollama === 'connected' && data.model_available, `Ollama ${data.ollama}; model ${data.model}${data.model_available ? ' ready' : ' unavailable'}`);
                const retrievalMode = data.document_retrieval || 'unavailable';
                const ragReady = retrievalMode === 'semantic' || retrievalMode === 'keyword' || retrievalMode === 'available';
                const retrievalLabel = retrievalMode === 'keyword' ? 'keyword fallback' : retrievalMode === 'semantic' || retrievalMode === 'available' ? 'semantic search' : 'unavailable';
                setDot(document.getElementById('status-chroma'), ragReady, `Document retrieval: ${retrievalLabel}; embedding model ${data.embedding_model || 'unknown'} ${data.embedding_model_available ? 'installed' : 'missing'}`);
                document.getElementById('status-api-text').textContent = data.market_data?.status === 'available' ? (data.market_data?.data_status || 'Connected') : 'Unavailable';
                document.getElementById('status-api-text').title = data.market_data?.error || `${data.market_data?.provider || 'Market provider'} · ${data.market_data?.data_status || ''}`;
                document.getElementById('status-ollama-text').textContent = data.ollama === 'connected' && data.model_available ? 'Ready' : 'Unavailable';
                document.getElementById('status-chroma-text').textContent = retrievalMode === 'keyword' ? 'Keyword' : ragReady ? 'Ready' : 'Unavailable';
                const allReady = data.market_data?.status === 'available' && data.ollama === 'connected' && data.model_available && ragReady;
                const summary = allReady ? 'Ready' : data.market_data?.status !== 'available' ? 'Market offline' : data.ollama !== 'connected' || !data.model_available ? 'AI offline' : 'Docs offline';
                document.getElementById('status-summary').textContent = summary;
                document.getElementById('status-summary-dot').style.background = allReady ? '#0a84ff' : '#f59e0b';
                document.getElementById('header-health').title = `Market: ${data.market_data?.status || 'unknown'} (${data.market_data?.data_status || 'unknown freshness'}); Ollama: ${data.ollama}, model ${data.model_available ? 'ready' : 'unavailable'}; document retrieval: ${retrievalLabel}${retrievalMode === 'keyword' ? ` (${data.embedding_model || 'embedding model'} missing)` : ''}`;
                apiDot.dataset.vectorStatus = data.vector_database;
                const engine = document.getElementById('chat-engine-status');
                const ready = data.ollama === 'connected' && data.model_available;
                const indicator = engine.querySelector('span');
                if (indicator) indicator.style.background = ready ? '#0a84ff' : '#f59e0b';
                engine.lastChild.textContent = ready ? ' Local model ready' : ' Local model unavailable';
            } catch (e) {
                document.getElementById('status-api').style.background = '#f59e0b';
                document.getElementById('status-ollama').style.background = '#f59e0b';
                document.getElementById('status-chroma').style.background = '#f59e0b';
                document.getElementById('status-api-text').textContent = 'Check failed';
                document.getElementById('status-ollama-text').textContent = 'Check failed';
                document.getElementById('status-chroma-text').textContent = 'Check failed';
                document.getElementById('status-summary').textContent = 'Check failed';
                document.getElementById('status-summary-dot').style.background = '#f59e0b';
            }
        }
        setInterval(checkHealth, 30000);
        setupComparisonSelectors();
        checkHealth();
        fetchSettings();
        restoreChatSession();
