/**
 * ims-core.js — Main materials page logic for Case-IMS.
 * Handles material listing, upload, case management, and detail view.
 */

(function () {
    let currentPage = 1;
    const pageSize = 50;
    let currentCaseId = null;
    let searchTimeout = null;

    document.addEventListener('DOMContentLoaded', () => {
        loadCases();
        loadMaterials();
        setupUpload();
        setupFilters();
        setupCaseModal();
        setupMaterialModal();
        pollQueueStatus();
    });

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
        } catch (err) {
            console.warn('Failed to load cases:', err);
        }
    }

    function setupCaseModal() {
        const newCaseBtn = document.getElementById('new-case-btn');
        const createBtn = document.getElementById('create-case-btn');
        if (!newCaseBtn || !createBtn) return;

        newCaseBtn.addEventListener('click', () => {
            if (!IMS.token) { window.location.href = '/static/login.html'; return; }
            new bootstrap.Modal(document.getElementById('newCaseModal')).show();
        });

        createBtn.addEventListener('click', async () => {
            const name = document.getElementById('case-name').value.trim();
            if (!name) return;
            try {
                await IMS.api('/cases/', { method: 'POST', json: { name, description: document.getElementById('case-desc').value } });
                bootstrap.Modal.getInstance(document.getElementById('newCaseModal')).hide();
                document.getElementById('case-name').value = '';
                document.getElementById('case-desc').value = '';
                loadCases();
                IMS.toast('התיק נוצר בהצלחה', 'success');
            } catch (err) {
                IMS.toast(err.message, 'error');
            }
        });
    }

    // ---- Materials List ----
    async function loadMaterials() {
        const list = document.getElementById('materials-list');
        const spinner = document.getElementById('loading-spinner');
        const empty = document.getElementById('empty-state');

        spinner.classList.remove('d-none');
        empty.classList.add('d-none');
        list.innerHTML = '';

        const params = new URLSearchParams({ page: currentPage, size: pageSize });
        if (currentCaseId) params.set('case_id', currentCaseId);

        const typeFilter = document.getElementById('type-filter')?.value;
        if (typeFilter) params.set('file_type', typeFilter);

        const searchQ = document.getElementById('search-input')?.value?.trim();
        if (searchQ) params.set('q', searchQ);

        try {
            const data = await IMS.api('/materials/?' + params.toString());
            spinner.classList.add('d-none');

            document.getElementById('total-count').textContent = `${data.total} חומרים`;

            if (data.materials.length === 0) {
                empty.classList.remove('d-none');
                return;
            }

            data.materials.forEach(mat => {
                list.appendChild(createMaterialCard(mat));
            });

            renderPagination(data.total, data.page, data.size);
        } catch (err) {
            spinner.classList.add('d-none');
            if (err.message !== 'Session expired') {
                list.innerHTML = `<div class="col-12 text-center text-danger"><p>${IMS.esc(err.message)}</p></div>`;
            }
        }
    }

    function createMaterialCard(mat) {
        const col = document.createElement('div');
        col.className = 'col-md-6 col-lg-4';

        const summary = mat.content_summary || '';
        const summaryPreview = summary.length > 100 ? summary.substring(0, 100) + '...' : summary;

        const metaKeys = mat.metadata_json?.ai_analysis ? Object.keys(mat.metadata_json.ai_analysis).slice(0, 3) : [];
        const tagHtml = metaKeys.map(k => `<span class="badge tag-badge me-1">${IMS.esc(k)}</span>`).join('');
        const E = IMS.esc;

        col.innerHTML = `
            <div class="card mat-card h-100" role="button" tabindex="0" data-id="${mat.id}">
                <div class="card-body">
                    <div class="d-flex align-items-start gap-3">
                        <i class="${IMS.typeIcon(mat.file_type)} type-icon mt-1"></i>
                        <div class="flex-grow-1 min-width-0">
                            <h6 class="mb-1 text-truncate" title="${E(mat.filename)}">${E(mat.filename)}</h6>
                            <div class="d-flex gap-2 align-items-center mb-1">
                                ${IMS.statusBadge(mat.extraction_status)}
                                <small class="text-muted">${IMS.formatSize(mat.file_size)}</small>
                                ${mat.page_count ? `<small class="text-muted">${mat.page_count} עמ'</small>` : ''}
                            </div>
                            ${mat.case_name ? `<small class="text-muted d-block"><i class="fas fa-briefcase me-1"></i>${E(mat.case_name)}</small>` : ''}
                            ${summaryPreview ? `<small class="text-muted d-block mt-1">${E(summaryPreview)}</small>` : ''}
                            ${tagHtml ? `<div class="mt-1">${tagHtml}</div>` : ''}
                        </div>
                    </div>
                </div>
                <div class="card-footer bg-transparent border-top-0 pt-0">
                    <small class="text-muted">${IMS.formatDate(mat.upload_date)}</small>
                </div>
            </div>
        `;

        col.querySelector('.mat-card').addEventListener('click', () => showMaterialDetail(mat.id));
        return col;
    }

    function renderPagination(total, page, size) {
        const nav = document.getElementById('pagination-nav');
        const ul = document.getElementById('pagination');
        const totalPages = Math.ceil(total / size);
        if (totalPages <= 1) { nav.classList.add('d-none'); return; }

        nav.classList.remove('d-none');
        ul.innerHTML = '';

        for (let i = 1; i <= totalPages; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${i === page ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#">${i}</a>`;
            li.addEventListener('click', (e) => { e.preventDefault(); currentPage = i; loadMaterials(); });
            ul.appendChild(li);
        }
    }

    // ---- Filters ----
    function setupFilters() {
        document.getElementById('case-select')?.addEventListener('change', (e) => {
            currentCaseId = e.target.value || null;
            currentPage = 1;
            loadMaterials();
            // Show/hide upload zone based on auth
            toggleUploadZone();
        });

        document.getElementById('type-filter')?.addEventListener('change', () => { currentPage = 1; loadMaterials(); });

        document.getElementById('search-input')?.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => { currentPage = 1; loadMaterials(); }, 400);
        });
    }

    function toggleUploadZone() {
        const wrapper = document.getElementById('upload-zone-wrapper');
        if (IMS.token) wrapper?.classList.remove('d-none');
        else wrapper?.classList.add('d-none');
    }

    // ---- Upload ----
    function setupUpload() {
        toggleUploadZone();
        const zone = document.getElementById('upload-zone');
        const fileInput = document.getElementById('file-input');
        const folderInput = document.getElementById('folder-input');
        const uploadFilesBtn = document.getElementById('upload-files-btn');
        const uploadFolderBtn = document.getElementById('upload-folder-btn');
        if (!zone || !fileInput) return;

        // Click on zone opens file picker
        zone.addEventListener('click', (e) => {
            if (e.target.closest('button')) return; // don't trigger from buttons
            fileInput.click();
        });
        zone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });

        // Dedicated buttons
        if (uploadFilesBtn) uploadFilesBtn.addEventListener('click', () => fileInput.click());
        if (uploadFolderBtn && folderInput) uploadFolderBtn.addEventListener('click', () => folderInput.click());

        // Drag and drop — supports both files and folders
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

        // File input change
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) {
                const entries = Array.from(fileInput.files).map(f => ({ file: f, relativePath: '' }));
                uploadFiles(entries);
            }
            fileInput.value = '';
        });

        // Folder input change
        if (folderInput) {
            folderInput.addEventListener('change', () => {
                if (folderInput.files.length) {
                    const entries = Array.from(folderInput.files).map(f => {
                        // webkitRelativePath = "folderName/subFolder/file.txt"
                        const relPath = f.webkitRelativePath || '';
                        const parts = relPath.split('/');
                        // Remove the filename from the path to get folder path
                        const folderPath = parts.length > 1 ? parts.slice(0, -1).join('/') : '';
                        return { file: f, relativePath: folderPath };
                    });
                    uploadFiles(entries);
                }
                folderInput.value = '';
            });
        }
    }

    // Recursively traverse dropped directory entries
    function traverseEntry(entry, basePath, results) {
        return new Promise((resolve) => {
            if (entry.isFile) {
                entry.file((file) => {
                    results.push({ file, relativePath: basePath });
                    resolve();
                }, () => resolve());
            } else if (entry.isDirectory) {
                const reader = entry.createReader();
                const dirPath = basePath ? basePath + '/' + entry.name : entry.name;
                const readAll = (entries) => {
                    reader.readEntries((batch) => {
                        if (batch.length === 0) {
                            Promise.all(entries).then(resolve);
                        } else {
                            const newPromises = batch.map(e => traverseEntry(e, dirPath, results));
                            readAll([...entries, ...newPromises]);
                        }
                    }, () => resolve());
                };
                readAll([]);
            } else {
                resolve();
            }
        });
    }

    async function uploadFiles(fileEntries) {
        const progress = document.getElementById('upload-progress');
        const summary = document.getElementById('upload-summary');
        const caseId = currentCaseId;
        const total = fileEntries.length;
        let succeeded = 0, failed = 0;

        if (summary) {
            summary.classList.remove('d-none');
            summary.textContent = `מעלה 0/${total} קבצים...`;
        }

        // Upload up to 3 files concurrently
        const CONCURRENCY = 3;
        let index = 0;

        async function uploadNext() {
            while (index < fileEntries.length) {
                const i = index++;
                const { file, relativePath } = fileEntries[i];
                const id = 'up-' + Math.random().toString(36).substring(2, 8);
                const displayName = relativePath ? relativePath + '/' + file.name : file.name;

                progress.innerHTML += `
                    <div id="${id}" class="d-flex align-items-center gap-2 mb-1">
                        <i class="fas fa-spinner fa-spin text-light"></i>
                        <span class="text-light small">${IMS.esc(displayName)}</span>
                    </div>
                `;

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

        if (summary) {
            summary.textContent = `הסתיים: ${succeeded}/${total} קבצים הועלו בהצלחה` + (failed ? ` (${failed} נכשלו)` : '');
        }

        // Clear progress after 4 seconds and reload
        setTimeout(() => {
            progress.innerHTML = '';
            if (summary) { summary.classList.add('d-none'); summary.textContent = ''; }
            loadMaterials();
        }, 4000);
    }

    // ---- Material Detail Modal ----
    function setupMaterialModal() {
        document.getElementById('modal-reprocess-btn')?.addEventListener('click', async () => {
            const id = document.getElementById('materialModal').dataset.materialId;
            if (!id) return;
            try {
                await IMS.api(`/materials/${id}/reprocess`, { method: 'POST' });
                IMS.toast('החומר נשלח לעיבוד מחדש', 'success');
            } catch (err) {
                IMS.toast(err.message, 'error');
            }
        });

        document.getElementById('modal-delete-btn')?.addEventListener('click', async () => {
            const id = document.getElementById('materialModal').dataset.materialId;
            if (!id || !confirm('למחוק את החומר?')) return;
            try {
                await IMS.api(`/materials/${id}`, { method: 'DELETE' });
                bootstrap.Modal.getInstance(document.getElementById('materialModal')).hide();
                loadMaterials();
                IMS.toast('החומר נמחק', 'success');
            } catch (err) {
                IMS.toast(err.message, 'error');
            }
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

            // Build metadata display
            const E = IMS.esc;
            let metaHtml = '';
            const analysis = mat.metadata_json?.ai_analysis;
            if (analysis && typeof analysis === 'object') {
                metaHtml = '<h6 class="mt-3"><i class="fas fa-robot me-1"></i>ניתוח AI</h6><div class="table-responsive"><table class="table table-sm table-bordered">';
                for (const [key, val] of Object.entries(analysis)) {
                    const display = Array.isArray(val) ? val.join(', ') : (typeof val === 'object' ? JSON.stringify(val, null, 2) : val);
                    metaHtml += `<tr><td class="fw-bold" style="width:30%">${E(key)}</td><td>${E(display) || '-'}</td></tr>`;
                }
                metaHtml += '</table></div>';
            }

            // Custom metadata (non-AI)
            let customMetaHtml = '';
            const customKeys = Object.keys(mat.metadata_json || {}).filter(k => k !== 'ai_analysis');
            if (customKeys.length) {
                customMetaHtml = '<h6 class="mt-3"><i class="fas fa-database me-1"></i>מטא-דאטה</h6><div class="table-responsive"><table class="table table-sm table-bordered">';
                for (const key of customKeys) {
                    const val = mat.metadata_json[key];
                    const display = typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val);
                    customMetaHtml += `<tr><td class="fw-bold" style="width:30%">${E(key)}</td><td>${E(display)}</td></tr>`;
                }
                customMetaHtml += '</table></div>';
            }

            // Load linked entities and groups for this material
            let linkedEntitiesHtml = '';
            let groupsHtml = '';
            try {
                const entities = await IMS.api(`/entities/?size=200`);
                // Filter entities that link to this material — we'll show a simplified view
                // For a full implementation, add a /materials/{id}/entities endpoint
                const entLinks = entities.entities ? entities.entities.filter(e => e.material_link_count > 0).slice(0, 10) : [];
                if (entLinks.length) {
                    linkedEntitiesHtml = `<h6 class="mt-3"><i class="fas fa-project-diagram me-1"></i>ישויות קשורות</h6><div class="d-flex flex-wrap gap-1">`;
                    for (const e of entLinks) {
                        linkedEntitiesHtml += `<a href="/static/entities.html" class="badge text-decoration-none" style="background:${IMS.entityTypeColor(e.entity_type)}">${E(e.name)}</a>`;
                    }
                    linkedEntitiesHtml += `</div>`;
                }
            } catch {}

            body.innerHTML = `
                <div class="row mb-3">
                    <div class="col-md-6">
                        <p><strong>סוג:</strong> ${E(mat.file_type)}</p>
                        <p><strong>גודל:</strong> ${IMS.formatSize(mat.file_size)}</p>
                        <p><strong>תאריך העלאה:</strong> ${IMS.formatDate(mat.upload_date)}</p>
                        ${mat.page_count ? `<p><strong>עמודים:</strong> ${mat.page_count}</p>` : ''}
                        ${mat.case_name ? `<p><strong>תיק:</strong> ${E(mat.case_name)}</p>` : ''}
                    </div>
                    <div class="col-md-6">
                        <p><strong>סטטוס:</strong> ${IMS.statusBadge(mat.extraction_status)}</p>
                        <p><strong>Hash:</strong> <code class="small">${E((mat.file_hash || '').substring(0, 16))}...</code></p>
                        <p><strong>ציבורי:</strong> ${mat.is_public ? 'כן' : 'לא'}</p>
                    </div>
                </div>
                ${mat.content_summary ? `<h6><i class="fas fa-align-right me-1"></i>תקציר</h6><p>${E(mat.content_summary)}</p>` : ''}
                ${metaHtml}
                ${customMetaHtml}
                ${linkedEntitiesHtml}
                ${groupsHtml}
                ${mat.content_text ? `
                    <h6 class="mt-3"><i class="fas fa-file-alt me-1"></i>תוכן מופק</h6>
                    <div class="content-text-preview">${E(mat.content_text.substring(0, 5000))}${mat.content_text.length > 5000 ? '\n\n... (קוצר)' : ''}</div>
                ` : ''}
            `;

            new bootstrap.Modal(modal).show();
        } catch (err) {
            IMS.toast(err.message, 'error');
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
