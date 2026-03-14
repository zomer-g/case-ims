/**
 * ims-core.js — Main materials page logic for Case-IMS.
 * Handles dual view, folder tree, table, multi-select, bulk actions,
 * tabbed file viewer, and prompts management.
 */

(function () {
    let currentPage = 1;
    const pageSize = 50;
    let currentCaseId = null;
    let currentFolderId = null;
    let currentSortBy = 'upload_date';
    let currentSortDir = 'desc';
    let viewMode = 'tree'; // 'tree' or 'list'
    let searchTimeout = null;

    // Selection state
    let selectedIds = new Set();
    let lastCheckedIndex = -1;
    let currentMaterialsList = [];

    document.addEventListener('DOMContentLoaded', () => {
        loadCases();
        loadMaterials();
        loadFolderTree();
        setupUpload();
        setupFilters();
        setupCaseModal();
        setupMaterialModal();
        setupViewToggle();
        setupSortHeaders();
        setupSelectAll();
        setupBulkActions();
        pollQueueStatus();
    });

    // ---- View Toggle ----
    function setupViewToggle() {
        document.getElementById('view-tree-btn')?.addEventListener('click', () => {
            viewMode = 'tree';
            document.getElementById('view-tree-btn').classList.add('active');
            document.getElementById('view-list-btn').classList.remove('active');
            document.getElementById('folder-sidebar').style.display = '';
            document.getElementById('folder-col-header').style.display = 'none';
            document.querySelectorAll('.folder-cell').forEach(c => c.style.display = 'none');
        });
        document.getElementById('view-list-btn')?.addEventListener('click', () => {
            viewMode = 'list';
            document.getElementById('view-list-btn').classList.add('active');
            document.getElementById('view-tree-btn').classList.remove('active');
            document.getElementById('folder-sidebar').style.display = 'none';
            document.getElementById('folder-col-header').style.display = '';
            document.querySelectorAll('.folder-cell').forEach(c => c.style.display = '');
            currentFolderId = null;
            loadMaterials();
        });
        // Init: tree view active
        document.getElementById('folder-col-header').style.display = 'none';
    }

    // ---- Sort Headers ----
    function setupSortHeaders() {
        document.querySelectorAll('.sortable-col').forEach(th => {
            th.addEventListener('click', () => {
                const col = th.dataset.sort;
                if (currentSortBy === col) {
                    currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    currentSortBy = col;
                    currentSortDir = 'asc';
                }
                updateSortArrows();
                currentPage = 1;
                loadMaterials();
            });
        });
    }

    function updateSortArrows() {
        document.querySelectorAll('.sortable-col').forEach(th => {
            const arrow = th.querySelector('.sort-arrow');
            if (th.dataset.sort === currentSortBy) {
                arrow.className = `fas fa-sort-${currentSortDir === 'asc' ? 'up' : 'down'} sort-arrow`;
            } else {
                arrow.className = 'fas fa-sort sort-arrow text-muted';
            }
        });
    }

    // ---- Cases ----
    async function loadCases() {
        if (!IMS.token) return;
        try {
            const cases = await IMS.api('/cases/');
            const select = document.getElementById('case-select');
            select.innerHTML = '<option value="">כל התיקים</option>';
            cases.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = `${c.name} (${c.material_count})`;
                select.appendChild(opt);
            });
        } catch (err) { console.warn('Failed to load cases:', err); }
    }

    function setupCaseModal() {
        document.getElementById('new-case-btn')?.addEventListener('click', () => {
            if (!IMS.token) { window.location.href = '/static/login.html'; return; }
            new bootstrap.Modal(document.getElementById('newCaseModal')).show();
        });
        document.getElementById('create-case-btn')?.addEventListener('click', async () => {
            const name = document.getElementById('case-name').value.trim();
            if (!name) return;
            try {
                await IMS.api('/cases/', { method: 'POST', json: { name, description: document.getElementById('case-desc').value } });
                bootstrap.Modal.getInstance(document.getElementById('newCaseModal')).hide();
                document.getElementById('case-name').value = '';
                document.getElementById('case-desc').value = '';
                loadCases();
                IMS.toast('התיק נוצר בהצלחה', 'success');
            } catch (err) { IMS.toast(err.message, 'error'); }
        });
    }

    // ---- Folder Tree ----
    async function loadFolderTree() {
        const container = document.getElementById('folder-tree');
        if (!container) return;
        try {
            const params = new URLSearchParams({ tree: 'true' });
            if (currentCaseId) params.set('case_id', currentCaseId);
            const data = await IMS.api('/folders/?' + params.toString());

            container.innerHTML = '';
            // "All files" root item
            const allItem = document.createElement('div');
            allItem.className = `folder-tree-item ${!currentFolderId ? 'active' : ''}`;
            allItem.innerHTML = `<i class="fas fa-home me-1 text-muted"></i>כל הקבצים`;
            allItem.addEventListener('click', () => {
                currentFolderId = null;
                currentPage = 1;
                loadMaterials();
                updateTreeActive();
            });
            container.appendChild(allItem);

            if (data.tree && data.tree.length) {
                renderTreeNodes(container, data.tree, 0);
            }
        } catch (err) { console.warn('Failed to load folder tree:', err); }
    }

    function renderTreeNodes(parent, nodes, depth) {
        nodes.forEach(node => {
            const item = document.createElement('div');
            item.className = `folder-tree-item ${currentFolderId === node.id ? 'active' : ''}`;
            item.style.paddingRight = (0.5 + depth * 1) + 'rem';
            item.dataset.folderId = node.id;
            const hasChildren = node.children && node.children.length;
            item.innerHTML = `<i class="fas fa-folder me-1 text-warning"></i>${IMS.esc(node.name)} <small class="text-muted">(${node.material_count || 0})</small>`;
            item.addEventListener('click', () => {
                currentFolderId = node.id;
                currentPage = 1;
                loadMaterials();
                updateTreeActive();
            });
            parent.appendChild(item);

            if (hasChildren) {
                const childContainer = document.createElement('div');
                childContainer.className = 'folder-children';
                renderTreeNodes(childContainer, node.children, depth + 1);
                parent.appendChild(childContainer);
            }
        });
    }

    function updateTreeActive() {
        document.querySelectorAll('.folder-tree-item').forEach(item => {
            const fid = item.dataset.folderId;
            if ((!fid && !currentFolderId) || (fid && parseInt(fid) === currentFolderId)) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }

    // ---- Materials List ----
    async function loadMaterials() {
        const tbody = document.getElementById('materials-tbody');
        const spinner = document.getElementById('loading-spinner');
        const empty = document.getElementById('empty-state');

        spinner.classList.remove('d-none');
        empty.classList.add('d-none');
        tbody.innerHTML = '';

        const params = new URLSearchParams({ page: currentPage, size: pageSize });
        if (currentCaseId) params.set('case_id', currentCaseId);
        if (currentFolderId) params.set('folder_id', currentFolderId);
        if (currentSortBy) params.set('sort_by', currentSortBy);
        if (currentSortDir) params.set('sort_dir', currentSortDir);

        const typeFilter = document.getElementById('type-filter')?.value;
        if (typeFilter) params.set('file_type', typeFilter);

        const statusFilter = document.getElementById('status-filter')?.value;
        if (statusFilter) params.set('status', statusFilter);

        const searchQ = document.getElementById('search-input')?.value?.trim();
        if (searchQ) params.set('search', searchQ);

        try {
            const data = await IMS.api('/materials/?' + params.toString());
            spinner.classList.add('d-none');
            document.getElementById('total-count').textContent = `${data.total} חומרים`;
            currentMaterialsList = data.materials;

            if (data.materials.length === 0) {
                empty.classList.remove('d-none');
                return;
            }

            data.materials.forEach((mat, idx) => {
                tbody.appendChild(createMaterialRow(mat, idx));
            });

            renderPagination(data.total, data.page, data.size);
            updateBulkBar();
        } catch (err) {
            spinner.classList.add('d-none');
            if (err.message !== 'Session expired') {
                tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger">${IMS.esc(err.message)}</td></tr>`;
            }
        }
    }

    function createMaterialRow(mat, idx) {
        const tr = document.createElement('tr');
        tr.className = `file-row ${selectedIds.has(mat.id) ? 'selected' : ''}`;
        tr.dataset.materialId = mat.id;
        tr.dataset.index = idx;
        const E = IMS.esc;
        const icon = IMS.typeIconDetailed ? IMS.typeIconDetailed(mat.file_type, mat.filename) : IMS.typeIcon(mat.file_type);

        const folderDisplay = mat.folder_name || (mat.original_path ? mat.original_path.split('/').slice(0, -1).join('/') : '');

        tr.innerHTML = `
            <td onclick="event.stopPropagation()"><input type="checkbox" class="form-check-input row-cb" data-id="${mat.id}" data-idx="${idx}" ${selectedIds.has(mat.id) ? 'checked' : ''}></td>
            <td><i class="${icon}" title="${E(mat.file_type)}"></i></td>
            <td class="text-truncate" style="max-width:300px" title="${E(mat.filename)}">${E(mat.filename)}</td>
            <td><small>${E(mat.file_type)}</small></td>
            <td class="folder-cell text-truncate" style="max-width:150px;${viewMode === 'tree' ? 'display:none' : ''}" title="${E(folderDisplay)}">${E(folderDisplay) || '-'}</td>
            <td><small>${IMS.formatSize(mat.file_size)}</small></td>
            <td><small>${IMS.formatDateShort(mat.upload_date)}</small></td>
            <td>${IMS.statusBadge(mat.extraction_status)}</td>
        `;

        // Click row to view detail
        tr.addEventListener('click', (e) => {
            if (e.target.closest('.row-cb') || e.target.tagName === 'INPUT') return;
            showMaterialDetail(mat.id);
        });

        // Checkbox with Shift+click
        const cb = tr.querySelector('.row-cb');
        cb.addEventListener('change', (e) => {
            handleCheckboxChange(e, mat.id, idx);
        });

        return tr;
    }

    // ---- Select All ----
    function setupSelectAll() {
        document.getElementById('select-all-cb')?.addEventListener('change', (e) => {
            const checked = e.target.checked;
            document.querySelectorAll('.row-cb').forEach(cb => {
                cb.checked = checked;
                const id = parseInt(cb.dataset.id);
                if (checked) selectedIds.add(id);
                else selectedIds.delete(id);
                cb.closest('tr')?.classList.toggle('selected', checked);
            });
            updateBulkBar();
        });
    }

    function handleCheckboxChange(e, materialId, idx) {
        if (e.shiftKey && lastCheckedIndex >= 0) {
            const start = Math.min(lastCheckedIndex, idx);
            const end = Math.max(lastCheckedIndex, idx);
            const rows = document.querySelectorAll('.file-row');
            for (let i = start; i <= end; i++) {
                const row = rows[i];
                if (!row) continue;
                const cb = row.querySelector('.row-cb');
                const id = parseInt(cb.dataset.id);
                cb.checked = true;
                selectedIds.add(id);
                row.classList.add('selected');
            }
        } else {
            if (e.target.checked) {
                selectedIds.add(materialId);
                e.target.closest('tr')?.classList.add('selected');
            } else {
                selectedIds.delete(materialId);
                e.target.closest('tr')?.classList.remove('selected');
            }
        }
        lastCheckedIndex = idx;
        updateBulkBar();
    }

    function updateBulkBar() {
        const bar = document.getElementById('bulk-action-bar');
        if (selectedIds.size > 0) {
            bar.classList.remove('d-none');
            document.getElementById('bulk-count').textContent = `${selectedIds.size} נבחרו`;
        } else {
            bar.classList.add('d-none');
        }
    }

    // ---- Bulk Actions ----
    function setupBulkActions() {
        document.getElementById('bulk-clear-btn')?.addEventListener('click', clearSelection);

        // Tag
        document.getElementById('bulk-tag-btn')?.addEventListener('click', () => {
            document.getElementById('bulk-tag-input').value = '';
            new bootstrap.Modal(document.getElementById('bulkTagModal')).show();
        });
        document.getElementById('bulk-tag-confirm')?.addEventListener('click', async () => {
            const tag = document.getElementById('bulk-tag-input').value.trim();
            if (!tag) return;
            try {
                const result = await IMS.api('/materials/bulk/tag', { method: 'POST', json: { material_ids: [...selectedIds], tag } });
                IMS.toast(`תגית "${tag}" נוספה ל-${result.updated} חומרים`, 'success');
                bootstrap.Modal.getInstance(document.getElementById('bulkTagModal')).hide();
                clearSelection();
                loadMaterials();
            } catch (err) { IMS.toast(err.message, 'error'); }
        });

        // Prompt
        document.getElementById('bulk-prompt-btn')?.addEventListener('click', async () => {
            document.getElementById('prompt-result-container').classList.add('d-none');
            document.getElementById('bulk-prompt-text').value = '';
            await loadPromptOptions();
            new bootstrap.Modal(document.getElementById('bulkPromptModal')).show();
        });
        document.getElementById('bulk-prompt-select')?.addEventListener('change', (e) => {
            const opt = e.target.options[e.target.selectedIndex];
            if (opt.dataset.text) document.getElementById('bulk-prompt-text').value = opt.dataset.text;
        });
        document.getElementById('bulk-prompt-run')?.addEventListener('click', runBulkPrompt);

        // Entity
        document.getElementById('bulk-entity-btn')?.addEventListener('click', () => {
            document.getElementById('entity-search-input').value = '';
            document.getElementById('entity-search-results').innerHTML = '';
            new bootstrap.Modal(document.getElementById('bulkEntityModal')).show();
        });
        let entitySearchTimeout;
        document.getElementById('entity-search-input')?.addEventListener('input', () => {
            clearTimeout(entitySearchTimeout);
            entitySearchTimeout = setTimeout(searchEntities, 400);
        });
        document.getElementById('create-entity-link-btn')?.addEventListener('click', createAndLinkEntity);

        // Event
        document.getElementById('bulk-event-btn')?.addEventListener('click', () => {
            document.getElementById('event-search-input').value = '';
            document.getElementById('event-search-results').innerHTML = '';
            new bootstrap.Modal(document.getElementById('bulkEventModal')).show();
        });
        let eventSearchTimeout;
        document.getElementById('event-search-input')?.addEventListener('input', () => {
            clearTimeout(eventSearchTimeout);
            eventSearchTimeout = setTimeout(searchEvents, 400);
        });
        document.getElementById('create-event-link-btn')?.addEventListener('click', createAndLinkEvent);

        // Upload toggle
        document.getElementById('toggle-upload-btn')?.addEventListener('click', () => {
            const wrapper = document.getElementById('upload-zone-wrapper');
            if (!IMS.token) { window.location.href = '/static/login.html'; return; }
            wrapper.classList.toggle('d-none');
        });
    }

    function clearSelection() {
        selectedIds.clear();
        lastCheckedIndex = -1;
        document.querySelectorAll('.row-cb').forEach(cb => { cb.checked = false; });
        document.querySelectorAll('.file-row').forEach(r => r.classList.remove('selected'));
        const selectAllCb = document.getElementById('select-all-cb');
        if (selectAllCb) selectAllCb.checked = false;
        updateBulkBar();
    }

    async function loadPromptOptions() {
        const sel = document.getElementById('bulk-prompt-select');
        sel.innerHTML = '<option value="">-- פרומפט מותאם אישית --</option>';
        try {
            const data = await IMS.api('/prompts/');
            data.prompts.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.name;
                opt.dataset.text = p.prompt_text;
                sel.appendChild(opt);
            });
        } catch {}
    }

    async function runBulkPrompt() {
        const promptId = document.getElementById('bulk-prompt-select').value;
        const promptText = document.getElementById('bulk-prompt-text').value.trim();
        const btn = document.getElementById('bulk-prompt-run');
        const resultContainer = document.getElementById('prompt-result-container');
        const resultText = document.getElementById('prompt-result-text');

        if (!promptText && !promptId) { IMS.toast('הכנס טקסט פרומפט', 'error'); return; }

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>מריץ...';

        try {
            let result;
            if (promptId) {
                result = await IMS.api(`/prompts/${promptId}/run`, { method: 'POST', json: { material_ids: [...selectedIds] } });
            } else {
                result = await IMS.api('/prompts/run-custom', { method: 'POST', json: { material_ids: [...selectedIds], prompt_text: promptText } });
            }
            resultContainer.classList.remove('d-none');
            resultText.textContent = JSON.stringify(result.result, null, 2);
            IMS.toast('הפרומפט הורץ בהצלחה', 'success');
        } catch (err) { IMS.toast(err.message, 'error'); }

        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-play me-1"></i>הרץ';
    }

    async function searchEntities() {
        const q = document.getElementById('entity-search-input').value.trim();
        const container = document.getElementById('entity-search-results');
        if (!q) { container.innerHTML = ''; return; }

        try {
            const params = new URLSearchParams({ q, size: 20 });
            if (currentCaseId) params.set('case_id', currentCaseId);
            const data = await IMS.api('/entities/?' + params.toString());
            container.innerHTML = '';
            if (!data.entities.length) { container.innerHTML = '<small class="text-muted">לא נמצאו ישויות</small>'; return; }
            data.entities.forEach(e => {
                const div = document.createElement('div');
                div.className = 'd-flex justify-content-between align-items-center p-1 border-bottom';
                div.innerHTML = `
                    <span><i class="${IMS.entityTypeIcon(e.entity_type)} me-1" style="color:${IMS.entityTypeColor(e.entity_type)}"></i>${IMS.esc(e.name)} <small class="text-muted">${IMS.entityTypeLabel(e.entity_type)}</small></span>
                    <button class="btn btn-sm btn-outline-primary link-entity-btn" data-id="${e.id}">קשר</button>
                `;
                div.querySelector('.link-entity-btn').addEventListener('click', async () => {
                    try {
                        const result = await IMS.api('/materials/bulk/link-entities', { method: 'POST', json: { material_ids: [...selectedIds], entity_ids: [e.id] } });
                        IMS.toast(`${result.linked} קישורים נוצרו`, 'success');
                    } catch (err) { IMS.toast(err.message, 'error'); }
                });
                container.appendChild(div);
            });
        } catch {}
    }

    async function createAndLinkEntity() {
        const name = document.getElementById('new-entity-name').value.trim();
        const type = document.getElementById('new-entity-type').value;
        if (!name) { IMS.toast('הכנס שם ישות', 'error'); return; }
        const caseId = currentCaseId || (currentMaterialsList[0]?.case_id);
        if (!caseId) { IMS.toast('בחר תיק', 'error'); return; }

        try {
            const result = await IMS.api('/materials/bulk/link-entities', {
                method: 'POST',
                json: { material_ids: [...selectedIds], entity_ids: [], create_entities: [{ name, entity_type: type, case_id: caseId }] }
            });
            IMS.toast(`ישות "${name}" נוצרה וקושרה ל-${result.linked} חומרים`, 'success');
            document.getElementById('new-entity-name').value = '';
        } catch (err) { IMS.toast(err.message, 'error'); }
    }

    async function searchEvents() {
        const q = document.getElementById('event-search-input').value.trim();
        const container = document.getElementById('event-search-results');
        if (!q) { container.innerHTML = ''; return; }

        try {
            const params = new URLSearchParams({ size: 50 });
            if (currentCaseId) params.set('case_id', currentCaseId);
            const data = await IMS.api('/timeline/?' + params.toString());
            const filtered = data.events.filter(ev => ev.title.includes(q));
            container.innerHTML = '';
            if (!filtered.length) { container.innerHTML = '<small class="text-muted">לא נמצאו אירועים</small>'; return; }
            filtered.forEach(ev => {
                const div = document.createElement('div');
                div.className = 'd-flex justify-content-between align-items-center p-1 border-bottom';
                div.innerHTML = `
                    <span><i class="fas fa-calendar-alt me-1 text-danger"></i>${IMS.esc(ev.title)} <small class="text-muted">${IMS.formatDateShort(ev.event_date)}</small></span>
                    <button class="btn btn-sm btn-outline-primary link-event-btn" data-id="${ev.id}">קשר</button>
                `;
                div.querySelector('.link-event-btn').addEventListener('click', async () => {
                    try {
                        const result = await IMS.api('/materials/bulk/link-timeline', { method: 'POST', json: { material_ids: [...selectedIds], event_ids: [ev.id] } });
                        IMS.toast(`${result.linked} קישורים נוצרו`, 'success');
                    } catch (err) { IMS.toast(err.message, 'error'); }
                });
                container.appendChild(div);
            });
        } catch {}
    }

    async function createAndLinkEvent() {
        const title = document.getElementById('new-event-title').value.trim();
        const eventDate = document.getElementById('new-event-date').value;
        if (!title || !eventDate) { IMS.toast('כותרת ותאריך חובה', 'error'); return; }
        const caseId = currentCaseId || (currentMaterialsList[0]?.case_id);
        if (!caseId) { IMS.toast('בחר תיק', 'error'); return; }

        try {
            const result = await IMS.api('/materials/bulk/link-timeline', {
                method: 'POST',
                json: { material_ids: [...selectedIds], event_ids: [], create_events: [{ title, event_date: eventDate, case_id: caseId }] }
            });
            IMS.toast(`אירוע "${title}" נוצר וקושר ל-${result.linked} חומרים`, 'success');
            document.getElementById('new-event-title').value = '';
            document.getElementById('new-event-date').value = '';
        } catch (err) { IMS.toast(err.message, 'error'); }
    }

    function renderPagination(total, page, size) {
        const nav = document.getElementById('pagination-nav');
        const ul = document.getElementById('pagination');
        const totalPages = Math.ceil(total / size);
        if (totalPages <= 1) { nav.classList.add('d-none'); return; }

        nav.classList.remove('d-none');
        ul.innerHTML = '';

        const maxVisible = 7;
        let start = Math.max(1, page - Math.floor(maxVisible / 2));
        let end = Math.min(totalPages, start + maxVisible - 1);
        if (end - start < maxVisible - 1) start = Math.max(1, end - maxVisible + 1);

        if (start > 1) {
            addPageItem(ul, 1, page);
            if (start > 2) ul.innerHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        for (let i = start; i <= end; i++) addPageItem(ul, i, page);
        if (end < totalPages) {
            if (end < totalPages - 1) ul.innerHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
            addPageItem(ul, totalPages, page);
        }
    }

    function addPageItem(ul, num, currentPageNum) {
        const li = document.createElement('li');
        li.className = `page-item ${num === currentPageNum ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#">${num}</a>`;
        li.addEventListener('click', (e) => { e.preventDefault(); currentPage = num; loadMaterials(); });
        ul.appendChild(li);
    }

    // ---- Filters ----
    function setupFilters() {
        document.getElementById('case-select')?.addEventListener('change', (e) => {
            currentCaseId = e.target.value ? parseInt(e.target.value) : null;
            currentFolderId = null;
            currentPage = 1;
            loadMaterials();
            loadFolderTree();
        });

        document.getElementById('type-filter')?.addEventListener('change', () => { currentPage = 1; loadMaterials(); });
        document.getElementById('status-filter')?.addEventListener('change', () => { currentPage = 1; loadMaterials(); });

        document.getElementById('search-input')?.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => { currentPage = 1; loadMaterials(); }, 400);
        });
    }

    // ---- Upload ----
    function setupUpload() {
        const zone = document.getElementById('upload-zone');
        const fileInput = document.getElementById('file-input');
        const folderInput = document.getElementById('folder-input');
        if (!zone || !fileInput) return;

        zone.addEventListener('click', (e) => {
            if (e.target.closest('button')) return;
            fileInput.click();
        });
        zone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });

        document.getElementById('upload-files-btn')?.addEventListener('click', () => fileInput.click());
        document.getElementById('upload-folder-btn')?.addEventListener('click', () => folderInput?.click());

        zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', async (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            const items = e.dataTransfer.items;
            if (items && items.length) {
                const fileEntries = [];
                const promises = [];
                for (let i = 0; i < items.length; i++) {
                    const entry = items[i].webkitGetAsEntry ? items[i].webkitGetAsEntry() : null;
                    if (entry) {
                        promises.push(traverseEntry(entry, '', fileEntries));
                    } else if (items[i].kind === 'file') {
                        const f = items[i].getAsFile();
                        if (f) fileEntries.push({ file: f, relativePath: '' });
                    }
                }
                await Promise.all(promises);
                if (fileEntries.length) uploadFiles(fileEntries);
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) {
                uploadFiles(Array.from(fileInput.files).map(f => ({ file: f, relativePath: '' })));
            }
            fileInput.value = '';
        });

        if (folderInput) {
            folderInput.addEventListener('change', () => {
                if (folderInput.files.length) {
                    const entries = Array.from(folderInput.files).map(f => {
                        const relPath = f.webkitRelativePath || '';
                        const parts = relPath.split('/');
                        const folderPath = parts.length > 1 ? parts.slice(0, -1).join('/') : '';
                        return { file: f, relativePath: folderPath };
                    });
                    uploadFiles(entries);
                }
                folderInput.value = '';
            });
        }
    }

    function traverseEntry(entry, basePath, results) {
        return new Promise((resolve) => {
            if (entry.isFile) {
                entry.file((file) => { results.push({ file, relativePath: basePath }); resolve(); }, () => resolve());
            } else if (entry.isDirectory) {
                const reader = entry.createReader();
                const dirPath = basePath ? basePath + '/' + entry.name : entry.name;
                const readAll = (entries) => {
                    reader.readEntries((batch) => {
                        if (batch.length === 0) { Promise.all(entries).then(resolve); }
                        else { readAll([...entries, ...batch.map(e => traverseEntry(e, dirPath, results))]); }
                    }, () => resolve());
                };
                readAll([]);
            } else { resolve(); }
        });
    }

    async function uploadFiles(fileEntries) {
        const progress = document.getElementById('upload-progress');
        const summary = document.getElementById('upload-summary');
        const caseId = currentCaseId;
        const total = fileEntries.length;
        let succeeded = 0, failed = 0;

        if (summary) { summary.classList.remove('d-none'); summary.textContent = `מעלה 0/${total} קבצים...`; }

        const CONCURRENCY = 3;
        let index = 0;

        async function uploadNext() {
            while (index < fileEntries.length) {
                const i = index++;
                const { file, relativePath } = fileEntries[i];
                const id = 'up-' + Math.random().toString(36).substring(2, 8);
                const displayName = relativePath ? relativePath + '/' + file.name : file.name;

                progress.innerHTML += `<div id="${id}" class="d-flex align-items-center gap-2 mb-1"><i class="fas fa-spinner fa-spin text-light"></i><span class="text-light small">${IMS.esc(displayName)}</span></div>`;

                try {
                    const formData = new FormData();
                    formData.append('file', file);
                    if (caseId) formData.append('case_id', caseId);
                    if (relativePath) formData.append('relative_path', relativePath);
                    await IMS.api('/materials/upload', { method: 'POST', body: formData });
                    succeeded++;
                    const el = document.getElementById(id);
                    if (el) el.innerHTML = `<i class="fas fa-check text-success"></i><span class="text-light small">${IMS.esc(displayName)} — הועלה</span>`;
                } catch (err) {
                    failed++;
                    const el = document.getElementById(id);
                    if (el) el.innerHTML = `<i class="fas fa-times text-danger"></i><span class="text-light small">${IMS.esc(displayName)} — ${IMS.esc(err.message)}</span>`;
                }
                if (summary) summary.textContent = `מעלה ${succeeded + failed}/${total} קבצים... (${succeeded} הצליחו, ${failed} נכשלו)`;
            }
        }

        const workers = [];
        for (let w = 0; w < CONCURRENCY; w++) workers.push(uploadNext());
        await Promise.all(workers);

        if (summary) summary.textContent = `הסתיים: ${succeeded}/${total} קבצים הועלו בהצלחה` + (failed ? ` (${failed} נכשלו)` : '');

        setTimeout(() => {
            progress.innerHTML = '';
            if (summary) { summary.classList.add('d-none'); summary.textContent = ''; }
            loadMaterials();
            loadFolderTree();
        }, 4000);
    }

    // ---- Material Detail Modal (Tabbed) ----
    function setupMaterialModal() {
        document.getElementById('modal-reprocess-btn')?.addEventListener('click', async () => {
            const id = document.getElementById('materialModal').dataset.materialId;
            if (!id) return;
            try {
                await IMS.api(`/materials/${id}/reprocess`, { method: 'POST' });
                IMS.toast('החומר נשלח לעיבוד מחדש', 'success');
            } catch (err) { IMS.toast(err.message, 'error'); }
        });

        document.getElementById('modal-delete-btn')?.addEventListener('click', async () => {
            const id = document.getElementById('materialModal').dataset.materialId;
            if (!id || !confirm('למחוק את החומר?')) return;
            try {
                await IMS.api(`/materials/${id}`, { method: 'DELETE' });
                bootstrap.Modal.getInstance(document.getElementById('materialModal')).hide();
                loadMaterials();
                IMS.toast('החומר נמחק', 'success');
            } catch (err) { IMS.toast(err.message, 'error'); }
        });
    }

    async function showMaterialDetail(id) {
        const modal = document.getElementById('materialModal');
        modal.dataset.materialId = id;

        try {
            const mat = await IMS.api(`/materials/${id}`);
            document.getElementById('materialModalLabel').textContent = mat.filename;
            document.getElementById('modal-download-btn').href = `/materials/${id}/download`;

            const body = document.getElementById('material-detail-body');
            const E = IMS.esc;

            body.innerHTML = `
                <ul class="nav nav-tabs" role="tablist">
                    <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#tab-source"><i class="fas fa-eye me-1"></i>מקור</button></li>
                    <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-markdown"><i class="fas fa-file-code me-1"></i>Markdown</button></li>
                    <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-metadata"><i class="fas fa-database me-1"></i>פרמטרים</button></li>
                    <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-entities"><i class="fas fa-project-diagram me-1"></i>ישויות</button></li>
                    <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-events"><i class="fas fa-calendar-alt me-1"></i>אירועים</button></li>
                </ul>
                <div class="tab-content pt-3">
                    <div class="tab-pane fade show active" id="tab-source">${renderSourceTab(mat)}</div>
                    <div class="tab-pane fade" id="tab-markdown">${renderMarkdownTab(mat)}</div>
                    <div class="tab-pane fade" id="tab-metadata">${renderMetadataTab(mat)}</div>
                    <div class="tab-pane fade" id="tab-entities"><div id="entities-tab-content"><div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div></div></div>
                    <div class="tab-pane fade" id="tab-events"><div id="events-tab-content"><div class="text-center py-3"><div class="spinner-border spinner-border-sm"></div></div></div></div>
                </div>
            `;

            new bootstrap.Modal(modal).show();
            loadEntitiesTab(id);
            loadEventsTab(id);
        } catch (err) { IMS.toast(err.message, 'error'); }
    }

    function renderSourceTab(mat) {
        const E = IMS.esc;
        if (mat.file_type === 'pdf') {
            return `<iframe src="/materials/${mat.id}/download" style="width:100%;height:500px;border:none;" title="${E(mat.filename)}"></iframe>`;
        } else if (mat.file_type === 'image') {
            return `<div class="text-center"><img src="/materials/${mat.id}/download" alt="${E(mat.filename)}" class="img-fluid rounded" style="max-height:500px;"></div>`;
        } else if (mat.file_type === 'audio') {
            return `<audio controls class="w-100"><source src="/materials/${mat.id}/download" type="${mat.mime_type || 'audio/mpeg'}"></audio>`;
        } else if (mat.file_type === 'video') {
            return `<video controls class="w-100" style="max-height:500px;"><source src="/materials/${mat.id}/download" type="${mat.mime_type || 'video/mp4'}"></video>`;
        }
        return `
            <div class="text-center py-4">
                <i class="${IMS.typeIcon(mat.file_type)} fa-3x mb-3 d-block"></i>
                <p>${E(mat.filename)}</p>
                <p class="text-muted">${E(mat.file_type)} — ${IMS.formatSize(mat.file_size)}</p>
                <a href="/materials/${mat.id}/download" class="btn btn-primary"><i class="fas fa-download me-1"></i>הורדה</a>
            </div>
        `;
    }

    function renderMarkdownTab(mat) {
        if (!mat.content_text) return '<p class="text-muted text-center py-4">אין תוכן טקסט זמין</p>';
        try {
            if (typeof marked !== 'undefined') {
                const html = marked.parse(mat.content_text);
                return `<div class="md-preview">${html}</div>`;
            }
        } catch {}
        return `<div class="content-text-preview">${IMS.esc(mat.content_text)}</div>`;
    }

    function renderMetadataTab(mat) {
        const E = IMS.esc;
        let html = `
            <div class="row mb-3">
                <div class="col-md-6">
                    <table class="table table-sm">
                        <tr><td class="fw-bold">סוג קובץ</td><td>${E(mat.file_type)}</td></tr>
                        <tr><td class="fw-bold">MIME</td><td><code>${E(mat.mime_type)}</code></td></tr>
                        <tr><td class="fw-bold">גודל</td><td>${IMS.formatSize(mat.file_size)}</td></tr>
                        <tr><td class="fw-bold">תאריך העלאה</td><td>${IMS.formatDate(mat.upload_date)}</td></tr>
                        ${mat.page_count ? `<tr><td class="fw-bold">עמודים</td><td>${mat.page_count}</td></tr>` : ''}
                        ${mat.duration_seconds ? `<tr><td class="fw-bold">אורך</td><td>${Math.floor(mat.duration_seconds / 60)}:${String(mat.duration_seconds % 60).padStart(2, '0')}</td></tr>` : ''}
                    </table>
                </div>
                <div class="col-md-6">
                    <table class="table table-sm">
                        <tr><td class="fw-bold">סטטוס</td><td>${IMS.statusBadge(mat.extraction_status)}</td></tr>
                        <tr><td class="fw-bold">Hash</td><td><code class="small">${E((mat.file_hash || '').substring(0, 20))}...</code></td></tr>
                        <tr><td class="fw-bold">ציבורי</td><td>${mat.is_public ? 'כן' : 'לא'}</td></tr>
                        ${mat.case_name ? `<tr><td class="fw-bold">תיק</td><td>${E(mat.case_name)}</td></tr>` : ''}
                        ${mat.dimensions ? `<tr><td class="fw-bold">ממדים</td><td>${E(mat.dimensions)}</td></tr>` : ''}
                    </table>
                </div>
            </div>
        `;

        if (mat.content_summary) {
            html += `<h6><i class="fas fa-align-right me-1"></i>תקציר</h6><p class="bg-light p-2 rounded">${E(mat.content_summary)}</p>`;
        }

        const analysis = mat.metadata_json?.ai_analysis;
        if (analysis && typeof analysis === 'object') {
            html += '<h6 class="mt-3"><i class="fas fa-robot me-1"></i>ניתוח AI</h6><div class="table-responsive"><table class="table table-sm table-bordered">';
            for (const [key, val] of Object.entries(analysis)) {
                const display = Array.isArray(val) ? val.join(', ') : (typeof val === 'object' ? JSON.stringify(val, null, 2) : val);
                html += `<tr><td class="fw-bold" style="width:30%">${E(key)}</td><td>${E(String(display)) || '-'}</td></tr>`;
            }
            html += '</table></div>';
        }

        const customKeys = Object.keys(mat.metadata_json || {}).filter(k => k !== 'ai_analysis');
        if (customKeys.length) {
            html += '<h6 class="mt-3"><i class="fas fa-tags me-1"></i>מטא-דאטה נוסף</h6><div class="table-responsive"><table class="table table-sm table-bordered">';
            for (const key of customKeys) {
                const val = mat.metadata_json[key];
                const display = typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val);
                html += `<tr><td class="fw-bold" style="width:30%">${E(key)}</td><td>${E(display)}</td></tr>`;
            }
            html += '</table></div>';
        }

        return html;
    }

    async function loadEntitiesTab(materialId) {
        const container = document.getElementById('entities-tab-content');
        if (!container) return;
        try {
            const data = await IMS.api(`/materials/${materialId}/entities`);
            if (!data.entities.length) {
                container.innerHTML = '<p class="text-muted text-center py-3">אין ישויות מקושרות</p>';
                return;
            }
            let html = '<div class="d-flex flex-column gap-2">';
            data.entities.forEach(e => {
                html += `
                    <div class="d-flex align-items-center gap-2 p-2 border rounded">
                        <i class="${IMS.entityTypeIcon(e.entity_type)}" style="color:${IMS.entityTypeColor(e.entity_type)}"></i>
                        <div>
                            <strong>${IMS.esc(e.name)}</strong>
                            <small class="text-muted d-block">${IMS.entityTypeLabel(e.entity_type)}${e.relevance ? ' — ' + IMS.esc(e.relevance) : ''}</small>
                            ${e.detail ? `<small class="text-muted">${IMS.esc(e.detail)}</small>` : ''}
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
        } catch (err) {
            container.innerHTML = `<p class="text-danger">${IMS.esc(err.message)}</p>`;
        }
    }

    async function loadEventsTab(materialId) {
        const container = document.getElementById('events-tab-content');
        if (!container) return;
        try {
            const data = await IMS.api(`/materials/${materialId}/timeline-events`);
            if (!data.events.length) {
                container.innerHTML = '<p class="text-muted text-center py-3">אין אירועים מקושרים</p>';
                return;
            }
            let html = '<div class="d-flex flex-column gap-2">';
            data.events.forEach(ev => {
                html += `
                    <div class="d-flex align-items-center gap-2 p-2 border rounded">
                        <i class="fas fa-calendar-alt text-danger"></i>
                        <div>
                            <strong>${IMS.esc(ev.title)}</strong>
                            <small class="text-muted d-block">${IMS.formatDateShort(ev.event_date)}${ev.event_end_date ? ' — ' + IMS.formatDateShort(ev.event_end_date) : ''}</small>
                            ${ev.description ? `<small class="text-muted">${IMS.esc(ev.description)}</small>` : ''}
                            ${ev.location ? `<small class="text-muted d-block"><i class="fas fa-map-marker-alt me-1"></i>${IMS.esc(ev.location)}</small>` : ''}
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
        } catch (err) {
            container.innerHTML = `<p class="text-danger">${IMS.esc(err.message)}</p>`;
        }
    }

    // ---- Queue Status Polling ----
    function pollQueueStatus() {
        if (!IMS.token) return;
        async function check() {
            try {
                const data = await IMS.api('/queue/status');
                const bar = document.getElementById('queue-status-bar');
                if (data.running_count > 0 || data.pending_count > 0) {
                    bar.classList.remove('d-none');
                    document.getElementById('queue-running').textContent = data.running_count;
                    document.getElementById('queue-pending').textContent = data.pending_count;
                } else {
                    bar.classList.add('d-none');
                }
            } catch {}
        }
        check();
        setInterval(check, 10000);
    }
})();
