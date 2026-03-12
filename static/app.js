/**
 * app.js — Shared utilities for Case-IMS frontend.
 * Handles auth state, API calls, and common UI helpers.
 */

const IMS = {
    token: localStorage.getItem('token'),
    user: null,

    init() {
        const stored = localStorage.getItem('user');
        if (stored) {
            try { this.user = JSON.parse(stored); } catch { this.user = null; }
        }
        this._updateNav();
    },

    _updateNav() {
        const emailEl = document.getElementById('user-email');
        const loginNav = document.getElementById('nav-login');
        const logoutNav = document.getElementById('nav-logout');
        const adminNav = document.getElementById('nav-admin');

        if (this.token && this.user) {
            if (emailEl) emailEl.textContent = this.user.email;
            if (loginNav) loginNav.classList.add('d-none');
            if (logoutNav) logoutNav.classList.remove('d-none');
            if (adminNav && this.user.is_admin) adminNav.classList.remove('d-none');
        } else {
            if (emailEl) emailEl.textContent = '';
            if (loginNav) loginNav?.classList.remove('d-none');
            if (logoutNav) logoutNav?.classList.add('d-none');
        }

        // Logout handler
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.logout();
            });
        }
    },

    logout() {
        // Call backend logout
        if (this.token) {
            fetch('/auth/logout', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + this.token },
            }).catch(() => {});
        }
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        this.token = null;
        this.user = null;
        window.location.href = '/static/login.html';
    },

    async api(path, options = {}) {
        const headers = options.headers || {};
        if (this.token && !headers['Authorization']) {
            headers['Authorization'] = 'Bearer ' + this.token;
        }
        if (options.json) {
            headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(options.json);
            delete options.json;
        }
        options.headers = headers;

        const res = await fetch(path, options);

        if (res.status === 401) {
            this.logout();
            throw new Error('Session expired');
        }
        if (!res.ok) {
            let detail = `Error ${res.status}`;
            try {
                const err = await res.json();
                detail = err.detail || detail;
            } catch {}
            throw new Error(detail);
        }
        return res.json();
    },

    // HTML escape to prevent XSS
    esc(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    },

    // File type icon mapping
    typeIcon(fileType) {
        const map = {
            pdf: 'fas fa-file-pdf text-danger',
            image: 'fas fa-file-image text-success',
            audio: 'fas fa-file-audio text-info',
            video: 'fas fa-file-video text-warning',
            table: 'fas fa-file-csv text-primary',
            other: 'fas fa-file-alt text-secondary',
        };
        return map[fileType] || map.other;
    },

    // Status badge
    statusBadge(status) {
        const map = {
            pending: '<span class="badge bg-warning status-badge">ממתין</span>',
            processing: '<span class="badge bg-info status-badge">בעיבוד</span>',
            done: '<span class="badge bg-success status-badge">הושלם</span>',
            failed: '<span class="badge bg-danger status-badge">נכשל</span>',
        };
        return map[status] || `<span class="badge bg-secondary status-badge">${this.esc(status)}</span>`;
    },

    // Format file size
    formatSize(bytes) {
        if (!bytes) return '-';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    },

    // Format date
    formatDate(dateStr) {
        if (!dateStr) return '-';
        try {
            const d = new Date(dateStr);
            return d.toLocaleDateString('he-IL') + ' ' + d.toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' });
        } catch {
            return dateStr;
        }
    },

    // Toast notification
    toast(message, type = 'info') {
        const container = document.getElementById('toast-container') || (() => {
            const div = document.createElement('div');
            div.id = 'toast-container';
            div.style.cssText = 'position:fixed;top:1rem;left:50%;transform:translateX(-50%);z-index:9999;';
            document.body.appendChild(div);
            return div;
        })();

        const colors = { success: 'bg-success', error: 'bg-danger', warning: 'bg-warning text-dark', info: 'bg-info' };
        const toast = document.createElement('div');
        toast.className = `alert ${colors[type] || colors.info} text-white py-2 px-3 mb-2 shadow`;
        toast.style.cssText = 'min-width:250px;max-width:400px;border-radius:0.5rem;animation:fadeIn 0.3s;';
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 4000);
    },
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => IMS.init());
