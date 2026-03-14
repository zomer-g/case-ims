/**
 * admin.js — Admin panel logic for Case-IMS.
 * Includes prompt builder, entity mapping, and system management.
 */

(function () {
    let editingPromptId = null;

    // Builder state
    let builderFields = [];   // [{name, type, description}]
    let entityMappings = [];  // [{field, entity_type, is_array}]

    document.addEventListener('DOMContentLoaded', () => {
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
        setupPromptEditModal();
        setupPromptBuilder();
        setupEntityMappings();
    });

    // ---- Stats ----
    async function loadStats() {
        try {
            const data = await IMS.api('/admin/stats');
            document.getElementById('stat-users').textContent = data.users;
            document.getElementById('stat-materials').textContent = data.materials;
            document.getElementById('stat-cases').textContent = data.cases;
            document.getElementById('stat-queue').textContent = data.queue_pending + data.queue_running;
        } catch (err) { console.error('Stats error:', err); }
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
            container.innerHTML = prompts.map(p => {
                // Parse entity mappings count
                let mappingCount = 0;
                try {
                    const schema = JSON.parse(p.json_schema || '{}');
                    mappingCount = (schema.entity_mappings || []).length;
                } catch {}
                return `
                <div class="card mb-2">
                    <div class="card-body py-2 px-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <strong>${E(p.name)}</strong>
                                ${p.trigger_tag ? `<span class="badge bg-info ms-2">${E(p.trigger_tag)}=${E(p.trigger_value) || '*'}</span>` : '<span class="badge bg-secondary ms-2">base</span>'}
                                ${p.case_name ? `<span class="badge bg-primary ms-1">${E(p.case_name)}</span>` : ''}
                                <span class="badge ${p.is_active ? 'bg-success' : 'bg-danger'} ms-1">${p.is_active ? 'פעיל' : 'מושבת'}</span>
                                ${mappingCount ? `<span class="badge bg-warning text-dark ms-1"><i class="fas fa-project-diagram me-1"></i>${mappingCount} מיפויים</span>` : ''}
                            </div>
                            <div>
                                <button class="btn btn-sm btn-outline-primary edit-prompt-btn" data-id="${p.id}"><i class="fas fa-edit"></i></button>
                                <button class="btn btn-sm btn-outline-danger delete-prompt-btn" data-id="${p.id}"><i class="fas fa-trash"></i></button>
                            </div>
                        </div>
                        <div class="mt-1"><small class="text-muted">${E(p.prompt_text.substring(0, 200))}${p.prompt_text.length > 200 ? '...' : ''}</small></div>
                    </div>
                </div>
                `;
            }).join('');

            container.querySelectorAll('.edit-prompt-btn').forEach(btn => {
                btn.addEventListener('click', () => openEditPrompt(parseInt(btn.dataset.id), prompts));
            });
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

    function openEditPrompt(id, prompts) {
        const p = prompts.find(x => x.id === id);
        if (!p) return;
        editingPromptId = id;
        document.getElementById('edit-prompt-name').value = p.name;
        document.getElementById('edit-prompt-text').value = p.prompt_text;
        document.getElementById('edit-prompt-trigger-tag').value = p.trigger_tag || '';
        document.getElementById('edit-prompt-trigger-value').value = p.trigger_value || '';
        document.getElementById('edit-prompt-max-tokens').value = p.max_tokens || 3000;
        document.getElementById('edit-prompt-active').checked = p.is_active;
        document.getElementById('editPromptModalLabel').textContent = 'עריכת חוק: ' + p.name;
        document.getElementById('builder-free-text').value = '';

        // Parse json_schema for entity mappings and builder fields
        entityMappings = [];
        builderFields = [];
        try {
            const schema = JSON.parse(p.json_schema || '{}');
            entityMappings = schema.entity_mappings || [];
            builderFields = schema.builder_fields || [];
        } catch {}
        renderBuilderFields();
        renderEntityMappings();

        new bootstrap.Modal(document.getElementById('editPromptModal')).show();
    }

    function setupPromptEditModal() {
        document.getElementById('add-prompt-btn')?.addEventListener('click', () => {
            editingPromptId = null;
            document.getElementById('edit-prompt-name').value = '';
            document.getElementById('edit-prompt-text').value = '';
            document.getElementById('edit-prompt-trigger-tag').value = '';
            document.getElementById('edit-prompt-trigger-value').value = '';
            document.getElementById('edit-prompt-max-tokens').value = '3000';
            document.getElementById('edit-prompt-active').checked = true;
            document.getElementById('editPromptModalLabel').textContent = 'חוק חדש';
            document.getElementById('builder-free-text').value = '';
            builderFields = [];
            entityMappings = [];
            renderBuilderFields();
            renderEntityMappings();
            new bootstrap.Modal(document.getElementById('editPromptModal')).show();
        });

        document.getElementById('save-edit-prompt-btn')?.addEventListener('click', async () => {
            const jsonSchema = JSON.stringify({
                entity_mappings: entityMappings,
                builder_fields: builderFields,
            });
            const data = {
                name: document.getElementById('edit-prompt-name').value.trim(),
                prompt_text: document.getElementById('edit-prompt-text').value.trim(),
                trigger_tag: document.getElementById('edit-prompt-trigger-tag').value.trim() || null,
                trigger_value: document.getElementById('edit-prompt-trigger-value').value.trim() || null,
                max_tokens: parseInt(document.getElementById('edit-prompt-max-tokens').value) || 3000,
                is_active: document.getElementById('edit-prompt-active').checked,
                json_schema: jsonSchema,
            };
            if (!data.name || !data.prompt_text) { IMS.toast('שם וטקסט חובה', 'error'); return; }

            try {
                if (editingPromptId) {
                    await IMS.api(`/admin/prompts/${editingPromptId}`, { method: 'PUT', json: data });
                    IMS.toast('החוק עודכן בהצלחה', 'success');
                } else {
                    await IMS.api('/admin/prompts/', { method: 'POST', json: data });
                    IMS.toast('החוק נוצר', 'success');
                }
                bootstrap.Modal.getInstance(document.getElementById('editPromptModal'))?.hide();
                loadPrompts();
            } catch (err) { IMS.toast(err.message, 'error'); }
        });
    }

    // ---- Prompt Builder ----
    function setupPromptBuilder() {
        document.getElementById('builder-add-field-btn')?.addEventListener('click', () => {
            const name = document.getElementById('builder-new-field-name').value.trim();
            const type = document.getElementById('builder-new-field-type').value;
            const desc = document.getElementById('builder-new-field-desc').value.trim();
            if (!name) { IMS.toast('הכנס שם שדה', 'error'); return; }
            if (builderFields.some(f => f.name === name)) { IMS.toast('שדה קיים', 'warning'); return; }
            builderFields.push({ name, type, description: desc });
            document.getElementById('builder-new-field-name').value = '';
            document.getElementById('builder-new-field-desc').value = '';
            renderBuilderFields();
        });

        document.getElementById('builder-generate-btn')?.addEventListener('click', generatePrompt);
    }

    function renderBuilderFields() {
        const container = document.getElementById('builder-fields-list');
        if (!container) return;
        const E = IMS.esc;
        const typeLabels = { string: 'טקסט', array: 'רשימה', date: 'תאריך', number: 'מספר' };
        const typeIcons = { string: 'fas fa-font', array: 'fas fa-list', date: 'fas fa-calendar', number: 'fas fa-hashtag' };

        if (!builderFields.length) {
            container.innerHTML = '<p class="text-muted small">לא הוגדרו שדות. הוסף שדות שהפרומפט יפיק.</p>';
            return;
        }
        container.innerHTML = builderFields.map((f, i) => `
            <div class="d-flex align-items-center gap-2 mb-1 p-1 border rounded" style="background:#f8f9fa;">
                <i class="${typeIcons[f.type] || 'fas fa-font'} text-muted"></i>
                <code>${E(f.name)}</code>
                <span class="badge bg-light text-dark">${typeLabels[f.type] || f.type}</span>
                ${f.description ? `<small class="text-muted">${E(f.description)}</small>` : ''}
                <button class="btn btn-sm btn-link text-danger ms-auto p-0 remove-field-btn" data-idx="${i}"><i class="fas fa-times"></i></button>
            </div>
        `).join('');

        container.querySelectorAll('.remove-field-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                builderFields.splice(parseInt(btn.dataset.idx), 1);
                renderBuilderFields();
            });
        });
    }

    function generatePrompt() {
        const freeText = document.getElementById('builder-free-text').value.trim();
        if (!builderFields.length && !freeText) {
            IMS.toast('הוסף שדות או כתוב תיאור חופשי', 'error');
            return;
        }

        let prompt = 'אתה מנתח חומרי חקירה מקצועי. קבל את תוכן המסמך הבא ומלא את שדות ה-JSON.\n';
        prompt += 'הנחיות:\n';
        prompt += '- ענה אך ורק ב-JSON תקין\n';
        prompt += '- אם שדה לא רלוונטי, השאר מחרוזת ריקה (או מערך ריק עבור שדות רשימה)\n';
        prompt += '- כתוב בעברית\n';

        if (freeText) {
            prompt += '- ' + freeText + '\n';
        }

        prompt += '\nשדות נדרשים:\n{\n';

        if (builderFields.length) {
            const lines = builderFields.map(f => {
                let defaultVal;
                switch (f.type) {
                    case 'array': defaultVal = '[]'; break;
                    case 'date': defaultVal = '"YYYY-MM-DD"'; break;
                    case 'number': defaultVal = '0'; break;
                    default: defaultVal = '""'; break;
                }
                const comment = f.description ? ` // ${f.description}` : '';
                return `  "${f.name}": ${defaultVal}${comment}`;
            });
            prompt += lines.join(',\n') + '\n';
        } else {
            // Auto-generate fields from free text keywords
            prompt += '  // השדות ייקבעו בהתאם לתיאור שנתת\n';
        }

        prompt += '}';

        document.getElementById('edit-prompt-text').value = prompt;

        // Switch to raw tab to show result
        const rawTab = document.querySelector('a[href="#prompt-tab-raw"]');
        if (rawTab) bootstrap.Tab.getOrCreateInstance(rawTab).show();

        IMS.toast('פרומפט נוצר! ניתן לערוך ידנית בלשונית "עריכה ידנית"', 'success');
    }

    // ---- Entity Mappings ----
    function setupEntityMappings() {
        document.getElementById('add-mapping-btn')?.addEventListener('click', () => {
            const field = document.getElementById('mapping-field-name').value.trim();
            const entityType = document.getElementById('mapping-entity-type').value;
            const isArray = document.getElementById('mapping-is-array').checked;
            if (!field) { IMS.toast('הכנס שם שדה', 'error'); return; }
            if (entityMappings.some(m => m.field === field)) { IMS.toast('מיפוי קיים לשדה זה', 'warning'); return; }
            entityMappings.push({ field, entity_type: entityType, is_array: isArray });
            document.getElementById('mapping-field-name').value = '';
            renderEntityMappings();
        });
    }

    function renderEntityMappings() {
        const container = document.getElementById('entity-mappings-list');
        if (!container) return;
        const E = IMS.esc;
        const typeLabels = { person: 'אדם', corporation: 'תאגיד', topic: 'נושא', event: 'אירוע' };
        const typeIcons = {
            person: 'fas fa-user', corporation: 'fas fa-building',
            topic: 'fas fa-tag', event: 'fas fa-calendar-alt',
        };
        const typeColors = {
            person: '#4e79a7', corporation: '#f28e2b',
            topic: '#59a14f', event: '#e15759',
        };

        if (!entityMappings.length) {
            container.innerHTML = '<p class="text-muted small">לא הוגדרו מיפויים. הוסף מיפוי כדי שהמערכת תיצור ישויות אוטומטית מתוצאות ה-AI.</p>';
            return;
        }

        container.innerHTML = entityMappings.map((m, i) => `
            <div class="d-flex align-items-center gap-2 mb-1 p-2 border rounded" style="background:#f8f9fa;">
                <code>${E(m.field)}</code>
                <i class="fas fa-arrow-left text-muted"></i>
                <span style="color:${typeColors[m.entity_type] || '#333'}">
                    <i class="${typeIcons[m.entity_type] || 'fas fa-circle'} me-1"></i>${typeLabels[m.entity_type] || m.entity_type}
                </span>
                ${m.is_array ? '<span class="badge bg-light text-dark">רשימה</span>' : '<span class="badge bg-light text-dark">ערך בודד</span>'}
                <button class="btn btn-sm btn-link text-danger ms-auto p-0 remove-mapping-btn" data-idx="${i}"><i class="fas fa-times"></i></button>
            </div>
        `).join('');

        container.querySelectorAll('.remove-mapping-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                entityMappings.splice(parseInt(btn.dataset.idx), 1);
                renderEntityMappings();
            });
        });
    }

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
            document.getElementById('users-list').innerHTML = `<p class="text-danger">${err.message}</p>`; }
    }

    // ---- Activity ----
    async function loadActivity() {
        try {
            const data = await IMS.api('/admin/activity?size=30');
            const container = document.getElementById('activity-list');
            if (data.items.length === 0) { container.innerHTML = '<p class="text-muted">אין פעילות.</p>'; return; }
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
        } catch (err) { document.getElementById('activity-list').innerHTML = `<p class="text-danger">${err.message}</p>`; }
    }

    // ---- Settings ----
    async function loadSettings() {
        try {
            const settings = await IMS.api('/admin/system/settings');
            const container = document.getElementById('settings-list');
            if (settings.length === 0) { container.innerHTML = '<p class="text-muted">אין הגדרות.</p>'; return; }
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
        } catch (err) { document.getElementById('settings-list').innerHTML = `<p class="text-danger">${err.message}</p>`; }
    }
})();
