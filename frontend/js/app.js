/**
 * InventoryScraper — Main Application Logic
 * Handles routing, state, event binding, and data flow.
 */

const app = {
    // State
    currentPage: 'dashboard',
    productFilters: { brand: '', search: '', in_stock: '', page: 1, per_page: 30 },
    alertFilters: { brand: '', alert_type: '' },
    pollingIntervals: {},

    // ── Initialization ────────────────────────────────────────────────
    async init() {
        this.bindNavigation();
        this.bindExportDropdown();
        await this.showPage('dashboard');
    },

    bindNavigation() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = e.currentTarget.dataset.page;
                if (page) this.showPage(page);
            });
        });
    },

    bindExportDropdown() {
        const btn = document.getElementById('export-btn');
        const menu = document.getElementById('export-menu');
        if (btn && menu) {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                menu.classList.toggle('show');
            });
            document.addEventListener('click', () => menu.classList.remove('show'));
        }
    },

    // ── Page Routing ──────────────────────────────────────────────────
    async showPage(page) {
        this.currentPage = page;

        // Update nav
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        const activeLink = document.querySelector(`.nav-link[data-page="${page}"]`);
        if (activeLink) activeLink.classList.add('active');

        // Show section
        document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
        const section = document.getElementById(`page-${page}`);
        if (section) section.classList.add('active');

        // Load data
        switch (page) {
            case 'dashboard': await this.loadDashboard(); break;
            case 'products': await this.loadProducts(); break;
            case 'alerts': await this.loadAlerts(); break;
            case 'history': await this.loadHistory(); break;
            case 'shopify': await this.loadShopify(); break;
        }
    },

    // ── Dashboard ─────────────────────────────────────────────────────
    async loadDashboard() {
        try {
            const [stats, brands, healthAlerts] = await Promise.all([
                api.getStats(),
                api.getBrands(),
                api.getHealthAlerts(),
            ]);

            // Stats bar
            document.getElementById('stats-bar').innerHTML = components.renderStats(stats);

            // Alert banner
            const alertBanner = document.getElementById('alert-banner');
            if (stats.active_alerts > 0) {
                alertBanner.classList.remove('hidden');
                alertBanner.querySelector('.alert-banner-text').innerHTML =
                    `<strong>${stats.active_alerts} stock alert(s)</strong> detected across your brands. <span class="alert-banner-link" onclick="app.showPage('alerts')">View alerts →</span>`;
            } else {
                alertBanner.classList.add('hidden');
            }

            // Health banner
            const healthBanner = document.getElementById('health-banner');
            if (healthAlerts.length > 0) {
                healthBanner.classList.remove('hidden');
                healthBanner.querySelector('.alert-banner-text').innerHTML =
                    `🔧 <strong>${healthAlerts.length} scraper(s) need attention</strong> — Structure changes detected. <span class="alert-banner-link" onclick="app.showPage('history')">View details →</span>`;
            } else {
                healthBanner.classList.add('hidden');
            }

            // Brand cards
            document.getElementById('brand-grid').innerHTML =
                brands.map(b => components.renderBrandCard(b)).join('');

            // Update nav badge
            this.updateAlertBadge(stats.active_alerts);

        } catch (err) {
            components.toast('Failed to load dashboard: ' + err.message, 'error');
        }
    },

    // ── Scraping ──────────────────────────────────────────────────────
    async scrape(brandSlug) {
        const btn = document.getElementById(`scrape-btn-${brandSlug}`);
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner spinner-sm"></span> Scraping...';
        }

        try {
            const result = await api.startScrape(brandSlug);
            components.toast(`Scrape started for ${brandSlug}`, 'info');

            // Poll for completion
            this.pollScrapeJob(result.job_id, brandSlug);

        } catch (err) {
            components.toast(err.message, 'error');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '🔍 Scrape';
            }
        }
    },

    async scrapeAll() {
        const btn = document.getElementById('scrape-all-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner spinner-sm"></span> Scraping All...';
        }

        try {
            const result = await api.startScrapeAll();
            components.toast(`Scraping started for ${result.started.length} brands`, 'info');

            // Reset button after a delay
            setTimeout(() => {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '🔍 Scrape All';
                }
            }, 3000);

            // Refresh dashboard periodically
            this.startDashboardPolling();

        } catch (err) {
            components.toast(err.message, 'error');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '🔍 Scrape All';
            }
        }
    },

    async clearDatabase() {
        if (!confirm('Are you sure you want to clear the database? This will delete all products, variants, alerts, and history. Brands will be kept. This action cannot be undone.')) {
            return;
        }

        const btn = document.getElementById('clear-db-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner spinner-sm"></span> Clearing...';
        }

        try {
            const res = await api.clearDatabase();
            components.toast(res.message || 'Database cleared successfully', 'success');
            await this.loadDashboard();
        } catch (err) {
            components.toast(err.message, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '🗑️ Clear Database';
            }
        }
    },

    pollScrapeJob(jobId, brandSlug) {
        const interval = setInterval(async () => {
            try {
                const status = await api.getScrapeStatus(jobId);
                if (['completed', 'warning', 'failed'].includes(status.status)) {
                    clearInterval(interval);

                    const msg = status.status === 'completed'
                        ? `✅ ${status.brand}: ${status.products_found} products scraped`
                        : status.status === 'warning'
                            ? `⚠️ ${status.brand}: Completed with warnings`
                            : `❌ ${status.brand}: Scrape failed`;

                    components.toast(msg, status.status === 'completed' ? 'success' : 'error');

                    // Refresh current page
                    await this.showPage(this.currentPage);
                }
            } catch (err) {
                clearInterval(interval);
            }
        }, 3000);

        // Auto-stop after 10 minutes
        setTimeout(() => clearInterval(interval), 600000);
    },

    startDashboardPolling() {
        if (this.pollingIntervals.dashboard) clearInterval(this.pollingIntervals.dashboard);

        this.pollingIntervals.dashboard = setInterval(async () => {
            if (this.currentPage === 'dashboard') {
                await this.loadDashboard();
            }
        }, 5000);

        // Stop after 10 minutes
        setTimeout(() => {
            clearInterval(this.pollingIntervals.dashboard);
            this.pollingIntervals.dashboard = null;
        }, 600000);
    },

    // ── Products ──────────────────────────────────────────────────────
    async loadProducts() {
        try {
            // Populate brand filter if not done
            const brandSelect = document.getElementById('filter-brand');
            if (brandSelect && brandSelect.options.length <= 1) {
                const brands = await api.getBrands();
                brands.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.slug;
                    opt.textContent = b.name;
                    brandSelect.appendChild(opt);
                });
            }

            const data = await api.getProducts(this.productFilters);

            const tbody = document.getElementById('products-tbody');
            if (data.products.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7">
                    <div class="empty-state">
                        <div class="empty-state-icon">📦</div>
                        <div class="empty-state-title">No products found</div>
                        <div class="empty-state-text">Start scraping to populate your inventory data.</div>
                    </div>
                </td></tr>`;
            } else {
                tbody.innerHTML = data.products.map(p => components.renderProductRow(p)).join('');
            }

            // Pagination
            document.getElementById('products-pagination').innerHTML =
                components.renderPagination(data.page, data.pages);

        } catch (err) {
            components.toast('Failed to load products: ' + err.message, 'error');
        }
    },

    toggleProduct(productId) {
        const row = document.getElementById(`detail-${productId}`);
        if (row) {
            row.classList.toggle('expanded');
        }
    },

    goToPage(page) {
        this.productFilters.page = page;
        this.loadProducts();
    },

    filterProducts() {
        this.productFilters.brand = document.getElementById('filter-brand').value;
        this.productFilters.in_stock = document.getElementById('filter-stock').value;
        this.productFilters.page = 1;
        this.loadProducts();
    },

    searchProducts() {
        clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(() => {
            this.productFilters.search = document.getElementById('search-input').value;
            this.productFilters.page = 1;
            this.loadProducts();
        }, 400);
    },

    // ── Alerts ─────────────────────────────────────────────────────────
    async loadAlerts() {
        try {
            // Brand filter
            const brandSelect = document.getElementById('alert-filter-brand');
            if (brandSelect && brandSelect.options.length <= 1) {
                const brands = await api.getBrands();
                brands.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.slug;
                    opt.textContent = b.name;
                    brandSelect.appendChild(opt);
                });
            }

            // Load threshold
            const settings = await api.getAlertSettings();
            const slider = document.getElementById('threshold-slider');
            const valueEl = document.getElementById('threshold-value');
            if (slider) slider.value = settings.low_stock_threshold;
            if (valueEl) valueEl.textContent = settings.low_stock_threshold;

            // Load alerts
            const alerts = await api.getAlerts(this.alertFilters);

            // Summary
            const lowStock = alerts.filter(a => a.alert_type === 'low_stock').length;
            const outOfStock = alerts.filter(a => a.alert_type === 'out_of_stock').length;
            const brands = new Set(alerts.map(a => a.brand.slug)).size;

            document.getElementById('alert-summary').innerHTML = `
                <div class="alert-summary-stat"><span class="dot amber"></span> ${lowStock} Low Stock</div>
                <div class="alert-summary-stat"><span class="dot red"></span> ${outOfStock} Out of Stock</div>
                <div class="alert-summary-stat"><span class="dot blue"></span> ${brands} Brand(s)</div>
            `;

            // Alert cards
            const grid = document.getElementById('alert-grid');
            if (alerts.length === 0) {
                grid.innerHTML = `
                    <div class="empty-state" style="grid-column: 1 / -1;">
                        <div class="empty-state-icon">✅</div>
                        <div class="empty-state-title">No active alerts</div>
                        <div class="empty-state-text">All inventory levels look healthy! Scrape your brands to check for updates.</div>
                    </div>`;
            } else {
                grid.innerHTML = alerts.map(a => components.renderAlertCard(a)).join('');
            }

        } catch (err) {
            components.toast('Failed to load alerts: ' + err.message, 'error');
        }
    },

    filterAlerts() {
        this.alertFilters.brand = document.getElementById('alert-filter-brand').value;
        this.alertFilters.alert_type = document.getElementById('alert-filter-type').value;
        this.loadAlerts();
    },

    async updateThreshold() {
        const slider = document.getElementById('threshold-slider');
        const valueEl = document.getElementById('threshold-value');
        const value = parseInt(slider.value);
        valueEl.textContent = value;

        try {
            await api.updateAlertSettings(value);
            components.toast(`Alert threshold updated to ${value}`, 'success');
        } catch (err) {
            components.toast('Failed to update threshold: ' + err.message, 'error');
        }
    },

    // ── History ────────────────────────────────────────────────────────
    async loadHistory() {
        try {
            const jobs = await api.getScrapeHistory(50);
            const container = document.getElementById('history-list');

            if (jobs.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📋</div>
                        <div class="empty-state-title">No scrape history</div>
                        <div class="empty-state-text">Start scraping brands to see your history here.</div>
                    </div>`;
            } else {
                container.innerHTML = jobs.map(j => components.renderHistoryItem(j)).join('');
            }

        } catch (err) {
            components.toast('Failed to load history: ' + err.message, 'error');
        }
    },

    // ── Export ─────────────────────────────────────────────────────────
    exportCSV() {
        api.exportData('csv', this.productFilters.brand || null);
        document.getElementById('export-menu').classList.remove('show');
        components.toast('Downloading CSV...', 'info');
    },

    exportExcel() {
        api.exportData('xlsx', this.productFilters.brand || null);
        document.getElementById('export-menu').classList.remove('show');
        components.toast('Downloading Excel...', 'info');
    },

    // ── Helpers ────────────────────────────────────────────────────────
    updateAlertBadge(count) {
        const badge = document.getElementById('alert-nav-badge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline';
            } else {
                badge.style.display = 'none';
            }
        }
    },

    // ── Shopify Sync ──────────────────────────────────────────────────
    async loadShopify() {
        try {
            const [status, config] = await Promise.all([
                api.getShopifySyncStatus(),
                api.getShopifyConfig(),
            ]);

            // Config warning
            const warning = document.getElementById('shopify-config-warning');
            if (!config.is_configured) {
                warning.classList.remove('hidden');
            } else {
                warning.classList.add('hidden');
            }

            // Stats bar
            document.getElementById('shopify-stats-bar').innerHTML = components.renderShopifyStats(status);

            // Populate brand filter
            const brandSelect = document.getElementById('shopify-brand-filter');
            if (brandSelect && brandSelect.options.length <= 1) {
                const brands = await api.getBrands();
                brands.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.slug;
                    opt.textContent = b.name;
                    brandSelect.appendChild(opt);
                });
            }

            // Update buttons
            const syncBtn = document.getElementById('shopify-sync-btn');
            const retryBtn = document.getElementById('shopify-retry-btn');
            if (status.is_running) {
                syncBtn.disabled = true;
                syncBtn.innerHTML = '<span class="spinner spinner-sm"></span> Syncing...';
                retryBtn.disabled = true;
                this.startShopifyPolling();
            } else {
                syncBtn.disabled = !config.is_configured;
                syncBtn.innerHTML = '🚀 Start Sync';
                retryBtn.disabled = status.failed_products === 0;
            }

            // Bind sync mode visual feedback
            const modeSelect = document.getElementById('shopify-sync-mode');
            if (modeSelect && !modeSelect._bound) {
                modeSelect._bound = true;
                modeSelect.addEventListener('change', () => {
                    if (modeSelect.value === 'publish') {
                        modeSelect.classList.add('publish-mode');
                    } else {
                        modeSelect.classList.remove('publish-mode');
                    }
                });
            }

            // Progress bar
            this.updateShopifyProgress(status);

            // History
            await this.loadShopifyHistory();

        } catch (err) {
            components.toast('Failed to load Shopify sync: ' + err.message, 'error');
        }
    },

    async loadShopifyHistory() {
        try {
            const history = await api.getShopifySyncHistory(20);
            const container = document.getElementById('shopify-history-list');

            if (history.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">🛍️</div>
                        <div class="empty-state-title">No sync history</div>
                        <div class="empty-state-text">Start syncing products to Shopify to see your history here.</div>
                    </div>`;
            } else {
                container.innerHTML = history.map(j => components.renderShopifySyncItem(j)).join('');
            }
        } catch (err) {
            // Silently fail — main status already loaded
        }
    },

    async startShopifySync() {
        const brand = document.getElementById('shopify-brand-filter').value;
        const modeSelect = document.getElementById('shopify-sync-mode');
        const mode = modeSelect ? modeSelect.value : 'draft';
        const syncBtn = document.getElementById('shopify-sync-btn');

        syncBtn.disabled = true;
        syncBtn.innerHTML = '<span class="spinner spinner-sm"></span> Starting...';

        // Confirm before publishing live
        if (mode === 'publish') {
            const confirmed = confirm(
                '⚠️ PUBLISH MODE\n\n'
                + 'Products will be set to ACTIVE and visible to customers on your Shopify store.\n\n'
                + 'Are you sure you want to continue?'
            );
            if (!confirmed) {
                syncBtn.disabled = false;
                syncBtn.innerHTML = '🚀 Start Sync';
                return;
            }
        }

        try {
            let result;
            if (brand) {
                result = await api.startShopifySyncBrand(brand, mode);
            } else {
                result = await api.startShopifySync(mode);
            }

            if (result.error) {
                components.toast(result.error, 'error');
                syncBtn.disabled = false;
                syncBtn.innerHTML = '🚀 Start Sync';
                return;
            }

            components.toast(result.message, 'info');
            this.startShopifyPolling();

        } catch (err) {
            components.toast(err.message, 'error');
            syncBtn.disabled = false;
            syncBtn.innerHTML = '🚀 Start Sync';
        }
    },

    startShopifyPolling() {
        if (this.pollingIntervals.shopify) clearInterval(this.pollingIntervals.shopify);

        this.pollingIntervals.shopify = setInterval(async () => {
            try {
                const status = await api.getShopifySyncStatus();
                this.updateShopifyProgress(status);

                // Update stats
                document.getElementById('shopify-stats-bar').innerHTML =
                    components.renderShopifyStats(status);

                if (!status.is_running) {
                    clearInterval(this.pollingIntervals.shopify);
                    this.pollingIntervals.shopify = null;

                    const syncBtn = document.getElementById('shopify-sync-btn');
                    syncBtn.disabled = false;
                    syncBtn.innerHTML = '🚀 Start Sync';

                    const retryBtn = document.getElementById('shopify-retry-btn');
                    retryBtn.disabled = status.failed_products === 0;

                    const job = status.latest_job;
                    if (job) {
                        const msg = job.failed === 0
                            ? `✅ Sync complete: ${job.completed} products uploaded`
                            : `⚠️ Sync done: ${job.completed} uploaded, ${job.failed} failed`;
                        components.toast(msg, job.failed === 0 ? 'success' : 'error');
                    }

                    await this.loadShopifyHistory();
                }
            } catch (err) {
                // Silently continue polling
            }
        }, 3000);

        // Auto-stop after 30 min
        setTimeout(() => {
            if (this.pollingIntervals.shopify) {
                clearInterval(this.pollingIntervals.shopify);
                this.pollingIntervals.shopify = null;
            }
        }, 1800000);
    },

    updateShopifyProgress(status) {
        const progress = document.getElementById('shopify-progress');
        const bar = document.getElementById('shopify-progress-bar');
        const stats = document.getElementById('shopify-progress-stats');

        if (status.is_running && status.latest_job) {
            progress.classList.remove('hidden');
            const job = status.latest_job;
            const done = (job.completed || 0) + (job.failed || 0);
            const total = job.total_products || 1;
            const pct = Math.min(100, Math.round((done / total) * 100));
            bar.style.width = `${pct}%`;
            stats.textContent = `${done} / ${total} (${pct}%)`;
        } else {
            progress.classList.add('hidden');
        }
    },

    async viewShopifyLogs(jobId) {
        try {
            const logs = await api.getShopifySyncLogs(jobId);
            const viewer = document.getElementById('shopify-log-viewer');
            document.getElementById('log-viewer-job-id').textContent = jobId;

            const completed = logs.filter(l => l.status === 'completed').length;
            const failed = logs.filter(l => l.status === 'failed').length;
            document.getElementById('log-viewer-summary').innerHTML = `
                <span class="log-stat completed">✅ ${completed} Completed</span>
                <span class="log-stat failed">❌ ${failed} Failed</span>
                <span class="log-stat total">📦 ${logs.length} Total</span>
            `;

            const tbody = document.getElementById('shopify-logs-tbody');
            if (logs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">📋</div><div class="empty-state-title">No logs</div></div></td></tr>';
            } else {
                tbody.innerHTML = logs.map(l => components.renderShopifySyncLogRow(l)).join('');
            }

            viewer.classList.remove('hidden');
            viewer.scrollIntoView({ behavior: 'smooth' });

        } catch (err) {
            components.toast('Failed to load sync logs: ' + err.message, 'error');
        }
    },

    closeShopifyLogs() {
        document.getElementById('shopify-log-viewer').classList.add('hidden');
    },

    async retryFailedShopify() {
        const btn = document.getElementById('shopify-retry-btn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner spinner-sm"></span> Retrying...';

        try {
            const result = await api.retryFailedSync();
            if (result.error) {
                components.toast(result.error, 'error');
            } else {
                components.toast(result.message, 'success');
                await this.loadShopify();
            }
        } catch (err) {
            components.toast(err.message, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '🔄 Retry Failed';
        }
    },
};

// ── Boot ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => app.init());
