/**
 * InventoryScraper — API Client
 * Handles all communication with the FastAPI backend.
 */

const API_BASE = '';

const api = {
    async get(endpoint) {
        const res = await fetch(`${API_BASE}${endpoint}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return res.json();
    },

    async post(endpoint, body = null) {
        const opts = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
        if (body) opts.body = JSON.stringify(body);
        const res = await fetch(`${API_BASE}${endpoint}`, opts);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return res.json();
    },

    async put(endpoint, body) {
        const res = await fetch(`${API_BASE}${endpoint}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return res.json();
    },

    // ── Brands
    getBrands: () => api.get('/api/brands'),

    // ── Scraping
    startScrape: (slug) => api.post(`/api/scrape/${slug}`),
    startScrapeAll: () => api.post('/api/scrape/all'),
    getScrapeStatus: (jobId) => api.get(`/api/scrape/status/${jobId}`),
    getScrapeHistory: (limit = 50) => api.get(`/api/scrape/history?limit=${limit}`),

    // ── Products
    getProducts: (params = {}) => {
        const qs = new URLSearchParams();
        if (params.brand) qs.set('brand', params.brand);
        if (params.search) qs.set('search', params.search);
        if (params.category) qs.set('category', params.category);
        if (params.in_stock !== undefined && params.in_stock !== '') qs.set('in_stock', params.in_stock);
        if (params.page) qs.set('page', params.page);
        if (params.per_page) qs.set('per_page', params.per_page);
        return api.get(`/api/products?${qs.toString()}`);
    },
    getProduct: (id) => api.get(`/api/products/${id}`),

    // ── Alerts
    getAlerts: (params = {}) => {
        const qs = new URLSearchParams();
        if (params.brand) qs.set('brand', params.brand);
        if (params.alert_type) qs.set('alert_type', params.alert_type);
        return api.get(`/api/alerts?${qs.toString()}`);
    },
    getAlertSettings: () => api.get('/api/alerts/settings'),
    updateAlertSettings: (threshold) => api.put('/api/alerts/settings', { threshold }),
    getHealthAlerts: (resolved = false) => api.get(`/api/health-alerts?resolved=${resolved}`),

    // ── Export
    exportData: (format = 'csv', brand = null) => {
        const qs = new URLSearchParams({ format });
        if (brand) qs.set('brand', brand);
        window.location.href = `${API_BASE}/api/export?${qs.toString()}`;
    },

    // ── Stats
    getStats: () => api.get('/api/stats'),
};
