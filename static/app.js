// Init Icons
        lucide.createIcons();

        let currentSymbol = null;
        let activeDatasetId = Number(localStorage.getItem('stockrag.datasetId')) || null;
        let mainChartInstance = null;
        const comparisonCharts = new Map();
        let comparisonLoaded = false;
        const landingCharts = new Map();
        const latestMarketResults = new Map();
        let compareResizeObserver = null;
        let landingResizeObserver = null;
        let landingNewsItems = [];
        let landingNewsUpdatedAt = null;
        let landingNewsMeta = null;
        let landingNewsFilter = 'all';
        let landingNewsSearch = '';
        let newsVisibleCount = 20;
        let landingLoadGeneration = 0;
        let landingNewsGeneration = 0;
        let landingOverviewAbortController = null;
        let landingNewsAbortController = null;
        let activePrimaryView = 'dashboard';
        let watchlistOnly = false;
        const watchlistSymbols = new Set(JSON.parse(localStorage.getItem('stockrag.watchlist') || '[]'));
        const landingSymbols = [
            {symbol:'AAPL',market:'us',label:'Apple'}, {symbol:'NVDA',market:'us',label:'NVIDIA'},
            {symbol:'MSFT',market:'us',label:'Microsoft'}, {symbol:'GOOGL',market:'us',label:'Alphabet'},
            {symbol:'RELIANCE.NS',market:'india',label:'Reliance Industries'}, {symbol:'TCS.NS',market:'india',label:'Tata Consultancy Services'},
            {symbol:'HDFCBANK.NS',market:'india',label:'HDFC Bank'}, {symbol:'INFY.NS',market:'india',label:'Infosys'}
        ];
        const popularSymbols = ['RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS','ICICIBANK.NS','SBIN.NS','BHARTIARTL.NS','ITC.NS','LT.NS','BAJFINANCE.NS','KOTAKBANK.NS','MARUTI.NS','TATAMOTORS.NS','SUNPHARMA.NS','AXISBANK.NS','HINDUNILVR.NS','AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','SPY','QQQ','^NSEI','^BSESN'];
        const knownUsSymbols = new Set(['AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','SPY','QQQ']);
        let chartMode = 'line';
        let analysisView = 'price';
        let activeChartPeriod = '1mo';
        let activeChartInterval = '1d';
        let technicalRequestGeneration = 0;
        let latestHistoryData = [];
        let latestIndicatorData = [];
        let chartResizeObserver = null;
        let indicatorCharts = [];
        let indicatorResizeObservers = [];
        let chatSessionId = localStorage.getItem('stockrag.sessionId') || null;
        let chatRestoreGeneration = 0;
        let chatHistoryItems = [];
        let pendingChatDeletion = null;
        let latestProjectStatusItems = [];
        let selectedDocumentIds = JSON.parse(localStorage.getItem('stockrag.documentIds') || '[]');
        let knownDocuments = [];
        let currentSettings = {};

        function disposeMainChart() {
            const chart = mainChartInstance;
            mainChartInstance = null;
            if (chart) chart.remove();
        }

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
            if (panel.classList.contains('chat-focus')) { closeChatFocus(); return; }
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
        function toggleMoreMenu() {
            document.getElementById('more-menu')?.classList.toggle('hidden');
        }
        function toggleSystemStatus(force) {
            const panel = document.getElementById('system-status-popover');
            if (!panel) return;
            const open = force === undefined ? panel.classList.contains('hidden') : Boolean(force);
            panel.classList.toggle('hidden', !open);
            for (const trigger of [document.getElementById('header-health'), document.getElementById('chat-system-status')]) {
                trigger?.setAttribute('aria-expanded', String(open));
            }
            if (open) document.getElementById('system-status-close')?.focus();
        }
        function updateProjectStatus(items, summary, state) {
            latestProjectStatusItems = items;
            const label = document.getElementById('status-summary');
            const header = document.getElementById('header-health');
            const aiLabel = document.getElementById('chat-system-status-label');
            const aiTrigger = document.getElementById('chat-system-status');
            const dot = document.getElementById('status-summary-dot');
            if (label) label.textContent = summary;
            if (aiLabel) aiLabel.textContent = summary;
            if (header) { header.dataset.status = state; header.setAttribute('aria-label', `Project status: ${summary}`); }
            if (aiTrigger) { aiTrigger.dataset.status = state; aiTrigger.setAttribute('aria-label', `Project status: ${summary}`); }
            if (dot) dot.dataset.status = state;
            const description = document.getElementById('system-status-summary');
            const details = document.getElementById('system-status-details');
            if (description) description.textContent = summary === 'Available'
                ? 'The API and configured provider connections are available. This check does not test a full model reply, and market freshness may be unverified.'
                : summary;
            if (!details) return;
            details.replaceChildren(...items.map(item => {
                const row = document.createElement('div');
                row.className = `system-status-row ${item.state}`;
                const icon = document.createElement('i');
                icon.dataset.lucide = item.icon;
                icon.className = 'h-4 w-4 shrink-0';
                icon.setAttribute('aria-hidden', 'true');
                const text = document.createElement('div');
                text.className = 'min-w-0 flex-1';
                const heading = document.createElement('div');
                heading.className = 'flex items-center justify-between gap-2';
                const name = document.createElement('span');
                name.className = 'text-xs font-semibold';
                name.textContent = item.name;
                const stateText = document.createElement('span');
                stateText.className = 'text-[10px] font-semibold uppercase tracking-wide';
                stateText.textContent = item.label || (item.state === 'ready' ? 'Ready' : item.state === 'warning' ? 'Degraded' : 'Issue');
                const detail = document.createElement('p');
                detail.className = 'mt-0.5 break-words text-[11px] leading-relaxed text-apple-gray';
                detail.textContent = item.detail;
                heading.append(name, stateText);
                text.append(heading, detail);
                row.append(icon, text);
                return row;
            }));
            lucide.createIcons();
        }
        function toggleChatPageMenu(force) {
            const menu = document.getElementById('chat-page-menu');
            const trigger = document.querySelector('.chat-page-menu-trigger');
            if (!menu) return;
            const open = force === undefined ? menu.classList.contains('hidden') : Boolean(force);
            menu.classList.toggle('hidden', !open);
            trigger?.setAttribute('aria-expanded', String(open));
        }
        function navigateFromChat(view) {
            toggleChatPageMenu(false);
            showView(view);
        }
        function setActiveNavigation(route) {
            document.querySelectorAll('.bottom-app-nav .nav-item[data-route]').forEach(button => {
                button.classList.toggle('active', button.dataset.route === route);
                button.setAttribute('aria-current', button.dataset.route === route ? 'page' : 'false');
            });
        }
        function showView(view, updateUrl = true) {
            if (!['dashboard','watchlist','news','compare','ai'].includes(view)) return;
            toggleChatPageMenu(false);
            closeChatFocus();
            activePrimaryView = view;
            document.getElementById('stock-view').classList.add('hidden');
            document.getElementById('empty-state').classList.toggle('hidden',view !== 'dashboard');
            document.getElementById('news-page').classList.toggle('hidden',view !== 'news');
            document.getElementById('watchlist-page').classList.toggle('hidden',view !== 'watchlist');
            document.getElementById('compare-page').classList.toggle('hidden',view !== 'compare');
            document.getElementById('ai-page').classList.toggle('hidden',view !== 'ai');
            watchlistOnly = false;
            if (view === 'watchlist') renderWatchlistTable();
            renderNewsContext();
            applyWatchlistFilter();
            document.getElementById('dashboard-view').scrollTop = 0;
            if (view === 'news') loadLandingNews(landingLoadGeneration, true);
            if (view === 'compare' && !comparisonLoaded) { comparisonLoaded = true; loadComparisons(); }
            setActiveNavigation(view);
            if (updateUrl) {
                const paths = {dashboard:'/markets',watchlist:'/watchlist',news:'/news',compare:'/compare',ai:'/ai'};
                if (location.pathname !== paths[view]) history.pushState({view},'',paths[view]);
            }
        }
        function restoreLocation() {
            const path = location.pathname;
            if (path === '/news') return showView('news',false);
            if (path === '/watchlist') return showView('watchlist',false);
            if (path === '/compare') return showView('compare',false);
            if (path === '/ai') return showView('ai',false);
            if (path.startsWith('/stock/')) {
                let symbol = path.slice('/stock/'.length);
                try { symbol = decodeURIComponent(symbol); } catch (_) {}
                document.getElementById('symbol-input').value = symbol;
                return handleSearch(false);
            }
            if (path === '/') history.replaceState({view:'dashboard'},'','/markets');
            showView('dashboard',false);
            loadLandingOverview();
            loadLandingNews(landingLoadGeneration,true);
        }
        window.addEventListener('popstate',restoreLocation);
        document.addEventListener('keydown', event => {
            if (event.key !== 'Escape') return;
            if (!document.getElementById('delete-chat-dialog').classList.contains('hidden')) closeDeleteChatDialog();
            else if (!document.getElementById('system-status-popover').classList.contains('hidden')) toggleSystemStatus(false);
            else if (!document.getElementById('chat-page-menu').classList.contains('hidden')) toggleChatPageMenu(false);
            if (document.getElementById('chat-panel').classList.contains('chat-focus')) closeChatFocus();
        });
        document.addEventListener('click', event => {
            const panel = document.getElementById('system-status-popover');
            if (panel?.classList.contains('hidden')) return;
            if (event.target.closest('#system-status-popover, #header-health, #chat-system-status')) return;
            toggleSystemStatus(false);
        });
        document.getElementById('analysis-chart-tabs')?.addEventListener('keydown', event => {
            if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
            event.preventDefault();
            const tabs = [...document.querySelectorAll('.analysis-tab')];
            const active = Math.max(0,tabs.findIndex(tab=>tab.dataset.analysisView===analysisView));
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (active + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length;
            setAnalysisView(tabs[next].dataset.analysisView); tabs[next].focus();
        });
        function focusChat() {
            showView('ai');
            setTimeout(() => document.getElementById('chat-input').focus(), 180);
        }
        function closeChatFocus() {
            const panel = document.getElementById('chat-panel');
            panel.classList.remove('chat-focus', 'mobile-open');
            document.body.classList.remove('chat-open');
            setActiveNavigation(activePrimaryView);
        }
        function setupChatPage() {
            const panel = document.getElementById('chat-panel');
            const mount = document.getElementById('ai-chat-workspace');
            if (!panel || !mount) return;
            mount.append(panel);
            panel.classList.remove('hidden');
            panel.classList.add('chat-page-open');
            loadChatHistory();
        }
        async function loadChatHistory() {
            const list = document.getElementById('chat-history-list');
            if (!list) return;
            const status = document.getElementById('chat-history-status');
            try {
                const response = await fetch('/api/chat/sessions?limit=50');
                if (!response.ok) throw new Error('Saved conversations are unavailable');
                const data = await response.json();
                chatHistoryItems = Array.isArray(data.sessions) ? data.sessions : [];
                renderChatHistory();
                if (status) status.textContent = `${chatHistoryItems.length} saved conversation${chatHistoryItems.length === 1 ? '' : 's'}`;
            } catch (_) {
                list.innerHTML = '<p class="px-2 py-3 text-xs text-apple-gray">Could not load conversation history.</p>';
                if (status) status.textContent = 'History unavailable';
            }
        }
        function renderChatHistory(filter = document.getElementById('chat-history-search')?.value || '') {
            const list = document.getElementById('chat-history-list');
            if (!list) return;
            const query = filter.trim().toLowerCase();
            const items = chatHistoryItems.filter(item => !query || `${item.title} ${item.preview}`.toLowerCase().includes(query));
            if (!items.length) {
                list.innerHTML = `<p class="px-2 py-3 text-xs text-apple-gray">${query ? 'No matching conversations.' : 'Your conversations will appear here.'}</p>`;
                return;
            }
            list.replaceChildren(...items.map(item => {
                const row = document.createElement('div');
                row.className = `chat-history-row ${item.session_id === chatSessionId ? 'active' : ''}`;
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'chat-history-item';
                button.setAttribute('aria-current', item.session_id === chatSessionId ? 'true' : 'false');
                const title = document.createElement('span');
                title.className = 'block truncate text-xs font-semibold';
                title.textContent = `${item.is_branch ? '↳ Branch · ' : ''}${item.title || 'New conversation'}`;
                const preview = document.createElement('span');
                preview.className = 'mt-1 block truncate text-[10px] text-apple-gray';
                preview.textContent = `${item.is_branch ? 'Branched · ' : ''}${item.message_count} messages · ${item.updated_at ? new Date(item.updated_at).toLocaleDateString() : 'Saved'}`;
                const text = document.createElement('span');
                text.className = 'min-w-0 flex-1';
                text.append(title, preview);
                button.append(text);
                button.addEventListener('click', () => { restoreChatSession(item.session_id); toggleChatHistory(false); });
                const remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'chat-history-delete';
                remove.setAttribute('aria-label', `Delete conversation: ${item.title || 'New conversation'}`);
                remove.title = 'Delete conversation';
                remove.innerHTML = '<i data-lucide="trash-2" class="h-4 w-4" aria-hidden="true"></i>';
                remove.addEventListener('click', () => requestDeleteChat(item.session_id, item.title || 'New conversation'));
                row.append(button, remove);
                return row;
            }));
            lucide.createIcons();
        }
        function filterChatHistory(query) { renderChatHistory(query); }
        function toggleChatHistory(force) {
            const mount = document.getElementById('ai-chat-mount');
            if (!mount) return;
            const mobile = window.matchMedia('(max-width: 767px)').matches;
            if (mobile) {
                const open = force === undefined ? !mount.classList.contains('history-open') : Boolean(force);
                mount.classList.toggle('history-open', open);
            } else if (force === undefined) {
                mount.classList.toggle('history-hidden');
            }
        }
        function requestDeleteChat(sessionId, title) {
            pendingChatDeletion = {sessionId, title};
            document.getElementById('delete-chat-name').textContent = title;
            const dialog = document.getElementById('delete-chat-dialog');
            dialog.classList.remove('hidden');
            dialog.classList.add('flex');
            document.getElementById('delete-chat-confirm').focus();
        }
        function closeDeleteChatDialog() {
            const dialog = document.getElementById('delete-chat-dialog');
            dialog.classList.add('hidden');
            dialog.classList.remove('flex');
            pendingChatDeletion = null;
        }
        async function confirmDeleteChat() {
            if (!pendingChatDeletion) return;
            const {sessionId, title} = pendingChatDeletion;
            const confirm = document.getElementById('delete-chat-confirm');
            confirm.disabled = true;
            confirm.textContent = 'Deleting…';
            try {
                const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {method:'DELETE'});
                const result = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(result.detail || 'The conversation could not be deleted.');
                chatHistoryItems = chatHistoryItems.filter(item => item.session_id !== sessionId);
                if (chatSessionId === sessionId) {
                    chatRestoreGeneration++;
                    chatSessionId = null;
                    localStorage.removeItem('stockrag.sessionId');
                    const messages = document.getElementById('chat-messages');
                    messages.replaceChildren();
                    appendChat('assistant', 'Start a new conversation. Your deleted chat and its messages have been removed.');
                }
                closeDeleteChatDialog();
                renderChatHistory();
                document.getElementById('chat-history-status').textContent = `Deleted “${title}”.`;
            } catch (error) {
                document.getElementById('chat-history-status').textContent = error.message;
                closeDeleteChatDialog();
            } finally {
                confirm.disabled = false;
                confirm.textContent = 'Delete chat';
            }
        }
        async function branchChat(messageId) {
            if (!chatSessionId || !messageId) return;
            const sourceSessionId = chatSessionId;
            const status = document.getElementById('chat-history-status');
            if (status) status.textContent = 'Creating a branch with context through this reply…';
            try {
                const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sourceSessionId)}/branch`, {
                    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message_id:messageId})
                });
                const result = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(result.detail || 'Could not create a conversation branch.');
                chatSessionId = result.session_id;
                localStorage.setItem('stockrag.sessionId', chatSessionId);
                await loadChatHistory();
                await restoreChatSession(chatSessionId);
                if (status) status.textContent = 'Branch created. Conversation history is copied; recent turns provide context.';
            } catch (error) {
                if (status) status.textContent = error.message;
            }
        }
        function addBranchButton(target, messageId) {
            if (!target || !messageId || target.querySelector('.chat-branch-button')) return;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'chat-branch-button';
            button.setAttribute('aria-label', 'Branch conversation from this message');
            button.title = 'Branch from this message';
            button.innerHTML = '<i data-lucide="git-branch" class="h-4 w-4"></i>';
            button.addEventListener('click', () => branchChat(messageId));
            target.append(button);
            lucide.createIcons();
        }
        function attachRetryToLastChatReply(question, target = document.getElementById('chat-messages')?.lastElementChild) {
            if (!question || !target) return;
            const retry = document.createElement('button');
            retry.type = 'button';
            retry.className = 'chat-retry-button mt-2 min-h-10 rounded-lg px-3 font-semibold';
            retry.innerHTML = '<i data-lucide="rotate-cw" class="mr-1 inline h-4 w-4"></i>Retry this question';
            retry.addEventListener('click', () => {
                const input = document.getElementById('chat-input');
                input.value = question;
                input.dispatchEvent(new Event('input', {bubbles:true}));
                sendChatMessage();
            }, {once:true});
            (target.querySelector('.chat-bubble-ai') || target).append(retry);
            lucide.createIcons();
        }
        function savedReplyMetricMismatch(question, answer) {
            const groups = [
                ['revenue', 'revenue', /\b(?:revenue|sales|turnover)\b/i],
                ['income', 'net income', /\bnet income\b/i],
                ['income', 'income or profit', /\b(?:income|profit|earnings)\b/i],
                ['eps', 'EPS', /\b(?:eps|earnings per share)\b/i],
                ['debt', 'debt', /\b(?:debt|borrowings)\b/i],
                ['cash', 'cash flow', /\b(?:cash|cash flow)\b/i],
                ['assets', 'assets', /\bassets?\b/i],
                ['liabilities', 'liabilities', /\bliabilit(?:y|ies)\b/i],
                ['margin', 'margin', /\bmargins?\b/i],
                ['dividend', 'dividend', /\bdividends?\b/i],
            ];
            const requested = [...new Set(groups.filter(([, , pattern]) => pattern.test(question)).map(([name]) => name))];
            const answered = [...new Set(groups.filter(([, , pattern]) => pattern.test(answer)).map(([name]) => name))];
            return requested.length && answered.length && !requested.some(name => answered.includes(name))
                ? {requested:groups.find(([, , pattern]) => pattern.test(question))[1], answered:groups.find(([, , pattern]) => pattern.test(answer))[1]} : null;
        }
        function startSuggestedChat(prompt) {
            focusChat();
            const input = document.getElementById('chat-input');
            input.value = prompt;
            input.dispatchEvent(new Event('input', {bubbles:true}));
            sendChatMessage();
        }
        function askAboutNews(article) {
            currentSymbol = article.ticker || currentSymbol;
            const prompt = [
                `Analyze this news story in the context of ${article.ticker || 'the market'}. Separate reported facts from interpretation, and explain uncertainty.`,
                `Headline: ${article.title || 'Unavailable'}`,
                `Publisher: ${article.publisher || 'Unavailable'}`,
                `Published: ${article.published_at || 'Unavailable'}`,
                article.summary ? `Publisher summary: ${article.summary}` : '',
                `Source URL: ${article.url || 'Unavailable'}`
            ].filter(Boolean).join('\n');
            startSuggestedChat(prompt);
        }
        function toggleWatchlist(symbol) {
            if (watchlistSymbols.has(symbol)) watchlistSymbols.delete(symbol); else watchlistSymbols.add(symbol);
            localStorage.setItem('stockrag.watchlist',JSON.stringify([...watchlistSymbols]));
            document.querySelectorAll(`[data-watch-symbol="${CSS.escape(symbol)}"]`).forEach(button => {
                const active = watchlistSymbols.has(symbol);
                button.setAttribute('aria-pressed',String(active));
                button.setAttribute('aria-label',`${active ? 'Remove from' : 'Add to'} watchlist: ${symbol}`);
                button.innerHTML = `<i data-lucide="star" class="h-4 w-4 ${active ? 'fill-current text-amber-500' : 'text-apple-gray'}"></i>`;
            });
            applyWatchlistFilter();
            renderWatchlistTable();
            renderNewsContext();
            lucide.createIcons();
        }
        function applyWatchlistFilter() {
            const grid = document.getElementById('landing-watch-grid');
            if (!grid) return;
            const cards = [...grid.querySelectorAll('[data-watch-card]')];
            const visible = cards.filter(card => !watchlistOnly || watchlistSymbols.has(card.dataset.symbol));
            cards.forEach(card => { card.hidden = watchlistOnly && !watchlistSymbols.has(card.dataset.symbol); });
            const empty = document.getElementById('watchlist-empty');
            if (empty) empty.classList.toggle('hidden',!watchlistOnly || visible.length > 0);
            const heading = document.getElementById('overview-heading');
            if (heading) heading.textContent = watchlistOnly ? 'Your watchlist' : 'Market watch';
        }

        function formatMarketNumber(value, digits = 2) {
            const number = Number(value);
            return Number.isFinite(number) ? new Intl.NumberFormat(undefined, {maximumFractionDigits:digits}).format(number) : '—';
        }

        function renderLandingSkeletons() {
            const grid = document.getElementById('landing-watch-grid');
            grid.replaceChildren(...landingSymbols.map(({symbol,label}) => {
                const card = document.createElement('div');
                card.className = 'glass-panel watch-card rounded-2xl p-4';
                card.innerHTML = `<div class="flex items-start justify-between"><div><p class="text-sm font-semibold">${escapeHtml(symbol)}</p><p class="mt-0.5 truncate text-xs text-apple-gray">${escapeHtml(label)}</p></div><span class="loading-dot h-2 w-2 rounded-full bg-apple-blue"></span></div><div class="mt-4 h-8 animate-pulse rounded-lg bg-black/5 dark:bg-white/5"></div><div class="mt-3 h-14 animate-pulse rounded-lg bg-black/5 dark:bg-white/5"></div><p class="mt-2 text-[10px] text-apple-gray">Loading verified provider data…</p>`;
                return card;
            }));
        }

        async function loadLandingOverview(force = false) {
            const grid = document.getElementById('landing-watch-grid');
            if (!grid) return;
            const generation = ++landingLoadGeneration;
            landingOverviewAbortController?.abort();
            landingOverviewAbortController = new AbortController();
            const requestSignal = AbortSignal.any([landingOverviewAbortController.signal,AbortSignal.timeout(20000)]);
            const status = document.getElementById('landing-market-status');
            status.textContent = force ? 'Refreshing provider-backed prices and history…' : 'Loading provider-backed market data…';
            for (const chart of landingCharts.values()) chart.remove();
            landingCharts.clear();
            if (landingResizeObserver) landingResizeObserver.disconnect();
            renderLandingSkeletons();

            const results = Array(landingSymbols.length);
            let cursor = 0, finished = 0;
            const workers = Array.from({length:3}, async () => {
                while (cursor < landingSymbols.length) {
                    const index = cursor++, item = landingSymbols[index];
                    let result;
                    try {
                        const base = `/api/stocks/${encodeURIComponent(item.symbol)}`;
                        const [quoteResponse, historyResponse] = await Promise.all([
                            fetch(`${base}/quote${force ? '?refresh=true' : ''}`, {signal:requestSignal}),
                            fetch(`${base}/history?period=1mo&interval=1d${force ? '&refresh=true' : ''}`, {signal:requestSignal})
                        ]);
                        const quote = await quoteResponse.json();
                        const history = await historyResponse.json();
                        if (!quoteResponse.ok || quote.success === false || !Number.isFinite(Number(quote.price))) throw new Error(quote.error?.message || 'Quote unavailable');
                        const rows = (history.data || []).filter(row => Number.isFinite(Number(row.Close)) && Number(row.Close) > 0);
                        result = {item,index,quote,history,rows,error:!historyResponse.ok || !rows.length ? (history.error?.message || 'Price history unavailable') : null};
                    } catch (error) { result = {item,index,error:error.message || 'Market data unavailable'}; }
                    if (generation !== landingLoadGeneration) return;
                    results[index] = result;
                    const grid = document.getElementById('landing-watch-grid');
                    if (finished === 0) grid.replaceChildren();
                    renderLandingCard(result);
                    finished++;
                    status.textContent = `${finished}/${landingSymbols.length} market cards updated…`;
                }
            });
            await Promise.all(workers);
            if (generation !== landingLoadGeneration) return;
            [...grid.children].sort((a,b) => Number(a.dataset.watchIndex) - Number(b.dataset.watchIndex)).forEach(card => grid.append(card));

            landingResizeObserver = new ResizeObserver(entries => entries.forEach(entry => {
                const index = Number(entry.target.dataset.chartIndex);
                const chart = landingCharts.get(index);
                if (chart) chart.applyOptions({width:Math.floor(entry.contentRect.width)});
            }));
            grid.querySelectorAll('[data-chart-index]').forEach(el => landingResizeObserver.observe(el));
            const goodQuotes = results.filter(result => result.quote).length;
            const allFresh = results.every(result => result.quote && ['LIVE','RECENT'].includes(String(result.quote.status || '').toUpperCase()));
            status.textContent = `${goodQuotes}/${landingSymbols.length} quotes available · ${allFresh ? 'provider marks data recent' : 'freshness varies by provider; quotes may be delayed or unverified'} · retrieved ${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;

        }

        function renderLandingCard(result) {
            const {item,index,quote,rows,error} = result;
            latestMarketResults.set(item.symbol,result);
            const card = document.createElement('article');
            card.className = 'glass-panel watch-card group rounded-2xl p-4 transition duration-200 hover:-translate-y-0.5 hover:border-apple-blue/40 hover:shadow-lg';
            card.dataset.watchIndex = String(index);
            card.dataset.watchCard = 'true'; card.dataset.symbol = item.symbol;
            const top = document.createElement('div');
            top.className = 'flex items-start justify-between gap-2';
            const identity = document.createElement('button');
            identity.className = 'min-w-0 text-left'; identity.type = 'button'; identity.title = `Open ${item.symbol}`;
            identity.innerHTML = `<span class="block text-sm font-bold tracking-tight group-hover:text-apple-blue">${escapeHtml(item.symbol)}</span><span class="mt-0.5 block truncate text-xs text-apple-gray">${escapeHtml(item.label)} · ${item.market === 'india' ? 'NSE' : 'US'}</span>`;
            identity.addEventListener('click', () => simulateSearch(item.symbol));
            top.append(identity);
            const source = document.createElement('span');
            source.className = 'max-w-[45%] truncate rounded-full bg-black/[.04] px-2 py-1 text-[9px] text-apple-gray dark:bg-white/[.06]';
            source.title = quote ? `${quote.source || 'Provider unknown'} · ${quote.status || quote.data_status || 'freshness unknown'} · ${quote.retrieved_at || ''}` : error;
            source.textContent = quote ? `${quote.status || quote.data_status || 'Freshness unknown'}`.replaceAll('_',' ') : 'Unavailable';
            const star = document.createElement('button'); star.type = 'button'; star.dataset.watchSymbol = item.symbol; star.className = 'flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition hover:bg-black/5 dark:hover:bg-white/10';
            star.setAttribute('aria-pressed',String(watchlistSymbols.has(item.symbol))); star.setAttribute('aria-label',`${watchlistSymbols.has(item.symbol) ? 'Remove from' : 'Add to'} watchlist: ${item.symbol}`); star.title = 'Add to watchlist';
            star.innerHTML = `<i data-lucide="star" class="h-4 w-4 ${watchlistSymbols.has(item.symbol) ? 'fill-current text-amber-500' : 'text-apple-gray'}"></i>`;
            star.addEventListener('click',event=>{event.stopPropagation();toggleWatchlist(item.symbol);});
            top.append(source,star); card.append(top);
            const summary = document.createElement('div');
            summary.className = 'mt-4 flex items-end justify-between gap-2';
            const price = document.createElement('p'); price.className = 'text-xl font-semibold tracking-tight';
            price.textContent = quote ? `${quote.currency || (item.market === 'india' ? 'INR' : 'USD')} ${formatMarketNumber(quote.price)}` : '—';
            summary.append(price);
            const change = document.createElement('span');
            const hasChange = quote && Number.isFinite(Number(quote.change_percent));
            change.className = `mb-0.5 rounded-lg px-2 py-1 text-xs font-semibold ${!hasChange ? 'bg-black/5 text-apple-gray dark:bg-white/5' : Number(quote.change_percent) >= 0 ? 'bg-emerald-500/10 text-emerald-600' : 'bg-rose-500/10 text-rose-600'}`;
            change.textContent = hasChange ? `${Number(quote.change_percent) >= 0 ? '+' : ''}${formatMarketNumber(quote.change_percent)}%` : 'Change n/a';
            summary.append(change); card.append(summary);
            const chartBox = document.createElement('div'); chartBox.className = 'watch-chart mt-2 h-[68px]'; chartBox.dataset.chartIndex = String(index);
            card.append(chartBox);
            const footer = document.createElement('div'); footer.className = 'mt-2 flex items-center justify-between gap-2 text-[10px] text-apple-gray';
            const volume = document.createElement('span'); volume.textContent = quote ? `Vol ${formatMarketNumber(quote.volume,0)}` : (error || 'Quote unavailable'); volume.title = quote?.source || '';
            const detail = document.createElement('span'); detail.className = 'truncate text-right'; detail.textContent = rows?.length ? `${rows.length} sessions · ${result.history.source || quote?.source || 'provider'}` : (result.error || 'Chart unavailable');
            footer.append(volume,detail); card.append(footer); document.getElementById('landing-watch-grid').append(card);
            card.hidden = watchlistOnly && !watchlistSymbols.has(item.symbol);
            if (rows?.length) {
                try {
                    const color = item.market === 'india' ? '#8b5cf6' : '#0a84ff';
                    const chart = LightweightCharts.createChart(chartBox, {width:chartBox.clientWidth || 280,height:68,layout:{background:{type:'solid',color:'transparent'},textColor:'transparent',attributionLogo:false},grid:{vertLines:{visible:false},horzLines:{visible:false}},rightPriceScale:{visible:false},leftPriceScale:{visible:false},timeScale:{visible:false,borderVisible:false},crosshair:{vertLine:{visible:false},horzLine:{visible:false}},handleScroll:false,handleScale:false});
                    const series = chart.addAreaSeries({lineColor:color,lineWidth:2,topColor:item.market === 'india' ? 'rgba(139,92,246,.22)' : 'rgba(10,132,255,.22)',bottomColor:'rgba(10,132,255,0)',priceLineVisible:false,lastValueVisible:false});
                    series.setData(rows.map(row => ({time:String(row.Date).slice(0,10),value:Number(row.Close)})));
                    landingCharts.set(index,chart);
                } catch (error) { chartBox.textContent = 'Chart rendering unavailable'; chartBox.classList.add('text-xs','text-apple-gray'); }
            } else { chartBox.classList.add('flex','items-center','justify-center','text-[10px]','text-apple-gray'); chartBox.textContent = 'History unavailable'; }
            renderWatchlistTable();
        }

        function renderWatchlistTable() {
            const body = document.getElementById('watchlist-table-body');
            const empty = document.getElementById('watchlist-page-empty');
            if (!body || !empty) return;
            const symbols = [...watchlistSymbols];
            body.replaceChildren();
            empty.classList.toggle('hidden',symbols.length > 0);
            if (!symbols.length) return;
            for (const symbol of symbols) {
                const result = latestMarketResults.get(symbol);
                const item = result?.item || {symbol,label:symbol};
                const quote = result?.quote;
                const row = document.createElement('tr'); row.className = 'market-table-row';
                const company = document.createElement('td');
                const open = document.createElement('button'); open.type = 'button'; open.className = 'text-left'; open.innerHTML = `<span class="block font-semibold">${escapeHtml(item.label || symbol)}</span><span class="mt-0.5 block text-[10px] text-apple-gray">${escapeHtml(symbol)} · ${item.market === 'india' ? 'NSE' : 'US'}</span>`;
                open.addEventListener('click',()=>simulateSearch(symbol)); company.append(open);
                const price = document.createElement('td'); price.textContent = quote ? `${quote.currency || ''} ${formatMarketNumber(quote.price)}`.trim() : '—';
                const change = document.createElement('td');
                const pct = Number(quote?.change_percent);
                change.textContent = Number.isFinite(pct) ? `${pct >= 0 ? '+' : ''}${formatMarketNumber(pct)}%` : '—';
                change.className = Number.isFinite(pct) ? pct >= 0 ? 'text-emerald-600' : 'text-rose-600' : 'text-apple-gray';
                const volume = document.createElement('td'); volume.textContent = quote ? formatMarketNumber(quote.volume,0) : '—';
                const trend = document.createElement('td'); trend.textContent = result?.rows?.length ? `${result.rows.length} sessions` : 'Unavailable';
                const freshness = document.createElement('td'); freshness.textContent = quote?.status || quote?.data_status || 'Unavailable'; freshness.className = 'text-[10px] text-apple-gray';
                row.append(company,price,change,volume,trend,freshness); body.append(row);
            }
        }

        async function loadLandingNews(generation = landingLoadGeneration, force = true, requestGeneration = ++landingNewsGeneration, market = 'all') {
            landingNewsAbortController?.abort();
            landingNewsAbortController = new AbortController();
            const requestSignal = AbortSignal.any([landingNewsAbortController.signal,AbortSignal.timeout(50000)]);
            const loading = `<div class="py-12 text-center"><span class="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-full bg-apple-blue/10 text-apple-blue"><i data-lucide="loader-circle" class="h-5 w-5 animate-spin"></i></span><p class="text-sm font-medium text-text-main">${force ? 'Fetching fresh headlines from publishers…' : 'Loading the latest headlines…'}</p><p class="mt-1 text-xs text-apple-gray">Checking market coverage and your tracked companies.</p></div>`;
            document.getElementById('landing-news-feed').innerHTML = loading;
            document.getElementById('news-feed').innerHTML = loading;
            document.getElementById('news-feed-refresh-state').textContent = 'Searching fresh publisher feeds…';
            const allItems = [...new Set([...landingSymbols.map(item => item.symbol),...watchlistSymbols])].slice(0,10);
            const items = market === 'all' ? allItems : allItems.filter(symbol => market === 'india' ? /\.(NS|BO)$/i.test(symbol) || symbol.startsWith('^') : !(/\.(NS|BO)$/i.test(symbol) || symbol.startsWith('^')));
            const days = document.getElementById('news-feed-period')?.value || '7';
            const params = new URLSearchParams({symbols:items.join(','),market,limit:'100',days});
            try {
                const response = await fetch(`/api/news/feed?${params}`, {signal:requestSignal,cache:'no-store'});
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'News providers could not be reached.');
                if (generation !== landingLoadGeneration || requestGeneration !== landingNewsGeneration) return;
                landingNewsItems = Array.isArray(result.news) ? result.news : [];
                landingNewsMeta = result;
                landingNewsUpdatedAt = result.retrieved_at ? new Date(result.retrieved_at) : new Date();
                newsVisibleCount = 20;
                renderLandingNews();
                document.getElementById('news-feed-refresh-state').textContent = result.success
                    ? `Updated ${landingNewsUpdatedAt.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})} · ${result.source_count || 0} publishers represented`
                    : 'No fresh publisher results returned';
            } catch (error) {
                if (error.name === 'AbortError' || generation !== landingLoadGeneration || requestGeneration !== landingNewsGeneration) return;
                document.getElementById('news-feed-refresh-state').textContent = 'Could not refresh';
                const message = error.name === 'TimeoutError' ? 'News sources took too long to respond.' : (error.message || 'News could not be loaded.');
                for (const container of [document.getElementById('landing-news-feed'),document.getElementById('news-feed')]) {
                    container.replaceChildren();
                    const empty = document.createElement('div'); empty.className = 'py-12 text-center';
                    const text = document.createElement('p'); text.className = 'text-sm text-apple-gray'; text.textContent = message;
                    const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'mt-2 min-h-11 rounded-lg px-3 text-sm font-semibold text-apple-blue'; retry.textContent = 'Try again'; retry.addEventListener('click',refreshLandingNews);
                    empty.append(text,retry); container.append(empty);
                }
            }
        }
        function refreshLandingNews() { return loadLandingNews(landingLoadGeneration, true, ++landingNewsGeneration, ['us','india'].includes(landingNewsFilter) ? landingNewsFilter : 'all'); }

        function searchLandingNews(value) {
            landingNewsSearch = String(value || '').trim().toLocaleLowerCase();
            newsVisibleCount = 20;
            renderLandingNews();
        }

        function loadMoreLandingNews() {
            newsVisibleCount = Math.min(newsVisibleCount + 20, 100);
            renderLandingNews();
        }

        function filterLandingNews(market) {
            landingNewsFilter = market;
            document.querySelectorAll('.feed-filter').forEach(button => button.classList.toggle('active',button.dataset.marketFilter === market));
            if (market === 'us' || market === 'india' || market === 'all' || market === 'watchlist') {
                newsVisibleCount = 20;
                // Region views are server-scoped live searches. Returning to
                // For you or My stocks must fetch the broad result set again.
                return loadLandingNews(landingLoadGeneration,true,++landingNewsGeneration,market === 'all' || market === 'watchlist' ? 'all' : market);
            }
            renderLandingNews();
        }

        function renderLandingNews() {
            const filtered = landingNewsFilter === 'all' ? landingNewsItems : landingNewsFilter === 'watchlist' ? landingNewsItems.filter(item => watchlistSymbols.has(item.ticker) || (item.related_tickers || []).some(symbol => watchlistSymbols.has(symbol))) : landingNewsItems.filter(item => item.market === landingNewsFilter);
            const items = landingNewsSearch ? filtered.filter(item => `${item.title || ''} ${item.publisher || ''} ${item.ticker || ''} ${item.summary || ''}`.toLocaleLowerCase().includes(landingNewsSearch)) : filtered;
            const count = document.getElementById('news-feed-count');
            if (count) count.textContent = `${items.length} ${items.length === 1 ? 'story' : 'stories'}${landingNewsMeta?.total_available > landingNewsItems.length ? ` · ${landingNewsMeta.total_available} found` : ''} · newest first`;
            const sourceLine = document.getElementById('news-feed-source');
            document.getElementById('news-load-more')?.classList.add('hidden');
            if (sourceLine) {
                sourceLine.textContent = 'Headlines are fetched from publisher RSS/search and configured company-news providers. Links open the publisher story; summaries and images appear only when a source supplies them. Wikipedia is an encyclopedia, so it is not used as a breaking-news feed.';
            }
            for (const container of [document.getElementById('landing-news-feed'),document.getElementById('news-feed')]) {
                if (!container) continue;
            if (!items.length) {
                    container.innerHTML = `<div class="py-10 text-center"><p class="text-sm text-apple-gray">${landingNewsItems.length ? 'No headlines match this filter.' : 'No recent stories were returned by the selected publishers.'}</p><button class="mt-2 min-h-11 px-3 text-sm font-semibold text-apple-blue" onclick="refreshLandingNews()">Refresh sources</button></div>`;
                    continue;
            }
                const visibleItems = container.id === 'landing-news-feed' ? items.slice(0,4) : items.slice(0,newsVisibleCount);
                container.replaceChildren(...visibleItems.map(item => {
                const row = document.createElement('article'); row.className = 'news-feed-item flex gap-3 py-5 first:pt-2 sm:gap-4';
                const body = document.createElement('div'); body.className = 'min-w-0 flex-1';
                const headline = document.createElement('a'); headline.className = 'line-clamp-3 text-[15px] font-semibold leading-snug tracking-[-.01em] transition hover:text-apple-blue sm:text-base'; headline.textContent = item.title;
                try { const url = new URL(item.url); if (['https:','http:'].includes(url.protocol)) { headline.href = url.href; headline.target = '_blank'; headline.rel = 'noopener noreferrer'; } } catch (_) {}
                const summary = document.createElement('p'); summary.className = 'mt-2 line-clamp-3 text-[13px] leading-relaxed text-apple-gray'; summary.textContent = item.summary || '';
                const meta = document.createElement('p'); meta.className = 'mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[11px] text-apple-gray';
                const date = Date.parse(item.published_at || '');
                    const publisher = document.createElement('span'); publisher.className = 'font-semibold text-text-main'; publisher.textContent = item.publisher || 'Publisher unavailable';
                    meta.append(publisher);
                    if (item.ticker) { const ticker = document.createElement('span'); ticker.className = 'rounded-full bg-black/[.05] px-2 py-0.5 font-semibold text-text-main dark:bg-white/[.08]'; ticker.textContent = item.ticker; meta.append(ticker); }
                    const published = document.createElement('time'); published.className = 'text-apple-gray'; published.textContent = date ? new Date(date).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : 'Publication time unavailable';
                    if (date) published.dateTime = new Date(date).toISOString();
                    meta.append(published);
                    if (item.summary_type) { const excerpt = document.createElement('span'); excerpt.className = 'text-apple-gray'; excerpt.textContent = 'Publisher excerpt'; meta.append(excerpt); }
                    if (item.feed_status === 'STALE') { const stale = document.createElement('span'); stale.className = 'rounded-full bg-amber-500/10 px-2 py-0.5 font-medium text-amber-700 dark:text-amber-300'; stale.textContent = 'Saved copy · may be old'; meta.append(stale); }
                    body.append(headline);
                    if (summary.textContent) body.append(summary);
                    body.append(meta);
                    if (container.id === 'news-feed') {
                        const actions = document.createElement('div'); actions.className = 'mt-2 flex flex-wrap items-center gap-x-3';
                        const ask = document.createElement('button'); ask.type = 'button'; ask.className = 'min-h-9 rounded-lg pr-2 text-[11px] font-semibold text-apple-blue transition hover:underline'; ask.textContent = 'Ask AI about this';
                        ask.addEventListener('click', () => askAboutNews(item));
                        actions.append(ask);
                        const openStory = document.createElement('a'); openStory.className = 'inline-flex min-h-9 items-center gap-1 text-[11px] font-semibold text-apple-gray transition hover:text-apple-blue'; openStory.href = item.url; openStory.target = '_blank'; openStory.rel = 'noopener noreferrer'; openStory.textContent = 'Read at source';
                        const externalIcon = document.createElement('i'); externalIcon.dataset.lucide = 'arrow-up-right'; externalIcon.className = 'h-3 w-3'; openStory.append(externalIcon); actions.append(openStory);
                        if (item.ticker) {
                            const company = document.createElement('button'); company.type = 'button'; company.className = 'min-h-9 rounded-lg px-2 text-[11px] font-semibold text-apple-gray transition hover:bg-black/5 hover:text-apple-blue'; company.textContent = `Open ${item.ticker}`;
                            company.addEventListener('click', () => simulateSearch(item.ticker));
                            actions.append(company);
                        }
                        body.append(actions);
                    }
                    if (item.image) {
                        try {
                            const imageUrl = new URL(item.image);
                            if (imageUrl.protocol === 'https:') {
                                const image = document.createElement('img'); image.className = 'news-thumbnail'; image.src = imageUrl.href; image.alt = item.image_alt || `Image supplied with ${item.publisher || 'publisher'} story`; image.loading = 'lazy'; image.referrerPolicy = 'no-referrer'; image.onerror = () => { image.replaceWith(sourceMark(item)); };
                                row.append(image);
                            }
                        } catch (_) {}
                    } else {
                        row.append(sourceMark(item));
                    }
                    row.prepend(body); return row;
            }));
            const more = document.getElementById('news-load-more');
            if (container.id === 'news-feed' && more) {
                const remaining = Math.max(0,items.length - newsVisibleCount);
                more.classList.toggle('hidden',remaining === 0);
                more.textContent = remaining ? `Load ${Math.min(20,remaining)} more stories · ${remaining} remaining` : 'All available stories shown';
            }
            }
            lucide.createIcons();
        }

        function sourceMark(item) {
            const mark = document.createElement('span'); mark.className = `news-source-mark ${item.market === 'india' ? 'news-source-india' : ''}`;
            mark.setAttribute('aria-label', `${item.publisher || 'Publisher'} story`);
            mark.textContent = String(item.publisher || item.ticker || 'N').trim().slice(0,1).toUpperCase();
            return mark;
        }

        function renderNewsContext() {
            const container = document.getElementById('news-context-watchlist');
            if (!container) return;
            const symbols = [...watchlistSymbols];
            if (!symbols.length) {
                container.innerHTML = '<p class="py-3 text-xs text-apple-gray">No saved stocks yet. Add one from the market overview.</p>';
                return;
            }
            container.replaceChildren(...symbols.map(symbol => {
                const item = landingSymbols.find(entry => entry.symbol === symbol) || {symbol,label:symbol};
                const button = document.createElement('button'); button.type = 'button'; button.className = 'flex min-h-12 w-full items-center justify-between gap-2 py-2 text-left';
                button.innerHTML = `<span class="min-w-0"><span class="block truncate text-xs font-semibold">${escapeHtml(item.label)}</span><span class="text-[10px] text-apple-gray">${escapeHtml(symbol)}</span></span><i data-lucide="arrow-up-right" class="h-4 w-4 shrink-0 text-apple-gray"></i>`;
                button.addEventListener('click',()=>simulateSearch(symbol));
                return button;
            }));
            lucide.createIcons();
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
                const aiHealth = document.getElementById('ai-page-health');
                aiHealth.textContent = !result.available ? 'Ollama unavailable' : models.length ? `Ollama connected · ${models.length} local model${models.length === 1 ? '' : 's'} installed` : 'Ollama connected · no chat models installed';
                aiHealth.title = result.error || 'Generation models are selected here; document embeddings are configured separately for retrieval.';
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
                document.getElementById('ai-page-health').textContent = 'Ollama model list unavailable';
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
            const comparisonSection = document.getElementById('market-comparison-section');
            const comparisonMount = document.getElementById('market-comparison-mount');
            if (comparisonSection && comparisonMount) {
                comparisonSection.classList.remove('hidden');
                comparisonMount.append(comparisonSection);
                comparisonSection.className = 'glass-panel rounded-3xl p-5 shadow-sm md:p-6';
            }
            document.querySelectorAll('.compare-symbol').forEach((select, index) => {
                select.innerHTML = popularSymbols.map(symbol => `<option value="${symbol}">${symbol}</option>`).join('');
                select.value = ['RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS'][index];
            });
        }

        async function loadComparisons(refresh = false) {
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
                    const response = await fetch(`/api/stocks/${encodeURIComponent(symbol)}/history?period=${period}&interval=1d${refresh ? '&refresh=true' : ''}`);
                    const result = await response.json();
                    if (!response.ok || !result.success || !result.data?.length) throw new Error(result.error?.message || 'Provider returned no price history');
                    const rows = result.data.filter(row => Number(row.Close) > 0);
                    if (!rows.length) throw new Error('No usable closing prices');
                    const base = Number(rows[0].Close);
                    container.replaceChildren();
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
                    retry.addEventListener('click', () => loadComparisons(true), {once:true});
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
        function citationHtml(value) {
            const citation = String(value ?? '');
            const match = citation.match(/https?:\/\/[^\s<>]+/i);
            if (!match) return escapeHtml(citation);
            const url = match[0].replace(/[),.;]+$/, '');
            if (!/^https?:\/\//i.test(url)) return escapeHtml(citation);
            const label = citation.slice(0, match.index).trim() || url;
            return `${escapeHtml(label)} <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open source</a>`;
        }

        async function loadDocuments() {
            const container = document.getElementById('document-list');
            try {
                const res = await fetch('/api/documents');
                if (!res.ok) throw new Error('Document list unavailable');
                const {documents} = await res.json();
                knownDocuments = documents;
                container.innerHTML = documents.length ? documents.map(doc => `<label class="flex min-h-11 items-center gap-3 rounded-xl px-2 hover:bg-black/5 dark:hover:bg-white/5"><input type="checkbox" class="h-4 w-4 accent-[var(--accent)]" ${['pdf','docx','txt','html','web'].includes(doc.type) ? `data-document-id="${doc.id}" ${selectedDocumentIds.includes(doc.id) ? 'checked' : ''}` : doc.type === 'dataset' ? `data-dataset-id="${doc.id}" ${activeDatasetId === doc.id ? 'checked' : ''}` : 'disabled'} ${doc.status !== 'completed' ? 'disabled' : ''}><span class="min-w-0 flex-1 truncate">${escapeHtml(doc.filename)}</span><span class="text-xs ${doc.status === 'completed' ? 'text-apple-green' : doc.status === 'failed' ? 'text-apple-red' : 'text-apple-gray'}">${escapeHtml(doc.status)}</span></label>`).join('') : '<p class="text-apple-gray">No uploaded documents yet.</p>';
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
        async function handleSearch(updateUrl = true, refreshData = false) {
            const inputEl = document.getElementById('symbol-input');
            const input = inputEl.value.trim();
            if (!input) return;

            // Natural language detection (if long or has spaces) -> send to chat
            if (input.includes(' ')) {
                if (window.innerWidth < 1024) toggleChatMobile();
                document.getElementById('chat-input').value = input;
                inputEl.value = '';
                sendChatMessage();
                return;
            }

            let symbol = input.toUpperCase();
            const exchangeSuffix = {IN:'.NS',UK:'.L',CA:'.TO',AU:'.AX'}[currentSettings.default_market_exchange];
            if (exchangeSuffix && !symbol.includes('.') && !symbol.includes('-') && !knownUsSymbols.has(symbol)) symbol += exchangeSuffix;
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
                document.getElementById('news-page').classList.add('hidden');
                document.getElementById('watchlist-page').classList.add('hidden');
                document.getElementById('compare-page').classList.add('hidden');
                document.getElementById('ai-page').classList.add('hidden');
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

            if (updateUrl && location.pathname !== `/stock/${encodeURIComponent(symbol)}`) history.pushState({view:'stock',symbol},'',`/stock/${encodeURIComponent(symbol)}`);
            activePrimaryView = 'dashboard';
            setActiveNavigation('stock');
            
            document.getElementById('empty-state').classList.add('hidden');
            document.getElementById('news-page').classList.add('hidden');
            document.getElementById('watchlist-page').classList.add('hidden');
            document.getElementById('compare-page').classList.add('hidden');
            document.getElementById('ai-page').classList.add('hidden');
            document.getElementById('stock-view').classList.remove('hidden');
            
            document.getElementById('stock-symbol').textContent = symbol;
            document.getElementById('stock-name').textContent = `Loading ${resolution.exchange} market data…`;
            document.getElementById('quote-retry').classList.add('hidden');
            document.getElementById('stock-status').classList.add('hidden');
            document.getElementById('stock-price').textContent = '—';
            currentSymbol = symbol;

            // Reset UI
            document.getElementById('basic-metrics').innerHTML = '<div class="col-span-4 text-center py-10 opacity-50"><div class="loading-dot inline-block w-2 h-2 bg-black dark:bg-white rounded-full mx-1"></div><div class="loading-dot inline-block w-2 h-2 bg-black dark:bg-white rounded-full mx-1" style="animation-delay: 0.2s"></div><div class="loading-dot inline-block w-2 h-2 bg-black dark:bg-white rounded-full mx-1" style="animation-delay: 0.4s"></div></div>';
            disposeMainChart();
            if (chartResizeObserver) chartResizeObserver.disconnect();
            document.getElementById('news-badge').textContent = '0';

            try {
                // Fetch basic data in parallel
                const [profileRes, quoteRes, newsRes] = await Promise.all([
                    fetch(`/api/stocks/${encodeURIComponent(symbol)}`),
                    fetch(`/api/stocks/${encodeURIComponent(symbol)}/quote${refreshData ? '?refresh=true' : ''}`),
                    fetch(`/api/stocks/${encodeURIComponent(symbol)}/news${refreshData ? '?refresh=true' : ''}`)
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
                    renderRetryState('mainChart', 'Price history is unavailable from configured providers.', () => loadChartData(currentSettings.default_chart_period || '1mo',true));
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
                loadChartData(currentSettings.default_chart_period || '1mo',refreshData);

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

                fetch(`/api/stocks/${encodeURIComponent(symbol)}/fundamentals${refreshData ? '?refresh=true' : ''}`).then(r=>r.json()).then(fund => {
                    if (fund.metrics) {
                        document.getElementById('fundamental-source-status').textContent = `${fund.source || 'Source unavailable'} · ${fund.data_status || 'freshness unknown'}${fund.retrieved_at ? ` · retrieved ${fund.retrieved_at}` : ''}`;
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
        async function loadTechnicalData(symbol, period, interval, refresh = false) {
            const generation = ++technicalRequestGeneration;
            const params = new URLSearchParams({period, interval});
            if (refresh) params.set('refresh', 'true');
            try {
                const response = await fetch(`/api/stocks/${encodeURIComponent(symbol)}/technical?${params}`);
                const tech = await response.json();
                if (generation !== technicalRequestGeneration || symbol !== currentSymbol || period !== activeChartPeriod || interval !== activeChartInterval) return;
                if (!response.ok || !tech.metrics) throw new Error(tech.detail || 'Technical data unavailable');
                document.getElementById('technical-source-status').textContent = `${tech.source || 'Source unavailable'} · ${tech.data_status || 'freshness unknown'} · ${tech.period || period} / ${tech.interval || interval} · last bar ${tech.last_bar_at || 'date unavailable'}${tech.retrieved_at ? ` · retrieved ${tech.retrieved_at}` : ''}`;
                let html = Object.entries(tech.metrics).filter(([_, value]) => value != null).map(([key, value]) => renderMetricsCard(key, value)).join('');
                if (tech.scenario_estimate) {
                    const forecast = tech.scenario_estimate;
                    const horizonLabel = `${forecast.horizon_bars ?? forecast.horizon_trading_days} ${forecast.bar_interval === '1wk' ? 'weekly bars' : forecast.bar_interval === '1mo' ? 'monthly bars' : 'daily sessions'}`;
                    html += `<div class="metric-card col-span-full"><h4 class="text-sm font-bold">${escapeHtml(horizonLabel)} statistical scenario range</h4><p class="mt-2 text-xs text-apple-gray">Central estimate ${escapeHtml(Number(forecast.central_estimate).toFixed(2))}; 80% scenario interval ${escapeHtml(Number(forecast.lower_80_percent).toFixed(2))}–${escapeHtml(Number(forecast.upper_80_percent).toFixed(2))}. Historical drift and volatility model; not a validated forecast. Baseline holdout MAE: ${forecast.persistence_baseline_holdout_mae == null ? 'unavailable' : escapeHtml(Number(forecast.persistence_baseline_holdout_mae).toFixed(2))}.</p><p class="mt-1 text-xs text-apple-gray">${escapeHtml(forecast.limitations)}</p></div>`;
                }
                if (tech.ml_analysis) {
                    const model = tech.ml_analysis;
                    html += model.available
                        ? `<div class="metric-card col-span-full"><h4 class="flex items-center gap-2 text-sm font-bold"><i data-lucide="brain-circuit" class="h-4 w-4 text-apple-blue"></i>Experimental ML · next ${escapeHtml(model.bar_interval || interval)} bar return</h4><p class="mt-2 text-xs text-apple-gray">Model estimate ${escapeHtml(Number(model.latest_next_bar_return_percent).toFixed(3))}% · ${escapeHtml(model.model)}${model.training_period ? ` · trained/evaluated with ${escapeHtml(model.training_period)} of same-interval bars` : ''}.</p><p class="mt-1 text-xs text-apple-gray">Time-ordered ${escapeHtml(model.walk_forward_holdout_bars ?? model.walk_forward_holdout_sessions)}-bar holdout MAE: ${escapeHtml(Number(model.walk_forward_mae_percent).toFixed(3))}% · historical-mean baseline: ${escapeHtml(Number(model.historical_mean_baseline_mae_percent).toFixed(3))}% · ${model.beats_baseline_mae ? 'beat' : 'did not beat'} the baseline on this holdout.</p><p class="mt-1 text-xs text-apple-gray">${escapeHtml(model.limitations)}</p></div>`
                        : `<div class="metric-card col-span-full"><h4 class="text-sm font-bold">Experimental ML analysis</h4><p class="mt-2 text-xs text-apple-gray">${escapeHtml(model.reason || 'Insufficient historical prices for model evaluation.')}</p></div>`;
                }
                document.getElementById('technical-metrics').innerHTML = html;
                lucide.createIcons();
            } catch (_) {
                if (generation === technicalRequestGeneration && symbol === currentSymbol && period === activeChartPeriod && interval === activeChartInterval) renderRetryState('technical-metrics', 'Technical data is unavailable.', () => loadChartData(period, true));
            }
        }

        async function loadChartData(period, refresh = false) {
            if (!currentSymbol) return;
            activeChartPeriod = period;
            activeChartInterval = currentSettings.default_chart_interval || '1d';
            loadTechnicalData(currentSymbol, activeChartPeriod, activeChartInterval, refresh);
            
            // Update UI buttons
            document.querySelectorAll('.chart-period-btn').forEach(b => b.classList.toggle('active', b.getAttribute('onclick')?.includes(`'${period}'`)));
            
            const loader = document.getElementById('chart-loading');
            loader.classList.remove('hidden');

            try {
                const interval = activeChartInterval;
                const res = await fetch(`/api/stocks/${encodeURIComponent(currentSymbol)}/history?period=${encodeURIComponent(period)}&interval=${encodeURIComponent(interval)}${refresh ? '&refresh=true' : ''}`);
                if (!res.ok) throw new Error('Chart request failed');
                const data = await res.json();
                
                if (data.success && data.data && data.data.length > 0) {
                    document.getElementById('chart-source-status').textContent = `${data.source || 'Provider unknown'} · ${data.data_status || 'historical data'} · ${period} / ${interval} · last bar ${data.last_bar_at || data.data.at(-1)?.Date || 'unknown'}`;
                    latestHistoryData = data.data;
                    latestIndicatorData = data.indicators?.data || [];
                    renderChart(latestHistoryData, latestIndicatorData, analysisView);
                } else renderRetryState('mainChart', 'Chart data unavailable.', () => loadChartData(period));
            } catch (e) {
                console.warn("Chart data request failed:", e.message);
                document.getElementById('chart-source-status').textContent = 'Provider unavailable';
                renderRetryState('mainChart', 'Chart data unavailable from configured providers.', () => loadChartData(period));
            }
            loader.classList.add('hidden');
        }

        const analysisCaptions = {
            price:'OHLC price history from the configured market provider.',
            volume:'Provider-reported traded volume for each historical session.',
            trend:'Close price with SMA 20 and EMA 20, calculated in Python from stored OHLCV.',
            bollinger:'Close price with 20-bar Bollinger bands, calculated in Python.',
            rsi:'RSI (14 bars), calculated in Python. Reference levels: 30 and 70.',
            macd:'MACD (12, 26, 9 bars), signal, and histogram, calculated in Python.',
            atr:'ATR (14 bars), calculated in Python from historical high, low, and close.',
            performance:'Indexed close-price performance. First available close = 100; no forecast.'
        };
        function chartBarLabel() { return activeChartInterval === '1wk' ? 'week' : activeChartInterval === '1mo' ? 'month' : 'session'; }
        function setAnalysisView(view) {
            if (!analysisCaptions[view]) return;
            analysisView = view;
            document.querySelectorAll('.analysis-tab').forEach(button => {
                const active = button.dataset.analysisView === view;
                button.classList.toggle('active',active);
                button.setAttribute('aria-selected',String(active));
                button.tabIndex = active ? 0 : -1;
            });
            if (latestHistoryData.length) renderChart(latestHistoryData,latestIndicatorData,view);
        }

        function renderChart(historyData, indicatorData = [], view = analysisView) {
            const chartContainer = document.getElementById('mainChart');
            disposeMainChart();
            if (chartResizeObserver) chartResizeObserver.disconnect();
            chartContainer.replaceChildren();
            const history = historyData.map(row => ({...row,time:String(row.Date || row.Datetime || '').slice(0,10)})).filter(row => row.time && Number.isFinite(Number(row.Close))).sort((a,b)=>a.time.localeCompare(b.time));
            const indicators = indicatorData.filter(row => row && row.time).sort((a,b)=>a.time.localeCompare(b.time));
            const indicatorByTime = new Map(indicators.map(row => [row.time,row]));
            const caption = document.getElementById('analysis-chart-caption');
            caption.textContent = (analysisCaptions[view] || analysisCaptions.price).replaceAll('bars', `${chartBarLabel()} bars`).replaceAll('sessions', `${chartBarLabel()}s`);
            const styleControls = document.querySelector('[aria-label="Chart style"]');
            styleControls.classList.toggle('invisible',view !== 'price');
            document.getElementById('mainChart').setAttribute('aria-label',`${currentSymbol || 'Selected stock'} ${view} chart`);
            mainChartInstance = LightweightCharts.createChart(chartContainer, {
                layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8E8E93' },
                grid: { vertLines: { color: 'rgba(0,0,0,0.05)' }, horzLines: { color: 'rgba(0,0,0,0.05)' } },
                rightPriceScale: { borderVisible: false, scaleMargins:{top:0.08,bottom:0.08} },
                timeScale: { borderVisible: false, timeVisible:true, secondsVisible:false },
                crosshair:{mode:LightweightCharts.CrosshairMode?.Normal ?? 0},
                handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},
                handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true}
            });
            const tooltipSeries = [];
            const line = (field,color,title,width=2) => {
                const points = indicators.filter(row => row[field] != null && Number.isFinite(Number(row[field]))).map(row => ({time:row.time,value:Number(row[field])}));
                if (!points.length) return null;
                const series = mainChartInstance.addLineSeries({color,lineWidth:width,title,priceLineVisible:false,lastValueVisible:true});
                series.setData(points); tooltipSeries.push({series,kind:'line',title}); return series;
            };
            const closes = history.map(row => ({time:row.time,value:Number(row.Close)}));
            if (view === 'price') {
                const series = chartMode === 'candlestick'
                    ? mainChartInstance.addCandlestickSeries({upColor:'#27845d',downColor:'#c24f50',borderVisible:false,wickUpColor:'#27845d',wickDownColor:'#c24f50'})
                    : mainChartInstance.addLineSeries({color:'#216bc2',lineWidth:2,title:'Close'});
                series.setData(chartMode === 'candlestick' ? history.filter(row=>Number.isFinite(Number(row.Open))&&Number.isFinite(Number(row.High))&&Number.isFinite(Number(row.Low))).map(row=>({time:row.time,open:Number(row.Open),high:Number(row.High),low:Number(row.Low),close:Number(row.Close)})) : closes);
                tooltipSeries.push({series,kind:chartMode === 'candlestick' ? 'ohlc' : 'line',title:'Close'});
            } else if (view === 'volume') {
                const bars = mainChartInstance.addHistogramSeries({priceFormat:{type:'volume'},title:'Volume'});
                bars.setData(history.filter(row=>row.Volume != null && Number.isFinite(Number(row.Volume))).map((row,index)=>({time:row.time,value:Number(row.Volume),color:index===0||Number(row.Close)>=Number(history[index-1]?.Close)?'rgba(39,132,93,.62)':'rgba(194,79,80,.62)'})));
                tooltipSeries.push({series:bars,kind:'line',title:'Volume'});
            } else if (view === 'trend') {
                line('close','#252a33','Close'); line('sma20','#d29c39','SMA 20',1); line('ema20','#216bc2','EMA 20',1);
            } else if (view === 'bollinger') {
                line('close','#252a33','Close'); line('bollinger_upper','#4c8d9b','Upper band',1); line('bollinger_lower','#4c8d9b','Lower band',1);
            } else if (view === 'rsi') {
                const rsi = line('rsi14','#216bc2','RSI 14');
                if (rsi) { rsi.createPriceLine({price:70,color:'rgba(194,79,80,.7)',lineStyle:2,lineWidth:1,axisLabelVisible:true,title:'70'}); rsi.createPriceLine({price:30,color:'rgba(39,132,93,.7)',lineStyle:2,lineWidth:1,axisLabelVisible:true,title:'30'}); }
            } else if (view === 'macd') {
                line('macd','#216bc2','MACD'); line('macd_signal','#d29c39','Signal',1);
                const histogram = mainChartInstance.addHistogramSeries({title:'Histogram',priceLineVisible:false});
                histogram.setData(indicators.filter(row=>row.macd_hist != null && Number.isFinite(Number(row.macd_hist))).map(row=>({time:row.time,value:Number(row.macd_hist),color:Number(row.macd_hist)>=0?'rgba(39,132,93,.55)':'rgba(194,79,80,.55)'})));
                tooltipSeries.push({series:histogram,kind:'line',title:'MACD histogram'});
            } else if (view === 'atr') line('atr14','#4c8d9b','ATR 14');
            else if (view === 'performance') {
                const base = closes.find(point=>point.value>0)?.value;
                const series = mainChartInstance.addLineSeries({color:'#216bc2',lineWidth:2,title:'Indexed close',priceFormat:{type:'custom',minMove:.1,formatter:value=>`${value.toFixed(1)}`}});
                if (base) series.setData(closes.map(point=>({time:point.time,value:Number((point.value/base*100).toFixed(2))})));
                tooltipSeries.push({series,kind:'line',title:'Indexed performance'});
            }
            if (view !== 'price' && view !== 'volume' && view !== 'macd' && view !== 'performance') {
                const used = indicators.some(row=>Number.isFinite(Number(row[{trend:'sma20',bollinger:'bollinger_upper',rsi:'rsi14',atr:'atr14'}[view]])));
                if (!used) chartContainer.innerHTML = '<div class="chart-empty-state">This indicator is unavailable for the selected history range.</div>';
            }
            mainChartInstance.timeScale().fitContent();
            const tooltip = document.getElementById('chart-hover-tip');
            mainChartInstance.subscribeCrosshairMove(param => {
                if (!param?.time || !param.point || param.point.x < 0 || param.point.y < 0) { tooltip.textContent = 'Move across the chart to inspect values'; return; }
                const label = typeof param.time === 'string' ? param.time : `${param.time.year}-${String(param.time.month).padStart(2,'0')}-${String(param.time.day).padStart(2,'0')}`;
                const values = tooltipSeries.map(({series,kind,title}) => {
                    const value = param.seriesData.get(series);
                    if (!value) return '';
                    if (kind === 'ohlc') return `O ${formatMarketNumber(value.open)}  H ${formatMarketNumber(value.high)}  L ${formatMarketNumber(value.low)}  C ${formatMarketNumber(value.close)}`;
                    return `${title} ${formatMarketNumber(value.value ?? value.close,2)}`;
                }).filter(Boolean);
                tooltip.textContent = values.length ? `${label}  ·  ${values.join('  ·  ')}` : `${label}  ·  No value for this session`;
            });
            chartResizeObserver = new ResizeObserver(entries => {
                const {width,height} = entries[0].contentRect;
                mainChartInstance?.applyOptions({width:Math.floor(width),height:Math.floor(height)});
            });
            chartResizeObserver.observe(chartContainer);
            document.getElementById('chart-loading').classList.add('hidden');
        }

        // Chat functionality
        async function consumeChatStream(response, typingId) {
            if (!response.ok) {
                const body = await response.json().catch(() => ({}));
                throw new Error(body.detail?.message || body.detail || 'The chat request failed. Please retry.');
            }
            if (!response.body?.getReader) throw new Error('This browser does not support streamed replies. Please reload and retry.');
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let result = null;
            let streamError = null;
            let streamedText = null;
            const handleFrame = frame => {
                let eventName = 'message';
                const dataLines = [];
                for (const line of frame.split(/\r?\n/)) {
                    if (line.startsWith('event:')) eventName = line.slice(6).trim();
                    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
                }
                if (!dataLines.length) return;
                let payload;
                try { payload = JSON.parse(dataLines.join('\n')); } catch (_) { return; }
                if (eventName === 'token' && typeof payload.text === 'string') {
                    const row = document.getElementById(typingId);
                    const bubble = row?.querySelector('.chat-bubble-ai');
                    if (!bubble) return;
                    if (!streamedText) {
                        bubble.replaceChildren();
                        streamedText = document.createElement('div');
                        streamedText.className = 'chat-streaming-text';
                        bubble.append(streamedText);
                    }
                    streamedText.textContent += payload.text;
                    const messages = document.getElementById('chat-messages');
                    messages.scrollTop = messages.scrollHeight;
                } else if (eventName === 'done') result = payload;
                else if (eventName === 'error') streamError = new Error(payload.message || 'The local AI request failed.');
            };
            while (true) {
                const {value, done} = await reader.read();
                buffer += decoder.decode(value || new Uint8Array(), {stream:!done});
                const frames = buffer.split(/\r?\n\r?\n/);
                buffer = frames.pop() || '';
                frames.forEach(handleFrame);
                if (done) break;
            }
            if (buffer.trim()) handleFrame(buffer);
            if (streamError) throw streamError;
            if (!result) throw new Error('The reply stream ended before the analysis was complete. Retry your question.');
            return result;
        }
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const msg = input.value.trim();
            if (!msg) return;

            const messages = document.getElementById('chat-messages');
            if (messages.querySelector('.chat-starters')) messages.replaceChildren();
            const userRowId = `chat-user-${Date.now()}`;
            appendChat('user', msg, null, userRowId);
            renderChatAttachments();
            input.value = '';
            input.style.height = '52px';
            
            const typingId = 'typing-' + Date.now();
            appendChat('assistant', '<p role="status" class="m-0 text-apple-gray"><span class="inline-flex gap-1 align-middle mr-2"><i class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></i><i class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></i><i class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></i></span>Checking relevant sources and preparing the analysis…</p>', null, typingId);

            try {
                const res = await fetch('/api/chat/stream', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: msg,
                        symbol: currentSymbol,
                        chart_period: activeChartPeriod,
                        chart_interval: activeChartInterval,
                        chart_mode: chartMode,
                        chart_view: analysisView,
                        dataset_id: activeDatasetId,
                        document_ids: selectedDocumentIds,
                        session_id: chatSessionId,
                        mode: currentSettings.default_chat_mode || 'auto'
                    })
                });
                const data = await consumeChatStream(res, typingId);
                addBranchButton(document.getElementById(userRowId), data.user_message_id);
                if (data.session_id) {
                    chatSessionId = data.session_id;
                    localStorage.setItem('stockrag.sessionId', chatSessionId);
                    renderChatHistory();
                    loadChatHistory();
                }
                document.getElementById(typingId).remove();
                appendChat('assistant', data.answer, currentSettings.citation_visibility === false || currentSettings.show_data_sources === false ? null : data.citations, null, data.data_status, {
                    model: data.model, timestamp: data.data_timestamp, retrieval: data.retrieval,
                    sourcesUnverified: data.sources_unverified, formatUnverified: data.format_unverified,
                    numericValidation: data.numeric_validation, answerMethod: data.answer_method
                }, data.assistant_message_id);
                
            } catch (err) {
                document.getElementById(typingId)?.remove();
                appendChat('assistant', `The analysis service could not produce a reply. ${err.message || 'Check the local AI service and retry.'}`, null, null, 'SERVICE_ERROR');
                attachRetryToLastChatReply(msg);
            }
        }

        function appendChat(role, content, citations = null, id = null, status = null, meta = null, messageId = null) {
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
                                ${citations.map(c => `<li>${citationHtml(c)}</li>`).join('')}
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
                const modelLabel = meta.model || (meta.answerMethod === 'extractive_source_fallback' ? 'Source extract · no LLM' : meta.answerMethod === 'deterministic_insufficient_evidence' ? 'Evidence check · no LLM' : meta.timestamp ? 'Model unavailable' : 'Model not recorded for this saved reply');
                    const retrievalLabel = meta.retrieval?.mode || (meta.retrieval?.document_modes || []).join(' + ');
                    extraHtml += `<div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-black/5 pt-2 text-[10px] text-apple-gray dark:border-white/10"><span>${escapeHtml(modelLabel)}</span><span>Data checked ${escapeHtml(time)}</span>${retrievalLabel ? `<span>${escapeHtml(retrievalLabel)} retrieval</span>` : ''}${warnings.map(warning => `<span class="text-amber-700 dark:text-amber-300">${escapeHtml(warning)}</span>`).join('')}</div>`;
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
                        ${!id && status !== 'SERVICE_ERROR' ? '<button type="button" class="chat-copy-button" aria-label="Copy assistant reply" title="Copy reply"><i data-lucide="copy" class="h-4 w-4"></i></button>' : ''}
                        ${!id && status !== 'SERVICE_ERROR' && messageId ? '<button type="button" class="chat-branch-button" aria-label="Branch conversation from this reply" title="Branch from this reply"><i data-lucide="git-branch" class="h-4 w-4"></i></button>' : ''}
                    </div>
                `;
            }
            
            container.insertAdjacentHTML('beforeend', bubbleHtml);
            const copyButton = container.lastElementChild?.querySelector('.chat-copy-button');
            const branchButton = container.lastElementChild?.querySelector('.chat-branch-button');
            branchButton?.addEventListener('click', () => branchChat(messageId));
            copyButton?.addEventListener('click', async () => {
                const bubble = copyButton.parentElement.querySelector('.chat-bubble-ai');
                try {
                    await navigator.clipboard.writeText(bubble?.innerText || '');
                    copyButton.title = 'Copied';
                    copyButton.setAttribute('aria-label', 'Reply copied');
                    copyButton.innerHTML = '<i data-lucide="check" class="h-4 w-4"></i>';
                    lucide.createIcons();
                    setTimeout(() => {
                        copyButton.title = 'Copy reply';
                        copyButton.setAttribute('aria-label', 'Copy assistant reply');
                        copyButton.innerHTML = '<i data-lucide="copy" class="h-4 w-4"></i>';
                        lucide.createIcons();
                    }, 1300);
                } catch (_) {
                    copyButton.title = 'Clipboard unavailable';
                }
            });
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
            if (currentSymbol) loadChartData(activeChartPeriod || currentSettings.default_chart_period || '1mo');
        }

        async function restoreChatSession(sessionToRestore = chatSessionId) {
            if (!sessionToRestore) { renderChatHistory(); return; }
            chatSessionId = sessionToRestore;
            localStorage.setItem('stockrag.sessionId', chatSessionId);
            renderChatHistory();
            const requestedSession = sessionToRestore;
            const generation = ++chatRestoreGeneration;
            try {
                const res = await fetch(`/api/chat/sessions/${encodeURIComponent(requestedSession)}`);
                if (!res.ok) throw new Error('Saved conversation unavailable');
                const data = await res.json();
                if (generation !== chatRestoreGeneration || requestedSession !== chatSessionId) return;
                selectedDocumentIds = Array.isArray(data.document_ids) ? data.document_ids.map(Number).filter(Number.isFinite) : [];
                activeDatasetId = data.dataset_id == null ? null : Number(data.dataset_id);
                renderChatAttachments();
                const container = document.getElementById('chat-messages');
                container.innerHTML = '';
                if (data.parent_session_id) {
                    const lineage = document.createElement('div');
                    lineage.className = 'chat-lineage-note';
                    lineage.textContent = 'Branch conversation · History through the selected message was copied. Recent turns are used as model context.';
                    container.append(lineage);
                }
                let precedingUserMessage = '';
                data.messages.forEach(message => {
                    if (message.role === 'user') precedingUserMessage = message.content;
                    const legacyFailure = message.role === 'assistant' && /^(?:Error:\s*Could not connect to Ollama|AI response unavailable:|Analysis failed before a response could be generated\.)/i.test(message.content);
                    if (legacyFailure) {
                        appendChat('assistant', `The analysis service did not generate a reply. ${message.content.replace(/^Error:\s*/i, '')}`, null, null, 'SERVICE_ERROR');
                        attachRetryToLastChatReply(precedingUserMessage);
                    } else {
                        const metricMismatch = message.role === 'assistant' ? savedReplyMetricMismatch(precedingUserMessage, message.content) : null;
                        const storedMeta = message.metadata || {};
                        const replyMeta = message.role === 'assistant' ? {
                            model: storedMeta.model, timestamp: storedMeta.data_timestamp, retrieval: storedMeta.retrieval,
                            sourcesUnverified: storedMeta.sources_unverified, formatUnverified: storedMeta.format_unverified,
                            numericValidation: storedMeta.numeric_validation, answerMethod: storedMeta.answer_method
                        } : null;
                        appendChat(message.role, message.content, message.role === 'assistant' ? message.sources : null, null, storedMeta.data_status, replyMeta, metricMismatch ? null : message.id);
                        if (message.role === 'user') addBranchButton(container.lastElementChild, message.id);
                        if (metricMismatch) {
                            const target = container.lastElementChild;
                            const bubble = target?.querySelector('.chat-bubble-ai');
                            if (bubble) {
                                const warning = document.createElement('p');
                                warning.className = 'chat-legacy-warning';
                                warning.textContent = `Review this saved answer: your question asks about ${metricMismatch.requested}, but this answer discusses ${metricMismatch.answered}. Re-check it against the source.`;
                                bubble.append(warning);
                            }
                            attachRetryToLastChatReply(precedingUserMessage, target);
                        }
                    }
                });
                renderChatHistory();
            } catch (_) {
                if (generation !== chatRestoreGeneration) return;
                localStorage.removeItem('stockrag.sessionId');
                chatSessionId = null;
            }
        }

        function renderRetryState(containerId, message, retry) {
            if (containerId === 'mainChart') {
                disposeMainChart();
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
            renderChatHistory();
            toggleChatHistory(false);
            document.getElementById('chat-input')?.focus();
        }

        function renderChatAttachments() {
            const root = document.getElementById('chat-attachments');
            if (!root) return;
            const chips = selectedDocumentIds.map(id => {
                const doc = knownDocuments.find(item => Number(item.id) === Number(id));
                const name = doc?.filename || `Research document ${Number(id)}`;
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

            const extension = file.name.toLowerCase().split('.').pop();
            const isDataset = ['csv','xlsx','xls'].includes(extension);
            const isResearchDocument = ['pdf','docx','txt','html','htm'].includes(extension);
            if (!isDataset && !isResearchDocument) {
                const status = document.getElementById('upload-status');
                status.className = 'text-sm font-bold p-3 rounded-xl bg-red-500/10 text-red-500 flex items-center justify-center gap-2 mt-4';
                status.textContent = 'Supported uploads: PDF, DOCX, TXT, HTML, CSV, XLSX, and XLS.';
                input.value = '';
                return;
            }
            const type = isDataset ? 'dataset' : 'document';
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
            if (isResearchDocument && !fromChat) {
                const metadata = {};
                const company = document.getElementById('document-company')?.value.trim();
                const ticker = document.getElementById('document-ticker')?.value.trim();
                const documentType = document.getElementById('document-kind')?.value;
                if (company) metadata.company = company;
                if (ticker) metadata.ticker = ticker;
                if (documentType && documentType !== 'pdf') metadata.document_type = documentType;
                fd.append('metadata_json', JSON.stringify(metadata));
            }
            
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
            const ticker = document.getElementById('crawl-ticker')?.value.trim().toUpperCase();
            if(!url) return;
            
            const status = document.getElementById('upload-status');
            status.classList.remove('hidden');
            status.className = 'text-sm font-bold p-3 rounded-xl bg-blue-500/10 text-blue-500 flex items-center justify-center gap-2 mt-4';
            status.innerHTML = `<div class="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div> Crawling and indexing...`;

            try {
                const res = await fetch('/api/crawl', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url, ...(ticker ? {ticker} : {})})
                });
                if(res.ok) {
                    const result = await res.json();
                    status.className = 'text-sm font-bold p-3 rounded-xl bg-green-500/10 text-green-500 flex items-center justify-center gap-2 mt-4';
                    status.textContent = `Indexed ${result.title || 'web page'}${ticker ? ` for ${ticker}` : ''}.`;
                    await loadDocuments();
                    input.value = '';
                    const tickerInput = document.getElementById('crawl-ticker');
                    if (tickerInput) tickerInput.value = '';
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
                setDot(aiDot, data.ollama === 'connected' && data.model_available, `Ollama ${data.ollama}; model ${data.model}${data.model_available ? ' installed' : ' unavailable'}`);
                const retrievalMode = data.document_retrieval || 'unavailable';
                const ragReady = retrievalMode === 'semantic' || retrievalMode === 'keyword' || retrievalMode === 'available';
                const retrievalLabel = retrievalMode === 'keyword' ? 'keyword fallback' : retrievalMode === 'semantic' || retrievalMode === 'available' ? 'semantic search' : 'unavailable';
                setDot(document.getElementById('status-faiss'), ragReady, `Document retrieval: ${retrievalLabel}; embedding model ${data.embedding_model || 'unknown'} ${data.embedding_model_available ? 'installed' : 'missing'}`);
                document.getElementById('status-api-text').textContent = data.market_data?.status === 'available' ? (data.market_data?.data_status || 'Connected') : 'Unavailable';
                document.getElementById('status-api-text').title = data.market_data?.error || `${data.market_data?.provider || 'Market provider'} · ${data.market_data?.data_status || ''}`;
                document.getElementById('status-ollama-text').textContent = data.ollama === 'connected' && data.model_available ? 'Connected' : 'Unavailable';
                document.getElementById('status-faiss-text').textContent = retrievalMode === 'keyword' ? 'Keyword' : ragReady ? 'Ready' : 'Unavailable';
                const items = [
                    {name:'Application API',icon:'server',state:'ready',detail:'Local API is responding.'},
                    {name:'Market data',icon:'chart-no-axes-combined',state:data.market_data?.status === 'available' ? 'ready' : 'issue',detail:data.market_data?.status === 'available' ? `${data.market_data.provider || 'Provider connected'} · ${data.market_data.data_status || 'freshness not verified'}` : (data.market_data?.error || 'No configured market-data provider is reachable.')},
                    {name:'Local AI model',icon:'cpu',state:data.ollama === 'connected' && data.model_available ? 'ready' : 'issue',label:data.ollama === 'connected' && data.model_available ? 'Connected' : undefined,detail:data.ollama === 'connected' && data.model_available ? `${data.model} is installed and Ollama is reachable. This status check does not test whether a complete chat reply can be generated.` : `Ollama ${data.ollama || 'status unknown'} · ${data.model || 'configured model'} ${data.model_available ? 'available' : 'not available'}.`},
                    {name:'Document retrieval',icon:'database',state:retrievalMode === 'semantic' ? 'ready' : retrievalMode === 'keyword' ? 'warning' : 'issue',detail:retrievalMode === 'semantic' ? `Semantic search ready with ${data.embedding_model || 'configured embeddings'}.` : retrievalMode === 'keyword' ? `Keyword fallback active; embedding model ${data.embedding_model || 'not configured'} ${data.embedding_model_available ? 'available' : 'missing'}.` : 'Document retrieval is unavailable.'},
                    {name:'Vector database',icon:'layers-3',state:data.vector_database === 'available' ? 'ready' : 'issue',detail:`${data.vector_database || 'Vector database status unknown'}${data.vector_backend ? ` · ${data.vector_backend}` : ''}.`},
                ];
                if (!data.embedding_model_available) items.push({name:'Embedding model',icon:'binary',state:'warning',detail:`${data.embedding_model || 'No embedding model'} is not installed or reachable; semantic retrieval may fall back to keyword search.`});
                const issueCount = items.filter(item => item.state === 'issue').length;
                const warningCount = items.filter(item => item.state === 'warning').length;
                const summary = issueCount || warningCount ? `${issueCount + warningCount} issue${issueCount + warningCount === 1 ? '' : 's'}` : 'Available';
                const statusState = issueCount ? 'issue' : warningCount ? 'warning' : 'ready';
                updateProjectStatus(items, summary, statusState);
                document.getElementById('header-health').title = `Click for project status details. ${summary}.`;
                apiDot.dataset.vectorStatus = data.vector_database;
                const engine = document.getElementById('chat-engine-status');
                const ready = data.ollama === 'connected' && data.model_available;
                const indicator = engine.querySelector('span');
                if (indicator) indicator.style.background = ready ? '#0a84ff' : '#f59e0b';
                const chatRetrievalLabel = data.document_retrieval === 'semantic' ? 'semantic RAG' : data.document_retrieval === 'keyword' ? 'keyword fallback' : 'retrieval unavailable';
                engine.lastChild.textContent = ready ? ` ${data.model} · ${chatRetrievalLabel}` : ` ${data.model || 'Local model'} unavailable · ${chatRetrievalLabel}`;
                engine.title = `Ollama ${ready ? 'connected' : 'unavailable'} · ${data.model || 'model unknown'} · ${chatRetrievalLabel} · embeddings ${data.embedding_model || 'not configured'}${data.embedding_model_available ? ' available' : ' unavailable'}`;
                document.getElementById('ai-page-health').textContent = ready
                    ? `Ollama connected · ${retrievalLabel} · ${data.model}`
                    : `Ollama unavailable · ${data.model || 'configured model'} not ready`;
                document.getElementById('ai-page-health').title = `Document retrieval: ${retrievalLabel}. Web crawl uses the same indexed document retrieval path. Embeddings: ${data.embedding_model || 'not configured'}${data.embedding_model_available ? ' ready' : ' unavailable'}.`;
            } catch (e) {
                document.getElementById('status-api').style.background = '#f59e0b';
                document.getElementById('status-ollama').style.background = '#f59e0b';
                document.getElementById('status-faiss').style.background = '#f59e0b';
                document.getElementById('status-api-text').textContent = 'Check failed';
                document.getElementById('status-ollama-text').textContent = 'Check failed';
                document.getElementById('status-faiss-text').textContent = 'Check failed';
                const message = e?.message || 'The app could not reach its local health endpoint.';
                updateProjectStatus([
                    {name:'Application API',icon:'server-off',state:'issue',detail:`GET /api/health failed: ${message}`},
                    {name:'Market data',icon:'chart-no-axes-combined',state:'warning',detail:'Could not check provider status because the local API health request failed.'},
                    {name:'Local AI model',icon:'cpu',state:'warning',detail:'Could not check Ollama or the configured model.'},
                    {name:'Document retrieval',icon:'database',state:'warning',detail:'Could not check semantic or keyword retrieval.'},
                ], 'API check failed', 'issue');
                document.getElementById('ai-page-health').textContent = 'Service status unavailable';
            }
        }
        setInterval(checkHealth, 30000);
        setupComparisonSelectors();
        setupChatPage();
        restoreLocation();
        checkHealth();
        fetchSettings();
        restoreChatSession();
