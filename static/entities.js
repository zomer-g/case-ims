/**
 * entities.js — Entity management page logic for Case-DMS.
 */
(function () {
    let currentPage = 1;
    const pageSize = 50;
    let searchTimeout = null;
    let currentEntityId = null;

    document.addEventListener('DOMContentLoaded', () => {
        if (!DMS.token) { window.location.href = '/static/login.html'; return; }
        setupFilters();
        setupEntityModal();
        setupDetailModal();
        setupLinkModal();
        // Listen for global case changes
        document.addEventListener('case-changed', () => { currentPage = 1; loadEntities(); });
    });

    // ---- Filters ----
    function setupFilters() {
        document.getElementById('type-filter')?.addEventListener('change', () => { currentPage = 1; loadEntities(); });
        document.getElementById('search-input')?.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => { currentPage = 1; loadEntities(); }, 400);
        });
    }

    // ---- Entity List ----
    async function loadEntities() {
        const list = document.getElementById('entities-list');
        const spinner = document.getElementById('loading-spinner');
        const empty = document.getElementById('empty-state');
        spinner.classList.remove('d-none'); empty.classList.add('d-none'); list.innerHTML = '';

        if (!DMS.currentCaseId) { spinner.classList.add('d-none'); empty.classList.remove('d-none'); return; }
        const params = new URLSearchParams({ page: currentPage, size: pageSize, case_id: DMS.currentCaseId });
        const type = document.getElementById('type-filter')?.value;
        const q = document.getElementById('search-input')?.value?.trim();
        if (type) params.set('entity_type', type);
        if (q) params.set('q', q);

        try {
            const data = await DMS.api('/entities/?' + params.toString());
            spinner.classList.add('d-none');
            document.getElementById('total-count').textContent = `${data.total} ישויות`;
            if (data.entities.length === 0) { empty.classList.remove('d-none'); return; }
            data.entities.forEach(e => list.appendChild(createEntityCard(e)));
        } catch (err) {
            spinner.classList.add('d-none');
            list.innerHTML = `<div class="col-12 text-center text-danger"><p>${DMS.esc(err.message)}</p></div>`;
        }
    }

    function createEntityCard(e) {
        const col = document.createElement('div');
        col.className = 'col-md-6 col-lg-4';
        const E = DMS.esc;
        const color = DMS.entityTypeColor(e.entity_type);
        const icon = DMS.entityTypeIcon(e.entity_type);
        const label = DMS.entityTypeLabel(e.entity_type);

        let extra = '';
        if (e.entity_type === 'person' && e.person_role) extra = `<small class="text-muted d-block">${E(e.person_role)}</small>`;
        if (e.entity_type === 'event' && e.event_date) extra = `<small class="text-muted d-block"><i class="fas fa-calendar me-1"></i>${DMS.formatDateShort(e.event_date)}</small>`;
        if (e.entity_type === 'corporation' && e.corp_type) extra = `<small class="text-muted d-block">${E(e.corp_type)}</small>`;

        col.innerHTML = `
            <div class="card entity-card h-100" data-id="${e.id}">
                <div class="card-body">
                    <div class="d-flex align-items-start gap-3">
                        <i class="${icon} mt-1" style="font-size:1.8rem; color:${color}"></i>
                        <div class="flex-grow-1">
                            <h6 class="mb-1">${E(e.name)}</h6>
                            <span class="entity-type-badge" style="background:${color}">${E(label)}</span>
                            ${e.description ? `<small class="text-muted d-block mt-1">${E(e.description.substring(0, 80))}${e.description.length > 80 ? '...' : ''}</small>` : ''}
                            ${extra}
                        </div>
                    </div>
                </div>
                <div class="card-footer bg-transparent border-top-0 pt-0 d-flex gap-2">
                    <small class="text-muted"><i class="fas fa-file me-1"></i>${e.material_link_count} חומרים</small>
                    <small class="text-muted"><i class="fas fa-link me-1"></i>${e.entity_link_count} קשרים</small>
                </div>
            </div>
        `;
        col.querySelector('.entity-card').addEventListener('click', () => showEntityDetail(e.id));
        return col;
    }

    // ---- Entity Create/Edit Modal ----
    function setupEntityModal() {
        document.getElementById('new-entity-btn')?.addEventListener('click', () => {
            document.getElementById('entity-id').value = '';
            document.getElementById('entityModalLabel').textContent = 'ישות חדשה';
            document.getElementById('entity-name').value = '';
            document.getElementById('entity-desc').value = '';
            document.getElementById('entity-metadata').value = '';
            document.getElementById('entity-type').value = 'person';
            toggleTypeFields('person');
            clearTypeFields();
            new bootstrap.Modal(document.getElementById('entityModal')).show();
        });

        document.getElementById('entity-type')?.addEventListener('change', (e) => toggleTypeFields(e.target.value));

        document.getElementById('save-entity-btn')?.addEventListener('click', saveEntity);
    }

    function toggleTypeFields(type) {
        document.querySelectorAll('.type-fields').forEach(el => el.classList.add('d-none'));
        const target = document.getElementById('fields-' + type);
        if (target) target.classList.remove('d-none');
    }

    function clearTypeFields() {
        ['person-role', 'person-id', 'event-date', 'event-end-date', 'event-location', 'corp-type', 'corp-reg', 'topic-color', 'topic-icon'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = el.type === 'color' ? '#6f42c1' : '';
        });
    }

    async function saveEntity() {
        const id = document.getElementById('entity-id').value;
        const body = {
            entity_type: document.getElementById('entity-type').value,
            case_id: DMS.currentCaseId,
            name: document.getElementById('entity-name').value.trim(),
            description: document.getElementById('entity-desc').value.trim() || null,
        };

        if (!body.name) { DMS.toast('שם חובה', 'error'); return; }
        if (!body.case_id) { DMS.toast('יש לבחור תיק', 'error'); return; }

        // Type-specific
        const type = body.entity_type;
        if (type === 'person') {
            body.person_role = document.getElementById('person-role').value || null;
            body.person_id_number = document.getElementById('person-id').value || null;
        } else if (type === 'event') {
            body.event_date = document.getElementById('event-date').value || null;
            body.event_end_date = document.getElementById('event-end-date').value || null;
            body.event_location = document.getElementById('event-location').value || null;
        } else if (type === 'corporation') {
            body.corp_type = document.getElementById('corp-type').value || null;
            body.corp_registration = document.getElementById('corp-reg').value || null;
        } else if (type === 'topic') {
            body.topic_color = document.getElementById('topic-color').value || null;
            body.topic_icon = document.getElementById('topic-icon').value || null;
        }

        // Metadata JSON
        const metaText = document.getElementById('entity-metadata').value.trim();
        if (metaText) {
            try { body.metadata_json = JSON.parse(metaText); } catch { DMS.toast('JSON לא תקין', 'error'); return; }
        }

        try {
            if (id) {
                await DMS.api(`/entities/${id}`, { method: 'PUT', json: body });
                DMS.toast('ישות עודכנה', 'success');
            } else {
                await DMS.api('/entities/', { method: 'POST', json: body });
                DMS.toast('ישות נוצרה', 'success');
            }
            bootstrap.Modal.getInstance(document.getElementById('entityModal')).hide();
            loadEntities();
        } catch (err) { DMS.toast(err.message, 'error'); }
    }

    // ---- Entity Detail ----
    async function showEntityDetail(entityId) {
        currentEntityId = entityId;
        try {
            const [entity, links] = await Promise.all([
                DMS.api(`/entities/${entityId}`),
                DMS.api(`/entities/${entityId}/links`),
            ]);

            document.getElementById('entityDetailLabel').textContent = entity.name;
            const E = DMS.esc;
            const color = DMS.entityTypeColor(entity.entity_type);
            const label = DMS.entityTypeLabel(entity.entity_type);

            let html = `
                <div class="d-flex gap-3 mb-3">
                    <i class="${DMS.entityTypeIcon(entity.entity_type)}" style="font-size:2.5rem; color:${color}"></i>
                    <div>
                        <h4 class="mb-1">${E(entity.name)}</h4>
                        <span class="entity-type-badge" style="background:${color}">${E(label)}</span>
                        ${entity.description ? `<p class="mt-2">${E(entity.description)}</p>` : ''}
                    </div>
                </div>
            `;

            // Type-specific info
            if (entity.entity_type === 'person') {
                html += `<div class="link-section"><h6>פרטי אדם</h6>`;
                if (entity.person_role) html += `<p><strong>תפקיד:</strong> ${E(entity.person_role)}</p>`;
                if (entity.person_id_number) html += `<p><strong>מזהה:</strong> ${E(entity.person_id_number)}</p>`;
                html += `</div>`;
            } else if (entity.entity_type === 'event') {
                html += `<div class="link-section"><h6>פרטי אירוע</h6>`;
                if (entity.event_date) html += `<p><strong>תאריך:</strong> ${DMS.formatDate(entity.event_date)}</p>`;
                if (entity.event_end_date) html += `<p><strong>סיום:</strong> ${DMS.formatDate(entity.event_end_date)}</p>`;
                if (entity.event_location) html += `<p><strong>מיקום:</strong> ${E(entity.event_location)}</p>`;
                html += `</div>`;
            } else if (entity.entity_type === 'corporation') {
                html += `<div class="link-section"><h6>פרטי תאגיד</h6>`;
                if (entity.corp_type) html += `<p><strong>סוג:</strong> ${E(entity.corp_type)}</p>`;
                if (entity.corp_registration) html += `<p><strong>מספר רישום:</strong> ${E(entity.corp_registration)}</p>`;
                html += `</div>`;
            }

            // Metadata
            if (entity.metadata_json && Object.keys(entity.metadata_json).length > 0) {
                html += `<div class="link-section"><h6><i class="fas fa-database me-1"></i>מטא-דאטה</h6><pre class="mb-0 small">${E(JSON.stringify(entity.metadata_json, null, 2))}</pre></div>`;
            }

            // Entity links
            html += `<div class="link-section">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0"><i class="fas fa-link me-1"></i>ישויות מקושרות (${links.entity_links.length})</h6>
                    <button class="btn btn-sm btn-outline-primary" onclick="window._openLinkModal('entity')"><i class="fas fa-plus me-1"></i>קשר ישות</button>
                </div>`;
            if (links.entity_links.length) {
                html += links.entity_links.map(l => `
                    <span class="link-tag me-1 mb-1">
                        <i class="${DMS.entityTypeIcon(l.entity_type)}"></i>
                        ${E(l.entity_name)}${l.relationship_type ? ` (${E(l.relationship_type)})` : ''}
                        <span class="remove-link" data-link-type="entity" data-link-id="${l.link_id}">&times;</span>
                    </span>
                `).join('');
            } else {
                html += `<small class="text-muted">אין ישויות מקושרות</small>`;
            }
            html += `</div>`;

            // Material links
            html += `<div class="link-section">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0"><i class="fas fa-file me-1"></i>חומרים מקושרים (${links.material_links.length})</h6>
                    <button class="btn btn-sm btn-outline-primary" onclick="window._openLinkModal('material')"><i class="fas fa-plus me-1"></i>קשר חומר</button>
                </div>`;
            if (links.material_links.length) {
                html += `<div class="list-group list-group-flush">`;
                links.material_links.forEach(l => {
                    html += `<div class="list-group-item d-flex justify-content-between align-items-center px-0">
                        <div><i class="${DMS.typeIcon(l.file_type)} me-2"></i>${E(l.filename)}${l.relevance ? ` <small class="text-muted">(${E(l.relevance)})</small>` : ''}</div>
                        <span class="remove-link text-danger" style="cursor:pointer" data-link-type="material" data-link-id="${l.link_id}">&times;</span>
                    </div>`;
                });
                html += `</div>`;
            } else {
                html += `<small class="text-muted">אין חומרים מקושרים</small>`;
            }
            html += `</div>`;

            // Folder links
            html += `<div class="link-section">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0"><i class="fas fa-folder me-1"></i>תיקיות מקושרות (${links.folder_links.length})</h6>
                    <button class="btn btn-sm btn-outline-primary" onclick="window._openLinkModal('folder')"><i class="fas fa-plus me-1"></i>קשר תיקייה</button>
                </div>`;
            if (links.folder_links.length) {
                html += links.folder_links.map(l => `
                    <span class="link-tag me-1 mb-1">
                        <i class="fas fa-folder"></i> ${E(l.folder_name)}
                        <span class="remove-link" data-link-type="folder" data-link-id="${l.link_id}">&times;</span>
                    </span>
                `).join('');
            } else {
                html += `<small class="text-muted">אין תיקיות מקושרות</small>`;
            }
            html += `</div>`;

            document.getElementById('entity-detail-body').innerHTML = html;

            // Remove link handlers
            document.querySelectorAll('.remove-link').forEach(el => {
                el.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    const linkType = el.dataset.linkType;
                    const linkId = el.dataset.linkId;
                    if (!confirm('להסיר קישור?')) return;
                    try {
                        await DMS.api(`/entities/link-${linkType}/${linkId}`, { method: 'DELETE' });
                        DMS.toast('קישור הוסר', 'success');
                        showEntityDetail(entityId);
                    } catch (err) { DMS.toast(err.message, 'error'); }
                });
            });

            new bootstrap.Modal(document.getElementById('entityDetailModal')).show();
        } catch (err) { DMS.toast(err.message, 'error'); }
    }

    function setupDetailModal() {
        document.getElementById('detail-edit-btn')?.addEventListener('click', async () => {
            if (!currentEntityId) return;
            bootstrap.Modal.getInstance(document.getElementById('entityDetailModal'))?.hide();
            try {
                const entity = await DMS.api(`/entities/${currentEntityId}`);
                document.getElementById('entity-id').value = entity.id;
                document.getElementById('entityModalLabel').textContent = 'עריכת ישות';
                document.getElementById('entity-type').value = entity.entity_type;
                document.getElementById('entity-case').value = entity.case_id;
                document.getElementById('entity-name').value = entity.name;
                document.getElementById('entity-desc').value = entity.description || '';
                document.getElementById('entity-metadata').value = Object.keys(entity.metadata_json || {}).length ? JSON.stringify(entity.metadata_json, null, 2) : '';
                toggleTypeFields(entity.entity_type);
                if (entity.entity_type === 'person') {
                    document.getElementById('person-role').value = entity.person_role || '';
                    document.getElementById('person-id').value = entity.person_id_number || '';
                } else if (entity.entity_type === 'event') {
                    document.getElementById('event-date').value = entity.event_date ? entity.event_date.substring(0, 16) : '';
                    document.getElementById('event-end-date').value = entity.event_end_date ? entity.event_end_date.substring(0, 16) : '';
                    document.getElementById('event-location').value = entity.event_location || '';
                } else if (entity.entity_type === 'corporation') {
                    document.getElementById('corp-type').value = entity.corp_type || '';
                    document.getElementById('corp-reg').value = entity.corp_registration || '';
                } else if (entity.entity_type === 'topic') {
                    document.getElementById('topic-color').value = entity.topic_color || '#6f42c1';
                    document.getElementById('topic-icon').value = entity.topic_icon || '';
                }
                new bootstrap.Modal(document.getElementById('entityModal')).show();
            } catch (err) { DMS.toast(err.message, 'error'); }
        });

        document.getElementById('detail-delete-btn')?.addEventListener('click', async () => {
            if (!currentEntityId || !confirm('למחוק ישות זו?')) return;
            try {
                await DMS.api(`/entities/${currentEntityId}`, { method: 'DELETE' });
                bootstrap.Modal.getInstance(document.getElementById('entityDetailModal'))?.hide();
                DMS.toast('ישות נמחקה', 'success');
                loadEntities();
            } catch (err) { DMS.toast(err.message, 'error'); }
        });
    }

    // ---- Link Modal ----
    function setupLinkModal() {
        document.getElementById('link-type')?.addEventListener('change', (e) => {
            document.getElementById('link-entity-fields').classList.toggle('d-none', e.target.value !== 'entity');
            document.getElementById('link-material-fields').classList.toggle('d-none', e.target.value !== 'material');
            document.getElementById('link-folder-fields').classList.toggle('d-none', e.target.value !== 'folder');
        });

        document.getElementById('save-link-btn')?.addEventListener('click', saveLink);
    }

    window._openLinkModal = async function (type) {
        document.getElementById('link-source-entity-id').value = currentEntityId;
        document.getElementById('link-type').value = type;
        document.getElementById('link-type').dispatchEvent(new Event('change'));

        // Load options based on type
        if (type === 'entity') {
            const params = DMS.currentCaseId ? `?case_id=${DMS.currentCaseId}&size=200` : '?size=200';
            const data = await DMS.api('/entities/' + params);
            const sel = document.getElementById('link-target-entity');
            sel.innerHTML = data.entities.filter(e => e.id !== currentEntityId).map(e =>
                `<option value="${e.id}">${DMS.esc(e.name)} (${DMS.entityTypeLabel(e.entity_type)})</option>`
            ).join('');
        } else if (type === 'material') {
            const data = await DMS.api(`/materials/?size=200${DMS.currentCaseId ? '&case_id=' + DMS.currentCaseId : ''}`);
            const sel = document.getElementById('link-target-material');
            sel.innerHTML = data.materials.map(m =>
                `<option value="${m.id}">${DMS.esc(m.filename)}</option>`
            ).join('');
        } else if (type === 'folder') {
            const data = await DMS.api('/folders/');
            const sel = document.getElementById('link-target-folder');
            sel.innerHTML = data.folders.map(f =>
                `<option value="${f.id}">${DMS.esc(f.name)}</option>`
            ).join('');
        }

        new bootstrap.Modal(document.getElementById('linkModal')).show();
    };

    async function saveLink() {
        const sourceId = document.getElementById('link-source-entity-id').value;
        const type = document.getElementById('link-type').value;

        try {
            if (type === 'entity') {
                const targetId = document.getElementById('link-target-entity').value;
                await DMS.api(`/entities/${sourceId}/link-entity`, {
                    method: 'POST',
                    json: { entity_a_id: parseInt(sourceId), entity_b_id: parseInt(targetId), relationship_type: document.getElementById('link-relationship').value || null },
                });
            } else if (type === 'material') {
                const matId = document.getElementById('link-target-material').value;
                await DMS.api(`/entities/${sourceId}/link-material`, {
                    method: 'POST',
                    json: { entity_id: parseInt(sourceId), material_id: parseInt(matId), relevance: document.getElementById('link-relevance').value || null },
                });
            } else if (type === 'folder') {
                const folderId = document.getElementById('link-target-folder').value;
                await DMS.api(`/entities/${sourceId}/link-folder`, {
                    method: 'POST',
                    json: { entity_id: parseInt(sourceId), folder_id: parseInt(folderId) },
                });
            }
            bootstrap.Modal.getInstance(document.getElementById('linkModal'))?.hide();
            DMS.toast('קישור נוצר', 'success');
            showEntityDetail(parseInt(sourceId));
        } catch (err) { DMS.toast(err.message, 'error'); }
    }
})();
