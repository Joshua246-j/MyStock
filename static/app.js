// Init Icons
        lucide.createIcons();

        let currentSymbol = null;
        let activeDataset = null;
        let mainChartInstance = null;
        let chatSessionId = localStorage.getItem('stockrag.sessionId') || null;
        let currentSettings = {};

        const EXTRA_SETTINGS = [
            ['response_detail','Response detail','select',['concise','balanced','detailed']],
            ['default_chat_mode','Default chat mode','select',['auto','market','documents','general']],
            ['max_retrieved_documents','Max retrieved passages','number'],
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

        function applyTheme(theme) {
            document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
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
            
            event.currentTarget.classList.add('active');
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
                document.getElementById('set-model').value = data.ai_model ?? 'gemma3:4b';
                document.getElementById('set-temp').value = data.temperature ?? 0.2;
                document.getElementById('set-ctx').value = data.context_size ?? 4096;
                document.getElementById('set-cite').checked = data.citation_visibility !== false;
                renderSettingsControls(data);
                applyTheme(data.theme);
            } catch (e) { console.warn("Failed to load settings", e); }
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
                applyTheme(currentSettings.theme);
                await checkHealth();
                toggleModal('settings-modal');
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

            const symbol = input.toUpperCase();
            inputEl.blur(); // dismiss keyboard
            
            document.getElementById('empty-state').classList.add('hidden');
            document.getElementById('stock-view').classList.remove('hidden');
            
            document.getElementById('stock-symbol').textContent = symbol;
            document.getElementById('stock-name').textContent = 'Fetching data...';
            currentSymbol = symbol;

            // Reset UI
            document.getElementById('basic-metrics').innerHTML = '<div class="col-span-4 text-center py-10 opacity-50"><div class="loading-dot inline-block w-2 h-2 bg-black dark:bg-white rounded-full mx-1"></div><div class="loading-dot inline-block w-2 h-2 bg-black dark:bg-white rounded-full mx-1" style="animation-delay: 0.2s"></div><div class="loading-dot inline-block w-2 h-2 bg-black dark:bg-white rounded-full mx-1" style="animation-delay: 0.4s"></div></div>';
            if (mainChartInstance) mainChartInstance.destroy();
            document.getElementById('news-badge').textContent = '0';

            try {
                // Fetch basic data in parallel
                const [profileRes, quoteRes, newsRes] = await Promise.all([
                    fetch(`/api/stocks/${symbol}`),
                    fetch(`/api/stocks/${symbol}/quote`),
                    fetch(`/api/stocks/${symbol}/news`)
                ]);
                
                if (!profileRes.ok || !quoteRes.ok) {
                    document.getElementById('stock-name').textContent = `No market data found for ${symbol}. Check the symbol and retry.`;
                    document.getElementById('basic-metrics').innerHTML = '';
                    return;
                }
                if (profileRes.ok) {
                    const profile = await profileRes.json();
                    document.getElementById('stock-name').textContent = profile.name || symbol;
                }
                
                if (quoteRes.ok) {
                    const quote = await quoteRes.json();
                    if (quote.success !== false) {
                        const price = quote.price || 0;
                        document.getElementById('stock-price').textContent = `$${price.toFixed(2)}`;
                        
                        const changeEl = document.getElementById('stock-change');
                        const iconEl = document.getElementById('stock-trend-icon');
                        const containerEl = document.getElementById('stock-change-container');
                        
                        const isUp = quote.change >= 0;
                        changeEl.textContent = `${isUp ? '+' : ''}${quote.change.toFixed(2)} (${isUp ? '+' : ''}${quote.change_percent.toFixed(2)}%)`;
                        
                        containerEl.className = `text-xl font-semibold mt-2 flex items-center md:justify-end gap-1.5 transition-colors ${isUp ? 'text-apple-green' : 'text-apple-red'}`;
                        iconEl.setAttribute('data-lucide', isUp ? 'trending-up' : 'trending-down');
                        lucide.createIcons();

                        document.getElementById('stock-exchange').textContent = quote.exchange || 'MKT';
                        
                        const statusBadge = document.getElementById('stock-status');
                        statusBadge.classList.remove('hidden');
                        if (quote.status === 'CACHED' || quote.status === 'DELAYED') {
                            statusBadge.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-orange-500/10 text-orange-500 uppercase';
                            statusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-current"></span> ${quote.status}`;
                        } else {
                            statusBadge.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-green-500/10 text-green-500 uppercase';
                            statusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-current animate-pulse"></span> LIVE`;
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

                // News
                if (newsRes.ok) {
                    const news = await newsRes.json();
                    const container = document.getElementById('news-container');
                    if (news.news && news.news.length > 0) {
                        document.getElementById('news-badge').textContent = news.news.length > 9 ? '9+' : news.news.length;
                        container.innerHTML = news.news.slice(0, 10).map(item => `
                            <a href="${item.url}" target="_blank" class="glass-panel p-5 rounded-2xl hover:border-apple-blue transition-all group hover:scale-[1.02] block">
                                <h4 class="text-sm font-bold mb-2 group-hover:text-apple-blue transition-colors line-clamp-2">${item.title}</h4>
                                <div class="text-xs text-apple-gray flex items-center gap-2 mt-auto">
                                    <i data-lucide="newspaper" class="w-3 h-3"></i>
                                    ${item.publisher} • ${new Date(item.published_at).toLocaleDateString()}
                                </div>
                            </a>
                        `).join('');
                        lucide.createIcons();
                    } else {
                        container.innerHTML = '<div class="col-span-2 text-center py-10 text-apple-gray">No recent news available.</div>';
                    }
                }

                // Async fetch tech/fund to not block UI
                fetch(`/api/stocks/${symbol}/technical`).then(r=>r.json()).then(tech => {
                    if (tech.metrics) {
                        document.getElementById('technical-metrics').innerHTML = 
                            Object.entries(tech.metrics).filter(([_, v]) => v != null)
                                  .map(([k, v]) => renderMetricsCard(k, v)).join('');
                    } else document.getElementById('technical-metrics').innerHTML = '<p class="text-apple-gray">Technical data unavailable. Retry by searching the symbol again.</p>';
                });
                fetch(`/api/stocks/${symbol}/fundamentals`).then(r=>r.json()).then(fund => {
                    if (fund.metrics) {
                        document.getElementById('fundamental-metrics').innerHTML = 
                            Object.entries(fund.metrics).filter(([_, v]) => v != null)
                                  .map(([k, v]) => renderMetricsCard(k, v)).join('');
                    } else document.getElementById('fundamental-metrics').innerHTML = '<p class="text-apple-gray">Fundamentals unavailable from current data providers.</p>';
                });

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
                    renderChart(data.data);
                } else document.getElementById('mainChart').innerHTML = `<div class="p-6 text-center text-apple-gray">Chart data unavailable. <button class="text-apple-blue underline" onclick="loadChartData('${period}')">Retry</button></div>`;
            } catch (e) {
                console.error("Chart error:", e);
                document.getElementById('mainChart').innerHTML = `<div class="p-6 text-center text-apple-gray">Chart data unavailable. <button class="text-apple-blue underline" onclick="loadChartData('${period}')">Retry</button></div>`;
            }
            loader.classList.add('hidden');
        }

        function renderChart(historyData) {
            
            // Initialize new lightweight chart
            const chartContainer = document.getElementById('mainChart');
            chartContainer.innerHTML = '';
            mainChartInstance = LightweightCharts.createChart(chartContainer, {
                layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8E8E93' },
                grid: { vertLines: { color: 'rgba(0,0,0,0.05)' }, horzLines: { color: 'rgba(0,0,0,0.05)' } },
                rightPriceScale: { borderVisible: false },
                timeScale: { borderVisible: false }
            });
            const lineSeries = mainChartInstance.addLineSeries({ color: '#007AFF', lineWidth: 2 });
            
            // map history data
            const cData = historyData.map(d => {
                const dateField = d.Date || d.Datetime;
                let t;
                if (dateField.includes(' ')) {
                    t = new Date(dateField).getTime() / 1000;
                } else {
                    t = new Date(dateField).getTime() / 1000;
                }
                return { time: t, value: d.Close };
            }).sort((a, b) => a.time - b.time); // ensure sorted ascending
            
            lineSeries.setData(cData);
            mainChartInstance.timeScale().fitContent();
            
            document.getElementById('chart-loading').classList.add('hidden');
        }

        // Chat functionality
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const msg = input.value.trim();
            if (!msg) return;

            appendChat('user', msg);
            input.value = '';
            input.style.height = '52px';
            
            const typingId = 'typing-' + Date.now();
            appendChat('assistant', '<div class="flex gap-1 py-1"><div class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></div><div class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></div><div class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></div></div>', null, typingId);

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: msg,
                        symbol: currentSymbol,
                        dataset_path: activeDataset,
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
                appendChat('assistant', data.answer, currentSettings.citation_visibility === false ? null : data.citations, null, data.data_status);
                
            } catch (err) {
                document.getElementById(typingId)?.remove();
                appendChat('assistant', `Request failed: ${err.message || 'Unable to connect to the analysis service.'}`);
            }
        }

        function appendChat(role, content, citations = null, id = null, status = null) {
            const container = document.getElementById('chat-messages');
            
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
                if (status && status !== 'LIVE') {
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

        // RAG Upload & Crawl
        async function uploadFile() {
            const input = document.getElementById(`file-upload`);
            const file = input.files[0];
            if(!file) return;

            const isPdf = file.name.toLowerCase().endsWith('.pdf');
            const type = isPdf ? 'pdf' : 'dataset';
            const status = document.getElementById('upload-status');
            
            status.classList.remove('hidden');
            status.className = 'text-sm font-bold p-3 rounded-xl bg-orange-500/10 text-orange-500 flex items-center justify-center gap-2 mt-4';
            status.innerHTML = `<div class="w-4 h-4 border-2 border-orange-500 border-t-transparent rounded-full animate-spin"></div> Processing ${file.name}...`;
            
            const fd = new FormData();
            fd.append('file', file);
            
            try {
                const res = await fetch(`/api/upload/${type}`, { method: 'POST', body: fd });
                const data = await res.json();
                if (res.ok) {
                    status.className = 'text-sm font-bold p-3 rounded-xl bg-green-500/10 text-green-500 flex items-center justify-center gap-2 mt-4';
                    status.innerHTML = `<i data-lucide="check-circle" class="w-5 h-5"></i> Successfully embedded to knowledge base`;
                    if(type === 'dataset') activeDataset = data.dataset_path;
                    lucide.createIcons();
                    setTimeout(() => toggleModal('docs-modal'), 2000);
                } else {
                    throw new Error(data.detail);
                }
            } catch (e) {
                status.className = 'text-sm font-bold p-3 rounded-xl bg-red-500/10 text-red-500 flex items-center justify-center gap-2 mt-4';
                status.innerHTML = `<i data-lucide="x-circle" class="w-5 h-5"></i> Upload failed`;
                lucide.createIcons();
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
                    status.innerHTML = `<i data-lucide="check-circle" class="w-5 h-5"></i> Web data added to knowledge base`;
                    input.value = '';
                    lucide.createIcons();
                    setTimeout(() => toggleModal('docs-modal'), 2000);
                } else {
                    throw new Error();
                }
            } catch (e) {
                status.className = 'text-sm font-bold p-3 rounded-xl bg-red-500/10 text-red-500 flex items-center justify-center gap-2 mt-4';
                status.innerHTML = `<i data-lucide="x-circle" class="w-5 h-5"></i> Crawl failed`;
                lucide.createIcons();
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
                    element.style.background = ok ? '#30d158' : '#ff453a';
                    element.title = label;
                    element.setAttribute('aria-label', label);
                };
                setDot(apiDot, data.market_data?.status === 'available', `Market data: ${data.market_data?.provider || data.market_data?.status || 'unknown'}`);
                setDot(aiDot, data.ollama === 'connected' && data.model_available, `Ollama ${data.ollama}; model ${data.model}${data.model_available ? ' ready' : ' unavailable'}`);
                apiDot.dataset.vectorStatus = data.vector_database;
            } catch (e) {
                document.getElementById('status-api').style.background = '#ff453a';
                document.getElementById('status-ollama').style.background = '#ff453a';
            }
        }
        setInterval(checkHealth, 30000);
        checkHealth();
        fetchSettings();
