/**
 * groups.js — Material group management for Case-IMS.
 */
(function () {
    let currentGroupId = null;

    document.addEventListener('DOMContentLoaded', () => {
        if (!IMS.token) { window.location.href = '/static/login.html'; return; }
        loadCases();
        loadGroups();
        setupCreateModal();
        setupDetailModal();
        setupAddMembersModal();
        document.getElementById('case-filter')?.addEventListener('change', loadGroups);
    });

    async function loadCases() {
        try {
            const cases = await IMS.api('/cases/');
            ['case-filter', 'group-case'].forEach(id => {
                const sel = document.getElementById(id);
                if (!sel) return;
                const d = id === 'case-filter' ? '<option value="">כל התיקים</option>' : '';
                sel.innerHTML = d;
                cases.forEach(c => { sel.innerHTML += `<option value="${c.id}">${IMS.esc(c.name)}</option>`; });
            });
        } catch (err) { console.warn(err); }
    }

    async function loadGroups() {
        const list = document.getElementById('groups-list');
        const spinner = document.getElementById('loading-spinner');
        const empty = document.getElementById('empty-state');
        spinner.classList.remove('d-none'); empty.classList.add('d-none'); list.innerHTML = '';

        const caseId = document.getElementById('case-filter')?.value;
        const params = caseId ? `?case_id=${caseId}` : '';

        try {
            const data = await IMS.api('/groups/' + params);
            spinner.classList.add('d-none');
            if (!data.groups.length) { empty.classList.remove('d-none'); return; }
            data.groups.forEach(g => {
                const col = document.createElement('div');
                col.className = 'col-md-6 col-lg-4';
                const E = IMS.esc;
                col.innerHTML = `
                    <div class="card group-card h-100" data-id="${g.id}">
                        <div class="card-body">
                            <h6><i class="fas fa-layer-group me-2 text-primary"></i>${E(g.name)}</h6>
                            ${g.description ? `<small class="text-muted">${E(g.description.substring(0, 100))}</small>` : ''}
                            <div class="mt-2">
                                <span class="badge bg-secondary">${g.member_count} חומרים</span>
                                ${g.analysis_result ? '<span class="badge bg-success ms-1">ניתוח זמין</span>' : ''}
                            </div>
                        </div>
                        <div class="card-footer bg-transparent pt-0">
                            <small class="text-muted">${IMS.formatDate(g.created_at)}</small>
                        </div>
                    </div>
                `;
                col.querySelector('.group-card').addEventListener('click', () => showGroupDetail(g.id));
                list.appendChild(col);
            });
        } catch (err) {
            spinner.classList.add('d-none');
            list.innerHTML = `<div class="col-12 text-center text-danger">${IMS.esc(err.message)}</div>`;
        }
    }

    function setupCreateModal() {
        document.getElementById('new-group-btn')?.addEventListener('click', () => {
            document.getElementById('group-name').value = '';
            document.getElementById('group-desc').value = '';
            new bootstrap.Modal(document.getElementById('createGroupModal')).show();
        });

        document.getElementById('create-group-btn')?.addEventListener('click', async () => {
            const name = document.getElementById('group-name').value.trim();
            const caseId = document.getElementById('group-case').value;
            if (!name || !caseId) { IMS.toast('שם ותיק חובה', 'error'); return; }
            try {
                await IMS.api('/groups/', { method: 'POST', json: { case_id: parseInt(caseId), name, description: document.getElementById('group-desc').value } });
                bootstrap.Modal.getInstance(document.getElementById('createGroupModal'))?.hide();
                IMS.toast('קבוצה נוצרה', 'success');
                loadGroups();
            } catch (err) { IMS.toast(err.message, 'error'); }
        });
    }

    async function showGroupDetail(groupId) {
        currentGroupId = groupId;
        try {
            const g = await IMS.api(`/groups/${groupId}`);
            document.getElementById('groupDetailLabel').textContent = g.name;
            const E = IMS.esc;

            let html = `
                <p>${E(g.description || '')}</p>
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6><i class="fas fa-file me-1"></i>חומרים בקבוצה (${g.members.length})</h6>
                    <button class="btn btn-sm btn-outline-primary" id="open-add-members"><i class="fas fa-plus me-1"></i>הוסף חומרים</button>
                </div>
            `;

            if (g.members.length) {
                html += `<div class="d-flex flex-column gap-2 mb-3">`;
                g.members.forEach(m => {
                    html += `<div class="member-item d-flex justify-content-between align-items-center">
                        <div>
                            <i class="${IMS.typeIcon(m.file_type)} me-2"></i>
                            <strong>${E(m.filename)}</strong>
                            <small class="text-muted ms-2">${IMS.formatSize(m.file_size)}</small>
                            ${m.content_summary ? `<small class="text-muted d-block">${E(m.content_summary.substring(0, 80))}...</small>` : ''}
                        </div>
                        <button class="btn btn-sm btn-outline-danger remove-member" data-mid="${m.material_id}"><i class="fas fa-times"></i></button>
                    </div>`;
                });
                html += `</div>`;
            } else {
                html += `<p class="text-muted">אין חומרים בקבוצה. הוסף חומרים לביצוע ניתוח.</p>`;
            }

            if (g.analysis_result) {
                html += `<h6 class="mt-3"><i class="fas fa-robot me-1"></i>תוצאות ניתוח</h6>`;
                html += `<div class="analysis-result">${E(g.analysis_result)}</div>`;
            }

            document.getElementById('group-detail-body').innerHTML = html;

            // Handlers
            document.getElementById('open-add-members')?.addEventListener('click', () => openAddMembers(groupId, g));
            document.querySelectorAll('.remove-member').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const mid = btn.dataset.mid;
                    try {
                        await IMS.api(`/groups/${groupId}/members/${mid}`, { method: 'DELETE' });
                        IMS.toast('חומר הוסר', 'success');
                        showGroupDetail(groupId);
                    } catch (err) { IMS.toast(err.message, 'error'); }
                });
            });

            new bootstrap.Modal(document.getElementById('groupDetailModal')).show();
        } catch (err) { IMS.toast(err.message, 'error'); }
    }

    function setupDetailModal() {
        document.getElementById('analyze-group-btn')?.addEventListener('click', async () => {
            if (!currentGroupId) return;
            const btn = document.getElementById('analyze-group-btn');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>מנתח...';
            try {
                const result = await IMS.api(`/groups/${currentGroupId}/analyze`, { method: 'POST' });
                IMS.toast(`ניתוח הושלם (${result.member_count} חומרים)`, 'success');
                showGroupDetail(currentGroupId);
            } catch (err) { IMS.toast(err.message, 'error'); }
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-robot me-1"></i>ניתוח AI';
        });

        document.getElementById('delete-group-btn')?.addEventListener('click', async () => {
            if (!currentGroupId || !confirm('למחוק קבוצה זו?')) return;
            try {
                await IMS.api(`/groups/${currentGroupId}`, { method: 'DELETE' });
                bootstrap.Modal.getInstance(document.getElementById('groupDetailModal'))?.hide();
                IMS.toast('קבוצה נמחקה', 'success');
                loadGroups();
            } catch (err) { IMS.toast(err.message, 'error'); }
        });
    }

    // ---- Add Members ----
    function setupAddMembersModal() {
        let searchTimeout;
        document.getElementById('member-search')?.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => loadAvailableMaterials(), 400);
        });
        document.getElementById('confirm-add-members')?.addEventListener('click', confirmAddMembers);
    }

    async function openAddMembers(groupId, group) {
        document.getElementById('add-members-group-id').value = groupId;
        document.getElementById('member-search').value = '';
        await loadAvailableMaterials();
        new bootstrap.Modal(document.getElementById('addMembersModal')).show();
    }

    async function loadAvailableMaterials() {
        const container = document.getElementById('available-materials');
        const q = document.getElementById('member-search').value.trim();
        const params = new URLSearchParams({ size: 100 });
        if (q) params.set('q', q);

        try {
            const data = await IMS.api('/materials/?' + params.toString());
            const E = IMS.esc;
            container.innerHTML = data.materials.map(m => `
                <div class="form-check mb-2">
                    <input class="form-check-input material-check" type="checkbox" value="${m.id}" id="mat-${m.id}">
                    <label class="form-check-label" for="mat-${m.id}">
                        <i class="${IMS.typeIcon(m.file_type)} me-1"></i>
                        ${E(m.filename)} <small class="text-muted">(${IMS.formatSize(m.file_size)})</small>
                    </label>
                </div>
            `).join('') || '<p class="text-muted">לא נמצאו חומרים</p>';
        } catch (err) {
            container.innerHTML = `<p class="text-danger">${IMS.esc(err.message)}</p>`;
        }
    }

    async function confirmAddMembers() {
        const groupId = document.getElementById('add-members-group-id').value;
        const checked = Array.from(document.querySelectorAll('.material-check:checked')).map(c => parseInt(c.value));
        if (!checked.length) { IMS.toast('בחר חומרים', 'warning'); return; }

        try {
            const result = await IMS.api(`/groups/${groupId}/members`, { method: 'POST', json: { material_ids: checked } });
            bootstrap.Modal.getInstance(document.getElementById('addMembersModal'))?.hide();
            IMS.toast(`${result.added} חומרים נוספו`, 'success');
            showGroupDetail(parseInt(groupId));
        } catch (err) { IMS.toast(err.message, 'error'); }
    }
})();
