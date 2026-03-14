/**
 * timeline.js — Timeline visualization and management for Case-DMS.
 */
(function () {
    document.addEventListener('DOMContentLoaded', () => {
        if (!DMS.token) { window.location.href = '/static/login.html'; return; }
        setupFilters();
        setupEventModal();
        setupGenerateModal();
        // Listen for global case changes
        document.addEventListener('case-changed', () => loadTimeline());
    });

    function setupFilters() {
        ['source-filter', 'date-from', 'date-to'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', loadTimeline);
        });
    }

    async function loadTimeline() {
        const container = document.getElementById('timeline-container');
        const spinner = document.getElementById('loading-spinner');
        const empty = document.getElementById('empty-state');
        spinner.classList.remove('d-none'); empty.classList.add('d-none'); container.innerHTML = '';

        if (!DMS.currentCaseId) { spinner.classList.add('d-none'); empty.classList.remove('d-none'); return; }
        const params = new URLSearchParams({ size: 500, case_id: DMS.currentCaseId });
        const dateFrom = document.getElementById('date-from')?.value;
        const dateTo = document.getElementById('date-to')?.value;
        const source = document.getElementById('source-filter')?.value;
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo) params.set('date_to', dateTo);
        if (source) params.set('source', source);

        try {
            const data = await DMS.api('/timeline/?' + params.toString());
            spinner.classList.add('d-none');
            document.getElementById('total-count').textContent = `${data.total} אירועים`;
            if (!data.events.length) { empty.classList.remove('d-none'); return; }
            data.events.forEach(ev => container.appendChild(createTimelineItem(ev)));
        } catch (err) {
            spinner.classList.add('d-none');
            container.innerHTML = `<p class="text-center text-danger">${DMS.esc(err.message)}</p>`;
        }
    }

    function createTimelineItem(ev) {
        const item = document.createElement('div');
        item.className = 'timeline-item';
        const E = DMS.esc;
        const dotClass = ev.source === 'ai' ? 'ai' : ev.source === 'entity' ? 'entity' : '';

        const sourceLabels = { manual: 'ידני', ai: 'AI', entity: 'ישות' };
        const sourceIcons = { manual: 'fas fa-hand-pointer', ai: 'fas fa-robot', entity: 'fas fa-project-diagram' };

        let tagsHtml = '';
        if (ev.tags && ev.tags.length) {
            tagsHtml = ev.tags.map(t => `<span class="timeline-tag">${E(t)}</span>`).join(' ');
        }

        let metaHtml = '';
        if (ev.material_filename) metaHtml += `<small class="text-muted d-block"><i class="fas fa-file me-1"></i>${E(ev.material_filename)}</small>`;
        if (ev.entity_name) metaHtml += `<small class="text-muted d-block"><i class="${DMS.entityTypeIcon(ev.entity_type)} me-1"></i>${E(ev.entity_name)}</small>`;
        if (ev.location) metaHtml += `<small class="text-muted d-block"><i class="fas fa-map-marker-alt me-1"></i>${E(ev.location)}</small>`;

        let confidenceHtml = '';
        if (ev.confidence) {
            confidenceHtml = `<div class="confidence-bar mt-1" title="ביטחון: ${ev.confidence}%"><div class="confidence-fill" style="width:${ev.confidence}%"></div></div>`;
        }

        item.innerHTML = `
            <div class="timeline-dot ${dotClass}"></div>
            <div class="timeline-card">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <div class="timeline-date">${DMS.formatDateShort(ev.event_date)}${ev.event_end_date ? ' — ' + DMS.formatDateShort(ev.event_end_date) : ''}</div>
                        <h6 class="mt-1 mb-1">${E(ev.title)}</h6>
                    </div>
                    <div class="d-flex gap-1 align-items-center">
                        <small class="text-muted"><i class="${sourceIcons[ev.source] || 'fas fa-circle'} me-1"></i>${E(sourceLabels[ev.source] || ev.source)}</small>
                        <div class="dropdown">
                            <button class="btn btn-sm btn-link text-muted p-0 ms-1" data-bs-toggle="dropdown"><i class="fas fa-ellipsis-v"></i></button>
                            <ul class="dropdown-menu dropdown-menu-end">
                                <li><a class="dropdown-item edit-event" href="#" data-id="${ev.id}"><i class="fas fa-edit me-1"></i>עריכה</a></li>
                                <li><a class="dropdown-item delete-event text-danger" href="#" data-id="${ev.id}"><i class="fas fa-trash me-1"></i>מחיקה</a></li>
                            </ul>
                        </div>
                    </div>
                </div>
                ${ev.description ? `<p class="mb-1 small">${E(ev.description)}</p>` : ''}
                ${metaHtml}
                ${tagsHtml ? `<div class="mt-1">${tagsHtml}</div>` : ''}
                ${confidenceHtml}
            </div>
        `;

        // Event handlers
        item.querySelector('.edit-event')?.addEventListener('click', (e) => { e.preventDefault(); editEvent(ev); });
        item.querySelector('.delete-event')?.addEventListener('click', async (e) => {
            e.preventDefault();
            if (!confirm('למחוק אירוע?')) return;
            try {
                await DMS.api(`/timeline/${ev.id}`, { method: 'DELETE' });
                DMS.toast('אירוע נמחק', 'success');
                loadTimeline();
            } catch (err) { DMS.toast(err.message, 'error'); }
        });

        return item;
    }

    // ---- Event Create/Edit ----
    function setupEventModal() {
        document.getElementById('new-event-btn')?.addEventListener('click', () => {
            document.getElementById('event-id').value = '';
            document.getElementById('eventModalLabel').textContent = 'אירוע חדש';
            ['event-title', 'event-desc', 'event-date', 'event-end-date', 'event-location', 'event-tags'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            new bootstrap.Modal(document.getElementById('eventModal')).show();
        });

        document.getElementById('save-event-btn')?.addEventListener('click', saveEvent);
    }

    function editEvent(ev) {
        document.getElementById('event-id').value = ev.id;
        document.getElementById('eventModalLabel').textContent = 'עריכת אירוע';
        // case_id from global selector
        document.getElementById('event-title').value = ev.title;
        document.getElementById('event-desc').value = ev.description || '';
        document.getElementById('event-date').value = ev.event_date ? ev.event_date.substring(0, 16) : '';
        document.getElementById('event-end-date').value = ev.event_end_date ? ev.event_end_date.substring(0, 16) : '';
        document.getElementById('event-location').value = ev.location || '';
        document.getElementById('event-tags').value = (ev.tags || []).join(', ');
        new bootstrap.Modal(document.getElementById('eventModal')).show();
    }

    async function saveEvent() {
        const id = document.getElementById('event-id').value;
        const title = document.getElementById('event-title').value.trim();
        const eventDate = document.getElementById('event-date').value;

        if (!title || !eventDate) { DMS.toast('כותרת ותאריך חובה', 'error'); return; }

        const tags = document.getElementById('event-tags').value.split(',').map(t => t.trim()).filter(Boolean);
        const body = {
            title,
            description: document.getElementById('event-desc').value || null,
            event_date: eventDate,
            event_end_date: document.getElementById('event-end-date').value || null,
            location: document.getElementById('event-location').value || null,
            tags,
        };

        try {
            if (id) {
                await DMS.api(`/timeline/${id}`, { method: 'PUT', json: body });
                DMS.toast('אירוע עודכן', 'success');
            } else {
                body.case_id = DMS.currentCaseId;
                if (!body.case_id) { DMS.toast('יש לבחור תיק', 'error'); return; }
                await DMS.api('/timeline/', { method: 'POST', json: body });
                DMS.toast('אירוע נוצר', 'success');
            }
            bootstrap.Modal.getInstance(document.getElementById('eventModal'))?.hide();
            loadTimeline();
        } catch (err) { DMS.toast(err.message, 'error'); }
    }

    // ---- AI Generate ----
    function setupGenerateModal() {
        document.getElementById('generate-btn')?.addEventListener('click', () => {
            new bootstrap.Modal(document.getElementById('generateModal')).show();
        });

        document.getElementById('run-generate-btn')?.addEventListener('click', async () => {
            const caseId = DMS.currentCaseId;
            const provider = document.getElementById('gen-provider').value;
            if (!caseId) { DMS.toast('יש לבחור תיק', 'error'); return; }

            const btn = document.getElementById('run-generate-btn');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>מפיק...';

            try {
                const result = await DMS.api('/timeline/generate', {
                    method: 'POST',
                    json: { case_id: caseId, provider },
                });
                bootstrap.Modal.getInstance(document.getElementById('generateModal'))?.hide();
                DMS.toast(`${result.created} אירועים נוצרו מ-${result.source_materials} חומרים`, 'success');
                loadTimeline();
            } catch (err) { DMS.toast(err.message, 'error'); }

            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-robot me-1"></i>הפק';
        });
    }
})();
