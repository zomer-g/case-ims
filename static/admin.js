/**
 * admin.js — Admin panel logic for Case-IMS.
 */

(function () {
    document.addEventListener('DOMContentLoaded', () => {
        // Check admin access
        if (!IMS.token || !IMS.user?.is_admin) {
            window.location.href = '/static/login.html';
            return;
        }
        loadStats();
        loadPrompts();
        loadFields();
        loadUsers();
        loadActivity();
        loadSettings();
    });

    // ---- Stats ----
    async function loadStats() {
        try {
            const data = await IMS.api('/admin/stats');
            document.getElementById('stat-users').textContent = data.users;
            document.getElementById('stat-materials').textContent = data.materials;
            document.getElementById('stat-cases').textContent = data.cases;
            document.getElementById('stat-queue').textContent = data.queue_pending + data.queue_running;
        } catch (err) {
            console.error('Stats error:', err);
        }
    }

    // ---- Prompts ----
    async function loadPrompts() {
        try {
            const prompts = await IMS.api('/admin/prompts/');
            const container = document.getElementById('prompts-list');
            if (prompts.length === 0) {
                container.innerHTML = '<p class="text-muted">אין חוקי פרומפט.</p>';
                return;
            }
            const E = IMS.esc;
            container.innerHTML = prompts.map(p => `
                <div class="card mb-2">
                    <div class="card-body py-2 px-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <strong>${E(p.name)}</strong>
                                ${p.trigger_tag ? `<span class="badge bg-info ms-2">${E(p.trigger_tag)}=${E(p.trigger_value) || '*'}</span>` : '<span class="badge bg-secondary ms-2">base</span>'}
                                ${p.case_name ? `<span class="badge bg-primary ms-1">${E(p.case_name)}</span>` : ''}
                                <span class="badge ${p.is_active ? 'bg-success' : 'bg-danger'} ms-1">${p.is_active ? 'פעיל' : 'מושבת'}</span>
                            </div>
                            <div>
                                <button class="btn btn-sm btn-outline-primary edit-prompt-btn" data-id="${p.id}"><i class="fas fa-edit"></i></button>
                                <button class="btn btn-sm btn-outline-danger delete-prompt-btn" data-id="${p.id}"><i class="fas fa-trash"></i></button>
                            </div>
                        </div>
                        <div class="mt-1"><small class="text-muted">${E(p.prompt_text.substring(0, 200))}${p.prompt_text.length > 200 ? '...' : ''}</small></div>
                    </div>
                </div>
            `).join('');

            container.querySelectorAll('.delete-prompt-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    if (!confirm('למחוק את החוק?')) return;
                    try {
                        await IMS.api(`/admin/prompts/${btn.dataset.id}`, { method: 'DELETE' });
                        loadPrompts();
                    } catch (err) { IMS.toast(err.message, 'error'); }
                });
            });
        } catch (err) {
            document.getElementById('prompts-list').innerHTML = `<p class="text-danger">${err.message}</p>`;
        }
    }

    document.getElementById('add-prompt-btn')?.addEventListener('click', () => {
        const name = prompt('שם החוק:');
        if (!name) return;
        const promptText = prompt('טקסט הפרומפט:');
        if (!promptText) return;
        IMS.api('/admin/prompts/', { method: 'POST', json: { name, prompt_text: promptText } })
            .then(() => { loadPrompts(); IMS.toast('החוק נוצר', 'success'); })
            .catch(err => IMS.toast(err.message, 'error'));
    });

    // ---- Fields ----
    async function loadFields() {
        try {
            const fields = await IMS.api('/admin/fields/');
            const container = document.getElementById('fields-list');
            if (fields.length === 0) {
                container.innerHTML = '<p class="text-muted">לא זוהו שדות עדיין.</p>';
                return;
            }
            container.innerHTML = `
                <div class="table-responsive">
                <table class="table table-sm table-striped">
                    <thead><tr><th>מפתח</th><th>שם ידידותי</th><th>סוג</th><th>מערך</th><th>זוהה לראשונה</th></tr></thead>
                    <tbody>${fields.map(f => { const E = IMS.esc; return `
                        <tr>
                            <td><code>${E(f.field_key)}</code></td>
                            <td>${E(f.friendly_name) || '-'}</td>
                            <td>${E(f.field_type) || '-'}</td>
                            <td>${f.is_array ? '<i class="fas fa-check text-success"></i>' : ''}</td>
                            <td>${IMS.formatDate(f.first_seen)}</td>
                        </tr>
                    `; }).join('')}</tbody>
                </table>
                </div>
            `;
        } catch (err) {
            document.getElementById('fields-list').innerHTML = `<p class="text-danger">${err.message}</p>`;
        }
    }

    // ---- Users ----
    async function loadUsers() {
        try {
            const users = await IMS.api('/users/');
            const container = document.getElementById('users-list');
            container.innerHTML = `
                <div class="table-responsive">
                <table class="table table-sm table-striped">
                    <thead><tr><th>ID</th><th>דוא״ל</th><th>ספק</th><th>מנהל</th><th>נוצר</th></tr></thead>
                    <tbody>${users.map(u => `
                        <tr>
                            <td>${u.id}</td>
                            <td>${IMS.esc(u.email)}</td>
                            <td>${IMS.esc(u.auth_provider)}</td>
                            <td>${u.is_admin ? '<i class="fas fa-check text-success"></i>' : ''}</td>
                            <td>${IMS.formatDate(u.created_at)}</td>
                        </tr>
                    `).join('')}</tbody>
                </table>
                </div>
            `;
        } catch (err) {
            document.getElementById('users-list').innerHTML = `<p class="text-danger">${err.message}</p>`;
        }
    }

    // ---- Activity ----
    async function loadActivity() {
        try {
            const data = await IMS.api('/admin/activity?size=30');
            const container = document.getElementById('activity-list');
            if (data.items.length === 0) {
                container.innerHTML = '<p class="text-muted">אין פעילות.</p>';
                return;
            }
            container.innerHTML = `
                <div class="table-responsive">
                <table class="table table-sm table-striped">
                    <thead><tr><th>זמן</th><th>אירוע</th><th>פרטים</th><th>משתמש</th></tr></thead>
                    <tbody>${data.items.map(a => `
                        <tr>
                            <td><small>${IMS.formatDate(a.timestamp)}</small></td>
                            <td><span class="badge bg-secondary">${IMS.esc(a.event_type)}</span></td>
                            <td><small>${IMS.esc(a.detail) || '-'}</small></td>
                            <td>${a.user_id || '-'}</td>
                        </tr>
                    `).join('')}</tbody>
                </table>
                </div>
            `;
        } catch (err) {
            document.getElementById('activity-list').innerHTML = `<p class="text-danger">${err.message}</p>`;
        }
    }

    // ---- Settings ----
    async function loadSettings() {
        try {
            const settings = await IMS.api('/admin/system/settings');
            const container = document.getElementById('settings-list');
            if (settings.length === 0) {
                container.innerHTML = '<p class="text-muted">אין הגדרות.</p>';
                return;
            }
            container.innerHTML = `
                <div class="table-responsive">
                <table class="table table-sm table-striped">
                    <thead><tr><th>מפתח</th><th>ערך</th><th>עודכן</th></tr></thead>
                    <tbody>${settings.map(s => `
                        <tr>
                            <td><code>${IMS.esc(s.key)}</code></td>
                            <td>${IMS.esc(s.value)}</td>
                            <td>${s.updated_at ? IMS.formatDate(s.updated_at) : '-'}</td>
                        </tr>
                    `).join('')}</tbody>
                </table>
                </div>
            `;
        } catch (err) {
            document.getElementById('settings-list').innerHTML = `<p class="text-danger">${err.message}</p>`;
        }
    }
})();
