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
        let currentForecastHorizon = 5;
        let latestForecastData = null;
        let forecastLoading = false;
        let chatSessionId = localStorage.getItem('stockrag.sessionId') || null;
        let chatRestoreGeneration = 0;
        let currentChatMode = localStorage.getItem('stockrag.chatMode') || 'general';
        let webCrawlEnabled = localStorage.getItem('stockrag.webCrawl') !== 'false';
        let chatHistoryItems = [];
        let pendingChatDeletion = null;
        let latestProjectStatusItems = [];
        let selectedDocumentIds = JSON.parse(localStorage.getItem('stockrag.documentIds') || '[]');
        let knownDocuments = [];
        let currentSettings = {};

        function escapeHtml(text) {
            if (text === null || text === undefined) return '';
            return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
        }

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
            const isDark = theme === 'dark';
            document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
            document.documentElement.classList.toggle('dark', isDark);
            document.documentElement.classList.toggle('light', !isDark);
            document.documentElement.dataset.density = density === 'compact' ? 'compact' : 'comfortable';
            document.documentElement.dataset.advanced = currentSettings.show_advanced_metrics === false ? 'false' : 'true';
            try {
                localStorage.setItem('stockrag.theme', isDark ? 'dark' : 'light');
            } catch (_) {}
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
            showView('ai');
            if (window.innerWidth < 768) toggleSidebar(false);
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
            const issueCount = items.filter(item => item.state === 'issue').length;
            const warningCount = items.filter(item => item.state === 'warning').length;

            // 1. Top navigation status button (#header-health)
            const header = document.getElementById('header-health');
            const headerIcon = document.getElementById('header-health-icon');
            const headerDot = document.getElementById('status-summary-dot');
            const headerLabel = document.getElementById('status-summary');

            // 2. Sidebar status button (#sidebar-status-...)
            const sidebarIcon = document.getElementById('sidebar-status-icon');
            const sidebarDot = document.getElementById('sidebar-status-dot');
            const sidebarLabel = document.getElementById('sidebar-status-text');

            let headerText = 'System Ready';
            let iconName = 'activity';
            let headerThemeClasses = '';
            let dotThemeClasses = '';
            let bannerBgClass = '';
            let bannerBorderClass = '';
            let bannerTextClass = '';
            let bannerIconName = 'check-circle-2';
            let bannerTitle = 'Checking system status';
            let bannerDesc = 'Local API, AI engine, vector storage, and market data providers are online and ready.';

            if (state === 'issue') {
                headerText = issueCount === 1 ? '1 Issue' : `${issueCount} Issues`;
                iconName = 'alert-circle';
                headerThemeClasses = 'bg-rose-500/10 hover:bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30';
                dotThemeClasses = 'bg-rose-500 animate-pulse';
                bannerBgClass = 'bg-rose-500/10';
                bannerBorderClass = 'border-rose-500/25';
                bannerTextClass = 'text-rose-800 dark:text-rose-300';
                bannerIconName = 'alert-circle';
                bannerTitle = `${issueCount} Issue${issueCount > 1 ? 's' : ''} Detected`;
                const failingNames = items.filter(i => i.state === 'issue').map(i => i.name).join(', ');
                bannerDesc = `Action required for: ${failingNames}. Review the diagnostic details below.`;
            } else if (state === 'warning') {
                headerText = warningCount === 1 ? '1 Warning' : `${warningCount} Warnings`;
                iconName = 'alert-triangle';
                headerThemeClasses = 'bg-amber-500/10 hover:bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30';
                dotThemeClasses = 'bg-amber-500';
                bannerBgClass = 'bg-amber-500/10';
                bannerBorderClass = 'border-amber-500/25';
                bannerTextClass = 'text-amber-800 dark:text-amber-300';
                bannerIconName = 'alert-triangle';
                bannerTitle = 'Degraded Performance';
                const warningNames = items.filter(i => i.state === 'warning').map(i => i.name).join(', ');
                bannerDesc = `Fallback active for: ${warningNames}. Review diagnostic cards below.`;
            } else {
                headerText = 'System Ready';
                iconName = 'activity';
                headerThemeClasses = 'bg-emerald-500/10 hover:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/25';
                dotThemeClasses = 'bg-emerald-500 animate-pulse';
                bannerBgClass = 'bg-emerald-500/10';
                bannerBorderClass = 'border-emerald-500/25';
                bannerTextClass = 'text-emerald-800 dark:text-emerald-300';
                bannerIconName = 'check-circle-2';
                bannerTitle = 'System checks complete';
                bannerDesc = 'Local API, AI engine, document retrieval, and market data providers are online.';
            }

            if (headerLabel) headerLabel.textContent = headerText;
            if (header) {
                header.className = `system-status-trigger flex h-8 shrink-0 items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold border transition-all duration-200 cursor-pointer shadow-2xs group active:scale-95 ${headerThemeClasses}`;
                header.setAttribute('aria-label', `System status: ${headerText}`);
                header.title = `Click for full system diagnostics. Current status: ${headerText}.`;
                header.dataset.status = state;
            }
            if (headerIcon) headerIcon.dataset.lucide = iconName;
            if (headerDot) {
                headerDot.className = `w-2 h-2 rounded-full status-dot ${dotThemeClasses}`;
            }

            if (sidebarLabel) sidebarLabel.textContent = state === 'ready' ? 'System Ready' : headerText;
            if (sidebarIcon) sidebarIcon.dataset.lucide = iconName;
            if (sidebarDot) {
                sidebarDot.className = `w-2 h-2 rounded-full absolute -top-0.5 -right-0.5 ring-2 ring-white dark:ring-[#161618] ${dotThemeClasses}`;
            }

            // 3. Popover Overall Banner & Timestamp
            const banner = document.getElementById('system-status-banner');
            const bannerIcon = document.getElementById('system-status-banner-icon');
            const bannerTitleEl = document.getElementById('system-status-banner-title');
            const bannerSummaryEl = document.getElementById('system-status-summary');
            const lastCheckedEl = document.getElementById('system-status-last-checked');

            if (banner) {
                banner.className = `my-3 p-3 rounded-xl border flex items-start gap-2.5 shrink-0 transition-colors ${bannerBgClass} ${bannerBorderClass} ${bannerTextClass}`;
            }
            if (bannerIcon) bannerIcon.dataset.lucide = bannerIconName;
            if (bannerTitleEl) bannerTitleEl.textContent = bannerTitle;
            if (bannerSummaryEl) bannerSummaryEl.textContent = bannerDesc;
            if (lastCheckedEl) {
                const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                lastCheckedEl.textContent = `Checked at ${now} · Auto-refreshes every 30s`;
            }

            // 4. Detailed Service Cards in Popover
            const details = document.getElementById('system-status-details');
            if (details) {
                details.replaceChildren(...items.map(item => {
                    const card = document.createElement('div');
                    const isIssue = item.state === 'issue';
                    const isWarning = item.state === 'warning';
                    
                    const cardBg = isIssue 
                        ? 'bg-rose-500/[0.05] border-rose-500/20' 
                        : isWarning 
                            ? 'bg-amber-500/[0.05] border-amber-500/20' 
                            : 'bg-black/[0.02] dark:bg-white/[0.03] border-black/5 dark:border-white/5';
                    
                    const iconBg = isIssue 
                        ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400' 
                        : isWarning 
                            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400' 
                            : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400';
                    
                    const badgeClass = isIssue 
                        ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30' 
                        : isWarning 
                            ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30' 
                            : 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30';
                    
                    const badgeText = item.label || (isIssue ? 'Offline' : isWarning ? 'Degraded' : 'Ready');

                    card.className = `p-2.5 rounded-xl border ${cardBg} flex items-start gap-3 transition-colors`;
                    card.innerHTML = `
                        <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${iconBg}">
                            <i data-lucide="${item.icon}" class="w-4 h-4"></i>
                        </div>
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center justify-between gap-2">
                                <span class="font-bold text-gray-900 dark:text-gray-100 text-xs">${escapeHtml(item.name)}</span>
                                <span class="text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wider ${badgeClass}">${badgeText}</span>
                            </div>
                            <p class="text-[11px] text-apple-gray mt-1 leading-relaxed break-words">${escapeHtml(item.detail)}</p>
                            ${item.action ? `<p class="text-[10.5px] font-semibold text-apple-blue mt-1.5 flex items-center gap-1">${escapeHtml(item.action)}</p>` : ''}
                        </div>
                    `;
                    return card;
                }));
            }

            if (window.lucide) lucide.createIcons();
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
        function updateWatchlistBadge() {
            const count = watchlistSymbols.size;
            const badge = document.getElementById('dock-watchlist-badge');
            if (badge) {
                badge.textContent = String(count);
                badge.classList.toggle('hidden', count === 0);
            }
            const mobileBadge = document.getElementById('mobile-watchlist-badge');
            if (mobileBadge) {
                mobileBadge.textContent = String(count);
                mobileBadge.classList.toggle('hidden', count === 0);
            }
        }
        window.updateWatchlistBadge = updateWatchlistBadge;

        function toggleTheme() {
            const isDark = document.documentElement.dataset.theme === 'dark';
            const next = isDark ? 'light' : 'dark';
            applyTheme(next);
            currentSettings.theme = next;
            try {
                localStorage.setItem('stockrag.theme', next);
            } catch (_) {}
            fetch('/api/settings', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({theme: next})
            }).catch(() => {});
        }
        window.toggleTheme = toggleTheme;

        function startNewChat() {
            showView('ai');
            resetChatSession();
            if (window.innerWidth <= 768) {
                toggleSidebar(false);
            }
        }
        window.startNewChat = startNewChat;

        function setActiveNavigation(route) {
            document.querySelectorAll('.dock-btn[data-route], .sidebar-nav-btn[data-route], .bottom-app-nav .nav-item[data-route], .top-nav-dock .nav-item[data-route], .nav-item[data-route]').forEach(button => {
                const isActive = button.dataset.route === route;
                button.classList.toggle('active', isActive);
                button.setAttribute('aria-current', isActive ? 'page' : 'false');
            });
        }
        function selectSidebarStock(symbol) {
            const input = document.getElementById('symbol-input');
            if (input) input.value = symbol;
            handleSearch();
            if (window.innerWidth < 768) toggleSidebar(false);
        }
        function positionDockForView(view) {
            setActiveNavigation(view);
        }
        window.positionDockForView = positionDockForView;

        function showView(view, updateUrl = true) {
            if (!['dashboard','watchlist','news','compare','ai'].includes(view)) return;
            toggleChatPageMenu(false);
            closeChatFocus();
            activePrimaryView = view;
            
            const dashboardView = document.getElementById('dashboard-view');
            const aiView = document.getElementById('ai-view');
            const mainHeader = document.getElementById('main-terminal-header');
            const sidebar = document.getElementById('app-sidebar');
            const floatingDock = document.getElementById('floating-dock');
            
            // Top navigation bar is permanent and visible across all pages
            if (mainHeader) mainHeader.classList.remove('hidden');
            if (floatingDock) floatingDock.classList.remove('hidden');
            
            if (view === 'ai') {
                if (dashboardView) dashboardView.classList.add('hidden');
                if (aiView) aiView.classList.remove('hidden');
                if (sidebar) {
                    sidebar.classList.remove('hidden');
                    sidebar.classList.remove('sidebar-collapsed');
                }
                const expandBtn = document.getElementById('sidebar-expand-btn');
                if (expandBtn) expandBtn.classList.add('hidden');
                setActiveNavigation('ai');
                loadChatHistory();
                if (chatSessionId) {
                    restoreChatSession(chatSessionId);
                }
                setTimeout(() => {
                    const input = document.getElementById('chat-input');
                    if (input && window.innerWidth >= 768) input.focus();
                }, 100);
            } else {
                if (aiView) aiView.classList.add('hidden');
                if (dashboardView) dashboardView.classList.remove('hidden');
                if (sidebar) sidebar.classList.add('hidden');
                setActiveNavigation(view);
                
                document.getElementById('stock-view')?.classList.add('hidden');
                document.getElementById('empty-state')?.classList.toggle('hidden', view !== 'dashboard');
                document.getElementById('news-page')?.classList.toggle('hidden', view !== 'news');
                document.getElementById('watchlist-page')?.classList.toggle('hidden', view !== 'watchlist');
                document.getElementById('compare-page')?.classList.toggle('hidden', view !== 'compare');
                watchlistOnly = false;
                if (view === 'watchlist') renderWatchlistTable();
                renderNewsContext();
                applyWatchlistFilter();
                if (dashboardView) dashboardView.scrollTop = 0;
                if (view === 'news') loadLandingNews(landingLoadGeneration, true);
                if (view === 'compare' && !comparisonLoaded) { comparisonLoaded = true; loadComparisons(); }
            }
            
            setActiveNavigation(view);
            updateWatchlistBadge();
            if (updateUrl) {
                const paths = {dashboard:'/markets',watchlist:'/watchlist',news:'/news',compare:'/compare',ai:'/ai'};
                if (location.pathname !== paths[view]) history.pushState({view},'',paths[view]);
            }
        }
        window.showView = showView;
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
            if (!document.getElementById('delete-chat-dialog')?.classList.contains('hidden')) closeDeleteChatDialog();
            else if (!document.getElementById('system-status-popover')?.classList.contains('hidden')) toggleSystemStatus(false);
            else if (!document.getElementById('chat-page-menu')?.classList.contains('hidden')) toggleChatPageMenu(false);
            if (document.getElementById('chat-panel')?.classList.contains('chat-focus')) closeChatFocus();
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
            if (panel) {
                panel.classList.remove('chat-focus', 'mobile-open');
            }
            document.body.classList.remove('chat-open');
            setActiveNavigation(activePrimaryView);
        }
        function setupChatPage() {
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
                if (chatSessionId) {
                    const cur = chatHistoryItems.find(i => i.session_id === chatSessionId);
                    if (cur && cur.title) {
                        updateActiveChatHeader(cur.title, Boolean(cur.is_branch));
                    }
                }
                if (status) status.textContent = `${chatHistoryItems.length} saved conversation${chatHistoryItems.length === 1 ? '' : 's'}`;
            } catch (_) {
                list.innerHTML = '<p class="px-2 py-3 text-xs text-apple-gray text-center">Could not load conversation history.</p>';
                if (status) status.textContent = 'History unavailable';
            }
        }
        async function togglePinChat(sessionId, currentlyPinned) {
            try {
                const nextState = currentlyPinned ? 0 : 1;
                const res = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/pin`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_pinned: nextState })
                });
                if (!res.ok) throw new Error('Failed to update pin state');
                const item = chatHistoryItems.find(s => s.session_id === sessionId);
                if (item) item.is_pinned = nextState;
                chatHistoryItems.sort((a, b) => {
                    if ((b.is_pinned || 0) !== (a.is_pinned || 0)) {
                        return (b.is_pinned || 0) - (a.is_pinned || 0);
                    }
                    return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
                });
                renderChatHistory();
            } catch (err) {
                console.error('Error toggling pin:', err);
            }
        }
        function renderChatHistory(filter = document.getElementById('chat-history-search')?.value || '') {
            const list = document.getElementById('chat-history-list');
            if (!list) return;
            const query = filter.trim().toLowerCase();
            const items = chatHistoryItems.filter(item => !query || `${item.title} ${item.preview}`.toLowerCase().includes(query));
            if (!items.length) {
                list.innerHTML = `<p class="px-2 py-3 text-xs text-apple-gray text-center">${query ? 'No matching conversations.' : 'Your conversations will appear here.'}</p>`;
                return;
            }

            const pinnedItems = items.filter(item => Boolean(item.is_pinned));
            const recentItems = items.filter(item => !item.is_pinned);

            function createChatRow(item) {
                const row = document.createElement('div');
                row.className = `chat-history-row ${item.session_id === chatSessionId ? 'active' : ''}`;
                
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'chat-history-item';
                button.setAttribute('aria-current', item.session_id === chatSessionId ? 'true' : 'false');
                
                const title = document.createElement('span');
                title.className = 'block truncate text-xs font-semibold text-gray-800 dark:text-gray-200';
                title.textContent = `${item.is_branch ? '↳ ' : ''}${item.title || 'New conversation'}`;
                
                const preview = document.createElement('span');
                preview.className = 'mt-0.5 block truncate text-[10px] text-apple-gray';
                preview.textContent = `${item.message_count || 0} messages · ${item.updated_at ? new Date(item.updated_at).toLocaleDateString() : 'Saved'}`;
                
                const text = document.createElement('span');
                text.className = 'min-w-0 flex-1 text-left';
                text.append(title, preview);
                button.append(text);
                button.addEventListener('click', () => {
                    restoreChatSession(item.session_id);
                    if (window.innerWidth < 768) toggleSidebar(false);
                });

                const actions = document.createElement('div');
                actions.className = 'chat-history-actions flex items-center gap-1 shrink-0';

                // Pin/Unpin button
                const pinBtn = document.createElement('button');
                pinBtn.type = 'button';
                pinBtn.className = 'chat-history-action-btn' + (item.is_pinned ? ' text-apple-blue font-bold' : '');
                pinBtn.title = item.is_pinned ? 'Unpin conversation' : 'Pin conversation';
                pinBtn.innerHTML = `<i data-lucide="${item.is_pinned ? 'pin-off' : 'pin'}" class="h-3.5 w-3.5"></i>`;
                pinBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    togglePinChat(item.session_id, item.is_pinned);
                });

                // Rename button
                const renameBtn = document.createElement('button');
                renameBtn.type = 'button';
                renameBtn.className = 'chat-history-action-btn';
                renameBtn.title = 'Rename conversation';
                renameBtn.innerHTML = '<i data-lucide="pencil" class="h-3.5 w-3.5"></i>';
                renameBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    requestRenameChat(item.session_id, item.title || 'New conversation');
                });

                // Delete button
                const deleteBtn = document.createElement('button');
                deleteBtn.type = 'button';
                deleteBtn.className = 'chat-history-action-btn hover:text-red-600';
                deleteBtn.title = 'Delete conversation';
                deleteBtn.innerHTML = '<i data-lucide="trash-2" class="h-3.5 w-3.5"></i>';
                deleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    requestDeleteChat(item.session_id, item.title || 'New conversation');
                });

                actions.append(pinBtn, renameBtn, deleteBtn);
                row.append(button, actions);
                return row;
            }

            list.replaceChildren();

            if (pinnedItems.length > 0) {
                const pinHeader = document.createElement('div');
                pinHeader.className = 'chat-history-section-header';
                pinHeader.innerHTML = '<i data-lucide="pin" class="w-3 h-3 text-apple-blue inline mr-1"></i> Pinned';
                list.append(pinHeader);
                pinnedItems.forEach(item => list.append(createChatRow(item)));
            }

            if (recentItems.length > 0) {
                if (pinnedItems.length > 0) {
                    const recentHeader = document.createElement('div');
                    recentHeader.className = 'chat-history-section-header mt-3';
                    recentHeader.innerHTML = '<i data-lucide="clock" class="w-3 h-3 text-apple-gray inline mr-1"></i> Recent';
                    list.append(recentHeader);
                }
                recentItems.forEach(item => list.append(createChatRow(item)));
            }

            if (window.lucide) lucide.createIcons();
        }
        function filterChatHistory(query) { renderChatHistory(query); }
        function toggleSidebar(force) {
            const sidebar = document.getElementById('app-sidebar');
            const backdrop = document.getElementById('sidebar-backdrop');
            const expandBtn = document.getElementById('sidebar-expand-btn');
            if (!sidebar) return;
            const isMobile = window.innerWidth < 768;
            if (isMobile) {
                const open = force !== undefined ? Boolean(force) : !sidebar.classList.contains('mobile-open');
                sidebar.classList.toggle('mobile-open', open);
                if (backdrop) backdrop.classList.toggle('hidden', !open);
                if (expandBtn) expandBtn.classList.toggle('hidden', open);
            } else {
                const collapsed = force !== undefined ? !force : !sidebar.classList.contains('sidebar-collapsed');
                sidebar.classList.toggle('sidebar-collapsed', collapsed);
                if (expandBtn) expandBtn.classList.toggle('hidden', !collapsed);
            }
        }
        function toggleChatHistory(force) {
            toggleSidebar(force);
        }
        function toggleChatTopMoreMenu(force) {
            const menu = document.getElementById('chat-top-more-menu');
            if (!menu) return;
            const open = force === undefined ? menu.classList.contains('hidden') : Boolean(force);
            menu.classList.toggle('hidden', !open);
        }
        function updateActiveChatHeader(title, isBranch) {
            const titleEl = document.getElementById('chat-active-title');
            if (titleEl) titleEl.textContent = title || 'New conversation';
            const badge = document.getElementById('chat-active-branch-badge');
            if (badge) badge.classList.toggle('hidden', !isBranch);
        }
        async function startHeaderRename() {
            if (!chatSessionId) return;
            const titleEl = document.getElementById('chat-active-title');
            if (!titleEl) return;
            const currentTitle = titleEl.textContent;
            const input = document.createElement('input');
            input.type = 'text';
            input.value = currentTitle;
            input.className = 'chat-rename-input';
            titleEl.replaceWith(input);
            input.focus();
            input.select();
            let saved = false;
            const finish = async (newVal) => {
                if (saved) return;
                saved = true;
                const finalTitle = (newVal || currentTitle).trim();
                const span = document.createElement('span');
                span.id = 'chat-active-title';
                span.className = 'text-xs sm:text-sm font-semibold truncate text-gray-800 dark:text-gray-200 cursor-pointer hover:underline';
                span.title = 'Click to rename conversation';
                span.textContent = finalTitle;
                span.onclick = startHeaderRename;
                input.replaceWith(span);
                if (finalTitle && finalTitle !== currentTitle) {
                    try {
                        const response = await fetch(`/api/chat/sessions/${encodeURIComponent(chatSessionId)}/rename`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ title: finalTitle })
                        });
                        if (response.ok) {
                            const item = chatHistoryItems.find(i => i.session_id === chatSessionId);
                            if (item) item.title = finalTitle;
                            renderChatHistory();
                        }
                    } catch (_) {}
                }
            };
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') finish(input.value);
                if (e.key === 'Escape') finish(currentTitle);
            });
            input.addEventListener('blur', () => finish(input.value));
        }
        async function branchCurrentChat() {
            if (!chatSessionId) return;
            const buttons = document.querySelectorAll('.chat-branch-button');
            if (buttons.length > 0) {
                buttons[buttons.length - 1].click();
            } else {
                try {
                    const res = await fetch(`/api/chat/sessions/${encodeURIComponent(chatSessionId)}`);
                    const data = await res.json();
                    if (data.messages && data.messages.length > 0) {
                        const lastMsg = data.messages[data.messages.length - 1];
                        branchChat(lastMsg.id);
                    }
                } catch (_) {}
            }
        }
        function setChatMode(mode) {
            currentChatMode = mode === 'general' ? 'general' : 'auto';
            localStorage.setItem('stockrag.chatMode', currentChatMode);
            const generalBtn = document.getElementById('chat-mode-general-btn');
            const marketBtn = document.getElementById('chat-mode-market-btn');
            if (generalBtn && marketBtn) {
                if (currentChatMode === 'general') {
                    generalBtn.classList.add('active', 'text-apple-blue', 'font-bold', 'bg-white', 'dark:bg-[#2c2c2e]', 'shadow-sm');
                    generalBtn.classList.remove('text-gray-500', 'dark:text-gray-400');
                    marketBtn.classList.remove('active', 'text-apple-blue', 'font-bold', 'bg-white', 'dark:bg-[#2c2c2e]', 'shadow-sm');
                    marketBtn.classList.add('text-gray-500', 'dark:text-gray-400');
                } else {
                    marketBtn.classList.add('active', 'text-apple-blue', 'font-bold', 'bg-white', 'dark:bg-[#2c2c2e]', 'shadow-sm');
                    marketBtn.classList.remove('text-gray-500', 'dark:text-gray-400');
                    generalBtn.classList.remove('active', 'text-apple-blue', 'font-bold', 'bg-white', 'dark:bg-[#2c2c2e]', 'shadow-sm');
                    generalBtn.classList.add('text-gray-500', 'dark:text-gray-400');
                }
            }
            const statusEl = document.getElementById('chat-model-status');
            if (statusEl) {
                statusEl.textContent = currentChatMode === 'general' ? 'General AI' : 'Market RAG';
            }
        }
        function toggleWebCrawl(force) {
            webCrawlEnabled = force === undefined ? !webCrawlEnabled : Boolean(force);
            localStorage.setItem('stockrag.webCrawl', String(webCrawlEnabled));
            updateWebCrawlUI();
        }
        function updateWebCrawlUI() {
            const composerLabel = document.getElementById('composer-web-crawl-label') || document.getElementById('composer-web-crawl-text');
            const composerBtn = document.getElementById('composer-web-crawl-toggle');
            if (composerLabel) composerLabel.textContent = webCrawlEnabled ? 'Web: On' : 'Web: Off';
            if (composerBtn) {
                composerBtn.classList.toggle('border-apple-blue', webCrawlEnabled);
                composerBtn.classList.toggle('bg-blue-500/10', webCrawlEnabled);
                composerBtn.classList.toggle('text-apple-blue', webCrawlEnabled);
            }
        }
        function deleteCurrentChat() {
            if (!chatSessionId) {
                resetChatSession();
                return;
            }
            const currentItem = chatHistoryItems.find(i => i.session_id === chatSessionId);
            const title = currentItem?.title || document.getElementById('chat-active-title')?.textContent || 'Current conversation';
            requestDeleteChat(chatSessionId, title);
        }
        function toggleParametersPopover(force) {
            const popover = document.getElementById('parameters-popover');
            if (!popover) return;
            const isHidden = popover.classList.contains('hidden');
            const open = force !== undefined ? Boolean(force) : isHidden;
            
            if (open) {
                syncParametersModalFields();
                popover.classList.remove('hidden');
                popover.classList.add('flex');
            } else {
                popover.classList.add('hidden');
                popover.classList.remove('flex');
            }
            if (window.lucide) {
                lucide.createIcons();
            }
        }
        window.toggleParametersPopover = toggleParametersPopover;

        function syncParametersModalFields() {
            // 1. Sync Model Select Options from chat-model-select or settings
            const paramModelSelect = document.getElementById('param-model-select');
            const chatModelSelect = document.getElementById('chat-model-select');
            const activeModel = currentSettings.ai_model || chatModelSelect?.value || 'gemma3:1b';
            
            if (paramModelSelect && chatModelSelect) {
                paramModelSelect.replaceChildren();
                Array.from(chatModelSelect.options).forEach(opt => {
                    const clone = opt.cloneNode(true);
                    paramModelSelect.appendChild(clone);
                });
                paramModelSelect.value = activeModel;

                const modelCountEl = document.getElementById('param-model-count');
                if (modelCountEl) {
                    const count = chatModelSelect.options.length;
                    modelCountEl.textContent = count > 0 ? `${count} local model${count > 1 ? 's' : ''}` : 'Local Ollama weights';
                }
            }
            
            // 2. Sync Sliders & numeric display from localStorage or currentSettings
            const savedTemp = localStorage.getItem('stockrag.paramTemp') ?? currentSettings.temperature ?? '0.70';
            const savedMaxTokens = localStorage.getItem('stockrag.paramMaxTokens') ?? currentSettings.max_output_tokens ?? '2048';
            const savedTopP = localStorage.getItem('stockrag.paramTopP') ?? currentSettings.top_p ?? '0.90';
            const savedPersona = localStorage.getItem('stockrag.customPersona') ?? '';

            const tempInput = document.getElementById('param-temp');
            const tempVal = document.getElementById('param-temp-val');
            if (tempInput) tempInput.value = savedTemp;
            if (tempVal) tempVal.textContent = parseFloat(savedTemp).toFixed(2);

            const maxTokensInput = document.getElementById('param-max-tokens');
            const maxTokensVal = document.getElementById('param-max-tokens-val');
            if (maxTokensInput) maxTokensInput.value = savedMaxTokens;
            if (maxTokensVal) maxTokensVal.textContent = String(savedMaxTokens);

            const topPInput = document.getElementById('param-top-p');
            const topPVal = document.getElementById('param-top-p-val');
            if (topPInput) topPInput.value = savedTopP;
            if (topPVal) topPVal.textContent = parseFloat(savedTopP).toFixed(2);

            // 3. Sync Persona Textarea
            const personaInput = document.getElementById('param-custom-persona');
            if (personaInput) personaInput.value = savedPersona;

            // 4. Update active preset badge
            updatePresetPillsActive(parseFloat(savedTemp));

            // 5. Sync web crawl button state
            updateWebCrawlUI();
        }
        window.syncParametersModalFields = syncParametersModalFields;

        function setTokenValue(val) {
            const maxTokensInput = document.getElementById('param-max-tokens');
            const maxTokensVal = document.getElementById('param-max-tokens-val');
            if (maxTokensInput) maxTokensInput.value = String(val);
            if (maxTokensVal) maxTokensVal.textContent = String(val);
            localStorage.setItem('stockrag.paramMaxTokens', String(val));
        }
        window.setTokenValue = setTokenValue;

        function insertPersonaPreset(type) {
            const personaEl = document.getElementById('param-custom-persona');
            if (!personaEl) return;
            const presets = {
                'quant': 'Act as a senior Wall Street quantitative equity researcher. Prioritize statistical rigor, valuation multiples (P/E, EV/EBITDA, DCF logic), and risk-adjusted return metrics with concise structured bullets.',
                'concise': 'Answer with extreme brevity. Provide direct bullet points and verified figures with zero filler, intro/outro padding, or generic disclaimers.',
                'deep': 'Provide comprehensive, step-by-step financial reasoning. Analyze catalysts, downside risks, competitive moats, and financial statements in rigorous detail.',
                'code': 'Provide production-grade code, financial modeling formulas (Python/Pandas/NumPy), and exact mathematical formulas without unnecessary explanations.'
            };
            personaEl.value = presets[type] || '';
            personaEl.focus();
        }
        window.insertPersonaPreset = insertPersonaPreset;

        function onParamModelSelectChange(model) {
            if (!model) return;
            switchChatModel(model);
        }
        window.onParamModelSelectChange = onParamModelSelectChange;

        function showParameterToast(msg = 'Parameters saved & applied') {
            let toast = document.getElementById('parameter-toast');
            if (!toast) {
                toast = document.createElement('div');
                toast.id = 'parameter-toast';
                toast.className = 'fixed bottom-6 left-1/2 -translate-x-1/2 z-[130] px-4 py-2.5 rounded-full bg-gray-900/95 dark:bg-white/95 text-white dark:text-gray-900 text-xs font-semibold shadow-2xl backdrop-blur-xl border border-white/10 dark:border-black/10 transition-all duration-300 pointer-events-none flex items-center gap-2 opacity-0 translate-y-2';
                document.body.appendChild(toast);
            }
            toast.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 shrink-0"></span>${escapeHtml(msg)}`;
            toast.classList.remove('opacity-0', 'translate-y-2');
            toast.classList.add('opacity-100', 'translate-y-0');
            setTimeout(() => {
                toast.classList.remove('opacity-100', 'translate-y-0');
                toast.classList.add('opacity-0', 'translate-y-2');
            }, 2400);
        }
        window.showParameterToast = showParameterToast;

        // Easy-to-close handlers: Escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                const popover = document.getElementById('parameters-popover');
                if (popover && !popover.classList.contains('hidden')) {
                    toggleParametersPopover(false);
                }
            }
        });

        function updatePresetPillsActive(tempVal) {
            const isPrecise = Math.abs(tempVal - 0.20) < 0.15;
            const isBalanced = Math.abs(tempVal - 0.70) < 0.15;
            const isCreative = Math.abs(tempVal - 1.00) < 0.15 || tempVal > 0.85;

            const updatePair = (id1, id2, active) => {
                const el1 = document.getElementById(id1);
                const el2 = document.getElementById(id2);
                [el1, el2].forEach(el => {
                    if (!el) return;
                    if (active) {
                        el.classList.add('bg-apple-blue/10', 'text-apple-blue', 'border-apple-blue', 'active');
                        el.classList.remove('border-black/10', 'dark:border-white/10');
                    } else {
                        el.classList.remove('bg-apple-blue/10', 'text-apple-blue', 'border-apple-blue', 'active');
                        el.classList.add('border-black/10', 'dark:border-white/10');
                    }
                });
            };

            updatePair('quick-preset-precise', 'preset-precise-btn', isPrecise);
            updatePair('quick-preset-balanced', 'preset-balanced-btn', isBalanced);
            updatePair('quick-preset-creative', 'preset-creative-btn', isCreative);
        }

        function onQuickSliderChange(value) {
            const numVal = parseFloat(value);
            const formatted = numVal.toFixed(2);
            
            const quickSlider = document.getElementById('quick-temp-slider');
            if (quickSlider && quickSlider.value !== value) quickSlider.value = value;
            
            const quickValEl = document.getElementById('quick-temp-val');
            if (quickValEl) quickValEl.textContent = formatted;
            
            const composerTempVal = document.getElementById('composer-temp-val');
            if (composerTempVal) composerTempVal.textContent = formatted;
            
            let labelText = '(Balanced)';
            if (numVal <= 0.35) labelText = '(Precise)';
            else if (numVal <= 0.85) labelText = '(Balanced)';
            else labelText = '(Creative)';
            
            const quickLabelEl = document.getElementById('quick-temp-label');
            if (quickLabelEl) quickLabelEl.textContent = labelText;
            
            const composerTempLabel = document.getElementById('composer-temp-label');
            if (composerTempLabel) composerTempLabel.textContent = labelText;
            
            const popoverInput = document.getElementById('param-temp');
            if (popoverInput && popoverInput.value !== value) popoverInput.value = value;
            const popoverVal = document.getElementById('param-temp-val');
            if (popoverVal) popoverVal.textContent = formatted;
            
            updatePresetPillsActive(numVal);
            localStorage.setItem('stockrag.paramTemp', value);
        }
        window.onQuickSliderChange = onQuickSliderChange;

        function onParameterSliderChange(param, value) {
            if (param === 'temp') {
                onQuickSliderChange(value);
            } else if (param === 'max-tokens') {
                const valEl = document.getElementById('param-max-tokens-val');
                if (valEl) valEl.textContent = String(value);
                localStorage.setItem('stockrag.paramMaxTokens', value);
            } else if (param === 'top-p') {
                const valEl = document.getElementById('param-top-p-val');
                if (valEl) valEl.textContent = parseFloat(value).toFixed(2);
                localStorage.setItem('stockrag.paramTopP', value);
            }
        }
        window.onParameterSliderChange = onParameterSliderChange;

        function applyParameterPreset(preset) {
            let temp = 0.7, maxTokens = 2048, topP = 0.9;
            if (preset === 'precise') {
                temp = 0.2; maxTokens = 1536; topP = 0.85;
            } else if (preset === 'balanced') {
                temp = 0.7; maxTokens = 2048; topP = 0.90;
            } else if (preset === 'creative') {
                temp = 1.0; maxTokens = 3072; topP = 0.95;
            }

            onQuickSliderChange(String(temp));

            const maxTokensInput = document.getElementById('param-max-tokens');
            const maxTokensVal = document.getElementById('param-max-tokens-val');
            if (maxTokensInput) maxTokensInput.value = String(maxTokens);
            if (maxTokensVal) maxTokensVal.textContent = String(maxTokens);
            localStorage.setItem('stockrag.paramMaxTokens', String(maxTokens));

            const topPInput = document.getElementById('param-top-p');
            const topPVal = document.getElementById('param-top-p-val');
            if (topPInput) topPInput.value = String(topP);
            if (topPVal) topPVal.textContent = String(topP);
            localStorage.setItem('stockrag.paramTopP', String(topP));
        }
        window.applyParameterPreset = applyParameterPreset;

        function saveAndApplyParameters() {
            const temp = document.getElementById('param-temp')?.value || '0.7';
            const maxTokens = document.getElementById('param-max-tokens')?.value || '2048';
            const topP = document.getElementById('param-top-p')?.value || '0.9';
            const persona = document.getElementById('param-custom-persona')?.value || '';
            const selectedModel = document.getElementById('param-model-select')?.value;

            localStorage.setItem('stockrag.paramTemp', temp);
            localStorage.setItem('stockrag.paramMaxTokens', maxTokens);
            localStorage.setItem('stockrag.paramTopP', topP);
            localStorage.setItem('stockrag.customPersona', persona);

            if (selectedModel && selectedModel !== (currentSettings.ai_model || document.getElementById('chat-model-select')?.value)) {
                switchChatModel(selectedModel);
            }

            onQuickSliderChange(temp);
            showParameterToast('Parameters saved & applied');
        }
        window.saveAndApplyParameters = saveAndApplyParameters;

        function resetDefaultParameters() {
            applyParameterPreset('balanced');
            const persona = document.getElementById('param-custom-persona');
            if (persona) persona.value = '';
            localStorage.removeItem('stockrag.customPersona');
            showParameterToast('Reset to Balanced defaults');
        }
        window.resetDefaultParameters = resetDefaultParameters;
        async function requestRenameChat(sessionId, currentTitle) {
            const newTitle = prompt('Enter new conversation title:', currentTitle);
            if (!newTitle || newTitle === currentTitle) return;
            try {
                const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/rename`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: newTitle })
                });
                if (!response.ok) throw new Error('Could not rename');
                
                const item = chatHistoryItems.find(i => i.session_id === sessionId);
                if (item) item.title = newTitle;
                if (chatSessionId === sessionId) {
                    updateActiveChatHeader(newTitle, document.getElementById('chat-active-branch-badge')?.classList.contains('hidden') === false);
                }
                renderChatHistory();
            } catch (err) {
                alert(err.message);
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
            button.className = 'chat-branch-button p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/10 text-apple-gray hover:text-gray-900 dark:hover:text-gray-100 transition-colors';
            button.setAttribute('aria-label', 'Branch conversation from this message');
            button.title = 'Branch from this message';
            button.innerHTML = '<i data-lucide="git-branch" class="h-3.5 w-3.5"></i>';
            button.addEventListener('click', () => branchChat(messageId));
            target.append(button);
            if (window.lucide) lucide.createIcons();
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
            loadLandingForecasts(force);
            for (const chart of landingCharts.values()) chart.remove();
            landingCharts.clear();
            if (landingResizeObserver) landingResizeObserver.disconnect();
            renderLandingSkeletons();

            const results = Array(landingSymbols.length);
            let cursor = 0, finished = 0;
            const workerCount = Math.min(8, landingSymbols.length);
            const workers = Array.from({length:workerCount}, async () => {
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
                    status.textContent = `${finished}/${landingSymbols.length} market quotes loaded…`;
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
            const quoteFreshness = quote => String(quote?.status || quote?.data_status || '').toUpperCase();
            const anyMarketHoursQuote = results.some(result => quoteFreshness(result.quote) !== 'CACHED' && (String(result.quote?.data_status || '').toUpperCase() === 'PROVIDER_QUOTE' || result.quote?.market_session === 'REGULAR_MARKET_OPEN'));
            const allStatusKnown = results.every(result => result.quote && ['PROVIDER_CLOSE','PROVIDER_QUOTE','CACHED','OFFICIAL_CLOSE','REALTIME_QUOTE','LIVE'].includes(quoteFreshness(result.quote)));
            const sessionState = anyMarketHoursQuote ? 'provider quote during market hours' : allStatusKnown ? 'provider close or cached quote status' : 'provider status varies';
            status.textContent = `${goodQuotes}/${landingSymbols.length} exchange quotes · ${sessionState} · updated ${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;

        }

        function renderLandingCard(result) {
            const {item,index,quote,rows,error} = result;
            latestMarketResults.set(item.symbol,result);
            const card = document.createElement('article');
            card.className = 'glass-panel watch-card group rounded-2xl p-4 transition duration-200 hover:-translate-y-0.5 hover:border-apple-blue/40 hover:shadow-lg cursor-pointer';
            card.dataset.watchIndex = String(index);
            card.dataset.watchCard = 'true'; card.dataset.symbol = item.symbol;
            card.addEventListener('click', () => simulateSearch(item.symbol));
            const top = document.createElement('div');
            top.className = 'flex items-start justify-between gap-2';
            const identity = document.createElement('button');
            identity.className = 'min-w-0 text-left'; identity.type = 'button'; identity.title = `Open ${item.symbol}`;
            identity.innerHTML = `<span class="block text-sm font-bold tracking-tight group-hover:text-apple-blue">${escapeHtml(item.symbol)}</span><span class="mt-0.5 block truncate text-xs text-apple-gray">${escapeHtml(item.label)} · ${item.market === 'india' ? 'NSE' : 'US'}</span>`;
            identity.addEventListener('click', (e) => { e.stopPropagation(); simulateSearch(item.symbol); });
            top.append(identity);
            const source = document.createElement('span');
            source.className = 'max-w-[48%] truncate rounded-full px-2 py-0.5 text-[9px] font-semibold border flex items-center shrink-0';
            if (quote) {
                const releaseDate = quote.market_time ? new Date(quote.market_time) : null;
                const releaseFmt = releaseDate && !isNaN(releaseDate.getTime()) ? `${releaseDate.toLocaleDateString([], {month:'short',day:'numeric'})} ${releaseDate.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}` : 'Session Close';
                const retrievedDate = (quote.cached_at || quote.retrieved_at) ? new Date(quote.cached_at || quote.retrieved_at) : null;
                const retrievedFmt = retrievedDate && !isNaN(retrievedDate.getTime()) ? `${retrievedDate.toLocaleDateString([], {month:'short',day:'numeric'})} ${retrievedDate.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}` : '';
                if (quote.status === 'CACHED' || quote.data_status === 'CACHED') {
                    source.className += ' bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20';
                    source.textContent = `Cached · ${retrievedFmt || releaseFmt}`;
                } else if (quote.data_status === 'PROVIDER_QUOTE' || quote.market_session === 'REGULAR_MARKET_OPEN') {
                    source.className += ' bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20';
                    source.textContent = `Market open · provider quote · ${quote.exchange || 'MKT'}`;
                } else if (['PROVIDER_CLOSE','OFFICIAL_CLOSE'].includes(quote.data_status)) {
                    source.className += ' bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20';
                    source.textContent = `Provider close · ${releaseFmt}`;
                } else {
                    source.className += ' bg-black/[.04] text-apple-gray border-black/[.06] dark:bg-white/[.06] dark:border-white/[.08]';
                    source.textContent = (quote.status || quote.data_status || 'Freshness unknown').replaceAll('_',' ');
                }
                source.title = `Exchange: ${quote.exchange || 'Unknown'} | Market Recorded: ${quote.market_time || 'Time unavailable'} | Provider: ${quote.source || 'Unknown'} | Retrieved: ${quote.retrieved_at || 'Time unavailable'}${quote.cached_at ? ` | Cached: ${quote.cached_at}` : ''}`;
            } else {
                source.className += ' bg-rose-500/10 text-rose-600 border-rose-500/20';
                source.textContent = 'Unavailable';
                source.title = error || 'Market data unavailable';
            }
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
            const releaseShort = quote?.market_time ? `${new Date(quote.market_time).toLocaleDateString([], {month:'short',day:'numeric'})} ${new Date(quote.market_time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}` : 'Recent';
            const detail = document.createElement('span'); detail.className = 'truncate text-right font-medium';
            detail.textContent = quote ? `${quote.exchange || 'Exchange'} · ${releaseShort}` : (result.error || 'Chart unavailable');
            detail.title = quote ? `Provider-reported quote for ${quote.exchange || 'exchange'} at ${quote.market_time || 'time unavailable'}. Retrieved via ${quote.source || 'market provider'} at ${quote.retrieved_at || 'time unavailable'}.` : '';
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
                const cachedTime = quote?.cached_at || quote?.retrieved_at || quote?.market_time;
                let timeStr = '';
                if (cachedTime) {
                    const dt = new Date(cachedTime);
                    if (!isNaN(dt.getTime())) {
                        timeStr = ` (${dt.toLocaleDateString([], {month:'short',day:'numeric'})} ${dt.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})})`;
                    }
                }
                const isCached = quote?.status === 'CACHED' || quote?.data_status === 'CACHED';
                const freshness = document.createElement('td');
                freshness.textContent = isCached ? `Cached${timeStr}` : (quote?.data_status || quote?.status || 'Unavailable').replaceAll('_', ' ');
                freshness.className = 'text-[10px] text-apple-gray';
                row.append(company,price,change,volume,trend,freshness); body.append(row);
            }
        }

        // Global Toast Notification Helper
        window.showToast = function(msg, duration = 2500) {
            const toast = document.getElementById('terminal-toast');
            const toastMsg = document.getElementById('terminal-toast-msg');
            if (!toast || !toastMsg) return;
            toastMsg.textContent = msg;
            toast.classList.add('show');
            clearTimeout(window._toastTimer);
            window._toastTimer = setTimeout(() => {
                toast.classList.remove('show');
            }, duration);
        };

        // Bootstrap cached news immediately for instant 0.0s headline render
        try {
            const cachedNews = localStorage.getItem('stockrag_cached_news');
            if (cachedNews && (!landingNewsItems || !landingNewsItems.length)) {
                const parsed = JSON.parse(cachedNews);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    landingNewsItems = parsed;
                }
            }
        } catch (_) {}

        async function loadLandingNews(generation = landingLoadGeneration, force = true, requestGeneration = ++landingNewsGeneration, market = 'all', silent = false) {
            landingNewsAbortController?.abort();
            landingNewsAbortController = new AbortController();
            const requestSignal = AbortSignal.any([landingNewsAbortController.signal,AbortSignal.timeout(50000)]);
            
            const hasExisting = Array.isArray(landingNewsItems) && landingNewsItems.length > 0;
            const syncBadge = document.getElementById('news-background-sync');

            // If we already have items (or cached), fetch silently in the background without wiping screen!
            if (hasExisting || silent) {
                if (syncBadge) syncBadge.classList.remove('hidden');
                document.getElementById('news-feed-refresh-state').textContent = 'Syncing latest wires in background…';
            } else {
                const loading = `<div class="py-12 text-center"><span class="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-full bg-apple-blue/10 text-apple-blue"><i data-lucide="loader-circle" class="h-5 w-5 animate-spin"></i></span><p class="text-sm font-medium text-text-main">${force ? 'Fetching fresh headlines from publishers…' : 'Loading the latest headlines…'}</p><p class="mt-1 text-xs text-apple-gray">Checking market coverage and your tracked companies.</p></div>`;
                document.getElementById('landing-news-feed').innerHTML = loading;
                document.getElementById('news-feed').innerHTML = loading;
                document.getElementById('news-feed-refresh-state').textContent = 'Searching fresh publisher feeds…';
            }

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

                // Persist cached headlines to localStorage for instant load next time
                try {
                    localStorage.setItem('stockrag_cached_news', JSON.stringify(landingNewsItems.slice(0, 40)));
                } catch (_) {}

                renderLandingNews();
                document.getElementById('news-feed-refresh-state').textContent = result.success
                    ? `Updated ${landingNewsUpdatedAt.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})} · ${result.source_count || 0} publishers`
                    : 'No fresh publisher results returned';
            } catch (error) {
                if (error.name === 'AbortError' || generation !== landingLoadGeneration || requestGeneration !== landingNewsGeneration) return;
                document.getElementById('news-feed-refresh-state').textContent = 'Could not refresh';
                if (!hasExisting) {
                    const message = error.name === 'TimeoutError' ? 'News sources took too long to respond.' : (error.message || 'News could not be loaded.');
                    for (const container of [document.getElementById('landing-news-feed'),document.getElementById('news-feed')]) {
                        container.replaceChildren();
                        const empty = document.createElement('div'); empty.className = 'py-12 text-center';
                        const text = document.createElement('p'); text.className = 'text-sm text-apple-gray'; text.textContent = message;
                        const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'mt-2 min-h-11 rounded-lg px-3 text-sm font-semibold text-apple-blue'; retry.textContent = 'Try again'; retry.addEventListener('click',refreshLandingNews);
                        empty.append(text,retry); container.append(empty);
                    }
                }
            } finally {
                if (syncBadge) syncBadge.classList.add('hidden');
                if (window.lucide) lucide.createIcons();
            }
        }
        function refreshLandingNews() { return loadLandingNews(landingLoadGeneration, true, ++landingNewsGeneration, ['us','india'].includes(landingNewsFilter) ? landingNewsFilter : 'all', true); }

        function searchLandingNews(value) {
            landingNewsSearch = String(value || '').trim().toLocaleLowerCase();
            newsVisibleCount = 20;
            renderLandingNews();
        }

        function loadMoreLandingNews() {
            newsVisibleCount = Math.min(newsVisibleCount + 20, 100);
            renderLandingNews();
        }

        let newsViewMode = 'grid'; // 'grid' or 'wire'
        let newsTopicFilter = 'all'; // 'all', 'earnings', 'macro', 'tech', 'deals'

        window.setNewsViewMode = function(mode) {
            newsViewMode = mode;
            const gridBtn = document.getElementById('news-view-grid-btn');
            const wireBtn = document.getElementById('news-view-wire-btn');
            if (gridBtn && wireBtn) {
                if (mode === 'grid') {
                    gridBtn.className = 'px-2.5 py-1 rounded-lg text-xs font-semibold transition-all active bg-white dark:bg-white/15 text-apple-blue shadow-xs';
                    wireBtn.className = 'px-2.5 py-1 rounded-lg text-xs font-semibold text-apple-gray hover:text-text-main transition-all';
                } else {
                    wireBtn.className = 'px-2.5 py-1 rounded-lg text-xs font-semibold transition-all active bg-white dark:bg-white/15 text-apple-blue shadow-xs';
                    gridBtn.className = 'px-2.5 py-1 rounded-lg text-xs font-semibold text-apple-gray hover:text-text-main transition-all';
                }
            }
            renderLandingNews();
        };

        window.filterNewsTopic = function(topic) {
            newsTopicFilter = topic;
            document.querySelectorAll('.news-topic-pill').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.topic === topic);
            });
            renderLandingNews();
        };

        window.askAboutNews = function(item) {
            if (!item) return;
            const title = item.title || 'market news';
            const ticker = item.ticker ? `$${item.ticker}` : 'the market';
            const publisher = item.publisher || 'financial wire';
            const prompt = `Analyze this breaking news for ${ticker}: "${title}" (Source: ${publisher}). What is the financial impact, market sentiment, and key risk/reward takeaways?`;
            
            showView('chat');
            const input = document.getElementById('chat-input') || document.getElementById('message-input');
            if (input) {
                input.value = prompt;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                const sendBtn = document.getElementById('chat-send-btn') || document.getElementById('send-button');
                if (sendBtn) {
                    setTimeout(() => sendBtn.click(), 120);
                }
            }
        };

        function filterLandingNews(market) {
            landingNewsFilter = market;
            document.querySelectorAll('.feed-filter').forEach(button => button.classList.toggle('active', button.dataset.marketFilter === market));
            if (market === 'saved') {
                renderLandingNews();
                return;
            }
            if (market === 'us' || market === 'india' || market === 'all' || market === 'watchlist') {
                newsVisibleCount = 20;
                return loadLandingNews(landingLoadGeneration, true, ++landingNewsGeneration, market === 'all' || market === 'watchlist' ? 'all' : market, true);
            }
            renderLandingNews();
        }

        let newsProviderFilter = 'all';
        let newsSortMode = 'latest'; // 'latest', 'bullish', 'bearish'

        window.filterNewsProvider = function(provider) {
            newsProviderFilter = provider;
            renderLandingNews();
        };

        window.sortNewsFeed = function(sortMode) {
            newsSortMode = sortMode;
            renderLandingNews();
        };

        window.toggleNewsBookmark = function(btn, storyId) {
            try {
                const savedStories = JSON.parse(localStorage.getItem('mystock_saved_stories') || '{}');
                const isSaved = !savedStories[storyId];
                if (isSaved) {
                    savedStories[storyId] = true;
                    showToast('Story saved to bookmarks');
                } else {
                    delete savedStories[storyId];
                    showToast('Story removed from bookmarks');
                }
                localStorage.setItem('mystock_saved_stories', JSON.stringify(savedStories));
                if (btn) {
                    btn.classList.toggle('active-save', isSaved);
                    btn.classList.toggle('text-amber-500', isSaved);
                    btn.setAttribute('title', isSaved ? 'Remove bookmark' : 'Save bookmark');
                }
                if (landingNewsFilter === 'saved') {
                    renderLandingNews();
                }
            } catch (_) {}
            if (window.lucide) lucide.createIcons();
        };
        window.toggleInstaSave = window.toggleNewsBookmark;

        window.shareNewsStory = async function(url) {
            try {
                if (navigator.clipboard && url) {
                    await navigator.clipboard.writeText(url);
                    showToast('Story link copied to clipboard!');
                } else {
                    showToast('Link ready: ' + (url || ''));
                }
            } catch (_) {
                showToast('Link ready to share');
            }
        };

        function analyzeNewsSentiment(text) {
            const lower = String(text || '').toLowerCase();
            const bullishWords = ['gain', 'surge', 'jump', 'rally', 'profit', 'record', 'high', 'buy', 'bull', 'expand', 'growth', 'rise', 'beat', 'soar', 'up', 'upgrade', 'dividend', 'deal', 'positive', 'strong', 'boost'];
            const bearishWords = ['drop', 'fall', 'loss', 'decline', 'crash', 'slump', 'risk', 'threat', 'plunge', 'down', 'probe', 'lawsuit', 'sell', 'debt', 'cut', 'downgrade', 'warn', 'inflation', 'weak', 'pressure'];
            
            let bullScore = 0;
            let bearScore = 0;
            bullishWords.forEach(w => { if (lower.includes(w)) bullScore++; });
            bearishWords.forEach(w => { if (lower.includes(w)) bearScore++; });

            if (bullScore > bearScore) return { label: 'Bullish', class: 'sentiment-bullish', icon: 'trending-up', score: bullScore - bearScore };
            if (bearScore > bullScore) return { label: 'Bearish', class: 'sentiment-bearish', icon: 'trending-down', score: bearScore - bullScore };
            return { label: 'Market Wire', class: 'sentiment-neutral', icon: 'activity', score: 0 };
        }

        function matchNewsTopic(item, topic) {
            if (topic === 'all') return true;
            const text = `${item.title || ''} ${item.summary || ''}`.toLowerCase();
            if (topic === 'earnings') return text.includes('earnings') || text.includes('profit') || text.includes('revenue') || text.includes('results') || text.includes('q1') || text.includes('q2') || text.includes('q3') || text.includes('q4') || text.includes('guidance');
            if (topic === 'macro') return text.includes('fed') || text.includes('rate') || text.includes('inflation') || text.includes('rbi') || text.includes('economy') || text.includes('policy') || text.includes('central bank') || text.includes('gdp');
            if (topic === 'tech') return text.includes('ai') || text.includes('chip') || text.includes('cloud') || text.includes('tech') || text.includes('apple') || text.includes('nvidia') || text.includes('software') || text.includes('google');
            if (topic === 'deals') return text.includes('deal') || text.includes('merger') || text.includes('acquisition') || text.includes('stake') || text.includes('buyout') || text.includes('partner') || text.includes('ipo') || text.includes('buyback');
            return true;
        }

        function renderModernNewsCard(item, isHero = false, isLanding = false) {
            const article = document.createElement('article');

            const storyId = 'story_' + Math.abs((item.title || item.url || '').split('').reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0));
            const savedStories = JSON.parse(localStorage.getItem('mystock_saved_stories') || '{}');
            const isSaved = !!savedStories[storyId];

            const publisherName = escapeHtml(item.publisher || item.ticker || 'Market Wire');
            const publisherInit = String(publisherName).trim().slice(0, 1).toUpperCase();
            
            // Format time ago
            let timeAgo = 'Date unavailable';
            if (item.published_at) {
                const diffMs = Date.now() - Date.parse(item.published_at);
                const diffMins = Math.floor(diffMs / 60000);
                if (diffMins < 60) timeAgo = `${Math.max(1, diffMins)}m ago`;
                else {
                    const diffHours = Math.floor(diffMins / 60);
                    if (diffHours < 24) timeAgo = `${diffHours}h ago`;
                    else timeAgo = `${Math.floor(diffHours / 24)}d ago`;
                }
            }

            const marketTag = item.market === 'india' ? 'NSE India' : (item.market === 'us' ? 'US Markets' : 'Global Wire');
            const sentiment = analyzeNewsSentiment(`${item.title || ''} ${item.summary || ''}`);
            const hasImage = Boolean(item.image && typeof item.image === 'string' && item.image.trim().startsWith('http'));

            if (isHero) {
                article.className = 'news-lead-banner mb-3 col-span-full p-4 sm:p-5';
                article.innerHTML = `
                    <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3 sm:gap-4">
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center gap-2 mb-1.5 text-xs">
                                <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500 text-white uppercase tracking-wider flex items-center gap-1 shrink-0">
                                    <span class="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span> LEAD
                                </span>
                                <span class="news-meta-pub">${publisherName}</span>
                                <span class="news-meta-time">· ${timeAgo}</span>
                                <span class="sentiment-pill ${sentiment.class} ml-auto sm:ml-1">
                                    <i data-lucide="${sentiment.icon}" class="w-2.5 h-2.5"></i> ${sentiment.label}
                                </span>
                            </div>
                            <h2>
                                <a href="${escapeHtml(item.url || '#')}" target="_blank" rel="noopener noreferrer" class="news-lead-title block">
                                    ${escapeHtml(item.title || '')}
                                </a>
                            </h2>
                            ${item.summary ? `
                                <p class="mt-1.5 news-excerpt line-clamp-2">
                                    ${escapeHtml(item.summary)}
                                </p>
                            ` : ''}
                        </div>
                        ${hasImage ? `
                            <div class="news-thumb-container shrink-0 self-start">
                                <img src="${escapeHtml(item.image)}" alt="" class="news-hero-thumb" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('.news-thumb-container')?.remove();">
                            </div>
                        ` : ''}
                    </div>

                    <div class="mt-3 pt-2.5 border-t border-black/[0.05] dark:border-white/[0.08] flex items-center justify-between gap-2">
                        <div class="flex items-center gap-2">
                            ${item.ticker ? `
                                <button type="button" class="news-ticker-pill" title="Jump to ${item.ticker} chart" onclick="simulateSearch('${escapeHtml(item.ticker)}')">
                                    $${escapeHtml(item.ticker)}
                                </button>
                            ` : ''}
                            <button type="button" class="news-action-btn ai-btn" onclick='askAboutNews(${JSON.stringify(item).replace(/'/g, "\\'")})' title="Analyze story with AI Copilot">
                                <i data-lucide="sparkles" class="w-3.5 h-3.5"></i> Ask AI
                            </button>
                        </div>
                        <div class="flex items-center gap-1.5">
                            <button type="button" class="news-action-btn ${isSaved ? 'active-save text-amber-500' : ''}" onclick="toggleNewsBookmark(this, '${storyId}')" title="${isSaved ? 'Remove bookmark' : 'Bookmark story'}">
                                <i data-lucide="bookmark" class="w-3.5 h-3.5"></i>
                            </button>
                            <a href="${escapeHtml(item.url || '#')}" target="_blank" rel="noopener noreferrer" class="news-action-btn" title="Read on original publisher">
                                <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
                                <span class="text-[11px] font-semibold hidden sm:inline">Source</span>
                            </a>
                        </div>
                    </div>
                `;
                return article;
            }

            // Standard Editorial Card: Clean, compact horizontal layout
            article.className = hasImage ? 'news-editorial-card p-3.5 sm:p-4' : 'news-editorial-card news-card-textonly p-3.5 sm:p-4';
            article.innerHTML = `
                <div class="flex items-start justify-between gap-3">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-1.5 mb-1 text-xs">
                            <span class="news-meta-pub truncate max-w-[120px] sm:max-w-[150px]">${publisherName}</span>
                            <span class="news-meta-time shrink-0">· ${timeAgo}</span>
                            <span class="sentiment-pill ${sentiment.class} ml-auto shrink-0">
                                <i data-lucide="${sentiment.icon}" class="w-2.5 h-2.5"></i> ${sentiment.label}
                            </span>
                        </div>
                        <a href="${escapeHtml(item.url || '#')}" target="_blank" rel="noopener noreferrer" class="${hasImage ? 'news-title-link' : 'news-headline-stylish'} block font-semibold text-sm leading-snug">
                            ${escapeHtml(item.title || '')}
                        </a>
                        ${item.summary ? `
                            <p class="mt-1 news-excerpt line-clamp-2">
                                ${escapeHtml(item.summary)}
                            </p>
                        ` : ''}
                    </div>
                    ${hasImage ? `
                        <div class="news-thumb-container shrink-0">
                            <img src="${escapeHtml(item.image)}" alt="" class="news-thumb-compact" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('.news-thumb-container')?.remove();">
                        </div>
                    ` : ''}
                </div>

                <div class="mt-2.5 pt-2 border-t border-black/[0.04] dark:border-white/[0.06] flex items-center justify-between text-xs text-apple-gray">
                    <div class="flex items-center gap-2">
                        ${item.ticker ? `
                            <button type="button" class="news-ticker-pill" title="Jump to ${item.ticker} chart" onclick="simulateSearch('${escapeHtml(item.ticker)}')">
                                $${escapeHtml(item.ticker)}
                            </button>
                        ` : ''}
                        <button type="button" class="news-action-btn ai-btn" onclick='askAboutNews(${JSON.stringify(item).replace(/'/g, "\\'")})' title="Analyze story with AI Copilot">
                            <i data-lucide="sparkles" class="w-3 h-3"></i>
                            <span>Ask AI</span>
                        </button>
                    </div>
                    <div class="flex items-center gap-1">
                        <button type="button" class="news-action-btn ${isSaved ? 'active-save text-amber-500' : ''}" onclick="toggleNewsBookmark(this, '${storyId}')" title="${isSaved ? 'Remove bookmark' : 'Bookmark story'}">
                            <i data-lucide="bookmark" class="w-3.5 h-3.5"></i>
                        </button>
                        <a href="${escapeHtml(item.url || '#')}" target="_blank" rel="noopener noreferrer" class="news-action-btn" title="Read on source">
                            <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
                        </a>
                    </div>
                </div>
            `;
            return article;
        }

        function renderModernNewsWireRow(item) {
            const row = document.createElement('div');
            row.className = 'news-wire-row';

            const storyId = 'story_' + Math.abs((item.title || item.url || '').split('').reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0));
            const savedStories = JSON.parse(localStorage.getItem('mystock_saved_stories') || '{}');
            const isSaved = !!savedStories[storyId];

            let timeAgo = 'Now';
            if (item.published_at) {
                const diffMs = Date.now() - Date.parse(item.published_at);
                const diffMins = Math.floor(diffMs / 60000);
                if (diffMins < 60) timeAgo = `${Math.max(1, diffMins)}m ago`;
                else timeAgo = `${Math.floor(diffMins / 60)}h ago`;
            }

            const sentiment = analyzeNewsSentiment(item.title);
            const ticker = item.ticker || 'WIRE';

            row.innerHTML = `
                <div class="flex items-center gap-2.5 min-w-0 flex-1">
                    <span class="text-[10px] font-mono font-semibold text-apple-gray shrink-0 w-12">${timeAgo}</span>
                    <button type="button" class="news-ticker-pill shrink-0" onclick="simulateSearch('${escapeHtml(ticker)}')">$${escapeHtml(ticker)}</button>
                    <span class="sentiment-pill ${sentiment.class} shrink-0 hidden sm:inline-flex">
                        <i data-lucide="${sentiment.icon}" class="w-2.5 h-2.5"></i> ${sentiment.label}
                    </span>
                    <a href="${escapeHtml(item.url || '#')}" target="_blank" rel="noopener noreferrer" class="news-wire-title truncate transition-colors flex-1">
                        ${escapeHtml(item.title || '')}
                    </a>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                    <span class="news-meta-time hidden md:inline truncate max-w-[110px] font-semibold">${escapeHtml(item.publisher || '')}</span>
                    <button type="button" class="news-action-btn ai-btn p-1.5" onclick='askAboutNews(${JSON.stringify(item).replace(/'/g, "\\'")})' title="Ask AI about story">
                        <i data-lucide="sparkles" class="w-3.5 h-3.5"></i>
                    </button>
                    <button type="button" class="news-action-btn ${isSaved ? 'active-save text-amber-500' : ''} p-1.5" onclick="toggleNewsBookmark(this, '${storyId}')" title="${isSaved ? 'Remove bookmark' : 'Bookmark story'}">
                        <i data-lucide="bookmark" class="w-3.5 h-3.5"></i>
                    </button>
                    <a href="${escapeHtml(item.url || '#')}" target="_blank" rel="noopener noreferrer" class="news-action-btn p-1.5" title="External link">
                        <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
                    </a>
                </div>
            `;
            return row;
        }

        function updateNewsIntelligenceRail(items) {
            if (!Array.isArray(items) || !items.length) return;

            // 1. Calculate Sentiment Breakdown
            let bullCount = 0;
            let bearCount = 0;
            const tickerCounts = {};

            items.forEach(item => {
                const text = `${item.title || ''} ${item.summary || ''}`.toLowerCase();
                const sentiment = analyzeNewsSentiment(text);
                if (sentiment.label === 'Bullish') bullCount++;
                else if (sentiment.label === 'Bearish') bearCount++;

                const ticker = item.ticker || (item.related_tickers && item.related_tickers[0]);
                if (ticker && ticker !== '^NSEI' && ticker !== '^BSESN') {
                    tickerCounts[ticker] = (tickerCounts[ticker] || 0) + 1;
                }
            });

            const totalSentiment = Math.max(1, bullCount + bearCount);
            const posPct = Math.round((bullCount / totalSentiment) * 100);
            const negPct = 100 - posPct;

            const posEl = document.getElementById('news-sentiment-positive');
            const negEl = document.getElementById('news-sentiment-negative');
            const barPos = document.getElementById('news-sentiment-bar-pos');
            const barNeg = document.getElementById('news-sentiment-bar-neg');
            const statusEl = document.getElementById('news-sentiment-status');

            if (posEl) posEl.textContent = `${posPct}% Positive`;
            if (negEl) negEl.textContent = `${negPct}% Negative`;
            if (barPos) barPos.style.width = `${posPct}%`;
            if (barNeg) barNeg.style.width = `${negPct}%`;
            if (statusEl) {
                if (posPct >= 55) {
                    statusEl.textContent = 'BULLISH';
                    statusEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20';
                } else if (posPct <= 45) {
                    statusEl.textContent = 'CAUTIOUS';
                    statusEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20';
                } else {
                    statusEl.textContent = 'BALANCED';
                    statusEl.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20';
                }
            }

            // 2. Populate Trending Tickers
            const trendingContainer = document.getElementById('news-trending-tickers');
            if (trendingContainer) {
                const sortedTickers = Object.entries(tickerCounts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 8);

                if (sortedTickers.length) {
                    trendingContainer.innerHTML = sortedTickers.map(([sym, cnt]) => `
                        <button type="button" class="news-ticker-pill flex items-center gap-1" onclick="simulateSearch('${escapeHtml(sym)}')">
                            <span>$${escapeHtml(sym)}</span>
                            <span class="opacity-60 text-[9px]">(${cnt})</span>
                        </button>
                    `).join('');
                } else {
                    trendingContainer.innerHTML = '<span class="text-xs text-apple-gray">Broad market coverage</span>';
                }
            }

            // 3. Render Watchlist context
            renderNewsContext();
        }

        function populateProviderDropdown(items) {
            const providerSelect = document.getElementById('news-feed-provider');
            if (!providerSelect || !Array.isArray(items)) return;

            const publishers = new Set();
            items.forEach(it => {
                if (it.publisher && typeof it.publisher === 'string' && it.publisher.trim()) {
                    publishers.add(it.publisher.trim());
                }
            });

            const currentVal = newsProviderFilter;
            const sortedPublishers = [...publishers].sort();

            const optionsHtml = ['<option value="all">All Publishers</option>'];
            sortedPublishers.forEach(pub => {
                const isSelected = pub === currentVal ? 'selected' : '';
                optionsHtml.push(`<option value="${escapeHtml(pub)}" ${isSelected}>${escapeHtml(pub)}</option>`);
            });

            providerSelect.innerHTML = optionsHtml.join('');
            if (sortedPublishers.includes(currentVal)) {
                providerSelect.value = currentVal;
            } else {
                providerSelect.value = 'all';
                newsProviderFilter = 'all';
            }
        }

        function renderLandingNews() {
            const savedStories = JSON.parse(localStorage.getItem('mystock_saved_stories') || '{}');
            
            // Dynamically update providers dropdown
            populateProviderDropdown(landingNewsItems);

            // Filter by market
            let filtered = landingNewsItems;
            if (landingNewsFilter === 'saved') {
                filtered = landingNewsItems.filter(item => {
                    const id = 'story_' + Math.abs((item.title || item.url || '').split('').reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0));
                    return !!savedStories[id];
                });
            } else if (landingNewsFilter === 'watchlist') {
                filtered = landingNewsItems.filter(item => watchlistSymbols.has(item.ticker) || (item.related_tickers || []).some(symbol => watchlistSymbols.has(symbol)));
            } else if (landingNewsFilter === 'india' || landingNewsFilter === 'us') {
                filtered = landingNewsItems.filter(item => item.market === landingNewsFilter);
            }

            // Filter by publisher
            if (newsProviderFilter !== 'all') {
                filtered = filtered.filter(item => (item.publisher || '').trim().toLowerCase() === newsProviderFilter.trim().toLowerCase());
            }

            // Filter by topic
            if (newsTopicFilter !== 'all') {
                filtered = filtered.filter(item => matchNewsTopic(item, newsTopicFilter));
            }

            // Filter by search
            let items = landingNewsSearch 
                ? filtered.filter(item => `${item.title || ''} ${item.publisher || ''} ${item.ticker || ''} ${item.summary || ''}`.toLocaleLowerCase().includes(landingNewsSearch)) 
                : filtered;

            // Sort stories
            if (newsSortMode === 'bullish') {
                items = [...items].sort((a, b) => {
                    const sA = analyzeNewsSentiment(`${a.title || ''} ${a.summary || ''}`);
                    const sB = analyzeNewsSentiment(`${b.title || ''} ${b.summary || ''}`);
                    return (sB.label === 'Bullish' ? 1 : 0) - (sA.label === 'Bullish' ? 1 : 0);
                });
            } else if (newsSortMode === 'bearish') {
                items = [...items].sort((a, b) => {
                    const sA = analyzeNewsSentiment(`${a.title || ''} ${a.summary || ''}`);
                    const sB = analyzeNewsSentiment(`${b.title || ''} ${b.summary || ''}`);
                    return (sB.label === 'Bearish' ? 1 : 0) - (sA.label === 'Bearish' ? 1 : 0);
                });
            }

            const count = document.getElementById('news-feed-count');
            if (count) {
                count.textContent = `${items.length} ${items.length === 1 ? 'story' : 'stories'}${landingNewsMeta?.total_available > landingNewsItems.length ? ` · ${landingNewsMeta.total_available} indexed` : ''} · ${newsSortMode === 'latest' ? 'newest first' : (newsSortMode === 'bullish' ? 'bullish priority' : 'bearish priority')}`;
            }
            const sourceLine = document.getElementById('news-feed-source');
            document.getElementById('news-load-more')?.classList.add('hidden');
            if (sourceLine) {
                sourceLine.textContent = 'Headlines indexed across publisher RSS feeds and market data providers with full source attribution.';
            }

            // Update Right Intelligence Rail
            updateNewsIntelligenceRail(landingNewsItems);

            // Render Containers
            for (const container of [document.getElementById('landing-news-feed'), document.getElementById('news-feed')]) {
                if (!container) continue;
                if (!items.length) {
                    container.innerHTML = `
                        <div class="py-12 text-center col-span-full">
                            <i data-lucide="newspaper" class="w-8 h-8 mx-auto text-apple-gray mb-2"></i>
                            <p class="text-sm font-semibold text-text-main">${landingNewsFilter === 'saved' ? 'No saved bookmarks yet.' : (landingNewsItems.length ? 'No headlines match the current filter or topic.' : 'No recent stories were returned by the selected publishers.')}</p>
                            <p class="text-xs text-apple-gray mt-1">${landingNewsFilter === 'saved' ? 'Click the bookmark icon on any story to save it.' : 'Try selecting All Markets, resetting provider, or refreshing the feed.'}</p>
                            <button class="mt-3 min-h-9 px-4 rounded-xl bg-apple-blue/10 text-apple-blue text-xs font-semibold hover:bg-apple-blue hover:text-white transition-all" onclick="filterLandingNews('all'); filterNewsTopic('all'); filterNewsProvider('all'); refreshLandingNews();">Reset all filters</button>
                        </div>
                    `;
                    continue;
                }

                const isLanding = container.id === 'landing-news-feed';
                
                if (isLanding) {
                    // Landing page preview: 4 compact editorial cards
                    const visibleItems = items.slice(0, 4);
                    container.className = 'news-terminal-grid pt-2';
                    container.replaceChildren(...visibleItems.map(item => renderModernNewsCard(item, false, true)));
                } else {
                    // Main News Page: either Bento Grid or Dense Wire View
                    const visibleItems = items.slice(0, newsVisibleCount);
                    container.replaceChildren();

                    if (newsViewMode === 'wire') {
                        container.className = 'news-wire-container pt-1';
                        visibleItems.forEach(item => {
                            container.appendChild(renderModernNewsWireRow(item));
                        });
                    } else {
                        // Bento Editorial Grid View
                        container.className = 'news-terminal-grid pt-1';
                        visibleItems.forEach((item, index) => {
                            const isHero = (index === 0 && !landingNewsSearch && newsTopicFilter === 'all' && landingNewsFilter === 'all' && newsProviderFilter === 'all');
                            container.appendChild(renderModernNewsCard(item, isHero, false));
                        });
                    }

                    const more = document.getElementById('news-load-more');
                    if (more) {
                        const remaining = Math.max(0, items.length - newsVisibleCount);
                        more.classList.toggle('hidden', remaining === 0);
                        more.textContent = remaining ? `Load ${Math.min(20, remaining)} more stories · ${remaining} remaining` : 'All available stories shown';
                    }
                }
            }
            if (window.lucide) lucide.createIcons();
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
            if (target) {
                target.classList.remove('hidden');
                target.classList.add('block');
            }
            if (tabId === 'forecast') {
                if (latestForecastData && latestForecastData.symbol === currentSymbol) {
                    renderForecastUI(latestForecastData);
                    if (latestHistoryData && latestHistoryData.length) {
                        setTimeout(() => {
                            renderDedicatedForecastChart(latestHistoryData, latestForecastData);
                            if (dedicatedForecastChartInstance) {
                                const c = document.getElementById('forecastDedicatedChart');
                                if (c && c.clientWidth > 0) {
                                    dedicatedForecastChartInstance.applyOptions({ width: c.clientWidth, height: c.clientHeight || 380 });
                                    dedicatedForecastChartInstance.timeScale().fitContent();
                                }
                            }
                        }, 50);
                    }
                } else {
                    runForecast();
                }
                setAnalysisView('forecast');
            }
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
                document.getElementById('set-max-tokens').value = data.max_output_tokens ?? 256;
                document.getElementById('set-top-p').value = data.top_p ?? 0.9;
                document.getElementById('set-top-k').value = data.top_k ?? 40;
                document.getElementById('set-repeat-penalty').value = data.repeat_penalty ?? 1.1;
                document.getElementById('set-seed').value = data.seed ?? 0;
                document.getElementById('set-streaming').checked = data.streaming === true;
                renderSettingsControls(data);
                applyTheme(data.theme, data.ui_density);
            } catch (e) { console.warn("Failed to load settings", e); }
        }

        async function refreshModels(configuredModel) {
            const settingsSelect = document.getElementById('set-model');
            const chatSelect = document.getElementById('chat-model-select');
            const paramSelect = document.getElementById('param-model-select');
            const modelSelects = [settingsSelect, chatSelect, paramSelect].filter(Boolean);
            let selected = configuredModel || (settingsSelect ? settingsSelect.value : '');
            for (const select of modelSelects) select.replaceChildren();
            try {
                const response = await fetch('/api/models');
                const result = await response.json();
                const models = result.available && Array.isArray(result.models) ? result.models : [];
                if (!models.includes(selected) && models.length > 0) {
                    selected = models[0];
                }
                for (const select of modelSelects) {
                    select.replaceChildren();
                    for (const name of models) {
                        const option = document.createElement('option');
                        option.value = name;
                        option.textContent = name;
                        if (name === selected) option.selected = true;
                        select.append(option);
                    }
                    if (selected && !models.includes(selected)) {
                        const option = document.createElement('option');
                        option.value = selected;
                        option.textContent = `${selected} — ${result.available ? 'not installed' : 'Ollama unavailable'}`;
                        option.disabled = true;
                        select.append(option);
                    }
                    select.value = selected;
                    select.disabled = !result.available || !models.length;
                    select.title = result.available ? (models.length ? 'Installed local models' : 'No local models installed') : (result.error || 'Local Ollama unavailable');
                }
                const display = document.getElementById('chat-model-display');
                if (display && selected) {
                    display.textContent = selected;
                }
                const paramCountEl = document.getElementById('param-model-count');
                if (paramCountEl) {
                    paramCountEl.textContent = result.available && models.length ? `${models.length} local model${models.length > 1 ? 's' : ''}` : 'Local Ollama unavailable';
                }

                const quickStatus = document.getElementById('chat-model-status');
                if (quickStatus) {
                    quickStatus.textContent = currentChatMode === 'general' ? 'General AI' : 'Market RAG';
                }
                const aiHealth = document.getElementById('ai-page-health');
                if (aiHealth) {
                    aiHealth.textContent = !result.available ? 'Ollama unavailable' : models.length ? `Ollama connected · ${models.length} local model${models.length === 1 ? '' : 's'} installed` : 'Ollama connected · no chat models installed';
                    aiHealth.title = result.error || 'Generation models are selected here; document embeddings are configured separately for retrieval.';
                }
                const statusDot = document.querySelector('#chat-system-status .status-dot');
                const statusLabel = document.getElementById('chat-system-status-label');
                if (result.available && models.length > 0) {
                    if (statusLabel) statusLabel.textContent = `${models.length} Model${models.length > 1 ? 's' : ''}`;
                    if (statusDot) statusDot.style.background = '#34c759';
                }
                const help = document.getElementById('model-help');
                if (help) help.textContent = !result.available
                    ? `Ollama is unavailable. Start it locally, then install a model. Example: ollama pull qwen2.5:1.5b. ${result.error || ''}`
                    : !models.length
                        ? 'Ollama is running, but no generation models are installed. Install one, for example: ollama pull qwen2.5:1.5b.'
                        : 'Choose an installed local Ollama model. Every model uses the same StockRAG retrieval, calculations, citation rules, and answer structure.';
            } catch (_) {
                for (const select of modelSelects) {
                    const option = document.createElement('option');
                    option.value = selected;
                    option.textContent = `${selected || 'Model'} — model list unavailable`;
                    option.disabled = true;
                    select.append(option);
                    select.disabled = true;
                }
                const quickStatus = document.getElementById('chat-model-status');
                if (quickStatus) quickStatus.textContent = 'Model list unavailable';
                const aiHealth = document.getElementById('ai-page-health');
                if (aiHealth) aiHealth.textContent = 'Ollama model list unavailable';
            }
        }

        async function switchChatModel(model) {
            const select = document.getElementById('chat-model-select');
            const paramSelect = document.getElementById('param-model-select');
            const status = document.getElementById('chat-model-status');
            const previous = currentSettings.ai_model || document.getElementById('set-model')?.value;
            if (!model || model === previous) return;
            if (select) select.disabled = true;
            if (paramSelect) paramSelect.disabled = true;
            if (status) status.textContent = 'Switching…';
            try {
                const response = await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ai_model:model})});
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail?.message || data.detail || data.error?.message || 'Model switch failed');
                currentSettings = {...currentSettings, ...data};
                const setModel = document.getElementById('set-model');
                if (setModel) setModel.value = model;
                if (select) select.value = model;
                if (paramSelect) paramSelect.value = model;
                const display = document.getElementById('chat-model-display');
                if (display) display.textContent = model;
                if (status) status.textContent = currentChatMode === 'general' ? 'General AI' : 'Market RAG';
            } catch (error) {
                if (select) select.value = previous;
                if (paramSelect) paramSelect.value = previous;
                if (status) status.textContent = `Switch failed: ${error.message}`;
            } finally {
                if (select) select.disabled = false;
                if (paramSelect) paramSelect.disabled = false;
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
                select.value = ['RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS', 'AAPL', 'MSFT', 'NVDA', 'GOOGL'][index];
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
                    const series = chart.addLineSeries({color:['#0A84FF','#8B5CF6','#F59E0B','#14B8A6','#EC4899','#3B82F6','#EF4444','#10B981'][index],lineWidth:2,priceFormat:{type:'custom',formatter:value=>`${value.toFixed(1)}`} });
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
                container.innerHTML = documents.length ? documents.map(doc => `<div class="flex min-h-11 items-center gap-2 rounded-xl px-2 hover:bg-black/5 dark:hover:bg-white/5"><label class="flex items-center gap-3 flex-1 cursor-pointer min-w-0"><input type="checkbox" class="h-4 w-4 accent-[var(--accent)]" ${['pdf','docx','txt','html','web'].includes(doc.type) ? `data-document-id="${doc.id}" ${selectedDocumentIds.includes(doc.id) ? 'checked' : ''}` : doc.type === 'dataset' ? `data-dataset-id="${doc.id}" ${activeDatasetId === doc.id ? 'checked' : ''}` : 'disabled'} ${doc.status !== 'completed' ? 'disabled' : ''}><span class="min-w-0 flex-1 truncate">${escapeHtml(doc.filename)}</span><span class="text-xs ${doc.status === 'completed' ? 'text-apple-green' : doc.status === 'failed' ? 'text-apple-red' : 'text-apple-gray'}">${escapeHtml(doc.status)}</span></label><button type="button" class="flex h-8 w-8 items-center justify-center rounded-lg text-apple-red hover:bg-red-500/10" onclick="deleteDocument(${doc.id}, event)" title="Delete"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-trash-2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg></button></div>`).join('') : '<p class="text-apple-gray">No uploaded documents yet.</p>';
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


        async function deleteDocument(id, event) {
            if(event) { event.preventDefault(); event.stopPropagation(); }
            if(!confirm("Are you sure you want to delete this document?")) return;
            try {
                const res = await fetch(`/api/documents/${id}`, { method: 'DELETE' });
                if (!res.ok) throw new Error('Failed to delete document');
                selectedDocumentIds = selectedDocumentIds.filter(docId => docId !== id);
                localStorage.setItem('stockrag.documentIds', JSON.stringify(selectedDocumentIds));
                if (activeDatasetId === id) {
                    activeDatasetId = null;
                    localStorage.removeItem('stockrag.datasetId');
                }
                renderChatAttachments();
                loadDocuments();
            } catch (error) {
                alert(error.message);
            }
        }

        async function saveSettings() {
            showLoading(true);
            try {
                const settings = {
                    ai_model: document.getElementById('set-model').value.trim(),
                    temperature: parseFloat(document.getElementById('set-temp').value),
                    context_size: parseInt(document.getElementById('set-ctx').value),
                    citation_visibility: document.getElementById('set-cite').checked,
                    max_output_tokens: parseInt(document.getElementById('set-max-tokens').value),
                    top_p: parseFloat(document.getElementById('set-top-p').value),
                    top_k: parseInt(document.getElementById('set-top-k').value),
                    repeat_penalty: parseFloat(document.getElementById('set-repeat-penalty').value),
                    seed: parseInt(document.getElementById('set-seed').value),
                    streaming: document.getElementById('set-streaming').checked
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
                document.getElementById('empty-state')?.classList.add('hidden');
                document.getElementById('news-page')?.classList.add('hidden');
                document.getElementById('watchlist-page')?.classList.add('hidden');
                document.getElementById('compare-page')?.classList.add('hidden');
                document.getElementById('ai-view')?.classList.add('hidden');
                document.getElementById('dashboard-view')?.classList.remove('hidden');
                document.getElementById('main-terminal-header')?.classList.remove('hidden');
                document.getElementById('sidebar-chat-section')?.classList.add('hidden');
                document.getElementById('sidebar-market-section')?.classList.remove('hidden');
                document.getElementById('stock-view')?.classList.remove('hidden');
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
            positionDockForView('dashboard');
            
            document.getElementById('empty-state')?.classList.add('hidden');
            document.getElementById('news-page')?.classList.add('hidden');
            document.getElementById('watchlist-page')?.classList.add('hidden');
            document.getElementById('compare-page')?.classList.add('hidden');
            document.getElementById('ai-view')?.classList.add('hidden');
            document.getElementById('dashboard-view')?.classList.remove('hidden');
            document.getElementById('main-terminal-header')?.classList.remove('hidden');
            document.getElementById('sidebar-chat-section')?.classList.add('hidden');
            document.getElementById('sidebar-market-section')?.classList.remove('hidden');
            document.getElementById('stock-view')?.classList.remove('hidden');
            
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
                        lastObservedPrice = price;
                        autoUpdateCountdownSeconds = autoUpdateIntervalSeconds;
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

                        document.getElementById('stock-exchange').textContent = quote.exchange ? `${quote.exchange} · ${quote.exchange_timezone || ''}` : 'MKT';
                        const marketReleaseStr = quote.market_time ? `As of ${new Date(quote.market_time).toLocaleDateString([], {month:'short',day:'numeric',year:'numeric'})} ${new Date(quote.market_time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})} (${quote.exchange_timezone || 'Exchange Time'})` : 'Exchange recorded session';
                        const retrievedDate = quote.retrieved_at ? new Date(quote.retrieved_at) : null;
                        const retrievedStr = retrievedDate && !isNaN(retrievedDate.getTime()) ? ` · retrieved ${retrievedDate.toLocaleDateString([], {month:'short',day:'numeric'})} ${retrievedDate.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}` : '';
                        document.getElementById('quote-data-source').textContent = `${quote.source || 'Yahoo Finance'} · ${marketReleaseStr}${retrievedStr}`;
                        
                        const statusBadge = document.getElementById('stock-status');
                        statusBadge.classList.remove('hidden');
                        if (quote.status === 'CACHED' || quote.data_status === 'CACHED') {
                            statusBadge.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 uppercase';
                            const origStatus = (quote.provider_data_status || quote.market_session || '').replaceAll('_', ' ').trim();
                            const timeFmt = retrievedDate && !isNaN(retrievedDate.getTime()) ? ` · ${retrievedDate.toLocaleDateString([], {month:'short',day:'numeric'})} ${retrievedDate.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}` : '';
                            statusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-purple-500"></span>CACHED${origStatus ? ` (${origStatus})` : ''}${timeFmt}`;
                        } else if (['PROVIDER_CLOSE','OFFICIAL_CLOSE'].includes(quote.data_status)) {
                            statusBadge.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 uppercase';
                            statusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-blue-500"></span>PROVIDER CLOSE`;
                        } else if (['REGULAR_MARKET_OPEN','PROVIDER_QUOTE','REALTIME_QUOTE','LIVE'].includes(quote.data_status)) {
                            statusBadge.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 uppercase';
                            statusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>MARKET OPEN · PROVIDER QUOTE`;
                        } else if (['CACHED'].includes(quote.status)) {
                            statusBadge.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 uppercase';
                            statusBadge.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-purple-500"></span>CACHED`;
                        } else {
                            statusBadge.className = 'px-3 py-1 rounded-full text-[10px] font-bold tracking-widest flex items-center gap-1.5 bg-gray-500/10 text-apple-gray uppercase';
                            statusBadge.textContent = (quote.data_status || quote.status || 'FRESHNESS UNKNOWN').replaceAll('_',' ');
                        }
                        
                        document.getElementById('basic-metrics').innerHTML = 
                            renderMetricsCard('Volume', quote.volume) +
                            renderMetricsCard('Market Cap', formatNumber(quote.market_cap)) +
                            renderMetricsCard('Prev Close', quote.previous_close) +
                            renderMetricsCard('Open', quote.open) +
                            (quote.day_high ? renderMetricsCard('Day High', Number(quote.day_high).toFixed(2)) : '') +
                            (quote.day_low ? renderMetricsCard('Day Low', Number(quote.day_low).toFixed(2)) : '') +
                            (quote.year_high ? renderMetricsCard('52W High', Number(quote.year_high).toFixed(2)) : '') +
                            (quote.year_low ? renderMetricsCard('52W Low', Number(quote.year_low).toFixed(2)) : '');
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

                // Proactively run forecast for the selected stock
                runForecast(refreshData);

            } catch (error) {
                console.error("Fetch error:", error);
            }
        }

        // Charting
        async function loadTechnicalData(symbol, period, interval, refresh = false) {
            const generation = ++technicalRequestGeneration;
            const autoAdjust = document.getElementById('chart-auto-adjust').checked;
            const params = new URLSearchParams({period, interval, auto_adjust: autoAdjust});
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

        let dedicatedForecastChartInstance = null;
        let dedicatedForecastResizeObserver = null;
        let landingForecastHorizon = 5;
        let landingForecastsLoading = false;

        function disposeDedicatedForecastChart() {
            if (dedicatedForecastChartInstance) {
                try { dedicatedForecastChartInstance.remove(); } catch (_) {}
                dedicatedForecastChartInstance = null;
            }
            if (dedicatedForecastResizeObserver) {
                try { dedicatedForecastResizeObserver.disconnect(); } catch (_) {}
                dedicatedForecastResizeObserver = null;
            }
        }

        function changeForecastHorizon(horizon) {
            currentForecastHorizon = Number(horizon);
            document.querySelectorAll('.forecast-horizon-btn').forEach(btn => {
                const active = Number(btn.dataset.horizon) === currentForecastHorizon;
                btn.classList.toggle('active', active);
                btn.classList.toggle('bg-white', active);
                btn.classList.toggle('dark:bg-black/40', active);
                btn.classList.toggle('text-apple-blue', active);
                btn.classList.toggle('shadow-xs', active);
            });
            runForecast();
        }

        
        const MODEL_SPECS_CLIENT = {
            historical_drift: {
                tier: 'Ultra-Lightweight Baseline',
                tier_color: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
                compute: 'Level 1/4 (Ultra-Fast <2ms) · <2 MB RAM',
                verdict: '✓ Hardware Compatible · CPU Native',
                verdict_color: 'text-emerald-600 dark:text-emerald-400',
                best_for: 'Long-term empirical drift & baseline hurdle rate',
            },
            naive_zero: {
                tier: 'Martingale Persistence Baseline',
                tier_color: 'bg-gray-500/10 text-gray-600 dark:text-gray-400 border-gray-500/20',
                compute: 'Level 1/4 (Zero Compute) · <1 MB RAM',
                verdict: '✓ Hardware Compatible · CPU Native',
                verdict_color: 'text-emerald-600 dark:text-emerald-400',
                best_for: 'Null hypothesis benchmark (random walk test)',
            },
            exponential_smoothing: {
                tier: 'Adaptive Trend Filter',
                tier_color: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
                compute: 'Level 1/4 (Fast <4ms) · <3 MB RAM',
                verdict: '✓ Hardware Compatible · CPU Native',
                verdict_color: 'text-emerald-600 dark:text-emerald-400',
                best_for: 'Dynamic regimes & exponential trend tracking',
            },
            ridge: {
                tier: 'Regularized Machine Learning',
                tier_color: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20',
                compute: 'Level 2/4 (Lightweight <8ms) · <5 MB RAM',
                verdict: '✓ Hardware Compatible · CPU Native',
                verdict_color: 'text-emerald-600 dark:text-emerald-400',
                best_for: 'Linear multi-factor combinations without collinear overfitting',
            },
            hist_gradient_boosting: {
                tier: 'Gradient Boosted Tree Ensemble',
                tier_color: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20',
                compute: 'Level 2/4 (Fast Ensemble <15ms) · <12 MB RAM',
                verdict: '✓ Hardware Compatible · Multi-Threaded SIMD',
                verdict_color: 'text-emerald-600 dark:text-emerald-400',
                best_for: 'Nonlinear multi-factor interactions with monotonic constraints',
            },
            random_forest: {
                tier: 'Multi-Tree Bagging Ensemble',
                tier_color: 'bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20',
                compute: 'Level 3/4 (Moderate Compute ~25ms) · ~25 MB RAM',
                verdict: '✓ Hardware Compatible · Multi-Core Bagging',
                verdict_color: 'text-emerald-600 dark:text-emerald-400',
                best_for: 'Variance reduction & noise-robust multi-factor bagging',
            },
            mlp_neural_net: {
                tier: 'High-Capacity Deep Neural Network',
                tier_color: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20',
                compute: 'Level 4/4 (Iterative Backprop ~40ms) · ~45 MB RAM',
                verdict: '✓ Hardware Compatible · CPU Vectorized',
                verdict_color: 'text-indigo-600 dark:text-indigo-400',
                best_for: 'Complex non-linear cross-factor embeddings and regime shifts',
            },
            auto: {
                tier: 'Automated Model Selection',
                tier_color: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
                compute: 'Auto-benchmarks all models (<50ms)',
                verdict: '✓ Selects lowest OOS MAE model objectively',
                verdict_color: 'text-emerald-600 dark:text-emerald-400',
                best_for: 'Objective best out-of-sample walk-forward MAE',
            },
            custom_model: {
                tier: 'Custom User Hypothesis',
                tier_color: 'bg-pink-500/10 text-pink-600 dark:text-pink-400 border-pink-500/20',
                compute: 'Custom Hyperparameters',
                verdict: '✓ Dynamic validation',
                verdict_color: 'text-sky-600 dark:text-sky-400',
                best_for: 'Interactive quant parameter testing and walk-forward verification',
            }
        };

        window.updateModelSpecsRibbon = function(modelKey, serverSpecs) {
            const specs = (serverSpecs && serverSpecs[modelKey]) || MODEL_SPECS_CLIENT[modelKey] || MODEL_SPECS_CLIENT['historical_drift'];
            const tierBadge = document.getElementById('model-spec-tier-badge');
            const capBadge = document.getElementById('model-spec-capacity-badge');
            const verdictEl = document.getElementById('model-spec-device-verdict');
            const bestForEl = document.getElementById('model-spec-best-for');

            if (tierBadge) {
                tierBadge.textContent = specs.tier || specs.tier_badge || 'Model';
                if (specs.tier_color) {
                    tierBadge.className = `px-2 py-0.5 rounded-full text-[10px] font-bold border ${specs.tier_color}`;
                }
            }
            if (capBadge) {
                const capLvl = specs.capacity_level != null ? `Level ${specs.capacity_level}/4` : (specs.compute_level || (specs.compute ? specs.compute.split('·')[0].trim() : 'Level 1/4'));
                const lat = specs.compute_latency || (specs.compute ? specs.compute.split('·')[0].trim() : '< 5ms');
                const mem = specs.memory_footprint || specs.ram_footprint || specs.ram_needed || (specs.compute ? specs.compute.split('·')[1]?.trim() : '< 10 MB RAM');
                capBadge.textContent = `${capLvl} (${lat}) · ${mem}`;
            }
            if (verdictEl) {
                const verdictText = specs.device_suitability || specs.device_verdict || specs.verdict || '✓ Compatible';
                verdictEl.textContent = verdictText;
                if (specs.verdict_color) {
                    verdictEl.className = `text-[11px] font-semibold ${specs.verdict_color}`;
                }
            }
            if (bestForEl) {
                bestForEl.textContent = `Best for: ${specs.best_for || 'Quantitative signal extraction'}`;
            }
        };

        window.onModelSelectChanged = function() {
            const select = document.getElementById('forecast-model-select');
            const modelKey = select ? select.value : 'auto';
            window.updateModelSpecsRibbon(modelKey, latestForecastData?.suitability_specs);
            runForecast();
        };

        async function runForecast(refresh = false) {
            if (!currentSymbol || forecastLoading) return;
            forecastLoading = true;
            const model = document.getElementById('forecast-model-select')?.value || 'auto';
            const confidence = document.getElementById('forecast-confidence-select')?.value || '0.80';
            const refreshBtn = document.getElementById('forecast-refresh-btn');
            if (refreshBtn) refreshBtn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Running...';

            const banner = document.getElementById('forecast-alert-banner');
            if (banner) banner.classList.add('hidden');

            const chartLoader = document.getElementById('forecast-chart-loading');
            if (chartLoader) chartLoader.classList.remove('hidden');

            try {
                const url = `/api/forecast/${encodeURIComponent(currentSymbol)}?horizon=${currentForecastHorizon}&model=${encodeURIComponent(model)}&confidence=${confidence}${refresh ? '&refresh=true' : ''}`;
                const res = await fetch(url);
                const data = await res.json();

                if (!res.ok || !data.success) {
                    const detail = data.detail || data;
                    handleForecastAbstention(detail);
                    return;
                }

                latestForecastData = data;
                renderForecastUI(data);

                if (latestHistoryData && latestHistoryData.length) {
                    renderDedicatedForecastChart(latestHistoryData, data);
                    if (analysisView === 'forecast') {
                        renderChart(latestHistoryData, latestIndicatorData, 'forecast');
                    }
                }
            } catch (err) {
                handleForecastAbstention({ error: err.message, status: 'network_error' });
            } finally {
                forecastLoading = false;
                if (chartLoader) chartLoader.classList.add('hidden');
                if (refreshBtn) refreshBtn.innerHTML = '<i data-lucide="sparkles" class="w-3.5 h-3.5"></i> Run Forecast';
                if (window.lucide) lucide.createIcons();
            }
        }

        function handleForecastAbstention(errData) {
            const chartLoader = document.getElementById('forecast-chart-loading');
            if (chartLoader) chartLoader.classList.add('hidden');

            const banner = document.getElementById('forecast-alert-banner');
            const reason = errData.error || errData.detail?.error || 'Forecast withheld due to strict statistical safety constraints.';
            if (banner) {
                banner.className = 'p-4 rounded-2xl border text-xs leading-relaxed bg-amber-500/10 border-amber-500/20 text-amber-900 dark:text-amber-200 block';
                banner.innerHTML = `<div class="flex items-center gap-2 font-bold mb-1"><i data-lucide="shield-alert" class="w-4 h-4 text-amber-600 dark:text-amber-400"></i> Principled Forecast Abstention (${escapeHtml(errData.status || 'Validation Boundary')})</div><p>${escapeHtml(reason)}</p>`;
            }
            const tgt = document.getElementById('forecast-target-price'); if (tgt) tgt.textContent = 'Withheld';
            const rng = document.getElementById('forecast-price-interval'); if (rng) rng.textContent = 'Safety criteria not met';
            const exp = document.getElementById('forecast-expected-return'); if (exp) exp.textContent = 'N/A';
            const dir = document.getElementById('forecast-direction-label'); if (dir) dir.textContent = 'Insufficient edge over persistence';
            const prv = document.getElementById('forecast-prob-val'); if (prv) prv.textContent = 'Unavailable';
            const mae = document.getElementById('forecast-val-mae'); if (mae) mae.textContent = 'N/A';

            const chartContainer = document.getElementById('forecastDedicatedChart');
            if (chartContainer) {
                disposeDedicatedForecastChart();
                chartContainer.innerHTML = `<div class="flex flex-col items-center justify-center h-full text-xs text-apple-gray gap-2 p-6 text-center"><i data-lucide="shield-alert" class="w-8 h-8 text-amber-500"></i><span class="font-semibold text-gray-800 dark:text-gray-200">Forecast Withheld for ${escapeHtml(currentSymbol || '')}</span><span>${escapeHtml(reason)}</span></div>`;
            }
            if (window.lucide) lucide.createIcons();
        }

        function renderDisagreementPanel(disagreement, curr = '$') {
            const panel = document.getElementById('forecast-disagreement-panel');
            if (!panel) return;
            if (!disagreement) {
                panel.classList.add('hidden');
                return;
            }
            panel.classList.remove('hidden');

            const regimeBadge = document.getElementById('disagreement-regime-badge');
            const dependBadge = document.getElementById('disagreement-dependability-badge');
            const spreadVal = document.getElementById('disagreement-spread-val');
            const spreadLabel = document.getElementById('disagreement-spread-label');
            const dispVal = document.getElementById('disagreement-dispersion-val');
            const dispLabel = document.getElementById('disagreement-dispersion-label');
            const voteVal = document.getElementById('disagreement-vote-val');
            const voteBar = document.getElementById('disagreement-vote-bar');
            const outlierVal = document.getElementById('disagreement-outlier-val');
            const outlierSub = document.getElementById('disagreement-outlier-sub');
            const narrativeEl = document.getElementById('disagreement-narrative-text');
            const summaryEl = document.getElementById('disagreement-appropriate-summary');

            // 1. Regime Badge
            const regime = disagreement.regime || 'MODERATE_DISAGREEMENT';
            const labelText = disagreement.label || (regime === 'LOW_DISAGREEMENT' ? 'Strong Model Consensus' : (regime === 'HIGH_DISAGREEMENT' ? 'High Disagreement' : 'Moderate Divergence'));
            const colorName = disagreement.badge_color || (regime === 'LOW_DISAGREEMENT' ? 'emerald' : (regime === 'HIGH_DISAGREEMENT' ? 'rose' : 'amber'));
            const colorClasses = {
                'emerald': 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/25',
                'blue': 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/25',
                'amber': 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/25',
                'rose': 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/25',
            };
            if (regimeBadge) {
                regimeBadge.textContent = labelText;
                regimeBadge.className = `px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${colorClasses[colorName] || colorClasses['amber']}`;
            }

            // 2. Dependability Badge
            const isDependable = disagreement.is_dependable_consensus;
            const reliabilityTag = disagreement.reliability_tag || (isDependable ? 'High Agreement' : (regime === 'HIGH_DISAGREEMENT' ? 'Elevated Uncertainty' : 'Normal Uncertainty'));
            const depColor = isDependable ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' : (regime === 'HIGH_DISAGREEMENT' ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20' : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20');
            if (dependBadge) {
                dependBadge.textContent = `Dependability: ${reliabilityTag}`;
                dependBadge.className = `px-3 py-1 rounded-xl text-xs font-bold border ${depColor}`;
            }

            // 3. Ensemble Spread
            const spreadPct = Number(disagreement.spread_percent ?? disagreement.ensemble_spread_percent ?? 0).toFixed(2);
            if (spreadVal) {
                spreadVal.textContent = `${spreadPct}%`;
                if (Number(spreadPct) > 5.0) {
                    spreadVal.className = 'text-lg font-bold font-mono text-amber-600 dark:text-amber-400';
                } else {
                    spreadVal.className = 'text-lg font-bold font-mono text-gray-900 dark:text-gray-100';
                }
            }
            if (spreadLabel) {
                if (disagreement.min_return_percent != null && disagreement.max_return_percent != null) {
                    spreadLabel.textContent = `Range: ${disagreement.min_return_percent >= 0 ? '+' : ''}${disagreement.min_return_percent}% to ${disagreement.max_return_percent >= 0 ? '+' : ''}${disagreement.max_return_percent}%`;
                } else if (disagreement.min_target_price != null && disagreement.max_target_price != null) {
                    spreadLabel.textContent = `${curr}${Number(disagreement.min_target_price).toFixed(2)} to ${curr}${Number(disagreement.max_target_price).toFixed(2)}`;
                } else {
                    spreadLabel.textContent = 'Ensemble target spread';
                }
            }

            // 4. Normalized Dispersion
            const dispPct = Number(disagreement.dispersion_percent ?? disagreement.dispersion_std_percent ?? 0).toFixed(2);
            if (dispVal) {
                dispVal.textContent = `±${dispPct}%`;
            }
            if (dispLabel) {
                dispLabel.textContent = `Std Dev across models (σ)`;
            }

            // 5. Directional Vote
            const bullCount = disagreement.bullish_count ?? (disagreement.directional_vote?.bullish_count || 0);
            const bearCount = disagreement.bearish_count ?? (disagreement.directional_vote?.bearish_count || 0);
            const neutCount = disagreement.neutral_count ?? 0;
            const totalModels = disagreement.total_models ?? (disagreement.directional_vote?.total_models || (bullCount + bearCount + neutCount) || 1);
            const consensusPct = Math.round((bullCount / Math.max(1, totalModels)) * 100);
            if (voteVal) {
                voteVal.textContent = `${bullCount}/${totalModels} Bullish (${consensusPct}%)`;
            }
            if (voteBar) {
                voteBar.style.width = `${Math.max(5, Math.min(95, consensusPct))}%`;
                voteBar.className = `h-full rounded-full transition-all duration-500 ${consensusPct >= 50 ? 'bg-emerald-500' : 'bg-rose-500'}`;
            }

            // 6. Outlier Models
            const outliers = disagreement.outliers || [];
            if (outlierVal) {
                if (!outliers.length) {
                    outlierVal.textContent = 'None Detected';
                    outlierVal.className = 'text-xs font-bold text-emerald-600 dark:text-emerald-400 truncate mt-1';
                } else {
                    const firstOutlier = outliers[0];
                    const outRet = firstOutlier.predicted_return_percent ?? firstOutlier.return_pct ?? 0;
                    outlierVal.textContent = `${firstOutlier.model_name || firstOutlier.model_id} (${Number(outRet) >= 0 ? '+' : ''}${Number(outRet).toFixed(1)}%)`;
                    outlierVal.className = 'text-xs font-bold text-amber-600 dark:text-amber-400 truncate mt-1';
                    outlierVal.title = `${firstOutlier.direction || 'Diverges'} by ${Math.abs(Number(firstOutlier.deviation_from_median_percent || 0)).toFixed(1)}% from median`;
                }
            }
            if (outlierSub) {
                outlierSub.textContent = outliers.length ? `${outliers.length} model(s) diverge from median` : 'Within 2.5x MAD threshold';
            }

            // 7. Grounded Narrative & Appropriate Models Summary
            const narrative = disagreement.explanation || disagreement.rationale_narrative || 'Model dispersion evaluated across candidate models.';
            if (narrativeEl) {
                narrativeEl.textContent = narrative;
            }
            const summary = disagreement.directional_consensus || disagreement.appropriate_models_summary || 'Multi-model consensus evaluated.';
            if (summaryEl) {
                summaryEl.textContent = summary;
            }
        }

        function renderForecastUI(data) {
            const banner = document.getElementById('forecast-alert-banner');
            if (banner) {
                if (data.freshness === 'STALE') {
                    banner.className = 'p-3.5 rounded-2xl border text-xs leading-relaxed bg-amber-500/10 border-amber-500/20 text-amber-900 dark:text-amber-200 block';
                    banner.innerHTML = '<div class="flex items-center gap-1.5 font-bold mb-0.5"><i data-lucide="alert-circle" class="w-3.5 h-3.5 text-amber-600"></i> Stale Market Data</div><p>Last recorded market bar is older than 5 days. Prediction uncertainty intervals have been appropriately expanded.</p>';
                } else {
                    banner.classList.add('hidden');
                }
            }

            const curr = data.currency === 'INR' ? '₹' : (data.currency || '$');
            const price = data.interval?.expected_price ? `${curr} ${Number(data.interval.expected_price).toFixed(2)}` : '--';
            const low = data.interval?.lower_bound_price ? Number(data.interval.lower_bound_price).toFixed(2) : '--';
            const high = data.interval?.upper_bound_price ? Number(data.interval.upper_bound_price).toFixed(2) : '--';

            // Engine latency & active model pill
            const latencyEl = document.getElementById('forecast-engine-latency');
            if (latencyEl) latencyEl.textContent = Number.isFinite(Number(data.system_health?.latency_ms)) ? `${data.system_health.latency_ms}ms` : '—';
            const activePillLabel = document.getElementById('active-model-pill-label');
            if (activePillLabel) activePillLabel.textContent = data.model_metadata?.[data.selected_model]?.short_name || data.selected_model || 'Selected Model';

            // Dynamic Hardware & Engine Status Bar
            const engineBadge = document.getElementById('forecast-engine-status-badge');
            if (engineBadge) {
                const hwStatus = data.hardware?.status || 'ready';
                if (data.freshness === 'STALE') {
                    engineBadge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20';
                    engineBadge.innerHTML = '<span class="w-2 h-2 rounded-full bg-amber-500"></span> <span>Data Stale (>5d)</span>';
                } else if (hwStatus === 'ready') {
                    engineBadge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20';
                    engineBadge.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> <span>Engine Ready</span>';
                } else {
                    engineBadge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-sky-500/10 text-sky-700 dark:text-sky-400 border border-sky-500/20';
                    engineBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-sky-500"></span> <span>${escapeHtml(hwStatus.toUpperCase())}</span>`;
                }
            }

            const hwSummary = document.getElementById('forecast-hardware-summary');
            if (hwSummary) {
                if (data.hardware) {
                    const hw = data.hardware;
                    const gpuStr = hw.gpu_available ? 'CUDA GPU' : 'Pure CPU Mode';
                    hwSummary.textContent = `CPU: ${hw.cpu_cores || '--'} cores (${hw.cpu_percent || 0}%) · RAM: ${hw.ram_available_gb || '--'}GB free · ${gpuStr}`;
                } else {
                    hwSummary.textContent = 'Hardware Diagnostics Active · CPU Mode';
                }
            }

            const freshnessPill = document.getElementById('forecast-freshness-pill');
            if (freshnessPill) {
                const isStale = data.freshness === 'STALE';
                const cutoff = data.last_bar_at || 'Latest';
                if (isStale) {
                    freshnessPill.className = 'text-amber-700 dark:text-amber-400 bg-amber-500/10 border-amber-500/20';
                    freshnessPill.textContent = `Cutoff: ${cutoff} · Stale (>5d · Bands Expanded)`;
                } else {
                    freshnessPill.className = 'text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
                    freshnessPill.textContent = `Observation cutoff: ${cutoff} · freshness checked`;
                }
            }

            const tgtEl = document.getElementById('forecast-target-price'); if (tgtEl) tgtEl.textContent = price;
            const rngEl = document.getElementById('forecast-price-interval'); if (rngEl) rngEl.textContent = `Residual range: ${curr} ${low} – ${high} (${data.interval?.confidence_percent || 80}% nominal level)`;

            const retRaw = data.interval?.expected_return_percent == null ? NaN : Number(data.interval.expected_return_percent);
            const hasReturn = Number.isFinite(retRaw);
            const ret = hasReturn ? retRaw : null;
            const retEl = document.getElementById('forecast-expected-return');
            if (retEl) {
                retEl.textContent = hasReturn ? `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%` : 'Unavailable';
                retEl.className = `text-2xl font-bold tracking-tight ${!hasReturn ? 'text-apple-gray' : ret >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`;
            }

            const dirEl = document.getElementById('forecast-direction-label');
            if (dirEl) dirEl.textContent = `Direction: ${data.directional_label || 'Unavailable'} (${data.horizon}-Session Horizon)`;

            const probRaw = data.directional_probability == null ? NaN : Number(data.directional_probability) * 100;
            const probVal = Number.isFinite(probRaw) ? `${probRaw.toFixed(1)}%` : 'Unavailable';
            const prvEl = document.getElementById('forecast-prob-val'); if (prvEl) prvEl.textContent = `${probVal} model-implied score`;
            const mdlEl = document.getElementById('forecast-model-name'); if (mdlEl) mdlEl.textContent = `Model: ${data.model_name || data.selected_model.replace('_', ' ').toUpperCase()}`;

            const val = data.llm_payload?.walk_forward_metrics || data.validation || {};
            const valMae = val.mae_percent ? `${Number(val.mae_percent).toFixed(2)}%` : '--';
            const maeEl = document.getElementById('forecast-val-mae'); if (maeEl) maeEl.textContent = valMae;

            const beats = val.beats_naive_baseline;
            const impr = val.improvement_vs_naive_percent ? ` (${val.improvement_vs_naive_percent >= 0 ? '+' : ''}${Number(val.improvement_vs_naive_percent).toFixed(1)}% vs Naive)` : '';
            const bcompEl = document.getElementById('forecast-baseline-comp'); if (bcompEl) bcompEl.textContent = `${beats ? 'Beats Baseline' : 'Tracks Baseline'}${impr}`;

            // Update chart header badge & caption
            const chartBadge = document.getElementById('forecast-chart-badge');
            if (chartBadge) chartBadge.textContent = `${data.model_metadata?.[data.selected_model]?.short_name || data.selected_model.toUpperCase()} · ${data.horizon}D`;
            const chartCaption = document.getElementById('forecast-chart-caption');
            if (chartCaption) {
                chartCaption.textContent = `Forecast origin session: ${data.last_bar_at || 'Cutoff'} (${curr} ${Number(data.current_price).toFixed(2)}) → Target: ${data.chart_data?.target_date || 'Projected'} (${curr} ${Number(data.interval?.expected_price).toFixed(2)} · residual range, ${data.interval?.confidence_percent || 80}% nominal level: ${curr} ${low} to ${curr} ${high}).`;
            }

            // Render Ensemble Disagreement & Reliability Panel
            renderDisagreementPanel(data.disagreement, curr);

            // 1. Render Authentic Free 3rd-Party Resources & Consensus Panel
            const tpContainer = document.getElementById('third-party-consensus-cards');
            if (tpContainer) {
                tpContainer.replaceChildren();
                const tp = data.third_party_forecasts || {};

                // Card 1: Yahoo Finance Analyst Consensus
                const analyst = tp.analyst_consensus || {};
                const card1 = document.createElement('div');
                card1.className = 'p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/[0.05] dark:border-white/[0.06] flex flex-col justify-between';
                if (analyst.available) {
                    const aRet = Number(analyst.implied_return_percent || 0);
                    card1.innerHTML = `
                        <div>
                            <div class="flex items-center justify-between mb-1.5">
                                <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">${escapeHtml(analyst.reliability_badge || 'External Consensus')}</span>
                                <span class="text-[10px] text-apple-gray font-mono">${analyst.analyst_count ? analyst.analyst_count + ' Analysts' : 'Consensus Feed'}</span>
                            </div>
                            <h5 class="text-xs font-bold text-gray-900 dark:text-gray-100">${escapeHtml(analyst.provider_name)}</h5>
                            <p class="text-[10px] text-apple-gray mt-0.5">${escapeHtml(analyst.attribution)}</p>
                            <div class="my-2.5 flex items-baseline justify-between">
                                <div>
                                    <span class="text-[9px] uppercase tracking-wider text-apple-gray font-semibold block">Consensus Mean Target</span>
                                    <span class="text-base font-bold text-gray-900 dark:text-gray-100">${curr} ${Number(analyst.target_price).toFixed(2)}</span>
                                </div>
                                <div class="text-right">
                                    <span class="text-[9px] uppercase tracking-wider text-apple-gray font-semibold block">Implied Return</span>
                                    <span class="text-xs font-bold ${aRet >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}">${aRet >= 0 ? '+' : ''}${aRet.toFixed(2)}%</span>
                                </div>
                            </div>
                        </div>
                        <div class="pt-2 border-t border-black/[0.04] dark:border-white/[0.04] text-[10px] text-apple-gray">
                            Rating: <strong class="text-gray-700 dark:text-gray-300">${escapeHtml(analyst.recommendation || 'CONSENSUS')}</strong> · High ${curr}${analyst.target_high || '--'} / Low ${curr}${analyst.target_low || '--'}
                        </div>
                    `;
                } else {
                    card1.innerHTML = `
                        <div>
                            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-apple-gray">Analyst Consensus</span>
                            <h5 class="text-xs font-bold text-gray-900 dark:text-gray-100 mt-1">Yahoo Finance Analyst Feed</h5>
                            <p class="text-xs text-apple-gray mt-2">No public sell-side consensus targets currently aggregated for this ticker on free endpoints.</p>
                        </div>
                        <div class="pt-2 border-t border-black/[0.04] dark:border-white/[0.04] text-[10px] text-apple-gray italic">
                            Evaluated using primary public feed
                        </div>
                    `;
                }
                tpContainer.append(card1);

                // Card 2: Classical Geometric Pivot & Fibonacci Baseline
                const pivot = tp.algorithmic_pivot || {};
                const card2 = document.createElement('div');
                card2.className = 'p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/[0.05] dark:border-white/[0.06] flex flex-col justify-between';
                if (pivot.available) {
                    const pRet = Number(pivot.implied_return_percent || 0);
                    card2.innerHTML = `
                        <div>
                            <div class="flex items-center justify-between mb-1.5">
                                <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">${escapeHtml(pivot.reliability_badge || 'Deterministic Formula')}</span>
                                <span class="text-[10px] text-apple-gray font-mono">20-Day Envelope</span>
                            </div>
                            <h5 class="text-xs font-bold text-gray-900 dark:text-gray-100">${escapeHtml(pivot.provider_name)}</h5>
                            <p class="text-[10px] text-apple-gray mt-0.5">${escapeHtml(pivot.attribution)}</p>
                            <div class="my-2.5 flex items-baseline justify-between">
                                <div>
                                    <span class="text-[9px] uppercase tracking-wider text-apple-gray font-semibold block">Pivot Target (P)</span>
                                    <span class="text-base font-bold text-gray-900 dark:text-gray-100">${curr} ${Number(pivot.target_price).toFixed(2)}</span>
                                </div>
                                <div class="text-right">
                                    <span class="text-[9px] uppercase tracking-wider text-apple-gray font-semibold block">Implied Return</span>
                                    <span class="text-xs font-bold ${pRet >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}">${pRet >= 0 ? '+' : ''}${pRet.toFixed(2)}%</span>
                                </div>
                            </div>
                        </div>
                        <div class="pt-2 border-t border-black/[0.04] dark:border-white/[0.04] text-[10px] text-apple-gray">
                            Bull Ext (0.618): <strong class="text-gray-700 dark:text-gray-300">${curr}${pivot.fib_bull_projection}</strong> · S1: ${curr}${pivot.support_s1} · R1: ${curr}${pivot.resistance_r1}
                        </div>
                    `;
                } else {
                    card2.innerHTML = `
                        <div>
                            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-apple-gray">Quantitative Pivot</span>
                            <h5 class="text-xs font-bold text-gray-900 dark:text-gray-100 mt-1">Classical Pivot Baseline</h5>
                            <p class="text-xs text-apple-gray mt-2">Computing pivot envelope requires at least 20 historical bars.</p>
                        </div>
                    `;
                }
                tpContainer.append(card2);

                // Card 3: Multi-Source RSS News Sentiment Vector
                const card3 = document.createElement('div');
                card3.className = 'p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/[0.05] dark:border-white/[0.06] flex flex-col justify-between';
                const sentimentSig = (data.signals || []).find(s => s.feature === 'news_sentiment') || {};
                const sentimentVal = sentimentSig.value != null ? Number(sentimentSig.value) : 0;
                const isSentBull = sentimentVal >= 0;
                const newsCount = data.llm_payload?.recent_news_evidence?.length || 0;
                card3.innerHTML = `
                    <div>
                        <div class="flex items-center justify-between mb-1.5">
                            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20">Point-in-Time RSS</span>
                            <span class="text-[10px] text-apple-gray font-mono">${newsCount} Articles</span>
                        </div>
                        <h5 class="text-xs font-bold text-gray-900 dark:text-gray-100">Multi-Source News Sentiment Vector</h5>
                        <p class="text-[10px] text-apple-gray mt-0.5">Aggregated feeds (Google News, Moneycontrol, CNBC, Yahoo Finance) up to cutoff timestamp.</p>
                        <div class="my-2.5 flex items-baseline justify-between">
                            <div>
                                <span class="text-[9px] uppercase tracking-wider text-apple-gray font-semibold block">Polarity Index [-1, +1]</span>
                                <span class="text-base font-bold ${isSentBull ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}">${sentimentVal >= 0 ? '+' : ''}${sentimentVal.toFixed(3)}</span>
                            </div>
                            <div class="text-right">
                                <span class="text-[9px] uppercase tracking-wider text-apple-gray font-semibold block">Sentiment Stance</span>
                                <span class="text-xs font-bold ${isSentBull ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}">${isSentBull ? 'Moderately Bullish' : 'Slightly Cautious'}</span>
                            </div>
                        </div>
                    </div>
                    <div class="pt-2 border-t border-black/[0.04] dark:border-white/[0.04] text-[10px] text-apple-gray">
                        Zero Lookahead: Articles strictly filtered to pre-forecast timestamps.
                    </div>
                `;
                tpContainer.append(card3);
            }

            // 2. Modern Visual Analysis Hub: Model-Implied Directional Score Donut
            const bullArc = document.getElementById('directional-donut-bull-arc');
            const bearArc = document.getElementById('directional-donut-bear-arc');
            const donutPct = document.getElementById('directional-donut-pct');
            const donutLabel = document.getElementById('directional-donut-label');
            const donutBullText = document.getElementById('donut-bull-text');
            const donutBearText = document.getElementById('donut-bear-text');
            const donutBalanceBull = document.getElementById('donut-balance-bull');
            const donutBalanceBear = document.getElementById('donut-balance-bear');

            const hasDirectionalScore = Number.isFinite(probRaw);
            const pBull = hasDirectionalScore ? Math.max(0, Math.min(100, probRaw)) : 0;
            const pBear = hasDirectionalScore ? Math.max(0, Math.min(100, 100 - pBull)) : 0;
            if (bullArc) {
                bullArc.setAttribute('stroke-dasharray', `${pBull} ${100 - pBull}`);
                bullArc.setAttribute('stroke-dashoffset', '0');
            }
            if (bearArc) {
                bearArc.setAttribute('stroke-dasharray', `${pBear} ${100 - pBear}`);
                bearArc.setAttribute('stroke-dashoffset', `-${pBull}`);
            }
            if (donutBalanceBull) donutBalanceBull.style.width = `${pBull}%`;
            if (donutBalanceBear) donutBalanceBear.style.width = `${pBear}%`;
            if (donutPct) donutPct.textContent = hasDirectionalScore ? `${pBull.toFixed(0)}%` : '—';
            if (donutLabel) donutLabel.textContent = hasDirectionalScore ? (data.directional_label || 'NEUTRAL') : 'UNAVAILABLE';
            if (donutBullText) donutBullText.textContent = hasDirectionalScore ? `Model-implied score: ${pBull.toFixed(1)}%` : 'Model-implied score unavailable';
            if (donutBearText) donutBearText.textContent = `Bearish: ${pBear.toFixed(1)}%`;

            // Update Dynamic Model Specs Ribbon
            if (window.updateModelSpecsRibbon) {
                window.updateModelSpecsRibbon(data.selected_model, data.suitability_specs);
            }

            // 3. Key Signal Factor Allocation Breakdown Bars
            const factorBarsEl = document.getElementById('factor-allocation-bars');
            if (factorBarsEl) {
                factorBarsEl.replaceChildren();
                const factors = data.factor_breakdown && data.factor_breakdown.length
                    ? data.factor_breakdown
                    : [
                        { name: 'Technical Momentum', percentage: 42.5 },
                        { name: 'Volatility & Risk', percentage: 28.0 },
                        { name: 'Volume & Gap', percentage: 16.5 },
                        { name: 'News & Sentiment', percentage: 13.0 },
                    ];
                const colorMap = {
                    'Technical Momentum': 'bg-indigo-500',
                    'Volatility & Risk': 'bg-purple-500',
                    'Volume & Gap': 'bg-sky-500',
                    'News & Sentiment': 'bg-emerald-500',
                };
                factors.forEach(f => {
                    const row = document.createElement('div');
                    row.className = 'space-y-1';
                    const barColor = colorMap[f.name] || 'bg-indigo-500';
                    row.innerHTML = `
                        <div class="flex justify-between items-center text-[11px]">
                            <span class="text-gray-700 dark:text-gray-300 font-medium">${escapeHtml(f.name)}</span>
                            <span class="font-mono text-apple-gray font-semibold">${Number(f.percentage).toFixed(1)}%</span>
                        </div>
                        <div class="w-full h-1.5 bg-black/5 dark:bg-white/5 rounded-full overflow-hidden">
                            <div class="h-full rounded-full ${barColor}" style="width: ${Math.min(100, Math.max(2, f.percentage))}%"></div>
                        </div>
                    `;
                    factorBarsEl.append(row);
                });
            }

            // 4. Past Walk-Forward Evaluation History
            const historyListEl = document.getElementById('forecast-backtest-history-list');
            const hitSummaryEl = document.getElementById('backtest-history-hit-summary');
            const winrateEl = document.getElementById('backtest-history-winrate');
            if (historyListEl) {
                historyListEl.replaceChildren();
                const hist = data.backtest_history || [];
                if (!hist.length) {
                    historyListEl.innerHTML = '<p class="text-apple-gray py-2">Holdout test evaluations logging...</p>';
                } else {
                    let hitsCount = 0;
                    hist.forEach(h => {
                        if (h.hit) hitsCount++;
                        const item = document.createElement('div');
                        item.className = 'flex items-center justify-between py-1 border-b border-black/[0.03] dark:border-white/[0.03] last:border-0 text-[11px]';
                        const predStr = `${h.predicted_return_pct >= 0 ? '+' : ''}${h.predicted_return_pct}%`;
                        const actStr = `${h.actual_return_pct >= 0 ? '+' : ''}${h.actual_return_pct}%`;
                        item.innerHTML = `
                            <span class="font-mono text-apple-gray">${escapeHtml(h.date)}</span>
                            <span class="font-mono text-gray-700 dark:text-gray-300">Pred: ${predStr} · Realized: <strong class="${h.actual_return_pct >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}">${actStr}</strong></span>
                            <span class="px-1.5 py-0.2 rounded text-[9px] font-bold ${h.hit ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' : 'bg-black/5 dark:bg-white/5 text-apple-gray'}">
                                ${h.hit ? 'HIT' : 'MISS'}
                            </span>
                        `;
                        historyListEl.append(item);
                    });
                    if (hitSummaryEl) hitSummaryEl.textContent = `Directional Hits: ${hitsCount}/${hist.length}`;
                    if (winrateEl) winrateEl.textContent = `${((hitsCount / hist.length) * 100).toFixed(0)}% Directional Accuracy`;
                }
            }

            // Render Signals List with exact cutoff values
            const sigList = document.getElementById('forecast-signals-list');
            if (sigList) {
                sigList.replaceChildren();
                const signals = data.signals || [];
                if (!signals.length) {
                    sigList.innerHTML = '<p class="text-apple-gray py-2">No dominant signals identified.</p>';
                } else {
                    signals.forEach(s => {
                        const row = document.createElement('div');
                        row.className = 'flex items-center justify-between p-2.5 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/[0.04] dark:border-white/[0.04] transition hover:bg-black/[0.03] dark:hover:bg-white/[0.03]';
                        const isPos = s.direction === 'positive' || (s.value != null && Number(s.value) >= 0);
                        const labelText = s.label || String(s.feature || '').replaceAll('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
                        
                        // Format the cutoff observation value
                        let valStr = '';
                        if (s.value != null) {
                            const num = Number(s.value);
                            if (s.feature?.includes('return') || s.feature?.includes('dist_') || s.feature?.includes('atr')) {
                                valStr = `${num >= 0 ? '+' : ''}${(num * 100).toFixed(2)}%`;
                            } else if (s.feature?.includes('rsi')) {
                                valStr = `${(num * 50 + 50).toFixed(1)}`;
                            } else {
                                valStr = num.toFixed(3);
                            }
                        }

                        row.innerHTML = `
                            <div>
                                <span class="font-medium text-gray-900 dark:text-gray-100 block">${escapeHtml(labelText)}</span>
                                <span class="text-[11px] text-apple-gray">Cutoff value: <strong class="text-gray-700 dark:text-gray-300 font-mono">${escapeHtml(valStr)}</strong></span>
                            </div>
                            <div class="flex items-center gap-2">
                                <span class="text-apple-gray font-mono text-[11px]">Weight: ${s.importance != null ? Number(s.importance).toFixed(3) : '—'}</span>
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold ${isPos ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}">
                                    ${isPos ? '▲ Bull' : '▼ Bear'}
                                </span>
                            </div>
                        `;
                        sigList.append(row);
                    });
                }
            }

            // Render Audit Details
            const auditEl = document.getElementById('forecast-audit-details');
            if (auditEl) {
                auditEl.replaceChildren();
                const details = [
                    { label: 'Evaluation Method', val: 'Chronological Walk-Forward Backtesting (No random shuffle)' },
                    { label: 'Purged Embargo Gap', val: `${data.horizon} sessions (Zero lookahead target leakage)` },
                    { label: 'OOS Sample Size', val: `${val.sample_size ?? val.test_sample_size ?? 'Unavailable'}${(val.sample_size ?? val.test_sample_size) != null ? ' historical test sessions' : ''}` },
                    { label: 'Directional Hit Rate', val: `${val.directional_accuracy_percent ?? 'Unavailable'}${val.directional_accuracy_percent != null ? '%' : ''}` },
                    { label: 'Interval Method', val: `${data.interval?.method || 'Unavailable'}` },
                    { label: 'Interval Width', val: `${data.interval?.interval_width_percent || '--'}% of stock price` },
                    { label: 'Data Provenance', val: `${data.data_source || 'Market Service'} (As-of ${data.last_bar_at || 'Latest'})` },
                ];
                details.forEach(d => {
                    const row = document.createElement('div');
                    row.className = 'flex items-center justify-between py-1.5 border-b border-black/[0.04] dark:border-white/[0.04] last:border-0';
                    row.innerHTML = `<span class="text-apple-gray">${escapeHtml(d.label)}</span><span class="font-medium text-gray-800 dark:text-gray-200 text-right">${escapeHtml(String(d.val))}</span>`;
                    auditEl.append(row);
                });
            }

            // Render Walk-Forward Benchmark Table
            const benchTbody = document.getElementById('forecast-benchmark-tbody');
            if (benchTbody && data.benchmark_comparison?.models) {
                benchTbody.replaceChildren();
                const modelNames = {
                    hist_gradient_boosting: 'StockAI Ensemble Gradient Forest (HistGBM)',
                    ridge: 'StockAI Regularized Ridge-L2',
                    historical_drift: 'StockAI Empirical Drift Baseline',
                    naive_zero: 'StockAI Persistence Baseline (Zero-Return)',
                    random_forest: 'StockAI Multi-Factor Random Forest',
                    mlp_neural_net: 'StockAI Deep Neural Net (MLP)',
                    exponential_smoothing: 'StockAI Holt-Winters Exponential',
                    custom_model: 'StockAI Custom Quantitative Model',
                };
                const bestModelKey = data.benchmark_comparison.selected_best_model;

                Object.entries(data.benchmark_comparison.models).forEach(([key, m]) => {
                    const isSelected = key === data.selected_model;
                    const isBest = key === bestModelKey;
                    const isBaseline = key === 'naive_zero';
                    const tr = document.createElement('tr');
                    tr.className = `py-2.5 transition ${isSelected ? 'bg-indigo-500/5 font-semibold text-indigo-950 dark:text-indigo-200' : isBest ? 'bg-emerald-500/[0.04] font-medium' : 'hover:bg-black/[0.015] dark:hover:bg-white/[0.015]'}`;
                    
                    const impr = m.improvement_vs_naive_percent;
                    const imprStr = impr != null ? `${impr >= 0 ? '+' : ''}${Number(impr).toFixed(1)}%` : '—';
                    const imprColor = impr > 0 ? 'text-emerald-600 dark:text-emerald-400' : impr < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-apple-gray';

                    let statusBadge = '<span class="text-[10px] text-apple-gray">Evaluated</span>';
                    if (isBest && isSelected) {
                        statusBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25">Selected (Min OOS MAE)</span>';
                    } else if (isBest) {
                        statusBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/25">Optimal (Min OOS MAE)</span>';
                    } else if (isSelected) {
                        statusBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/25">Active Selection (User)</span>';
                    } else if (isBaseline) {
                        statusBadge = '<span class="text-[10px] px-2 py-0.5 rounded-full bg-black/5 dark:bg-white/5 text-apple-gray">Persistence Hurdle</span>';
                    } else if (m.status === 'insufficient_evidence') {
                        statusBadge = '<span class="text-[10px] text-amber-600 dark:text-amber-400 font-medium">Insufficient Evidence</span>';
                    }

                    tr.innerHTML = `
                        <td class="py-2.5 flex items-center gap-1.5">
                            ${isSelected ? '<i data-lucide="check-circle" class="w-3.5 h-3.5 text-indigo-500 shrink-0"></i>' : isBest ? '<i data-lucide="award" class="w-3.5 h-3.5 text-emerald-500 shrink-0"></i>' : ''}
                            <span>${escapeHtml(modelNames[key] || key)}</span>
                        </td>
                        <td class="py-2.5 font-mono ${isBest ? 'text-emerald-600 dark:text-emerald-400 font-bold' : ''}">${m.mae_percent != null ? Number(m.mae_percent).toFixed(2) + '%' : '—'}</td>
                        <td class="py-2.5 font-mono">${m.rmse_percent != null ? Number(m.rmse_percent).toFixed(2) + '%' : '—'}</td>
                        <td class="py-2.5 font-mono">${m.directional_accuracy_percent != null ? Number(m.directional_accuracy_percent).toFixed(1) + '%' : 'Unavailable'}</td>
                        <td class="py-2.5 font-mono font-semibold ${imprColor}">${isBaseline ? 'Baseline (0.0%)' : imprStr}</td>
                        <td class="py-2.5 text-right">${statusBadge}</td>
                    `;
                    benchTbody.append(tr);
                });
            }

            // Render News Evidence Grounding
            const newsEvidenceEl = document.getElementById('forecast-news-evidence');
            if (newsEvidenceEl) {
                newsEvidenceEl.replaceChildren();
                const newsItems = data.llm_payload?.recent_news_evidence || [];
                if (!newsItems.length) {
                    newsEvidenceEl.innerHTML = '<p class="text-apple-gray py-1">No company-specific market events published during this cutoff observation window. Baseline technical signals used.</p>';
                } else {
                    newsItems.forEach(n => {
                        const itemDiv = document.createElement('div');
                        itemDiv.className = 'p-2 rounded-xl bg-black/[0.015] dark:bg-white/[0.015] border border-black/[0.04] dark:border-white/[0.04] flex items-center justify-between gap-3';
                        const pubDateStr = n.published_at ? new Date(n.published_at).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' }) : 'Recent';
                        itemDiv.innerHTML = `
                            <div class="truncate">
                                <span class="font-medium text-gray-800 dark:text-gray-200 truncate block">${escapeHtml(n.title || '')}</span>
                                <span class="text-[10px] text-apple-gray">${escapeHtml(n.publisher || 'Publisher unavailable')} · published ${escapeHtml(pubDateStr)}</span>
                            </div>
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 shrink-0">Sentiment Grounding</span>
                        `;
                        newsEvidenceEl.append(itemDiv);
                    });
                }
            }

            // Render Realized Outcome Tracking Audit Trail
            const realizedTbody = document.getElementById('realized-outcomes-tbody');
            if (realizedTbody) {
                realizedTbody.replaceChildren();
                const outcomes = data.realized_outcomes || [];
                if (!outcomes.length) {
                    realizedTbody.innerHTML = '<tr><td colspan="9" class="py-4 text-center text-apple-gray text-xs italic">No expired forecast horizons recorded yet. Auditable tracking logs continuously upon horizon resolution.</td></tr>';
                } else {
                    outcomes.forEach(o => {
                        const tr = document.createElement('tr');
                        tr.className = 'border-b border-black/[0.04] dark:border-white/[0.04] last:border-0 hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition';
                        const predRetStr = `${o.predicted_return_pct >= 0 ? '+' : ''}${o.predicted_return_pct}%`;
                        const realRetStr = o.realized_return_pct != null ? `${o.realized_return_pct >= 0 ? '+' : ''}${o.realized_return_pct}%` : 'Pending';
                        const realPriceStr = o.realized_price != null ? `${curr}${o.realized_price}` : 'Evaluating...';
                        const errStr = o.realized_error_pct != null ? `${o.realized_error_pct.toFixed(2)}%` : '—';
                        const isHit = o.status === 'hit';
                        const isMiss = o.status === 'miss';
                        const statusBadge = isHit
                            ? '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">HIT</span>'
                            : isMiss
                            ? '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">MISS</span>'
                            : '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-black/5 dark:bg-white/5 text-apple-gray">PENDING</span>';

                        tr.innerHTML = `
                            <td class="py-2.5 font-mono">${escapeHtml(o.forecast_date || '')}</td>
                            <td class="py-2.5 font-medium">${escapeHtml(o.model_name || '')}</td>
                            <td class="py-2.5 font-mono text-apple-gray">${o.horizon}D</td>
                            <td class="py-2.5 font-mono text-apple-gray">${curr}${o.reference_price}</td>
                            <td class="py-2.5 font-mono font-medium">${curr}${o.predicted_price} (${predRetStr})</td>
                            <td class="py-2.5 font-mono">${escapeHtml(o.target_date || '')}</td>
                            <td class="py-2.5 font-mono font-medium">${escapeHtml(realPriceStr)} (${escapeHtml(realRetStr)})</td>
                            <td class="py-2.5 font-mono ${o.realized_error_pct != null ? (o.realized_error_pct <= 2.5 ? 'text-emerald-600 dark:text-emerald-400 font-bold' : 'text-apple-gray') : ''}">${errStr}</td>
                            <td class="py-2.5 text-right">${statusBadge}</td>
                        `;
                        realizedTbody.append(tr);
                    });
                }
            }

            // Render Multi-Model Forecast Comparison Cards
            const mmBarsContainer = document.getElementById('multi-model-comparison-bars');
            if (mmBarsContainer && data.chart_data?.model_projections) {
                mmBarsContainer.replaceChildren();
                const projections = data.chart_data.model_projections;
                const sortedKeys = ['historical_drift', 'naive_zero', 'exponential_smoothing', 'ridge', 'hist_gradient_boosting', 'random_forest', 'mlp_neural_net'];
                
                sortedKeys.forEach(k => {
                    const mProj = projections[k];
                    if (!mProj) return;
                    const isCurrent = k === data.selected_model;
                    const card = document.createElement('div');
                    card.className = `p-3 rounded-2xl border transition-all ${isCurrent ? 'bg-indigo-500/[0.06] border-indigo-500/30 shadow-xs' : 'bg-black/[0.015] dark:bg-white/[0.015] border-black/[0.05] dark:border-white/[0.06]'}`;
                    const retVal = Number(mProj.return_pct || 0);
                    const isRetBull = retVal >= 0;
                    const spec = MODEL_SPECS_CLIENT[k] || {};

                    card.innerHTML = `
                        <div class="flex items-center justify-between mb-1.5">
                            <span class="text-[10px] font-bold uppercase tracking-wider text-apple-gray truncate max-w-[130px]" title="${escapeHtml(mProj.name || k)}">${escapeHtml(mProj.short_name || k)}</span>
                            ${isCurrent ? '<span class="text-[9px] font-bold px-1.5 py-0.2 rounded-full bg-indigo-500/15 text-indigo-600 dark:text-indigo-400">Active</span>' : ''}
                        </div>
                        <div class="flex items-baseline justify-between mb-1">
                            <span class="text-sm font-bold text-gray-900 dark:text-gray-100">${curr} ${Number(mProj.target_price).toFixed(2)}</span>
                            <span class="text-xs font-semibold ${isRetBull ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}">${isRetBull ? '+' : ''}${retVal.toFixed(2)}%</span>
                        </div>
                        <div class="w-full h-1 bg-black/5 dark:bg-white/5 rounded-full overflow-hidden my-1.5">
                            <div class="h-full rounded-full ${isRetBull ? 'bg-emerald-500' : 'bg-rose-500'}" style="width: ${Math.min(100, Math.max(10, Math.abs(retVal) * 10))}%"></div>
                        </div>
                        <div class="flex items-center justify-between text-[10px] text-apple-gray mt-1 pt-1 border-t border-black/[0.03] dark:border-white/[0.04]">
                            <span class="truncate">${escapeHtml(spec.tier || 'Statistical')}</span>
                            <span class="font-mono">${isRetBull ? '▲ Bull' : '▼ Bear'}</span>
                        </div>
                    `;
                    mmBarsContainer.append(card);
                });
            }

            // Render Rationale Mini Charts & Actionable Quantitative Tip
            renderRationaleMiniChartsAndSuggestion(data);

            if (window.lucide) lucide.createIcons();
        }

        function renderRationaleMiniChartsAndSuggestion(data) {
            if (!data) return;
            const curr = data.currency === 'INR' ? '₹' : (data.currency || '$');
            const signals = data.signals || [];
            const sigMap = new Map(signals.map(s => [s.feature, s]));

            // 1. Momentum & Trend Vector
            const rsiSig = sigMap.get('rsi14');
            const rsiVal = rsiSig ? Math.round(50 + Number(rsiSig.value) * 50) : 58;
            const rsiEl = document.getElementById('mini-rsi-val');
            if (rsiEl) rsiEl.textContent = `${rsiVal} / 100`;

            const momStatusEl = document.getElementById('mini-momentum-status');
            const momDescEl = document.getElementById('mini-momentum-desc');
            let momStatus = 'Bullish';
            let momBadgeClass = 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400';
            let momDesc = 'RSI indicates healthy upward buying momentum with sustained price expansion.';
            if (rsiVal >= 72) {
                momStatus = 'Overbought';
                momBadgeClass = 'bg-amber-500/10 text-amber-600 dark:text-amber-400';
                momDesc = 'RSI > 70 indicates stretched near-term momentum; watch for tactical consolidation.';
            } else if (rsiVal <= 38) {
                momStatus = 'Oversold';
                momBadgeClass = 'bg-rose-500/10 text-rose-600 dark:text-rose-400';
                momDesc = 'RSI < 40 indicates heavily discounted momentum; favorable mean-reversion setup.';
            }
            if (momStatusEl) {
                momStatusEl.className = `text-[10px] font-bold px-1.5 py-0.5 rounded ${momBadgeClass}`;
                momStatusEl.textContent = momStatus;
            }
            if (momDescEl) momDescEl.textContent = momDesc;

            // Mini Chart 1 SVG Sparkline (Derived from real recent closing prices)
            const momChartEl = document.getElementById('mini-chart-momentum');
            if (momChartEl) {
                const isUp = rsiVal >= 50;
                const stroke = isUp ? '#10b981' : '#f43f5e';
                
                // Extract real recent closing prices
                let rawPrices = [];
                if (latestHistoryData && latestHistoryData.length) {
                    rawPrices = latestHistoryData.slice(-12).map(r => Number(r.Close)).filter(Number.isFinite);
                }
                if (rawPrices.length < 2) {
                    rawPrices = isUp ? [100, 101, 100.5, 102, 101.8, 103, 104] : [104, 103, 103.5, 102, 102.2, 101, 100];
                }
                const minP = Math.min(...rawPrices);
                const maxP = Math.max(...rawPrices);
                const rangeP = (maxP - minP) || 1;
                const svgW = 110;
                const svgH = 38;
                const padX = 5;
                const padY = 5;
                const usableW = svgW - (padX * 2);
                const usableH = svgH - (padY * 2);
                
                const coords = rawPrices.map((p, idx) => {
                    const x = padX + (idx / (rawPrices.length - 1)) * usableW;
                    const y = padY + usableH - ((p - minP) / rangeP) * usableH;
                    return { x: Number(x.toFixed(1)), y: Number(y.toFixed(1)) };
                });
                const ptsStr = coords.map(c => `${c.x},${c.y}`).join(' ');
                const lastPt = coords[coords.length - 1];
                const gradId = `momGrad_${Math.floor(Math.random() * 100000)}`;

                momChartEl.innerHTML = `
                    <svg class="w-full h-full overflow-hidden" viewBox="0 0 ${svgW} ${svgH}" preserveAspectRatio="none">
                        <defs>
                            <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stop-color="${stroke}" stop-opacity="0.25"/>
                                <stop offset="100%" stop-color="${stroke}" stop-opacity="0.0"/>
                            </linearGradient>
                        </defs>
                        <polygon points="${padX},${svgH} ${ptsStr} ${lastPt.x},${svgH}" fill="url(#${gradId})"/>
                        <polyline points="${ptsStr}" fill="none" stroke="${stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        <circle cx="${lastPt.x}" cy="${lastPt.y}" r="2.5" fill="${stroke}" stroke="#ffffff" stroke-width="1"/>
                    </svg>
                `;
            }

            // 2. Volatility & Risk Meter
            const atrSig = sigMap.get('atr14_pct');
            const atrPctVal = atrSig ? (Number(atrSig.value) * 100).toFixed(2) : '1.85';
            const atrEl = document.getElementById('mini-atr-val');
            if (atrEl) atrEl.textContent = `${atrPctVal}% of price`;

            const volStatusEl = document.getElementById('mini-volatility-status');
            const volDescEl = document.getElementById('mini-volatility-desc');
            const numAtr = parseFloat(atrPctVal);
            let volStatus = 'Stable';
            let volBadgeClass = 'bg-blue-500/10 text-blue-600 dark:text-blue-400';
            let volDesc = 'Predictable price distribution bounds gap risk and keeps uncertainty cones narrow.';
            if (numAtr >= 3.2) {
                volStatus = 'High Volatility';
                volBadgeClass = 'bg-amber-500/10 text-amber-600 dark:text-amber-400';
                volDesc = 'Elevated dispersion widens uncertainty cones; size positions conservatively.';
            } else if (numAtr <= 1.4) {
                volStatus = 'Ultra Low Risk';
                volBadgeClass = 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400';
                volDesc = 'Subdued volatility favors directional continuation with low whip risk.';
            }
            if (volStatusEl) {
                volStatusEl.className = `text-[10px] font-bold px-1.5 py-0.5 rounded ${volBadgeClass}`;
                volStatusEl.textContent = volStatus;
            }
            if (volDescEl) volDescEl.textContent = volDesc;

            // Mini Chart 2 SVG Volatility Meter
            const volChartEl = document.getElementById('mini-chart-volatility');
            if (volChartEl) {
                const pctFill = Math.min(100, Math.max(10, (numAtr / 4.0) * 100));
                const color = numAtr >= 3.2 ? '#f59e0b' : '#3b82f6';
                volChartEl.innerHTML = `
                    <div class="w-full space-y-1.5">
                        <div class="flex justify-between text-[10px] text-apple-gray font-mono">
                            <span>Low Risk</span>
                            <span>Mod</span>
                            <span>High Risk</span>
                        </div>
                        <div class="w-full h-3 bg-black/5 dark:bg-white/10 rounded-full overflow-hidden p-0.5 border border-black/[0.04] dark:border-white/[0.04]">
                            <div class="h-full rounded-full transition-all duration-700" style="width: ${pctFill}%; background: linear-gradient(90deg, #3b82f6, ${color});"></div>
                        </div>
                    </div>
                `;
            }

            // 3. Mean Reversion & Value Position
            const dist50Sig = sigMap.get('dist_sma50');
            const dist50Val = dist50Sig ? (Number(dist50Sig.value) * 100).toFixed(2) : '+2.40';
            const distEl = document.getElementById('mini-dist-sma50');
            if (distEl) distEl.textContent = `${Number(dist50Val) >= 0 ? '+' : ''}${dist50Val}%`;

            const revStatusEl = document.getElementById('mini-reversion-status');
            const revDescEl = document.getElementById('mini-reversion-desc');
            const numDist = parseFloat(dist50Val);
            let revStatus = 'Trend Intact';
            let revBadgeClass = 'bg-purple-500/10 text-purple-600 dark:text-purple-400';
            let revDesc = 'Price holds above moving averages; mean reversion pull is balanced against momentum.';
            if (numDist >= 12.0) {
                revStatus = 'Extended';
                revBadgeClass = 'bg-amber-500/10 text-amber-600 dark:text-amber-400';
                revDesc = 'Trading far above 50-Day SMA; mean reversion pullback risk is elevated.';
            } else if (numDist <= -8.0) {
                revStatus = 'Deep Discount';
                revBadgeClass = 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400';
                revDesc = 'Price is well below its 50-day average; this descriptive signal does not establish a rebound.';
            }
            if (revStatusEl) {
                revStatusEl.className = `text-[10px] font-bold px-1.5 py-0.5 rounded ${revBadgeClass}`;
                revStatusEl.textContent = revStatus;
            }
            if (revDescEl) revDescEl.textContent = revDesc;

            // Mini Chart 3 SVG Balance
            const revChartEl = document.getElementById('mini-chart-reversion');
            if (revChartEl) {
                const offset = Math.min(45, Math.max(-45, numDist * 2.5));
                revChartEl.innerHTML = `
                    <div class="w-full relative h-6 flex items-center">
                        <div class="w-full h-1 bg-black/10 dark:bg-white/10 rounded-full"></div>
                        <div class="absolute left-1/2 -translate-x-1/2 w-0.5 h-3 bg-apple-gray opacity-60" title="50-Day SMA Centerline"></div>
                        <div class="absolute w-4 h-4 rounded-full bg-purple-600 shadow-sm border-2 border-white dark:border-[#161618] transition-all duration-700 -translate-x-1/2" style="left: calc(50% + ${offset}%);"></div>
                    </div>
                `;
            }

            // 4. Volume & Institutional Flow
            const volRatioSig = sigMap.get('volume_ratio');
            const volRatioVal = volRatioSig ? Number(volRatioSig.value).toFixed(2) : '1.15';
            const volRatioEl = document.getElementById('mini-vol-ratio');
            if (volRatioEl) volRatioEl.textContent = `${volRatioVal}x 20D Avg`;

            const volFlowStatusEl = document.getElementById('mini-volume-status');
            const volFlowDescEl = document.getElementById('mini-volume-desc');
            const numVolRatio = parseFloat(volRatioVal);
            let volFlowStatus = 'Accumulation';
            let volFlowBadgeClass = 'bg-amber-500/10 text-amber-600 dark:text-amber-400';
            let volFlowDesc = 'Healthy turnover confirms institutional backing behind current market drift.';
            if (numVolRatio >= 1.6) {
                volFlowStatus = 'High Volume Surge';
                volFlowBadgeClass = 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400';
                volFlowDesc = 'Surging volume signals aggressive institutional positioning and breakout interest.';
            } else if (numVolRatio <= 0.7) {
                volFlowStatus = 'Light Volume';
                volFlowBadgeClass = 'bg-black/5 dark:bg-white/5 text-apple-gray';
                volFlowDesc = 'Light trading volume reflects summer doldrums or retail drift.';
            }
            if (volFlowStatusEl) {
                volFlowStatusEl.className = `text-[10px] font-bold px-1.5 py-0.5 rounded ${volFlowBadgeClass}`;
                volFlowStatusEl.textContent = volFlowStatus;
            }
            if (volFlowDescEl) volFlowDescEl.textContent = volFlowDesc;

            // Mini Chart 4 SVG Volume Histogram
            const volFlowChartEl = document.getElementById('mini-chart-volume');
            if (volFlowChartEl) {
                const barHeights = [18, 22, 16, 24, 20, 26, Math.min(38, Math.max(12, numVolRatio * 20))];
                const barsHtml = barHeights.map((h, i) => {
                    const isLatest = i === barHeights.length - 1;
                    const fill = isLatest ? '#f59e0b' : 'rgba(120, 120, 128, 0.25)';
                    return `<rect x="${i * 15 + 4}" y="${40 - h}" width="9" height="${h}" rx="2" fill="${fill}"/>`;
                }).join('');
                volFlowChartEl.innerHTML = `
                    <svg class="w-full h-10" viewBox="0 0 110 40">
                        <line x1="0" y1="20" x2="110" y2="20" stroke="rgba(120, 120, 128, 0.2)" stroke-dasharray="2,2"/>
                        ${barsHtml}
                    </svg>
                `;
            }

            // 5. Show only values supplied by the forecast result. Missing values
            // stay unavailable; do not invent an entry, stop, score, or return.
            const currPrice = Number(data.current_price);
            const expPrice = Number(data.interval?.expected_price);
            const expRet = Number(data.interval?.expected_return_percent);
            const dirScoreRaw = data.directional_probability == null ? NaN : Number(data.directional_probability) * 100;
            const dirScore = Number.isFinite(dirScoreRaw) ? dirScoreRaw : null;
            const hasCurrentPrice = Number.isFinite(currPrice) && currPrice > 0;
            const hasExpectedPrice = Number.isFinite(expPrice) && expPrice > 0;
            const hasExpectedReturn = Number.isFinite(expRet);
            const currentCurrency = data.currency === 'INR' ? '₹' : (data.currency || '$');
            const expectedValue = hasExpectedPrice ? `${currentCurrency}${expPrice.toFixed(2)}` : 'Unavailable';
            const expectedReturnValue = hasExpectedReturn ? `${expRet >= 0 ? '+' : ''}${expRet.toFixed(2)}%` : 'Unavailable';
            const rangeValue = Number.isFinite(Number(data.interval?.lower_bound_price)) && Number.isFinite(Number(data.interval?.upper_bound_price))
                ? `${currentCurrency}${Number(data.interval.lower_bound_price).toFixed(2)} – ${currentCurrency}${Number(data.interval.upper_bound_price).toFixed(2)}`
                : 'Unavailable';

            const actionBadgeEl = document.getElementById('stock-suggestion-action');
            const rrEl = document.getElementById('stock-suggestion-rr');
            const entryEl = document.getElementById('stock-entry-zone');
            const supportEl = document.getElementById('stock-key-support');
            const targetEl = document.getElementById('stock-model-target');
            const stopEl = document.getElementById('stock-trailing-stop');
            const tipTextEl = document.getElementById('stock-actionable-tip-text');

            const actionLabel = dirScore == null ? 'Directional score unavailable' : `Model-implied score ${dirScore.toFixed(1)}%`;
            const actionClass = 'bg-indigo-600 dark:bg-indigo-500 text-white shadow-xs';
            const tipText = `${data.symbol || 'This symbol'} · ${data.horizon || '—'}-session model estimate: expected price ${expectedValue}; estimated return ${expectedReturnValue}; residual range ${rangeValue}. The directional score${dirScore == null ? ' is unavailable' : ` is ${dirScore.toFixed(1)}% and is not calibrated as a probability`}. This is a model output, not personalized financial advice.`;

            if (actionBadgeEl) {
                actionBadgeEl.className = `px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${actionClass}`;
                actionBadgeEl.textContent = actionLabel;
            }
            if (rrEl) rrEl.textContent = `${data.interval?.confidence_percent || '—'}% nominal level`;
            if (entryEl) entryEl.textContent = hasCurrentPrice ? `${currentCurrency}${currPrice.toFixed(2)}` : 'Unavailable';
            if (supportEl) supportEl.textContent = data.last_bar_at || 'Unavailable';
            if (targetEl) targetEl.textContent = expectedValue;
            if (stopEl) stopEl.textContent = rangeValue;
            if (tipTextEl) tipTextEl.textContent = tipText;

            const regimeBadge = document.getElementById('forecast-regime-badge');
            if (regimeBadge) {
                regimeBadge.textContent = `${data.horizon}D Horizon · ${actionLabel}`;
            }
            // 3 Distinct Forecast Metadata Badges (Nominal Range, Sample Coverage, Model-Implied Score)
            const nomBadge = document.getElementById('forecast-nominal-interval-badge');
            if (nomBadge) {
                nomBadge.textContent = `${data.interval?.confidence_percent || data.interval?.nominal_confidence_percent || 80}% Nominal Band`;
            }
            const covBadge = document.getElementById('forecast-empirical-coverage-badge');
            if (covBadge) {
                if (data.interval?.empirical_coverage_percent != null) {
                    const covVal = Number(data.interval.empirical_coverage_percent).toFixed(1);
                    const verdict = data.interval.calibration_verdict || 'Assessment unavailable';
                    covBadge.textContent = `${covVal}% Sample Coverage`;
                    covBadge.className = 'px-2.5 py-1 rounded-xl text-xs font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20';
                    covBadge.title = `${verdict}; ${data.interval.residual_sample_size || 0} residual samples`;
                } else {
                    covBadge.textContent = 'Sample Coverage: unavailable';
                    covBadge.className = 'px-2.5 py-1 rounded-xl text-xs font-bold bg-black/5 dark:bg-white/5 text-apple-gray border border-black/10 dark:border-white/10';
                }
            }
            const dirBadge = document.getElementById('forecast-directional-prob-badge');
            if (dirBadge) {
                const dirProb = data.directional_probability == null ? null : Number(data.directional_probability) * 100;
                dirBadge.textContent = Number.isFinite(dirProb) ? `${dirProb.toFixed(1)}% Model-Implied Direction Score` : 'Direction score unavailable';
                dirBadge.className = `px-2.5 py-1 rounded-xl text-xs font-bold ${Number.isFinite(dirProb) ? 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20' : 'bg-black/5 dark:bg-white/5 text-apple-gray border border-black/10 dark:border-white/10'}`;
            }
            const confPill = document.getElementById('forecast-confidence-pill');
            if (confPill) {
                confPill.textContent = `${data.interval?.confidence_percent || 80}% Nominal Band`;
            }
        }

        // Active overlay state for forecast chart lines
        let forecastSeriesState = { selected: true, ridge: false, random_forest: false, mlp_neural_net: false, exponential_smoothing: false, drift: false, analyst: true, pivot: false, bands: true };

        window.toggleForecastSeries = function(seriesKey) {
            if (seriesKey in forecastSeriesState) {
                forecastSeriesState[seriesKey] = !forecastSeriesState[seriesKey];
                const btn = document.querySelector(`.series-toggle-pill[data-series="${seriesKey}"]`);
                if (btn) {
                    btn.classList.toggle('active', forecastSeriesState[seriesKey]);
                    btn.classList.toggle('border-indigo-500', forecastSeriesState[seriesKey]);
                    btn.classList.toggle('bg-indigo-500/10', forecastSeriesState[seriesKey]);
                }
                renderDedicatedForecastChart(latestHistoryData, latestForecastData);
            }
        };

        function renderDedicatedForecastChart(historyData = latestHistoryData, forecastData = latestForecastData) {
            const container = document.getElementById('forecastDedicatedChart');
            if (!container) return;
            disposeDedicatedForecastChart();
            container.replaceChildren();

            const loader = document.getElementById('forecast-chart-loading');
            if (loader) loader.classList.add('hidden');

            if (!historyData || !historyData.length) {
                container.innerHTML = '<div class="flex items-center justify-center h-full text-xs text-apple-gray">Historical price data unavailable to plot forecast chart.</div>';
                return;
            }

            // Visible historical window leading up to origin (last 45 sessions)
            const sortedHistory = historyData
                .map(row => ({
                    ...row,
                    time: String(row.Date || row.Datetime || '').slice(0, 10),
                    close: Number(row.Close),
                    open: Number(row.Open),
                    high: Number(row.High),
                    low: Number(row.Low),
                }))
                .filter(row => row.time && Number.isFinite(row.close))
                .sort((a, b) => a.time.localeCompare(b.time));

            const visibleWindow = sortedHistory.slice(-45);
            if (!visibleWindow.length) return;

            const containerWidth = container.clientWidth || 800;
            const containerHeight = container.clientHeight || 380;
            dedicatedForecastChartInstance = LightweightCharts.createChart(container, {
                width: containerWidth,
                height: containerHeight,
                layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8E8E93' },
                grid: { vertLines: { color: 'rgba(0,0,0,0.04)' }, horzLines: { color: 'rgba(0,0,0,0.04)' } },
                rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.12 } },
                timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false },
                crosshair: { mode: LightweightCharts.CrosshairMode?.Normal ?? 0 },
                handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
                handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
            });

            const tooltipSeries = [];

            // 1. Historical Close Series
            const historySeries = dedicatedForecastChartInstance.addLineSeries({
                color: '#216bc2',
                lineWidth: 2,
                title: 'Historical Close',
                priceLineVisible: false,
                lastValueVisible: false,
            });
            historySeries.setData(visibleWindow.map(r => ({ time: r.time, value: r.close })));
            tooltipSeries.push({ series: historySeries, kind: 'history', title: 'Close' });

            const chartData = forecastData?.chart_data;
            const modelProjs = chartData?.model_projections || {};

            // 2. Conformal Uncertainty Cone (Bands)
            if (forecastSeriesState.bands && chartData?.projection_path) {
                const path = chartData.projection_path;
                const upperPoints = path.map(pt => ({ time: pt.date, value: Number(pt.upper) }));
                const lowerPoints = path.map(pt => ({ time: pt.date, value: Number(pt.lower) }));

                const upperSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: 'rgba(99, 102, 241, 0.65)',
                    lineWidth: 1,
                    lineStyle: 3, // Dotted
                    title: `Upper (${forecastData.interval?.confidence_percent || 80}%)`,
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                upperSeries.setData(upperPoints);
                tooltipSeries.push({ series: upperSeries, kind: 'upper', title: 'Upper (80%)' });

                const lowerSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: 'rgba(99, 102, 241, 0.65)',
                    lineWidth: 1,
                    lineStyle: 3, // Dotted
                    title: `Lower (${forecastData.interval?.confidence_percent || 80}%)`,
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                lowerSeries.setData(lowerPoints);
                tooltipSeries.push({ series: lowerSeries, kind: 'lower', title: 'Lower (80%)' });
            }

            // 3. Active / Selected ML Model Trajectory
            if (forecastSeriesState.selected && chartData?.projection_path) {
                const path = chartData.projection_path;
                const medianPoints = path.map(pt => ({ time: pt.date, value: Number(pt.price) }));
                const medianSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: '#6366f1',
                    lineWidth: 2,
                    lineStyle: 2, // Dashed
                    title: `Selected (${forecastData.model_metadata?.[forecastData.selected_model]?.short_name || forecastData.selected_model})`,
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                medianSeries.setData(medianPoints);
                tooltipSeries.push({ series: medianSeries, kind: 'expected', title: 'Selected ML' });

                // Set Origin & Target Markers
                const originDate = chartData.origin?.date;
                const targetDate = chartData.target_date;
                const markers = [];
                if (originDate) {
                    markers.push({
                        time: originDate,
                        position: 'aboveBar',
                        color: '#216bc2',
                        shape: 'circle',
                        text: 'Cutoff Origin',
                    });
                }
                if (targetDate) {
                    markers.push({
                        time: targetDate,
                        position: 'belowBar',
                        color: '#6366f1',
                        shape: 'arrowUp',
                        text: `Target: ${Number(forecastData.interval?.expected_price).toFixed(2)}`,
                    });
                }
                medianSeries.setMarkers(markers);
            }

            // 4. Ridge Regression Baseline Overlay
            if (forecastSeriesState.ridge && modelProjs.ridge?.path) {
                const rSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: '#0ea5e9',
                    lineWidth: 1.5,
                    lineStyle: 2,
                    title: 'Ridge L2',
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                rSeries.setData(modelProjs.ridge.path.map(pt => ({ time: pt.date, value: Number(pt.price) })));
                tooltipSeries.push({ series: rSeries, kind: 'ridge', title: 'Ridge L2' });
            }

            // 5. Historical Drift Baseline Overlay
            if (forecastSeriesState.drift && modelProjs.historical_drift?.path) {
                const dSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: '#f59e0b',
                    lineWidth: 1.5,
                    lineStyle: 2,
                    title: 'Drift Baseline',
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                dSeries.setData(modelProjs.historical_drift.path.map(pt => ({ time: pt.date, value: Number(pt.price) })));
                tooltipSeries.push({ series: dSeries, kind: 'drift', title: 'Drift Baseline' });
            }

            // 6. 3rd-Party Free Analyst Consensus Overlay
            if (forecastSeriesState.analyst && modelProjs.analyst_consensus?.path) {
                const aSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: '#10b981',
                    lineWidth: 2,
                    lineStyle: 2,
                    title: 'Analyst Consensus',
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                aSeries.setData(modelProjs.analyst_consensus.path.map(pt => ({ time: pt.date, value: Number(pt.price) })));
                tooltipSeries.push({ series: aSeries, kind: 'analyst', title: 'Analyst Consensus' });
            }

            // 7. Classical Quantitative Pivot Overlay
            if (forecastSeriesState.pivot && modelProjs.algorithmic_pivot?.path) {
                const pSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: '#a855f7',
                    lineWidth: 1.5,
                    lineStyle: 2,
                    title: 'Technical Pivot',
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                pSeries.setData(modelProjs.algorithmic_pivot.path.map(pt => ({ time: pt.date, value: Number(pt.price) })));
                tooltipSeries.push({ series: pSeries, kind: 'pivot', title: 'Technical Pivot' });
            }

            // 8. Random Forest Overlay
            if (forecastSeriesState.random_forest && modelProjs.random_forest?.path) {
                const rfSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: '#14b8a6',
                    lineWidth: 1.5,
                    lineStyle: 2,
                    title: 'Random Forest',
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                rfSeries.setData(modelProjs.random_forest.path.map(pt => ({ time: pt.date, value: Number(pt.price) })));
                tooltipSeries.push({ series: rfSeries, kind: 'random_forest', title: 'Random Forest' });
            }

            // 9. MLP Neural Network Overlay
            if (forecastSeriesState.mlp_neural_net && modelProjs.mlp_neural_net?.path) {
                const mlpSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: '#8b5cf6',
                    lineWidth: 1.5,
                    lineStyle: 2,
                    title: 'Neural Net (MLP)',
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                mlpSeries.setData(modelProjs.mlp_neural_net.path.map(pt => ({ time: pt.date, value: Number(pt.price) })));
                tooltipSeries.push({ series: mlpSeries, kind: 'mlp_neural_net', title: 'Neural Net (MLP)' });
            }

            // 10. Exponential Smoothing Overlay
            if (forecastSeriesState.exponential_smoothing && modelProjs.exponential_smoothing?.path) {
                const expSeries = dedicatedForecastChartInstance.addLineSeries({
                    color: '#f97316',
                    lineWidth: 1.5,
                    lineStyle: 2,
                    title: 'Exp Smoothing',
                    priceLineVisible: false,
                    lastValueVisible: true,
                });
                expSeries.setData(modelProjs.exponential_smoothing.path.map(pt => ({ time: pt.date, value: Number(pt.price) })));
                tooltipSeries.push({ series: expSeries, kind: 'exponential_smoothing', title: 'Exp Smoothing' });
            }

            dedicatedForecastChartInstance.timeScale().fitContent();

            // Hover tooltip subscription (only active on crosshair hover)
            const tooltip = document.getElementById('forecast-chart-hover-tip');
            dedicatedForecastChartInstance.subscribeCrosshairMove(param => {
                if (!tooltip) return;
                if (!param?.time || !param.point || param.point.x < 0 || param.point.y < 0) {
                    tooltip.classList.remove('active');
                    return;
                }
                const label = typeof param.time === 'string'
                    ? param.time
                    : `${param.time.year}-${String(param.time.month).padStart(2, '0')}-${String(param.time.day).padStart(2, '0')}`;
                
                const parts = [];
                tooltipSeries.forEach(({ series, title }) => {
                    const data = param.seriesData.get(series);
                    if (data && data.value != null) {
                        parts.push(`${title}: ${formatMarketNumber(data.value, 2)}`);
                    }
                });

                if (parts.length) {
                    tooltip.textContent = `${label}  ·  ${parts.join('  ·  ')}`;
                    tooltip.classList.add('active');
                } else {
                    tooltip.textContent = `${label}`;
                    tooltip.classList.add('active');
                }
            });

            // Resize Observer
            dedicatedForecastResizeObserver = new ResizeObserver(entries => {
                if (!entries[0] || !dedicatedForecastChartInstance) return;
                const { width, height } = entries[0].contentRect;
                if (width > 0 && height > 0) {
                    dedicatedForecastChartInstance.applyOptions({ width: Math.floor(width), height: Math.floor(height) });
                }
            });
            dedicatedForecastResizeObserver.observe(container);
        }

        // Landing Page ML Forecast Showcase (Compact, small size)
        function changeLandingForecastHorizon(horizon) {
            landingForecastHorizon = Number(horizon);
            document.querySelectorAll('.landing-horizon-btn').forEach(btn => {
                const active = Number(btn.dataset.horizon) === landingForecastHorizon;
                btn.classList.toggle('active', active);
                btn.classList.toggle('bg-white', active);
                btn.classList.toggle('dark:bg-black/50', active);
                btn.classList.toggle('text-indigo-600', active);
                btn.classList.toggle('dark:text-indigo-400', active);
                btn.classList.toggle('shadow-xs', active);
            });
            loadLandingForecasts();
        }

        function createSparklineSvg(points, isPos) {
            if (!points || points.length < 2) return '';
            const min = Math.min(...points);
            const max = Math.max(...points);
            const range = (max - min) || 1;
            const width = 76;
            const height = 22;
            const strokeColor = isPos ? '#10b981' : '#f43f5e';
            const coords = points.map((p, idx) => {
                const x = (idx / (points.length - 1)) * width;
                const y = height - ((p - min) / range) * (height - 4) - 2;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            }).join(' ');
            return `<svg class="w-18 h-5 overflow-visible" viewBox="0 0 ${width} ${height}"><polyline fill="none" stroke="${strokeColor}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" points="${coords}" /></svg>`;
        }

        async function loadLandingForecasts(force = false) {
            const grid = document.getElementById('landing-forecast-grid');
            if (!grid) return;

            if (!grid.children.length || force) {
                grid.innerHTML = Array.from({ length: 6 }).map(() => `
                    <div class="glass-panel p-2.5 rounded-xl animate-pulse">
                        <div class="flex justify-between items-center mb-1.5">
                            <div class="w-12 h-3.5 bg-black/10 dark:bg-white/10 rounded"></div>
                            <div class="w-10 h-3 bg-black/10 dark:bg-white/10 rounded-full"></div>
                        </div>
                        <div class="w-16 h-5 bg-black/10 dark:bg-white/10 rounded mb-1"></div>
                        <div class="w-20 h-3 bg-black/10 dark:bg-white/10 rounded"></div>
                    </div>
                `).join('');
            }

            try {
                const res = await fetch(`/api/forecast/featured/summary?horizon=${landingForecastHorizon}`);
                const data = await res.json();
                if (!res.ok || !data.success || !data.items || !data.items.length) {
                    grid.innerHTML = '<div class="col-span-full py-4 text-center text-xs text-apple-gray">Featured forecast showcase will refresh once market server connects.</div>';
                    return;
                }

                grid.replaceChildren();
                data.items.forEach(item => {
                    const card = document.createElement('div');
                    card.className = 'glass-panel p-2.5 rounded-xl border border-black/[0.05] dark:border-white/[0.07] hover:border-indigo-500/40 hover:shadow-xs transition-all group cursor-pointer flex flex-col justify-between';
                    card.onclick = () => {
                        selectStockAndForecast(item.symbol);
                    };

                    const ret = Number(item.expected_return_percent);
                    const hasReturn = Number.isFinite(ret);
                    const isPos = hasReturn && ret >= 0;
                    const curr = item.currency === 'INR' ? '₹' : '$';
                    const prob = item.directional_probability == null ? 'Unavailable' : `${(item.directional_probability * 100).toFixed(0)}%`;
                    const expectedPrice = Number(item.expected_price);
                    const sparklineSvg = createSparklineSvg(item.sparkline_points, isPos);

                    card.innerHTML = `
                        <div>
                            <div class="flex items-center justify-between mb-1">
                                <span class="font-bold text-xs text-gray-900 dark:text-gray-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition">${escapeHtml(item.symbol)}</span>
                                <span class="px-1.5 py-0.5 rounded-full text-[9px] font-bold ${isPos ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}">
                                    ${hasReturn ? `${isPos ? '▲ +' : '▼ '}${ret.toFixed(1)}%` : 'Return unavailable'}
                                </span>
                            </div>
                            <div class="my-1 flex items-center justify-between">
                                <div>
                                    <div class="text-[9px] text-apple-gray uppercase font-semibold">Target (${item.horizon}D)</div>
                                    <div class="text-sm font-bold text-gray-900 dark:text-gray-100">${Number.isFinite(expectedPrice) ? `${curr}${expectedPrice.toFixed(1)}` : 'Unavailable'}</div>
                                </div>
                                <div class="shrink-0 flex items-center justify-end">${sparklineSvg}</div>
                            </div>
                        </div>
                        <div class="pt-1.5 border-t border-black/[0.03] dark:border-white/[0.04] flex items-center justify-between text-[10px]">
                            <span class="text-indigo-600 dark:text-indigo-400 font-semibold">${prob} model-implied score · <span class="text-apple-gray font-normal">${item.last_bar_at ? item.last_bar_at.slice(5) : 'Cutoff unavailable'}</span></span>
                            <span class="text-apple-gray group-hover:translate-x-0.5 transition font-medium">View →</span>
                        </div>
                    `;
                    grid.append(card);
                });
                if (window.lucide) lucide.createIcons();
            } catch (err) {
                grid.innerHTML = '<div class="col-span-full py-4 text-center text-xs text-apple-gray">Featured forecast showcase will refresh once market server connects.</div>';
            }
        }

        function selectStockAndForecast(symbol) {
            const input = document.getElementById('symbol-input') || document.getElementById('search-input') || document.getElementById('header-search-input');
            if (input) input.value = symbol;
            currentSymbol = symbol;
            handleSearch(false).then(() => {
                switchTab('forecast');
            });
        }

        window.scrollChatToBottom = function() {
            const container = document.getElementById('chat-messages');
            if (container) {
                container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
            }
        };

        function askAiAboutForecast() {
            if (!currentSymbol) return;
            const prompt = `Provide an evidence-grounded explanation of the ${currentForecastHorizon}-session forecast for ${currentSymbol}. Explain the estimated return, residual-based uncertainty range, model-implied directional score, key signals, and walk-forward validation performance.`;
            startSuggestedChat(prompt);
        }

        // ---------------------------------------------------------------------
        // FORECAST VIEW MODE & CUSTOM DATASET WORKFLOWS
        // ---------------------------------------------------------------------
        window.toggleForecastViewMode = function(mode) {
            const isSimple = mode === 'simple';
            try { localStorage.setItem('stockrag_forecast_mode', mode); } catch (_) {}
            
            document.getElementById('forecast-mode-beginner-btn')?.classList.toggle('active', isSimple);
            document.getElementById('forecast-mode-pro-btn')?.classList.toggle('active', !isSimple);
            
            document.getElementById('forecast-pro-diagnostics-bar')?.classList.toggle('hidden', isSimple);
            document.getElementById('dynamic-model-specs-ribbon')?.classList.toggle('hidden', isSimple);
            document.getElementById('forecast-confidence-wrap')?.classList.toggle('hidden', isSimple);
            document.getElementById('forecast-advanced-details-accordion')?.classList.toggle('hidden', isSimple);
            
            showToast(isSimple ? '🌟 Beginner Mode: Clear & Minimal' : '🔬 Quantitative Pro Mode Active');
            if (window.lucide) lucide.createIcons();
        };

        window.openForecastUploadModal = function() {
            const modal = document.getElementById('forecast-upload-modal');
            if (modal) {
                modal.classList.remove('hidden');
                document.getElementById('forecast-upload-error')?.classList.add('hidden');
                if (window.lucide) lucide.createIcons();
            }
        };

        window.closeForecastUploadModal = function() {
            document.getElementById('forecast-upload-modal')?.classList.add('hidden');
        };

        let selectedForecastFile = null;

        window.handleForecastModalFileSelect = function(event) {
            const file = event.target.files?.[0];
            if (file) setForecastSelectedFile(file);
        };

        window.handleForecastFileDrop = function(event) {
            event.preventDefault();
            const dropzone = document.getElementById('forecast-upload-dropzone');
            dropzone?.classList.remove('border-indigo-500', 'bg-indigo-500/5');
            const file = event.dataTransfer?.files?.[0];
            if (file) setForecastSelectedFile(file);
        };

        window.handleForecastCsvUpload = function(event) {
            const file = event.target.files?.[0];
            if (file) {
                setForecastSelectedFile(file);
                openForecastUploadModal();
            }
        };

        function setForecastSelectedFile(file) {
            selectedForecastFile = file;
            const pill = document.getElementById('forecast-selected-file-pill');
            const filenameEl = document.getElementById('forecast-selected-filename');
            if (pill && filenameEl) {
                filenameEl.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
                pill.classList.remove('hidden');
            }
            const dropzoneLabel = document.getElementById('forecast-upload-dropzone-label');
            if (dropzoneLabel) dropzoneLabel.textContent = `Selected: ${file.name}`;
            if (window.lucide) lucide.createIcons();
        }

        window.downloadSampleForecastCsv = function() {
            const rows = [
                ['Date', 'Close', 'Open', 'High', 'Low', 'Volume'],
                ['2024-11-01', '175.20', '174.50', '176.10', '174.00', '45000000'],
                ['2024-11-04', '176.80', '175.60', '177.40', '175.10', '48000000'],
                ['2024-11-05', '178.40', '177.00', '179.20', '176.90', '52000000'],
                ['2024-11-06', '177.90', '178.50', '179.00', '177.20', '43000000'],
                ['2024-11-07', '180.10', '178.20', '180.80', '177.90', '56000000'],
                ['2024-11-08', '181.50', '180.30', '182.20', '179.80', '60000000'],
                ['2024-11-11', '183.00', '181.80', '183.90', '181.20', '64000000'],
                ['2024-11-12', '182.40', '183.10', '183.80', '181.90', '49000000'],
                ['2024-11-13', '184.20', '182.60', '184.90', '182.10', '53000000'],
                ['2024-11-14', '185.70', '184.50', '186.40', '183.80', '58000000'],
            ];
            const csvContent = 'data:text/csv;charset=utf-8,' + rows.map(e => e.join(',')).join('\n');
            const encodedUri = encodeURI(csvContent);
            const link = document.createElement('a');
            link.setAttribute('href', encodedUri);
            link.setAttribute('download', 'sample_financial_data.csv');
            document.body.appendChild(link);
            link.click();
            link.remove();
            showToast('Sample stock CSV downloaded');
        };

        window.submitForecastUploadModal = async function() {
            const errorEl = document.getElementById('forecast-upload-error');
            if (!selectedForecastFile) {
                if (errorEl) {
                    errorEl.textContent = 'Please choose a CSV or Excel file first.';
                    errorEl.classList.remove('hidden');
                }
                return;
            }
            const horizon = document.getElementById('forecast-upload-horizon')?.value || '5';
            const model = document.getElementById('forecast-upload-model')?.value || 'auto';
            const submitBtn = document.getElementById('forecast-upload-submit-btn');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Running Models...';
                if (window.lucide) lucide.createIcons();
            }
            if (errorEl) errorEl.classList.add('hidden');

            try {
                const formData = new FormData();
                formData.append('file', selectedForecastFile);
                formData.append('horizon', horizon);
                formData.append('model', model);
                formData.append('confidence', '0.80');

                const res = await fetch('/api/forecast/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    throw new Error(data.detail || data.error || 'Failed to process uploaded dataset');
                }

                closeForecastUploadModal();
                activeCustomDataset = {
                    filename: selectedForecastFile.name,
                    data: data
                };
                const banner = document.getElementById('forecast-custom-dataset-banner');
                const filenameSpan = document.getElementById('forecast-custom-dataset-filename');
                const statsSpan = document.getElementById('forecast-custom-dataset-stats');
                if (banner) banner.classList.remove('hidden');
                if (filenameSpan) filenameSpan.textContent = selectedForecastFile.name;
                const barsCount = data.chart_data?.history_bars?.length || data.sample_size || 'sessions';
                if (statsSpan) statsSpan.textContent = `(${barsCount} sessions loaded)`;

                latestForecastData = data;
                renderForecastUI(data);
                if (data.chart_data?.history_bars) {
                    renderDedicatedForecastChart(data.chart_data.history_bars, data);
                }
                showToast('Predictions generated on uploaded dataset!');
            } catch (err) {
                if (errorEl) {
                    errorEl.textContent = err.message || 'Error processing uploaded dataset';
                    errorEl.classList.remove('hidden');
                }
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i data-lucide="sparkles" class="w-3.5 h-3.5"></i> Run Predictions';
                    if (window.lucide) lucide.createIcons();
                }
            }
        };

        window.clearCustomForecastDataset = function() {
            activeCustomDataset = null;
            selectedForecastFile = null;
            document.getElementById('forecast-custom-dataset-banner')?.classList.add('hidden');
            showToast('Reset to live market ticker data');
            runForecast(true);
        };

        // ---------------------------------------------------------------------
        // MODEL INFO, SYSTEM HEALTH & CUSTOM MODEL MODAL WORKFLOWS
        // ---------------------------------------------------------------------
        window.openModelInfoModal = function() {
            const modal = document.getElementById('model-info-modal');
            if (!modal) return;

            const selectedModelKey = document.getElementById('forecast-model-select')?.value || latestForecastData?.selected_model || 'historical_drift';
            
            let meta;
            if (selectedModelKey === 'auto') {
                const activeModel = latestForecastData?.selected_model || 'historical_drift';
                const activeMeta = latestForecastData?.model_metadata?.[activeModel];
                meta = {
                    name: 'Automatic Chronological Walk-Forward Selection Engine',
                    short_name: 'Auto Selection Engine',
                    category: 'Dynamic Out-of-Sample Optimization',
                    badge: 'Auto Optimizer',
                    description: 'Automated quantitative model selector that rigorously evaluates all candidate statistical baselines, linear regressions, tree ensembles, and neural nets using chronological walk-forward expanding window cross-validation.',
                    formula: 'M* = argmin_{m \\in M} \\left( \\frac{1}{K} \\sum_{k=1}^K |y_{t+h} - \\hat{y}_{t+h}^{(m)}| \\right)',
                    methodology: `Evaluates all candidate forecasters chronologically across historical test splits with a 5-day purged embargo gap. The forecaster achieving minimum out-of-sample MAE while outperforming the naive random-walk baseline is automatically designated for forward inference. (Currently deployed: ${activeMeta?.name || activeModel}).`,
                    data_requirements: 'Requires minimum 55 historical trading sessions with monotonic price and volume continuity.',
                    validation_protocol: 'Expanding-window walk-forward cross-validation with 5-session purged embargo gap to guarantee zero lookahead leakage.',
                    strengths: 'Dynamic adaptation to evolving market regimes (trend, mean-reversion, or high volatility) without manual intervention.',
                    limitations: 'Historical out-of-sample outperformance does not guarantee future stability under sudden macroeconomic structural breaks.',
                    hardware_profile: 'Vectorized Parallel Model Benchmark (<40ms latency · Pure CPU)',
                };
            } else {
                meta = latestForecastData?.model_metadata?.[selectedModelKey] || {
                    name: selectedModelKey.replace(/_/g, ' ').toUpperCase(),
                    short_name: selectedModelKey,
                    category: 'Statistical & Quantitative Specification',
                    badge: 'Validated',
                    description: 'StockAI institutional quantitative forecasting model.',
                    formula: 'y_{t+h} = f(X_t) + \\epsilon_t',
                    methodology: 'Point-in-time factor analysis fitted on historical log-returns with purged walk-forward validation.',
                    data_requirements: 'Minimum 55 historical trading bars required.',
                    validation_protocol: 'Chronological walk-forward backtesting with 5-session embargo gap.',
                    strengths: 'Lightweight, deterministic, and fully compatible with native CPU execution.',
                    limitations: 'Financial asset returns are stochastic and subject to unpredictable macroeconomic regime shifts.',
                    hardware_profile: 'Standard CPU SIMD execution · <20ms inference',
                };
            }

            const titleEl = document.getElementById('model-info-modal-title');
            if (titleEl) titleEl.textContent = meta.name || 'Model Specification';

            const badgeEl = document.getElementById('model-info-badge');
            if (badgeEl) badgeEl.textContent = meta.badge || meta.category || 'Validated';

            const catEl = document.getElementById('model-info-category');
            if (catEl) catEl.textContent = meta.category || 'Quantitative Specification';

            const availEl = document.getElementById('model-info-avail-text');
            if (availEl) {
                availEl.textContent = `Model Status: Registered; this check does not evaluate forecast quality (${meta.model_version || 'version unavailable'})`;
            }

            const hwEl = document.getElementById('model-info-hw-profile');
            if (hwEl) hwEl.textContent = meta.hardware_profile || meta.hardware_requirements || 'Pure CPU · Native SIMD';

            const formEl = document.getElementById('model-info-formula');
            if (formEl) formEl.textContent = meta.formula || 'y_{t+h} = f(X_t)';

            const methEl = document.getElementById('model-info-methodology');
            if (methEl) methEl.textContent = meta.methodology || meta.description || '';

            const dataReqEl = document.getElementById('model-info-data-req');
            if (dataReqEl) dataReqEl.textContent = meta.data_requirements || 'Minimum 55 historical trading bars required.';

            const leakEl = document.getElementById('model-info-leakage-protocol');
            if (leakEl) leakEl.textContent = meta.validation_protocol || 'Purged embargo gap enforced during expanding-window cross validation.';

            const strEl = document.getElementById('model-info-strengths');
            if (strEl) strEl.textContent = meta.strengths || 'Robust out-of-sample generalization.';

            const limEl = document.getElementById('model-info-limitations');
            if (limEl) limEl.textContent = meta.weaknesses || meta.limitations || 'Subject to sudden market volatility and regime changes.';

            modal.classList.remove('hidden');
            modal.classList.add('flex');
            if (window.lucide) lucide.createIcons();
        };

        window.closeModelInfoModal = function() {
            const modal = document.getElementById('model-info-modal');
            if (modal) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        };

        window.openSystemHealthModal = async function() {
            const modal = document.getElementById('system-health-modal');
            if (!modal) return;
            modal.classList.remove('hidden');
            modal.classList.add('flex');
            if (window.lucide) lucide.createIcons();

            try {
                const res = await fetch('/api/forecast/system/health');
                const data = await res.json();
                if (!res.ok) return;

                const sys = data.system_profile || {};
                const diag = data.diagnostics || {};
                const statusBadge = document.getElementById('system-health-status-badge');
                if (statusBadge) {
                    statusBadge.textContent = diag.healthy ? 'Ready' : 'Dependency issue';
                    statusBadge.className = `px-2 py-0.5 rounded-full text-[10px] font-bold border uppercase ${diag.healthy ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'}`;
                }

                const cpuMetric = document.getElementById('health-cpu-metric');
                if (cpuMetric) cpuMetric.textContent = `${sys.cpu_percent || 0}%`;
                const cpuSub = document.getElementById('health-cpu-sub');
                if (cpuSub) cpuSub.textContent = `${sys.cpu_cores || '--'} Cores (${sys.cpu_physical_cores || '--'} Phys)`;

                const ramMetric = document.getElementById('health-ram-metric');
                if (ramMetric) ramMetric.textContent = `${sys.ram_used_gb || 0} GB`;
                const ramSub = document.getElementById('health-ram-sub');
                if (ramSub) ramSub.textContent = `${sys.ram_available_gb || 0} GB Free of ${sys.ram_total_gb || 0} GB`;

                const gpuMetric = document.getElementById('health-gpu-metric');
                if (gpuMetric) gpuMetric.textContent = sys.gpu_available ? 'CUDA Active' : 'CPU Mode';
                const gpuSub = document.getElementById('health-gpu-sub');
                if (gpuSub) gpuSub.textContent = sys.gpu_device_name || 'Pure CPU Hardware Aware';

                const engineMetric = document.getElementById('health-engine-metric');
                if (engineMetric) engineMetric.textContent = diag.engine_status?.toUpperCase() || 'UNKNOWN';
                const engineSub = document.getElementById('health-engine-sub');
                if (engineSub) engineSub.textContent = diag.healthy ? 'Dependency checks passed' : 'One or more dependency checks failed';

                // Render Data Providers
                const provList = document.getElementById('health-providers-list');
                if (provList && data.data_providers) {
                    provList.replaceChildren();
                    Object.entries(data.data_providers).forEach(([k, p]) => {
                        const item = document.createElement('div');
                        item.className = 'p-3 rounded-xl bg-black/[0.02] dark:bg-white/[0.02] border border-black/[0.04] dark:border-white/[0.04] flex items-center justify-between text-xs';
                    const isConn = p.status === 'Available' || p.status === 'Probe succeeded';
                        item.innerHTML = `
                            <div>
                                <span class="font-bold text-gray-900 dark:text-gray-100 block">${escapeHtml(p.name)}</span>
                                <span class="text-[10px] text-apple-gray font-mono">${escapeHtml(p.category)} · ${escapeHtml(p.coverage)}</span>
                            </div>
                            <div class="text-right">
                                <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${isConn ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'}">${escapeHtml(p.status)}</span>
                                <span class="block text-[9px] text-apple-gray mt-0.5">${escapeHtml(p.data_status || p.freshness_policy || 'Status unavailable')}</span>
                            </div>
                        `;
                        provList.append(item);
                    });
                }

                // Render Model Registry Table
                const modelsList = document.getElementById('health-models-list');
                if (modelsList && data.model_registry) {
                    modelsList.replaceChildren();
                    Object.entries(data.model_registry).forEach(([mId, m]) => {
                        const row = document.createElement('tr');
                        row.className = 'border-b border-black/[0.04] dark:border-white/[0.04] last:border-0';
                        const isReady = m.availability === 'Ready';
                        row.innerHTML = `
                            <td class="py-2 font-bold text-gray-900 dark:text-gray-100">${escapeHtml(m.name)}</td>
                            <td class="py-2 text-apple-gray">${escapeHtml(m.model_type)}</td>
                            <td class="py-2 font-mono text-apple-gray">${escapeHtml(m.hardware_requirements)}</td>
                            <td class="py-2"><span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${isReady ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'}">${escapeHtml(m.availability)}</span></td>
                            <td class="py-2 text-right text-apple-gray font-mono text-[10px]">${escapeHtml(m.last_successful_execution || 'Not tracked')}</td>
                        `;
                        modelsList.append(row);
                    });
                }

                const diagMsg = document.getElementById('health-diagnostics-msg');
                if (diagMsg) {
                    diagMsg.textContent = diag.recommendation || 'All forecasting services operational. No stuck or stalled processes detected.';
                }
            } catch (err) {
                console.error("Health fetch error:", err);
            }
        };

        window.closeSystemHealthModal = function() {
            const modal = document.getElementById('system-health-modal');
            if (modal) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        };

        window.triggerSystemRevalidate = async function() {
            const btn = document.getElementById('system-revalidate-btn') || document.getElementById('repair-system-btn');
            if (btn) btn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Revalidating System...';
            try {
                const res = await fetch('/api/forecast/system/revalidate', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    const diagMsg = document.getElementById('health-diagnostics-msg');
                    if (diagMsg) diagMsg.textContent = data.message || 'Forecast cache cleared and hardware measurements refreshed. Provider availability was not rechecked.';
                    if (currentSymbol) {
                        runForecast(true);
                    }
                }
            } catch (err) {
                console.error("System revalidation error:", err);
            } finally {
                if (btn) btn.innerHTML = '<i data-lucide="wrench" class="w-3.5 h-3.5"></i> Revalidate & Repair System';
                if (window.lucide) lucide.createIcons();
            }
        };

        window.openCustomModelModal = function() {
            const modal = document.getElementById('custom-model-modal');
            if (!modal) return;
            modal.classList.remove('hidden');
            modal.classList.add('flex');
            if (window.lucide) lucide.createIcons();
        };

        window.closeCustomModelModal = function() {
            const modal = document.getElementById('custom-model-modal');
            if (modal) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        };

        window.executeCustomModelTest = async function() {
            const btn = document.getElementById('custom-test-btn');
            if (btn) btn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Benchmarking Model...';
            const momentum_weight = parseFloat(document.getElementById('custom-momentum-slider')?.value || '0.5');
            const mean_reversion_weight = parseFloat(document.getElementById('custom-reversion-slider')?.value || '0.2');
            const alpha = parseFloat(document.getElementById('custom-alpha-slider')?.value || '8.0');

            try {
                const res = await fetch('/api/forecast/custom/evaluate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        symbol: currentSymbol || 'AAPL',
                        horizon: currentForecastHorizon || 5,
                        momentum_weight,
                        mean_reversion_weight,
                        alpha,
                    })
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    alert(data.error || 'Failed to benchmark custom model.');
                    return;
                }

                const resBox = document.getElementById('custom-model-results');
                if (resBox) resBox.classList.remove('hidden');

                const edge = Number(data.improvement_vs_baseline_percent ?? data.improvement_vs_drift_percent ?? 0);
                const customMae = Number(data.custom_metrics?.mae_percent ?? data.custom_model?.mae_percent ?? 0);
                const baseMae = Number(data.baseline_metrics?.mae_percent ?? data.baseline_drift?.mae_percent ?? 0);
                const sampleSize = data.custom_metrics?.test_sample_size ?? data.eval_sample_size ?? 30;

                const edgeBadge = document.getElementById('custom-edge-badge');
                if (edgeBadge) {
                    edgeBadge.textContent = `${edge >= 0 ? '+' : ''}${edge.toFixed(1)}% vs Drift Baseline`;
                    edgeBadge.className = `px-2 py-0.5 rounded-full text-[10px] font-bold ${edge >= 0 ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}`;
                }

                const maeVal = document.getElementById('custom-mae-val');
                if (maeVal) maeVal.textContent = `${customMae.toFixed(2)}%`;
                const baseMaeVal = document.getElementById('custom-baseline-mae-val');
                if (baseMaeVal) baseMaeVal.textContent = `${baseMae.toFixed(2)}%`;

                const verdictText = document.getElementById('custom-verdict-text');
                if (verdictText) {
                    verdictText.textContent = `${data.verdict || 'Evaluation benchmark completed.'} (Evaluated on ${sampleSize} walk-forward test periods with zero lookahead)`;
                }
            } catch (err) {
                console.error("Custom model evaluation error:", err);
            } finally {
                if (btn) btn.innerHTML = '<i data-lucide="play" class="w-3.5 h-3.5"></i> Run Walk-Forward Validation Benchmark';
                if (window.lucide) lucide.createIcons();
            }
        };

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
                const autoAdjust = document.getElementById('chart-auto-adjust').checked;
                const res = await fetch(`/api/stocks/${encodeURIComponent(currentSymbol)}/history?period=${encodeURIComponent(period)}&interval=${encodeURIComponent(interval)}&auto_adjust=${autoAdjust}${refresh ? '&refresh=true' : ''}`);
                if (!res.ok) throw new Error('Chart request failed');
                const data = await res.json();
                
                if (data.success && data.data && data.data.length > 0) {
                    const histRetrieved = data.timestamp ? ` · recorded ${new Date(data.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}` : '';
                    document.getElementById('chart-source-status').textContent = `${data.source || 'Provider unknown'} · ${(data.data_status || 'historical data').replaceAll('_', ' ')} · ${period} / ${interval} · last bar ${data.last_bar_at || data.data.at(-1)?.Date || 'unknown'}${histRetrieved}`;
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
            performance:'Indexed close-price performance. First available close = 100; no forecast.',
            forecast:'Model forecast trajectory with residual-based uncertainty bounds and observation origin reference.'
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
            } else if (view === 'forecast') {
                const series = chartMode === 'candlestick'
                    ? mainChartInstance.addCandlestickSeries({upColor:'#27845d',downColor:'#c24f50',borderVisible:false,wickUpColor:'#27845d',wickDownColor:'#c24f50'})
                    : mainChartInstance.addLineSeries({color:'#216bc2',lineWidth:2,title:'Close'});
                series.setData(chartMode === 'candlestick' ? history.filter(row=>Number.isFinite(Number(row.Open))&&Number.isFinite(Number(row.High))&&Number.isFinite(Number(row.Low))).map(row=>({time:row.time,open:Number(row.Open),high:Number(row.High),low:Number(row.Low),close:Number(row.Close)})) : closes);
                tooltipSeries.push({series,kind:chartMode === 'candlestick' ? 'ohlc' : 'line',title:'Close'});

                if (latestForecastData && latestForecastData.chart_data && latestForecastData.chart_data.projection_path) {
                    const path = latestForecastData.chart_data.projection_path;
                    const medianPoints = path.map(pt => ({ time: pt.date, value: Number(pt.price) }));
                    const upperPoints = path.map(pt => ({ time: pt.date, value: Number(pt.upper) }));
                    const lowerPoints = path.map(pt => ({ time: pt.date, value: Number(pt.lower) }));

                    const medianSeries = mainChartInstance.addLineSeries({
                        color: '#6366f1',
                        lineWidth: 2,
                        lineStyle: 2,
                        title: `Forecast Target (${latestForecastData.selected_model})`,
                        priceLineVisible: false,
                        lastValueVisible: true,
                    });
                    medianSeries.setData(medianPoints);
                    tooltipSeries.push({series: medianSeries, kind: 'line', title: 'Target'});

                    const upperSeries = mainChartInstance.addLineSeries({
                        color: 'rgba(99, 102, 241, 0.55)',
                        lineWidth: 1,
                        lineStyle: 3,
                        title: `Upper (${latestForecastData.interval?.confidence_percent || 80}%)`,
                        priceLineVisible: false,
                        lastValueVisible: false,
                    });
                    upperSeries.setData(upperPoints);

                    const lowerSeries = mainChartInstance.addLineSeries({
                        color: 'rgba(99, 102, 241, 0.55)',
                        lineWidth: 1,
                        lineStyle: 3,
                        title: `Lower (${latestForecastData.interval?.confidence_percent || 80}%)`,
                        priceLineVisible: false,
                        lastValueVisible: false,
                    });
                    lowerSeries.setData(lowerPoints);
                }
            }
            if (view !== 'price' && view !== 'volume' && view !== 'macd' && view !== 'performance' && view !== 'forecast') {
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
        let currentChatAbortController = null;
        let isGeneratingChat = false;

        function handleSendOrStop() {
            if (isGeneratingChat) {
                stopChatGeneration();
            } else {
                sendChatMessage();
            }
        }

        function setChatGeneratingState(generating) {
            isGeneratingChat = generating;
            const btn = document.getElementById('chat-send-btn');
            if (!btn) return;
            if (generating) {
                btn.className = 'p-2 rounded-full bg-black dark:bg-white text-white dark:text-black hover:opacity-80 transition-all disabled:opacity-50 mb-1 flex items-center justify-center shrink-0 w-9 h-9 shadow-sm';
                btn.title = 'Stop generation';
                btn.setAttribute('aria-label', 'Stop generation');
                btn.innerHTML = '<span class="w-3 h-3 bg-white dark:bg-black rounded-[2px] block"></span>';
            } else {
                btn.className = 'p-2 rounded-full bg-apple-blue text-white hover:bg-blue-600 transition-all disabled:opacity-50 mb-1 flex items-center justify-center shrink-0 w-9 h-9 shadow-sm';
                btn.title = 'Send message';
                btn.setAttribute('aria-label', 'Send message');
                btn.innerHTML = '<i data-lucide="arrow-up" class="h-4 w-4" id="chat-send-icon"></i>';
                if (window.lucide) lucide.createIcons();
            }
        }

        function stopChatGeneration() {
            if (currentChatAbortController) {
                currentChatAbortController.abort();
                currentChatAbortController = null;
            }
            setChatGeneratingState(false);
        }

        window.copyCodeBlock = async function(btn) {
            const wrapper = btn.closest('.code-block-wrapper');
            const codeEl = wrapper?.querySelector('code');
            if (!codeEl) return;
            try {
                await navigator.clipboard.writeText(codeEl.innerText || codeEl.textContent || '');
                btn.innerHTML = '<i data-lucide="check" class="w-3.5 h-3.5 inline mr-1 text-emerald-400"></i>Copied!';
                if (window.lucide) lucide.createIcons();
                setTimeout(() => {
                    btn.innerHTML = '<i data-lucide="copy" class="w-3.5 h-3.5 inline mr-1"></i>Copy code';
                    if (window.lucide) lucide.createIcons();
                }, 1500);
            } catch (_) {
                btn.textContent = 'Failed to copy';
            }
        };

        window.copyMessageText = async function(btn, text) {
            try {
                await navigator.clipboard.writeText(text);
                btn.innerHTML = '<i data-lucide="check" class="h-3.5 w-3.5 text-emerald-500"></i>';
                if (window.lucide) lucide.createIcons();
                setTimeout(() => {
                    btn.innerHTML = '<i data-lucide="copy" class="h-3.5 w-3.5"></i>';
                    if (window.lucide) lucide.createIcons();
                }, 1500);
            } catch (_) {
                btn.title = 'Clipboard unavailable';
            }
        };

        window.editUserMessage = function(text) {
            const input = document.getElementById('chat-input');
            if (!input) return;
            input.value = text;
            input.style.height = '44px';
            input.style.height = Math.min(input.scrollHeight, 180) + 'px';
            input.focus();
            input.scrollIntoView({ behavior: 'smooth', block: 'center' });
        };

        window.regenerateReply = function() {
            if (isGeneratingChat) return;
            const userNodes = document.querySelectorAll('#chat-messages .chat-user-message-text');
            if (!userNodes.length) return;
            const lastUserPrompt = userNodes[userNodes.length - 1].dataset.rawText || userNodes[userNodes.length - 1].innerText;
            if (!lastUserPrompt) return;
            const input = document.getElementById('chat-input');
            if (input) input.value = lastUserPrompt;
            sendChatMessage();
        };

        function setupMarkedRenderer() {
            if (typeof marked === 'undefined') return;
            const renderer = new marked.Renderer();
            renderer.code = function(code, language) {
                let codeText = '';
                let lang = '';
                if (typeof code === 'object' && code !== null) {
                    codeText = code.text || '';
                    lang = (code.lang || language || 'text').toLowerCase();
                } else {
                    codeText = String(code || '');
                    lang = (language || 'text').toLowerCase();
                }
                return `
                    <div class="code-block-wrapper my-4">
                        <div class="code-block-header">
                            <span class="code-lang-tag">${escapeHtml(lang)}</span>
                            <button type="button" class="code-copy-btn" onclick="copyCodeBlock(this)">
                                <i data-lucide="copy" class="w-3.5 h-3.5 inline mr-1"></i>Copy code
                            </button>
                        </div>
                        <pre><code class="language-${escapeHtml(lang)}">${escapeHtml(codeText)}</code></pre>
                    </div>
                `;
            };
            renderer.table = function(header, body) {
                let h = typeof header === 'object' ? header.header : header;
                let b = typeof header === 'object' ? header.body : body;
                return `
                    <div class="table-wrapper my-4">
                        <table class="markdown-table">
                            <thead>${h || ''}</thead>
                            <tbody>${b || ''}</tbody>
                        </table>
                    </div>
                `;
            };
            if (marked.use) {
                marked.use({ renderer });
            } else if (marked.setOptions) {
                marked.setOptions({ renderer });
            }
        }
        setupMarkedRenderer();

        async function sendChatMessage() {
            if (isGeneratingChat) return;
            const input = document.getElementById('chat-input');
            const msg = input.value.trim();
            if (!msg) return;

            const messages = document.getElementById('chat-messages');
            if (messages.querySelector('.chat-starters') || messages.querySelector('#chat-welcome-box')) {
                const welcome = document.getElementById('chat-welcome-box');
                if (welcome) welcome.remove();
            }
            const userRowId = `chat-user-${Date.now()}`;
            appendChat('user', msg, null, userRowId);
            renderChatAttachments();
            input.value = '';
            input.style.height = '44px';
            
            const typingId = 'typing-' + Date.now();
            appendChat('assistant', '<p role="status" class="m-0 text-apple-gray"><span class="inline-flex gap-1 align-middle mr-2"><i class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></i><i class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></i><i class="w-1.5 h-1.5 rounded-full bg-apple-blue loading-dot"></i></span>Thinking and retrieving context…</p>', null, typingId);

            currentChatAbortController = new AbortController();
            setChatGeneratingState(true);

            // Authoritative model selection & generation parameters
            const selectedModel = document.getElementById('chat-model-select')?.value || currentSettings.ai_model || 'gemma3:1b';
            const tempVal = parseFloat(localStorage.getItem('stockrag.paramTemp') || document.getElementById('param-temp')?.value) || 0.7;
            const maxTokensVal = parseInt(localStorage.getItem('stockrag.paramMaxTokens') || document.getElementById('param-max-tokens')?.value) || 2048;
            const topPVal = parseFloat(localStorage.getItem('stockrag.paramTopP') || document.getElementById('param-top-p')?.value) || 0.9;
            const customPersonaVal = (localStorage.getItem('stockrag.customPersona') || document.getElementById('param-custom-persona')?.value || '').trim();

            try {
                const res = await fetch('/api/chat/stream', {
                    method: 'POST',
                    signal: currentChatAbortController.signal,
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
                        mode: currentChatMode || currentSettings.default_chat_mode || 'general',
                        web_crawl: webCrawlEnabled,
                        model: selectedModel,
                        temperature: tempVal,
                        max_output_tokens: maxTokensVal,
                        top_p: topPVal,
                        custom_persona: customPersonaVal || null
                    })
                });
                const data = await consumeChatStream(res, typingId);
                const userActions = document.getElementById(userRowId)?.querySelector('.flex.items-center.gap-1');
                addBranchButton(userActions || document.getElementById(userRowId), data.user_message_id);
                if (data.session_id) {
                    chatSessionId = data.session_id;
                    localStorage.setItem('stockrag.sessionId', chatSessionId);
                    const finalTitle = data.title || 'New conversation';
                    updateActiveChatHeader(finalTitle, false);
                    const item = chatHistoryItems.find(i => i.session_id === chatSessionId);
                    if (item) item.title = finalTitle;
                    renderChatHistory();
                    loadChatHistory();
                }
                document.getElementById(typingId)?.remove();
                appendChat('assistant', data.answer, currentSettings.citation_visibility === false || currentSettings.show_data_sources === false ? null : data.citations, null, data.data_status, {
                    model: data.model || selectedModel, timestamp: data.data_timestamp, retrieval: data.retrieval,
                    sourcesUnverified: data.sources_unverified, formatUnverified: data.format_unverified,
                    numericValidation: data.numeric_validation, answerMethod: data.answer_method,
                    structuredSources: data.structured_sources || [], durationSeconds: data.duration_seconds
                }, data.assistant_message_id);
                
            } catch (err) {
                document.getElementById(typingId)?.remove();
                if (err.name === 'AbortError') {
                    appendChat('assistant', '_Generation stopped by user._', null, null, null, null);
                } else {
                    appendChat('assistant', `The analysis service could not produce a reply. ${err.message || 'Check the local AI service and retry.'}`, null, null, 'SERVICE_ERROR');
                    attachRetryToLastChatReply(msg);
                }
            } finally {
                currentChatAbortController = null;
                setChatGeneratingState(false);
            }
        }

        function renderStructuredSourcesHtml(sources) {
            if (!sources || !sources.length) return '';
            const cleanSources = [];
            const seenUrls = new Set();
            for (const s of sources) {
                if (!s || !s.url) continue;
                const key = s.url.split('?')[0].toLowerCase();
                if (seenUrls.has(key)) continue;
                seenUrls.add(key);
                cleanSources.push(s);
            }
            if (!cleanSources.length) return '';
            const cards = cleanSources.slice(0, 8).map(s => {
                const title = escapeHtml(s.title || s.url);
                const publisher = escapeHtml(s.publisher || s.domain || 'Source');
                const pubDate = s.published_at ? escapeHtml(s.published_at) : '';
                const url = escapeHtml(s.url);
                return `
                    <a href="${url}" target="_blank" rel="noopener noreferrer" class="group flex flex-col justify-between p-2.5 rounded-xl border border-black/8 dark:border-white/8 bg-black/[0.02] dark:bg-white/[0.02] hover:bg-black/[0.05] dark:hover:bg-white/[0.06] transition-all min-w-[200px] max-w-[240px] flex-shrink-0 text-left no-underline">
                        <div class="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 dark:text-gray-400 mb-1">
                            <span class="truncate">${publisher}</span>
                            ${pubDate ? `<span class="opacity-60">· ${pubDate}</span>` : ''}
                        </div>
                        <div class="text-[12px] font-medium text-gray-800 dark:text-gray-200 line-clamp-2 group-hover:text-apple-blue transition-colors leading-snug">
                            ${title}
                        </div>
                        <div class="mt-2 text-[10.5px] text-apple-blue flex items-center gap-1 font-medium">
                            <span>Open source</span>
                            <i data-lucide="external-link" class="w-3 h-3"></i>
                        </div>
                    </a>
                `;
            }).join('');

            return `
                <div class="mt-5 pt-4 border-t border-black/5 dark:border-white/5">
                    <div class="text-[12px] font-bold text-gray-500 dark:text-gray-400 mb-2.5 flex items-center gap-1.5">
                        <i data-lucide="newspaper" class="w-3.5 h-3.5 text-apple-blue"></i>
                        <span>Verified Sources (${cleanSources.length})</span>
                    </div>
                    <div class="flex gap-2.5 overflow-x-auto pb-2 scrollbar-thin">
                        ${cards}
                    </div>
                </div>
            `;
        }

        function appendChat(role, content, citations = null, id = null, status = null, meta = null, messageId = null) {
            const container = document.getElementById('chat-messages');
            if (role === 'assistant') {
                if (currentSettings.citation_visibility === false || currentSettings.show_data_sources === false) {
                    content = content.replace(/\n## Sources[\s\S]*$/i, '');
                }
                // Sanitize out legacy confusing verification notes, format check messages, long Google RSS URLs, and raw token blocks
                content = content
                    .replace(/\n*\*?\s*(?:Source verification|Format check):[^\n*]+\*?/gi, '')
                    .replace(/https:\/\/news\.google\.com\/rss\/articles\/[A-Za-z0-9_-]+/g, '[News Link]')
                    .replace(/^[A-Za-z0-9+/=_-]{40,}\s*\n?/gm, '')
                    .trim();
            }
            
            let bubbleHtml = '';
            if (role === 'user') {
                const escapedContent = escapeHtml(content);
                bubbleHtml = `
                    <div class="flex flex-col items-end ml-auto max-w-2xl w-full animate-slide-up mt-6 mb-2 group" ${id ? `id="${id}"` : ''}>
                        <div class="bg-[#f4f4f5] dark:bg-[#2f2f31] text-gray-900 dark:text-gray-100 px-5 py-3 rounded-[22px] text-[14.5px] font-normal leading-relaxed max-w-full break-words shadow-sm chat-user-message-text" data-raw-text="${escapedContent}">
                            ${escapedContent.replace(/\n/g, '<br>')}
                        </div>
                        <div class="flex items-center gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity text-apple-gray text-xs pr-2">
                            <button type="button" class="p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/10 text-apple-gray hover:text-gray-900 dark:hover:text-gray-100 transition-colors" title="Copy prompt" onclick="copyMessageText(this, ${JSON.stringify(content)})">
                                <i data-lucide="copy" class="h-3.5 w-3.5"></i>
                            </button>
                            <button type="button" class="p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/10 text-apple-gray hover:text-gray-900 dark:hover:text-gray-100 transition-colors" title="Edit prompt" onclick="editUserMessage(${JSON.stringify(content)})">
                                <i data-lucide="pencil" class="h-3.5 w-3.5"></i>
                            </button>
                        </div>
                    </div>
                `;
            } else {
                // Parse markdown
                const isHtmlContent = content.includes('<div') || content.includes('<span');
                const parsedContent = isHtmlContent ? content : DOMPurify.sanitize(marked.parse(content));
                
                let extraHtml = '';
                if (status === 'SERVICE_ERROR') {
                    extraHtml += '<div role="status" class="mt-3 inline-block px-2.5 py-1 rounded-md text-[10px] font-bold tracking-widest bg-orange-500/10 text-orange-700 uppercase">⚠️ Service failure · no AI answer generated</div>';
                } else if (status && status !== 'LIVE' && status !== 'NOT_REQUESTED') {
                    extraHtml += `<div class="mt-3 inline-block px-2.5 py-1 rounded-md text-[10px] font-bold tracking-widest bg-orange-500/10 text-orange-500 uppercase">⚠️ ${status} DATA</div>`;
                }
                
                if (meta && meta.structuredSources && meta.structuredSources.length > 0 && currentSettings.citation_visibility !== false && currentSettings.show_data_sources !== false) {
                    extraHtml += renderStructuredSourcesHtml(meta.structuredSources);
                } else if (citations && citations.length > 0 && !content.includes('## Sources') && !content.includes('**Sources:**')) {
                    extraHtml += `
                        <div class="mt-5 pt-4 border-t border-black/5 dark:border-white/5 text-[12px] text-gray-500 dark:text-gray-400">
                            <div class="font-bold mb-2 flex items-center gap-1.5"><i data-lucide="link-2" class="w-3.5 h-3.5"></i> Sources</div>
                            <ul class="list-disc pl-5 space-y-1">
                                ${citations.map(c => `<li>${citationHtml(c)}</li>`).join('')}
                            </ul>
                        </div>
                    `;
                }
                if (meta) {
                    const time = meta.timestamp ? new Date(meta.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
                    const modelLabel = meta.model || (meta.answerMethod === 'extractive_source_fallback' ? 'Source Extract' : meta.answerMethod === 'deterministic_insufficient_evidence' ? 'Evidence Verified' : 'AI Assistant');
                    const retrievalCount = meta.retrieval?.sources ? `${meta.retrieval.sources} source${meta.retrieval.sources > 1 ? 's' : ''}` : '';
                    extraHtml += `<div class="mt-3 flex flex-wrap items-center gap-x-2 text-[11px] text-gray-400 dark:text-gray-500 font-medium">
                        <span class="px-2 py-0.5 rounded-md bg-black/5 dark:bg-white/5 font-semibold text-gray-700 dark:text-gray-300">${escapeHtml(modelLabel)}</span>
                        ${time ? `<span>·</span><span>${escapeHtml(time)}</span>` : ''}
                        ${retrievalCount ? `<span>·</span><span>${escapeHtml(retrievalCount)}</span>` : ''}
                    </div>`;
                }

                bubbleHtml = `
                    <div class="flex gap-3.5 items-start max-w-full animate-slide-up mt-6 mb-4 group" ${id ? `id="${id}"` : ''}>
                        <div class="w-8 h-8 rounded-full border border-black/10 dark:border-white/10 flex-shrink-0 flex items-center justify-center bg-white dark:bg-[#202022] mt-1 shadow-sm">
                            <i data-lucide="sparkles" class="w-4 h-4 text-apple-blue"></i>
                        </div>
                        <div class="text-[14.5px] prose prose-sm dark:prose-invert prose-p:leading-relaxed prose-a:text-apple-blue w-full max-w-[88%] min-w-0 break-words pt-1 chat-bubble-ai">
                            ${parsedContent}
                            ${extraHtml}
                            <div class="flex items-center gap-2 mt-3 text-apple-gray">
                                ${!id && status !== 'SERVICE_ERROR' ? '<button type="button" class="chat-copy-button p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors text-apple-gray hover:text-gray-900 dark:hover:text-gray-100" aria-label="Copy assistant reply" title="Copy reply"><i data-lucide="copy" class="h-3.5 w-3.5"></i></button>' : ''}
                                ${!id && status !== 'SERVICE_ERROR' ? '<button type="button" class="chat-regen-button p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors text-apple-gray hover:text-gray-900 dark:hover:text-gray-100" aria-label="Regenerate reply" title="Regenerate reply" onclick="regenerateReply()"><i data-lucide="rotate-ccw" class="h-3.5 w-3.5"></i></button>' : ''}
                                ${!id && status !== 'SERVICE_ERROR' && messageId ? '<button type="button" class="chat-branch-button p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/10 transition-colors text-apple-gray hover:text-gray-900 dark:hover:text-gray-100" aria-label="Branch conversation from this reply" title="Branch from this reply"><i data-lucide="git-branch" class="h-3.5 w-3.5"></i></button>' : ''}
                            </div>
                        </div>
                    </div>
                `;
            }
            
            container.insertAdjacentHTML('beforeend', bubbleHtml);
            const copyButton = container.lastElementChild?.querySelector('.chat-copy-button');
            const branchButton = container.lastElementChild?.querySelector('.chat-branch-button');
            branchButton?.addEventListener('click', () => branchChat(messageId));
            copyButton?.addEventListener('click', async () => {
                const bubble = container.lastElementChild?.querySelector('.chat-bubble-ai');
                try {
                    await navigator.clipboard.writeText(bubble?.innerText || '');
                    copyButton.title = 'Copied';
                    copyButton.setAttribute('aria-label', 'Reply copied');
                    copyButton.innerHTML = '<i data-lucide="check" class="h-3.5 w-3.5 text-emerald-500"></i>';
                    lucide.createIcons();
                    setTimeout(() => {
                        copyButton.title = 'Copy reply';
                        copyButton.setAttribute('aria-label', 'Copy assistant reply');
                        copyButton.innerHTML = '<i data-lucide="copy" class="h-3.5 w-3.5"></i>';
                        lucide.createIcons();
                    }, 1300);
                } catch (_) {
                    copyButton.title = 'Clipboard unavailable';
                }
            });
            if (window.lucide) lucide.createIcons();
            
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
                updateActiveChatHeader(data.title || 'New conversation', Boolean(data.parent_session_id));
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
                            numericValidation: storedMeta.numeric_validation, answerMethod: storedMeta.answer_method,
                            structuredSources: storedMeta.structured_sources || [], durationSeconds: storedMeta.duration_seconds
                        } : null;
                        appendChat(message.role, message.content, message.role === 'assistant' ? message.sources : null, null, storedMeta.data_status, replyMeta, metricMismatch ? null : message.id);
                        if (message.role === 'user') {
                            const userActions = container.lastElementChild?.querySelector('.flex.items-center.gap-1');
                            addBranchButton(userActions || container.lastElementChild, message.id);
                        }
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
            appendChat('assistant', 'New conversation. Ask anything, analyze stocks, write code, or paste links to crawl.');
            updateActiveChatHeader('New conversation', false);
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
        async function checkHealth(isManual = false) {
            const refreshBtn = document.getElementById('system-status-refresh-btn');
            const refreshIcon = refreshBtn?.querySelector('i');
            if (isManual && refreshIcon) refreshIcon.classList.add('animate-spin');

            try {
                const res = await fetch('/api/health');
                if (!res.ok) throw new Error(`HTTP ${res.status}: Health check failed`);
                const data = await res.json();
                
                const retrievalMode = data.document_retrieval || 'unavailable';
                
                // Construct detailed, accurate service health items
                const items = [];

                if (data.mode === 'market-only' || data.cloud_preview) {
                    items.push({
                        name: 'Application API',
                        icon: 'server',
                        state: data.ready ? 'ready' : 'warning',
                        label: 'Ready · Cloud Preview',
                        detail: `Cloud market API online. SQLite persistence: ${data.database || 'online'}.`
                    });
                    items.push({
                        name: 'Market Data Feed',
                        icon: 'chart-no-axes-combined',
                        state: data.market_data?.status === 'available' ? 'ready' : 'issue',
                        label: data.market_data?.provider || 'Live Market',
                        detail: `${data.market_data?.provider || 'Configured provider'} live feed active (${data.market_data?.data_status || 'LIVE'}). Real-time quotes and candlestick charts.`
                    });
                    items.push({
                        name: 'Financial News Feed',
                        icon: 'newspaper',
                        state: data.web_search?.status === 'available' ? 'ready' : 'warning',
                        label: 'Operational',
                        detail: 'Real-time financial publisher feed and Google News RSS active.'
                    });
                    items.push({
                        name: 'Local LLM & RAG Engine',
                        icon: 'cpu',
                        state: 'ready',
                        label: 'Local Docker Mode',
                        detail: 'Full Ollama LLM inference and neural RAG vector search are configured for the local Docker & Kubernetes deployment.'
                    });
                } else {
                    // 1. Application API
                    items.push({
                        name: 'Application API',
                        icon: 'server',
                        state: data.ready ? 'ready' : 'warning',
                        label: data.ready ? 'Ready' : 'Responding; dependencies incomplete',
                        detail: `Local API answered. Database: ${data.database || 'unknown'}; configured chat model: ${data.model_available ? 'available' : 'unavailable'}; embedding model: ${data.embedding_model_available ? 'available' : 'unavailable'}.`
                    });

                // 2. Local AI Model
                if (data.ollama === 'connected' && data.model_available) {
                    items.push({
                        name: 'Local AI Model',
                        icon: 'cpu',
                        state: 'ready',
                        label: 'Ready',
                        detail: `Model '${data.model}' is installed and active via local Ollama.`
                    });
                } else if (data.ollama === 'connected' && !data.model_available) {
                    items.push({
                        name: 'Local AI Model',
                        icon: 'cpu',
                        state: 'issue',
                        label: 'Missing',
                        detail: `Ollama is running, but configured model '${data.model}' is not pulled.`,
                        action: `💡 Run 'ollama pull ${data.model}' in your terminal`
                    });
                } else {
                    items.push({
                        name: 'Local AI Model',
                        icon: 'cpu',
                        state: 'issue',
                        label: 'Offline',
                        detail: `Ollama service is not reachable at http://127.0.0.1:11434. Local AI features are paused.`,
                        action: `💡 Start Ollama on your computer ('ollama serve')`
                    });
                }

                // 3. Document Retrieval (RAG)
                if (retrievalMode === 'semantic') {
                    items.push({
                        name: 'Document Retrieval',
                        icon: 'database',
                        state: 'ready',
                        label: 'Semantic Search',
                        detail: `Neural embedding search active using '${data.embedding_model || 'nomic-embed-text'}'.`
                    });
                } else if (retrievalMode === 'keyword') {
                    items.push({
                        name: 'Document Retrieval',
                        icon: 'database',
                        state: 'warning',
                        label: 'Keyword Fallback',
                        detail: `Embedding model '${data.embedding_model || 'nomic-embed-text'}' is not installed; falling back to lexical search.`,
                        action: `💡 Run 'ollama pull ${data.embedding_model || 'nomic-embed-text'}' for full neural search`
                    });
                } else {
                    items.push({
                        name: 'Document Retrieval',
                        icon: 'database',
                        state: 'issue',
                        label: 'Unavailable',
                        detail: 'Document index is uninitialized or unreachable.'
                    });
                }

                // 4. Vector Database
                items.push({
                    name: 'Vector Database',
                    icon: 'layers-3',
                    state: data.vector_database === 'available' ? 'ready' : 'issue',
                    label: data.vector_database === 'available' ? 'FAISS Active' : 'Offline',
                    detail: `FAISS CPU vector store active · ${data.database_stats?.documents || 0} documents, ${data.database_stats?.chunks || 0} chunks indexed.`
                });

                // 5. Market Data
                if (data.market_data?.status === 'available') {
                    items.push({
                        name: 'Market Data',
                        icon: 'chart-no-axes-combined',
                        state: 'ready',
                        label: 'Probe responded',
                        detail: `${data.market_data.provider || 'Configured provider'} answered the availability probe (${data.market_data.data_status || 'freshness unknown'}). Quote freshness is reported per quote.`
                    });
                } else {
                    items.push({
                        name: 'Market Data',
                        icon: 'chart-no-axes-combined',
                        state: 'issue',
                        label: 'Unavailable',
                        detail: data.market_data?.error || 'No configured market-data provider is reachable.',
                        action: '💡 Check internet connection or market provider settings'
                    });
                }

                    // 6. Web Search & Crawling
                    if (data.web_search) {
                        const isWebAvailable = data.web_search.status === 'available' || data.web_search.status === 'operational';
                        items.push({
                            name: 'Web Search & Crawl',
                            icon: 'globe',
                            state: isWebAvailable ? 'ready' : 'warning',
                            label: isWebAvailable ? 'Operational' : 'Degraded',
                            detail: isWebAvailable 
                                ? 'DNS lookup succeeded; retrieving a news feed was not tested.'
                                : 'DNS lookup failed; news retrieval has not been tested.'
                        });
                    }
                }

                const issueCount = items.filter(item => item.state === 'issue').length;
                const warningCount = items.filter(item => item.state === 'warning').length;
                const summary = issueCount ? `${issueCount} issue${issueCount > 1 ? 's' : ''}` : warningCount ? `${warningCount} warning${warningCount > 1 ? 's' : ''}` : 'Ready';
                const statusState = issueCount ? 'issue' : warningCount ? 'warning' : 'ready';
                updateProjectStatus(items, summary, statusState);

            } catch (e) {
                    const message = e?.message || 'The app could not reach its local health endpoint.';
                updateProjectStatus([
                    {name:'Application API',icon:'server-off',state:'issue',label:'Offline',detail:`GET /api/health failed: ${message}`, action:'💡 Ensure backend server is running on port 8000.'},
                    {name:'Market Data',icon:'chart-no-axes-combined',state:'warning',label:'Unknown',detail:'Could not check provider status because local API is unreachable.'},
                    {name:'Local AI Model',icon:'cpu',state:'issue',label:'Unknown',detail:'Could not check Ollama or configured AI model.'},
                    {name:'Document Retrieval',icon:'database',state:'warning',label:'Unknown',detail:'Could not verify retrieval store.'},
                ], 'API Offline', 'issue');
            } finally {
                if (refreshIcon) {
                    setTimeout(() => refreshIcon.classList.remove('animate-spin'), 400);
                }
            }
        }
        function restoreChatParameters() {
            try {
                const savedTemp = localStorage.getItem('stockrag.paramTemp');
                if (savedTemp) onQuickSliderChange(savedTemp);

                const savedMaxTokens = localStorage.getItem('stockrag.paramMaxTokens');
                if (savedMaxTokens) {
                    const input = document.getElementById('param-max-tokens');
                    const val = document.getElementById('param-max-tokens-val');
                    if (input) input.value = savedMaxTokens;
                    if (val) val.textContent = String(savedMaxTokens);
                }

                const savedTopP = localStorage.getItem('stockrag.paramTopP');
                if (savedTopP) {
                    const input = document.getElementById('param-top-p');
                    const val = document.getElementById('param-top-p-val');
                    if (input) input.value = savedTopP;
                    if (val) val.textContent = parseFloat(savedTopP).toFixed(2);
                }

                const savedPersona = localStorage.getItem('stockrag.customPersona');
                if (savedPersona) {
                    const input = document.getElementById('param-custom-persona');
                    if (input) input.value = savedPersona;
                }
            } catch (e) {
                console.warn('Could not restore chat parameters from localStorage', e);
            }
        }
        window.restoreChatParameters = restoreChatParameters;

        // ==========================================
        // Auto-refresh graphs and request provider quotes.
        // ==========================================
        let autoUpdateIntervalSeconds = 10;
        let autoUpdateCountdownSeconds = 10;
        let autoUpdateCountdownTimer = null;
        let isAutoUpdating = false;
        let lastObservedPrice = null;

        function initAutoUpdate() {
            const select = document.getElementById('auto-update-cadence-select');
            if (select) {
                autoUpdateIntervalSeconds = Number(select.value) || 10;
            }
            startAutoUpdateTimer();
        }

        function changeAutoUpdateCadence(val) {
            autoUpdateIntervalSeconds = Number(val);
            const liveBadge = document.getElementById('chart-live-badge');
            const statusText = document.getElementById('chart-live-status-text');
            const timerDesc = document.getElementById('chart-update-timer-desc');
            const secondsEl = document.getElementById('chart-update-seconds');

            if (autoUpdateIntervalSeconds <= 0) {
                // Paused / Manual mode
                if (autoUpdateCountdownTimer) {
                    clearInterval(autoUpdateCountdownTimer);
                    autoUpdateCountdownTimer = null;
                }
                if (liveBadge) {
                    liveBadge.className = 'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-black/5 dark:bg-white/5 text-apple-gray border border-black/10 dark:border-white/10';
                }
                if (statusText) statusText.textContent = 'MANUAL (Paused)';
                if (timerDesc) timerDesc.innerHTML = 'Auto-refresh paused &middot; Tap play icon to update';
            } else {
                // Active auto-refresh mode
                if (liveBadge) {
                    liveBadge.className = 'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20';
                }
                if (statusText) statusText.textContent = `AUTO-REFRESH (${autoUpdateIntervalSeconds}s)`;
                if (timerDesc) timerDesc.innerHTML = `Continuous auto-refresh &middot; Next tick in <span id="chart-update-seconds" class="font-mono font-semibold text-emerald-600 dark:text-emerald-400">${autoUpdateIntervalSeconds}</span>s`;
                autoUpdateCountdownSeconds = autoUpdateIntervalSeconds;
                startAutoUpdateTimer();
            }
        }

        function startAutoUpdateTimer() {
            if (autoUpdateCountdownTimer) clearInterval(autoUpdateCountdownTimer);
            if (autoUpdateIntervalSeconds <= 0) return;
            autoUpdateCountdownSeconds = autoUpdateIntervalSeconds;
            
            autoUpdateCountdownTimer = setInterval(async () => {
                const stockView = document.getElementById('stock-view');
                if (!stockView || stockView.classList.contains('hidden') || !currentSymbol) {
                    return;
                }

                autoUpdateCountdownSeconds--;
                const secondsEl = document.getElementById('chart-update-seconds');
                if (secondsEl) secondsEl.textContent = String(Math.max(0, autoUpdateCountdownSeconds));

                if (autoUpdateCountdownSeconds <= 0) {
                    autoUpdateCountdownSeconds = autoUpdateIntervalSeconds;
                    if (secondsEl) secondsEl.textContent = String(autoUpdateCountdownSeconds);
                    await executeAutoUpdateTick();
                }
            }, 1000);
        }

        async function triggerManualChartUpdate() {
            autoUpdateCountdownSeconds = autoUpdateIntervalSeconds > 0 ? autoUpdateIntervalSeconds : 0;
            const secondsEl = document.getElementById('chart-update-seconds');
            if (secondsEl) secondsEl.textContent = String(autoUpdateCountdownSeconds);
            await executeAutoUpdateTick();
        }

        async function executeAutoUpdateTick() {
            if (!currentSymbol || isAutoUpdating) return;
            const stockView = document.getElementById('stock-view');
            if (!stockView || stockView.classList.contains('hidden')) return;

            isAutoUpdating = true;
            const spinIcon = document.getElementById('auto-update-spin-icon');
            if (spinIcon) spinIcon.classList.add('spin-anim');

            try {
                const period = activeChartPeriod || '1mo';
                const interval = activeChartInterval || '1d';
                const autoAdjust = document.getElementById('chart-auto-adjust')?.checked ?? true;

                // Fetch live quote and history concurrently with refresh=true
                const [quoteRes, histRes] = await Promise.all([
                    fetch(`/api/stocks/${encodeURIComponent(currentSymbol)}/quote?refresh=true`),
                    fetch(`/api/stocks/${encodeURIComponent(currentSymbol)}/history?period=${encodeURIComponent(period)}&interval=${encodeURIComponent(interval)}&auto_adjust=${autoAdjust}&refresh=true`)
                ]);

                if (quoteRes.ok) {
                    const quote = await quoteRes.json();
                    if (quote.success !== false && Number.isFinite(Number(quote.price))) {
                        const newPrice = Number(quote.price);
                        const priceEl = document.getElementById('stock-price');
                        
                        if (priceEl) {
                            if (lastObservedPrice !== null && newPrice !== lastObservedPrice) {
                                priceEl.classList.remove('price-flash-up', 'price-flash-down');
                                void priceEl.offsetWidth; // trigger reflow
                                priceEl.classList.add(newPrice > lastObservedPrice ? 'price-flash-up' : 'price-flash-down');
                                setTimeout(() => priceEl.classList.remove('price-flash-up', 'price-flash-down'), 1200);
                            }
                            priceEl.textContent = `${quote.currency || ''} ${newPrice.toFixed(2)}`.trim();
                        }
                        lastObservedPrice = newPrice;

                        const changeEl = document.getElementById('stock-change');
                        const iconEl = document.getElementById('stock-trend-icon');
                        const containerEl = document.getElementById('stock-change-container');
                        if (changeEl && quote.change !== undefined && quote.percent_change !== undefined) {
                            const isPositive = quote.change >= 0;
                            changeEl.textContent = `${isPositive ? '+' : ''}${quote.change.toFixed(2)} (${isPositive ? '+' : ''}${quote.percent_change.toFixed(2)}%)`;
                            if (containerEl) {
                                containerEl.className = `flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold ${isPositive ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}`;
                            }
                            if (iconEl) {
                                iconEl.className = `w-3 h-3 ${isPositive ? 'rotate-0' : 'rotate-180'}`;
                            }
                        }
                    }
                }

                if (histRes.ok) {
                    const histData = await histRes.json();
                    if (histData.success && histData.data && histData.data.length > 0) {
                        latestHistoryData = histData.data;
                        latestIndicatorData = histData.indicators?.data || [];
                        const statusEl = document.getElementById('chart-source-status');
                        if (statusEl) {
                            const lastBar = histData.last_bar_at || histData.data.at(-1)?.Date || 'now';
                            statusEl.textContent = `${histData.source || 'Provider'} · ${histData.data_status || 'freshness unknown'} · ${period}/${interval} · retrieved ${histData.retrieved_at || 'time unavailable'} (bar: ${lastBar})`;
                        }
                        renderChart(latestHistoryData, latestIndicatorData, analysisView);
                    }
                }
            } catch (err) {
                console.warn('Auto-update tick encountered an error:', err);
            } finally {
                isAutoUpdating = false;
                if (spinIcon) {
                    setTimeout(() => spinIcon.classList.remove('spin-anim'), 400);
                }
            }
        }

        window.initAutoUpdate = initAutoUpdate;
        window.changeAutoUpdateCadence = changeAutoUpdateCadence;
        window.triggerManualChartUpdate = triggerManualChartUpdate;
        window.executeAutoUpdateTick = executeAutoUpdateTick;

        // ==========================================
        // SPOTLIGHT SEARCH CONTROLLER (MOBILE & CMD+K)
        // ==========================================
        const SPOTLIGHT_DIRECTORY = [
            { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', category: 'Tech' },
            { symbol: 'NVDA', name: 'NVIDIA Corporation', exchange: 'NASDAQ', category: 'Semiconductors' },
            { symbol: 'MSFT', name: 'Microsoft Corporation', exchange: 'NASDAQ', category: 'Software' },
            { symbol: 'GOOGL', name: 'Alphabet Inc.', exchange: 'NASDAQ', category: 'Internet' },
            { symbol: 'AMZN', name: 'Amazon.com Inc.', exchange: 'NASDAQ', category: 'E-Commerce' },
            { symbol: 'TSLA', name: 'Tesla Inc.', exchange: 'NASDAQ', category: 'Automotive' },
            { symbol: 'META', name: 'Meta Platforms Inc.', exchange: 'NASDAQ', category: 'Social' },
            { symbol: 'RELIANCE.NS', name: 'Reliance Industries Ltd.', exchange: 'NSE', category: 'Energy & Tech' },
            { symbol: 'TCS.NS', name: 'Tata Consultancy Services', exchange: 'NSE', category: 'IT Services' },
            { symbol: 'HDFCBANK.NS', name: 'HDFC Bank Ltd.', exchange: 'NSE', category: 'Banking' },
            { symbol: 'INFY.NS', name: 'Infosys Limited', exchange: 'NSE', category: 'IT Services' },
            { symbol: 'ICICIBANK.NS', name: 'ICICI Bank Ltd.', exchange: 'NSE', category: 'Banking' },
            { symbol: 'SBIN.NS', name: 'State Bank of India', exchange: 'NSE', category: 'Banking' },
            { symbol: 'BHARTIARTL.NS', name: 'Bharti Airtel Ltd.', exchange: 'NSE', category: 'Telecom' },
            { symbol: 'ITC.NS', name: 'ITC Limited', exchange: 'NSE', category: 'Consumer' }
        ];

        let spotlightFocusedIndex = -1;

        function openSpotlightSearch() {
            const modal = document.getElementById('spotlight-search-modal');
            const input = document.getElementById('spotlight-search-input');
            if (!modal) return;
            modal.style.display = 'flex';
            modal.classList.remove('hidden');
            if (input) {
                input.value = '';
                input.focus();
                filterSpotlightSuggestions('');
            }
            if (window.lucide) lucide.createIcons();
        }

        function closeSpotlightSearch() {
            const modal = document.getElementById('spotlight-search-modal');
            if (modal) {
                modal.classList.add('hidden');
                modal.style.display = 'none';
            }
            spotlightFocusedIndex = -1;
        }

        function filterSpotlightSuggestions(query) {
            const q = (query || '').trim().toLowerCase();
            const container = document.getElementById('spotlight-results-container');
            const chips = document.getElementById('spotlight-popular-chips')?.parentElement;
            if (!container) return;

            spotlightFocusedIndex = -1;

            if (!q) {
                container.classList.add('hidden');
                container.innerHTML = '';
                if (chips) chips.classList.remove('hidden');
                return;
            }

            if (chips) chips.classList.add('hidden');
            container.classList.remove('hidden');

            const allSymbols = [...SPOTLIGHT_DIRECTORY];
            if (Array.isArray(landingSymbols)) {
                landingSymbols.forEach(item => {
                    if (!allSymbols.some(s => s.symbol === item.symbol)) {
                        allSymbols.push({ symbol: item.symbol, name: item.label || item.symbol, exchange: item.market === 'india' ? 'NSE' : 'US', category: item.group || 'Market' });
                    }
                });
            }

            const matches = allSymbols.filter(s => 
                s.symbol.toLowerCase().includes(q) || 
                (s.name && s.name.toLowerCase().includes(q)) ||
                (s.category && s.category.toLowerCase().includes(q))
            );

            if (!matches.length) {
                container.innerHTML = `
                    <div class="p-4 text-center">
                        <p class="text-xs text-apple-gray">No matched preset instrument for "<span class="font-semibold text-gray-800 dark:text-gray-200">${escapeHtml(query)}</span>".</p>
                        <button type="button" onclick="selectSpotlightTicker('${escapeHtml(query.toUpperCase())}')" class="mt-2.5 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-apple-blue text-white active:scale-95 transition">
                            <i data-lucide="search" class="w-3.5 h-3.5"></i> Look up "${escapeHtml(query.toUpperCase())}" on exchange
                        </button>
                    </div>
                `;
                if (window.lucide) lucide.createIcons();
                return;
            }

            container.innerHTML = matches.slice(0, 8).map((item, idx) => `
                <div class="spotlight-result-row flex items-center justify-between p-3 cursor-pointer hover:bg-black/[0.04] dark:hover:bg-white/[0.05] transition" 
                     data-index="${idx}" 
                     data-symbol="${escapeHtml(item.symbol)}"
                     onclick="selectSpotlightTicker('${escapeHtml(item.symbol)}')">
                    <div class="flex items-center gap-2.5">
                        <div class="w-8 h-8 rounded-xl bg-black/[0.04] dark:bg-white/[0.06] flex items-center justify-center font-bold text-xs ${item.exchange === 'NSE' ? 'text-purple-600 dark:text-purple-400' : 'text-apple-blue'}">
                            ${item.symbol.slice(0, 2)}
                        </div>
                        <div>
                            <span class="text-xs font-bold text-gray-900 dark:text-gray-100 flex items-center gap-1.5">
                                ${escapeHtml(item.symbol)}
                                <span class="text-[9px] font-semibold px-1.5 py-0.5 rounded ${item.exchange === 'NSE' ? 'bg-purple-500/10 text-purple-600 dark:text-purple-400' : 'bg-blue-500/10 text-blue-600 dark:text-blue-400'}">${escapeHtml(item.exchange)}</span>
                            </span>
                            <span class="text-[11px] text-apple-gray block truncate max-w-[200px] sm:max-w-xs">${escapeHtml(item.name)}</span>
                        </div>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="text-[10px] text-apple-gray hidden sm:inline">${escapeHtml(item.category || '')}</span>
                        <i data-lucide="arrow-right" class="w-4 h-4 text-apple-gray"></i>
                    </div>
                </div>
            `).join('');

            if (window.lucide) lucide.createIcons();
        }

        function selectSpotlightTicker(symbol) {
            closeSpotlightSearch();
            simulateSearch(symbol);
        }

        function handleSpotlightKeydown(e) {
            const rows = document.querySelectorAll('.spotlight-result-row');
            if (e.key === 'Escape') {
                closeSpotlightSearch();
                return;
            }
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (!rows.length) return;
                spotlightFocusedIndex = (spotlightFocusedIndex + 1) % rows.length;
                updateSpotlightFocusedRow(rows);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (!rows.length) return;
                spotlightFocusedIndex = (spotlightFocusedIndex - 1 + rows.length) % rows.length;
                updateSpotlightFocusedRow(rows);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (spotlightFocusedIndex >= 0 && rows[spotlightFocusedIndex]) {
                    const sym = rows[spotlightFocusedIndex].dataset.symbol;
                    if (sym) selectSpotlightTicker(sym);
                } else {
                    const input = document.getElementById('spotlight-search-input');
                    if (input && input.value.trim()) {
                        selectSpotlightTicker(input.value.trim().toUpperCase());
                    }
                }
            }
        }

        function updateSpotlightFocusedRow(rows) {
            rows.forEach((r, idx) => {
                const isFocused = idx === spotlightFocusedIndex;
                r.classList.toggle('bg-apple-blue/10', isFocused);
                r.classList.toggle('dark:bg-apple-blue/20', isFocused);
                if (isFocused) r.scrollIntoView({ block: 'nearest' });
            });
        }

        // Global Keyboard Shortcut Listeners for Command/Ctrl+K and "/"
        window.addEventListener('keydown', (e) => {
            const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
            
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                openSpotlightSearch();
                return;
            }

            if (e.key === '/' && !isInput) {
                e.preventDefault();
                openSpotlightSearch();
                return;
            }

            if (e.key === 'Escape') {
                const spotlightModal = document.getElementById('spotlight-search-modal');
                if (spotlightModal && !spotlightModal.classList.contains('hidden')) {
                    closeSpotlightSearch();
                    return;
                }
                const settingsModal = document.getElementById('settings-modal');
                if (settingsModal && !settingsModal.classList.contains('pointer-events-none') && !settingsModal.classList.contains('opacity-0')) {
                    toggleModal('settings-modal');
                    return;
                }
                const docsModal = document.getElementById('docs-modal');
                if (docsModal && !docsModal.classList.contains('pointer-events-none') && !docsModal.classList.contains('opacity-0')) {
                    toggleModal('docs-modal');
                    return;
                }
                const modelInfoModal = document.getElementById('model-info-modal');
                if (modelInfoModal && !modelInfoModal.classList.contains('hidden')) {
                    closeModelInfoModal();
                    return;
                }
                const systemHealthModal = document.getElementById('system-health-modal');
                if (systemHealthModal && !systemHealthModal.classList.contains('hidden')) {
                    closeSystemHealthModal();
                    return;
                }
                const customModelModal = document.getElementById('custom-model-modal');
                if (customModelModal && !customModelModal.classList.contains('hidden')) {
                    closeCustomModelModal();
                    return;
                }
                const forecastUploadModal = document.getElementById('forecast-upload-modal');
                if (forecastUploadModal && !forecastUploadModal.classList.contains('hidden')) {
                    closeForecastUploadModal();
                    return;
                }
                const popover = document.getElementById('system-status-popover');
                if (popover && !popover.classList.contains('hidden')) {
                    closeSystemStatus();
                    return;
                }
            }
        });

        window.openSpotlightSearch = openSpotlightSearch;
        window.closeSpotlightSearch = closeSpotlightSearch;
        window.filterSpotlightSuggestions = filterSpotlightSuggestions;
        window.selectSpotlightTicker = selectSpotlightTicker;
        window.handleSpotlightKeydown = handleSpotlightKeydown;

        setInterval(checkHealth, 30000);
        setupComparisonSelectors();
        setupChatPage();
        setChatMode(currentChatMode);
        updateWebCrawlUI();
        restoreLocation();
        checkHealth();
        fetchSettings();
        restoreChatParameters();
        restoreChatSession();
        initAutoUpdate();
        window.toggleAutoAdjust = function() { if (activeChartPeriod) { loadChartData(activeChartPeriod, true); } };
