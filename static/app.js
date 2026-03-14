/**
 * app.js — Shared utilities for Case-IMS frontend.
 * Handles auth state, API calls, and common UI helpers.
 */

const IMS = {
    token: localStorage.getItem('token'),
    user: null,
    currentCaseId: null,
    _cases: [],

    init() {
        const stored = localStorage.getItem('user');
        if (stored) {
            try { this.user = JSON.parse(stored); } catch { this.user = null; }
        }
        // Restore case selection
        const savedCase = localStorage.getItem('currentCaseId');
        if (savedCase) this.currentCaseId = parseInt(savedCase);
        this._updateNav();
        if (this.token) this.loadCases();
    },

    async loadCases() {
        try {
            this._cases = await this.api('/cases/');
            this._renderCaseSelector();
        } catch (err) { console.warn('Failed to load cases:', err); }
    },

    _renderCaseSelector() {
        const sel = document.getElementById('global-case-select');
        if (!sel) return;
        sel.innerHTML = '';
        if (!this._cases.length) {
            sel.innerHTML = '<option value="">אין תיקים</option>';
            this.currentCaseId = null;
            localStorage.removeItem('currentCaseId');
            return;
        }
        this._cases.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name;
            sel.appendChild(opt);
        });
        // Restore selection or default to first
        if (this.currentCaseId && this._cases.some(c => c.id === this.currentCaseId)) {
            sel.value = this.currentCaseId;
        } else {
            this.currentCaseId = this._cases[0].id;
            sel.value = this.currentCaseId;
            localStorage.setItem('currentCaseId', this.currentCaseId);
        }
        // Fire initial case-changed so pages load data
        document.dispatchEvent(new CustomEvent('case-changed', { detail: { caseId: this.currentCaseId } }));
        sel.addEventListener('change', () => {
            const newId = parseInt(sel.value);
            if (newId !== this.currentCaseId) {
                this.currentCaseId = newId;
                localStorage.setItem('currentCaseId', newId);
                document.dispatchEvent(new CustomEvent('case-changed', { detail: { caseId: newId } }));
            }
        });
    },

    requireCase() {
        if (!this.currentCaseId) {
            this.toast('יש לבחור תיק לפני ביצוע פעולה', 'error');
            return null;
        }
        return this.currentCaseId;
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

    // Detailed file type icon based on extension
    typeIconDetailed(fileType, filename) {
        if (!filename) return this.typeIcon(fileType);
        const ext = (filename.split('.').pop() || '').toLowerCase();
        const extMap = {
            pdf: 'fas fa-file-pdf text-danger',
            doc: 'fas fa-file-word text-primary',
            docx: 'fas fa-file-word text-primary',
            xls: 'fas fa-file-excel text-success',
            xlsx: 'fas fa-file-excel text-success',
            csv: 'fas fa-file-csv text-success',
            tsv: 'fas fa-file-csv text-success',
            pptx: 'fas fa-file-powerpoint text-warning',
            ppt: 'fas fa-file-powerpoint text-warning',
            txt: 'fas fa-file-lines text-secondary',
            html: 'fas fa-file-code text-info',
            htm: 'fas fa-file-code text-info',
            png: 'fas fa-file-image text-success',
            jpg: 'fas fa-file-image text-success',
            jpeg: 'fas fa-file-image text-success',
            gif: 'fas fa-file-image text-success',
            webp: 'fas fa-file-image text-success',
            tiff: 'fas fa-file-image text-success',
            tif: 'fas fa-file-image text-success',
            bmp: 'fas fa-file-image text-success',
            mp3: 'fas fa-file-audio text-info',
            wav: 'fas fa-file-audio text-info',
            m4a: 'fas fa-file-audio text-info',
            ogg: 'fas fa-file-audio text-info',
            flac: 'fas fa-file-audio text-info',
            aac: 'fas fa-file-audio text-info',
            mp4: 'fas fa-file-video text-warning',
            avi: 'fas fa-file-video text-warning',
            mov: 'fas fa-file-video text-warning',
            mkv: 'fas fa-file-video text-warning',
            webm: 'fas fa-file-video text-warning',
        };
        return extMap[ext] || this.typeIcon(fileType);
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

    // Entity type icon + label
    entityTypeIcon(type) {
        const map = {
            person: 'fas fa-user',
            event: 'fas fa-calendar-alt',
            corporation: 'fas fa-building',
            topic: 'fas fa-tag',
        };
        return map[type] || 'fas fa-circle';
    },
    entityTypeLabel(type) {
        const map = { person: 'אדם', event: 'אירוע', corporation: 'תאגיד', topic: 'נושא' };
        return map[type] || type;
    },
    entityTypeColor(type) {
        const map = { person: '#0d6efd', event: '#dc3545', corporation: '#198754', topic: '#6f42c1' };
        return map[type] || '#6c757d';
    },

    // Short date (no time)
    formatDateShort(dateStr) {
        if (!dateStr) return '-';
        try { return new Date(dateStr).toLocaleDateString('he-IL'); } catch { return dateStr; }
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
