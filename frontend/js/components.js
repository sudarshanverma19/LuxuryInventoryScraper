/**
 * InventoryScraper — UI Component Renderers
 */

const components = {
    // ── Stats Bar ─────────────────────────────────────────────────────
    renderStats(stats) {
        return `
            <div class="stat-card">
                <div class="stat-icon purple">📦</div>
                <div class="stat-info">
                    <div class="stat-value">${stats.total_products}</div>
                    <div class="stat-label">Total Products</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon teal">🏷️</div>
                <div class="stat-info">
                    <div class="stat-value">${stats.active_brands}</div>
                    <div class="stat-label">Brands Active</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon green">✅</div>
                <div class="stat-info">
                    <div class="stat-value">${stats.in_stock_products}</div>
                    <div class="stat-label">In Stock</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon amber">⚠️</div>
                <div class="stat-info">
                    <div class="stat-value">${stats.active_alerts}</div>
                    <div class="stat-label">Active Alerts</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon red">🔧</div>
                <div class="stat-info">
                    <div class="stat-value">${stats.active_health_alerts}</div>
                    <div class="stat-label">Health Issues</div>
                </div>
            </div>
        `;
    },

    // ── Brand Card ────────────────────────────────────────────────────
    renderBrandCard(brand) {
        const initials = brand.name.split(' ').map(w => w[0]).join('').substring(0, 2);
        const lastScrape = brand.last_scrape
            ? this.timeAgo(brand.last_scrape.completed_at || brand.last_scrape.started_at)
            : 'Never';
        const statusText = brand.last_scrape ? brand.last_scrape.status : 'No data';

        return `
            <div class="brand-card" data-brand-slug="${brand.slug}">
                <div class="brand-card-header">
                    <div class="brand-info">
                        <div class="brand-avatar">${initials}</div>
                        <div>
                            <div class="brand-name">${brand.name}</div>
                            <div class="brand-category">${brand.category || ''}</div>
                        </div>
                    </div>
                    ${brand.alert_count > 0 ? `<div class="brand-alert-badge">⚠️ ${brand.alert_count}</div>` : ''}
                </div>
                <div class="brand-card-stats">
                    <div class="brand-stat">
                        <div class="brand-stat-value">${brand.product_count}</div>
                        <div class="brand-stat-label">Products</div>
                    </div>
                    <div class="brand-stat">
                        <div class="brand-stat-value">${brand.last_scrape ? brand.last_scrape.products_found : 0}</div>
                        <div class="brand-stat-label">Last Found</div>
                    </div>
                    <div class="brand-stat">
                        <div class="brand-stat-value">${this.statusIcon(statusText)}</div>
                        <div class="brand-stat-label">Status</div>
                    </div>
                </div>
                <div class="brand-card-footer">
                    <div class="brand-last-scrape">Last: ${lastScrape}</div>
                    <button class="btn btn-primary btn-sm" onclick="app.scrape('${brand.slug}')"
                        id="scrape-btn-${brand.slug}" ${brand.is_scraping ? 'disabled' : ''}>
                        ${brand.is_scraping ? '<span class="spinner spinner-sm"></span> Scraping...' : '🔍 Scrape'}
                    </button>
                </div>
            </div>
        `;
    },

    // ── Product Row ───────────────────────────────────────────────────
    renderProductRow(product) {
        const colors = product.colors.slice(0, 4).map(c =>
            `<span class="color-chip">${c}</span>`
        ).join('');
        const moreColors = product.colors.length > 4
            ? `<span class="color-chip">+${product.colors.length - 4}</span>` : '';

        const stockClass = product.in_stock ? 'in-stock' : 'out-of-stock';
        const stockText = product.in_stock ? 'In Stock' : 'Out of Stock';
        const stockDot = product.in_stock ? '●' : '●';

        const sizes = product.sizes.slice(0, 5).map(s =>
            `<span class="size-tag">${s}</span>`
        ).join('');
        const moreSizes = product.sizes.length > 5
            ? `<span class="size-tag">+${product.sizes.length - 5}</span>` : '';

        return `
            <tr class="product-row" data-product-id="${product.id}" onclick="app.toggleProduct(${product.id})">
                <td><strong>${product.brand.name}</strong></td>
                <td>${product.name}</td>
                <td>${product.category || '-'}</td>
                <td>${product.price ? `$${product.price.toFixed(2)}` : '-'}</td>
                <td><div class="color-chips">${colors}${moreColors}</div></td>
                <td><div class="size-tags">${sizes}${moreSizes}</div></td>
                <td><span class="stock-badge ${stockClass}">${stockDot} ${stockText}</span></td>
            </tr>
            <tr class="product-detail-row" id="detail-${product.id}">
                <td colspan="7">
                    <div class="product-detail-content">
                        <div style="margin-bottom: 0.75rem; font-size: 0.85rem;">
                            <strong>Variants (${product.variants.length}):</strong>
                            <a href="${product.url}" target="_blank" style="color: var(--accent-purple-light); margin-left: 1rem; font-size: 0.8rem;">View on website →</a>
                        </div>
                        <div class="variant-grid">
                            ${product.variants.map(v => this.renderVariantCard(v)).join('')}
                        </div>
                    </div>
                </td>
            </tr>
        `;
    },

    renderVariantCard(variant) {
        const stockClass = variant.in_stock ? 'in-stock' : 'out-of-stock';
        const stockText = variant.in_stock ? 'In Stock' : 'Out of Stock';

        return `
            <div class="variant-card">
                ${variant.size ? `<div class="variant-attr"><span class="variant-label">Size</span><span>${variant.size}</span></div>` : ''}
                ${variant.color ? `<div class="variant-attr"><span class="variant-label">Color</span><span>${variant.color}</span></div>` : ''}
                ${variant.quantity !== null && variant.quantity !== undefined ? `<div class="variant-attr"><span class="variant-label">Qty</span><span>${variant.quantity}</span></div>` : ''}
                ${variant.sku ? `<div class="variant-attr"><span class="variant-label">SKU</span><span>${variant.sku}</span></div>` : ''}
                <div class="variant-attr"><span class="variant-label">Stock</span><span class="stock-badge ${stockClass}" style="font-size: 0.65rem; padding: 1px 6px;">${stockText}</span></div>
            </div>
        `;
    },

    // ── Alert Card ────────────────────────────────────────────────────
    renderAlertCard(alert) {
        const typeClass = alert.alert_type === 'out_of_stock' ? 'out-of-stock' : 'low-stock';
        const typeLabel = alert.alert_type === 'out_of_stock' ? '🔴 Out of Stock' : '🟡 Low Stock';

        return `
            <div class="alert-card ${typeClass}">
                <div class="alert-card-header">
                    <div>
                        <div class="alert-product-name">${alert.product.name}</div>
                        <div class="alert-brand">${alert.brand.name}</div>
                    </div>
                    <span class="stock-badge ${typeClass}">${typeLabel}</span>
                </div>
                <div class="alert-details">
                    ${alert.variant.size ? `<div class="alert-detail"><strong>Size:</strong> ${alert.variant.size}</div>` : ''}
                    ${alert.variant.color ? `<div class="alert-detail"><strong>Color:</strong> ${alert.variant.color}</div>` : ''}
                    ${alert.quantity !== null && alert.quantity !== undefined ? `<div class="alert-detail"><strong>Qty:</strong> ${alert.quantity}</div>` : ''}
                </div>
                <a href="${alert.product.url}" target="_blank" class="alert-visit-link">View on website →</a>
            </div>
        `;
    },

    // ── History Item ──────────────────────────────────────────────────
    renderHistoryItem(job) {
        const icon = this.statusIcon(job.status);
        const duration = job.completed_at && job.started_at
            ? this.duration(job.started_at, job.completed_at)
            : 'Running...';

        return `
            <div class="history-item">
                <div class="history-status-icon ${job.status}">${icon}</div>
                <div class="history-info">
                    <div class="history-brand">${job.brand_name}</div>
                    <div class="history-meta">
                        <span>${this.formatDate(job.started_at)}</span>
                        <span>Duration: ${duration}</span>
                    </div>
                </div>
                <div class="history-stats">
                    <span>📦 ${job.products_found} products</span>
                    <span>${job.variants_found} variants</span>
                </div>
                <span class="stock-badge ${job.status === 'completed' ? 'in-stock' : job.status === 'warning' ? 'low-stock' : job.status === 'failed' ? 'out-of-stock' : ''}">${job.status}</span>
            </div>
        `;
    },

    // ── Pagination ────────────────────────────────────────────────────
    renderPagination(page, totalPages) {
        if (totalPages <= 1) return '';

        let buttons = '';
        buttons += `<button class="pagination-btn" ${page <= 1 ? 'disabled' : ''} onclick="app.goToPage(${page - 1})">← Prev</button>`;

        const start = Math.max(1, page - 2);
        const end = Math.min(totalPages, page + 2);

        if (start > 1) {
            buttons += `<button class="pagination-btn" onclick="app.goToPage(1)">1</button>`;
            if (start > 2) buttons += `<span class="pagination-info">...</span>`;
        }

        for (let i = start; i <= end; i++) {
            buttons += `<button class="pagination-btn ${i === page ? 'active' : ''}" onclick="app.goToPage(${i})">${i}</button>`;
        }

        if (end < totalPages) {
            if (end < totalPages - 1) buttons += `<span class="pagination-info">...</span>`;
            buttons += `<button class="pagination-btn" onclick="app.goToPage(${totalPages})">${totalPages}</button>`;
        }

        buttons += `<button class="pagination-btn" ${page >= totalPages ? 'disabled' : ''} onclick="app.goToPage(${page + 1})">Next →</button>`;

        return buttons;
    },

    // ── Utilities ─────────────────────────────────────────────────────
    statusIcon(status) {
        const map = { completed: '✅', warning: '⚠️', failed: '❌', running: '🔄', pending: '⏳' };
        return map[status] || '—';
    },

    timeAgo(isoDate) {
        if (!isoDate) return 'Never';
        const diff = Date.now() - new Date(isoDate).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'Just now';
        if (mins < 60) return `${mins}m ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        return `${days}d ago`;
    },

    formatDate(isoDate) {
        if (!isoDate) return '-';
        return new Date(isoDate).toLocaleString();
    },

    duration(start, end) {
        const diff = new Date(end) - new Date(start);
        const secs = Math.floor(diff / 1000);
        if (secs < 60) return `${secs}s`;
        const mins = Math.floor(secs / 60);
        const remainSecs = secs % 60;
        return `${mins}m ${remainSecs}s`;
    },

    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span>${this.statusIcon(type === 'success' ? 'completed' : type === 'error' ? 'failed' : 'running')}</span><span>${message}</span>`;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    },

    // ── Shopify Sync Components ───────────────────────────────────────
    renderShopifyStats(status) {
        return `
            <div class="stat-card shopify-stat">
                <div class="stat-icon purple">🛍️</div>
                <div class="stat-info">
                    <div class="stat-value">${status.is_running ? '🔄 Running' : '⏸️ Idle'}</div>
                    <div class="stat-label">Sync Status</div>
                </div>
            </div>
            <div class="stat-card shopify-stat">
                <div class="stat-icon amber">⏳</div>
                <div class="stat-info">
                    <div class="stat-value">${status.pending_products}</div>
                    <div class="stat-label">Pending</div>
                </div>
            </div>
            <div class="stat-card shopify-stat">
                <div class="stat-icon green">✅</div>
                <div class="stat-info">
                    <div class="stat-value">${status.completed_products}</div>
                    <div class="stat-label">Uploaded</div>
                </div>
            </div>
            <div class="stat-card shopify-stat">
                <div class="stat-icon red">❌</div>
                <div class="stat-info">
                    <div class="stat-value">${status.failed_products}</div>
                    <div class="stat-label">Failed</div>
                </div>
            </div>
        `;
    },

    renderShopifySyncItem(job) {
        const icon = this.statusIcon(job.status);
        const duration = job.completed_at && job.started_at
            ? this.duration(job.started_at, job.completed_at)
            : job.status === 'running' ? 'Running...' : '-';

        const brandLabel = job.brand_filter
            ? `<span class="sync-brand-tag">${job.brand_filter}</span>`
            : '<span class="sync-brand-tag all">All Brands</span>';

        return `
            <div class="history-item shopify-sync-item">
                <div class="history-status-icon ${job.status}">${icon}</div>
                <div class="history-info">
                    <div class="history-brand">Sync Job #${job.id} ${brandLabel}</div>
                    <div class="history-meta">
                        <span>${this.formatDate(job.started_at)}</span>
                        <span>Duration: ${duration}</span>
                    </div>
                </div>
                <div class="history-stats shopify-sync-stats">
                    <span class="sync-stat-completed">✅ ${job.completed || 0}</span>
                    <span class="sync-stat-failed">❌ ${job.failed || 0}</span>
                    <span class="sync-stat-skipped">⏭️ ${job.skipped || 0}</span>
                </div>
                <button class="btn btn-secondary btn-sm" onclick="app.viewShopifyLogs(${job.id})">📋 Logs</button>
                <span class="stock-badge ${job.status === 'completed' ? 'in-stock' : job.status === 'failed' ? 'out-of-stock' : ''}">${job.status}</span>
            </div>
        `;
    },

    renderShopifySyncLogRow(log) {
        const statusClass = log.status === 'completed' ? 'in-stock' : 'out-of-stock';
        const statusText = log.status === 'completed' ? '✅ Completed' : '❌ Failed';
        const shopifyId = log.shopify_product_id
            ? `<code class="shopify-id">${log.shopify_product_id.replace('gid://shopify/Product/', '#')}</code>`
            : '-';
        const errorMsg = log.error_message
            ? `<span class="log-error" title="${log.error_message}">${log.error_message.substring(0, 80)}${log.error_message.length > 80 ? '...' : ''}</span>`
            : '-';

        return `
            <tr>
                <td><strong>${log.product_name}</strong></td>
                <td>${log.brand_name}</td>
                <td><span class="stock-badge ${statusClass}" style="font-size: 0.75rem;">${statusText}</span></td>
                <td>${log.images_uploaded}/${log.image_count}</td>
                <td>${shopifyId}</td>
                <td>${errorMsg}</td>
            </tr>
        `;
    },
};
