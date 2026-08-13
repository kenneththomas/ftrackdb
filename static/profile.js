(function () {
    'use strict';

    const page = document.getElementById('athlete-profile');
    if (!page) return;

    const data = window.athleteProfileData || {};
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const tabs = Array.from(document.querySelectorAll('[data-profile-tab]'));
    const panels = Array.from(document.querySelectorAll('[data-profile-panel]'));

    function openPanel(name, updateHash) {
        const target = panels.find(panel => panel.dataset.profilePanel === name);
        if (!target) return;
        tabs.forEach(tab => {
            const active = tab.dataset.profileTab === name;
            tab.classList.toggle('is-active', active);
            tab.setAttribute('aria-selected', active ? 'true' : 'false');
            tab.tabIndex = active ? 0 : -1;
        });
        panels.forEach(panel => panel.classList.toggle('hidden', panel !== target));
        if (updateHash) history.replaceState(null, '', '#' + name);
    }

    tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => openPanel(tab.dataset.profileTab, true));
        tab.addEventListener('keydown', event => {
            if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
            event.preventDefault();
            const direction = event.key === 'ArrowRight' ? 1 : -1;
            const next = tabs[(index + direction + tabs.length) % tabs.length];
            next.focus();
            openPanel(next.dataset.profileTab, true);
        });
    });
    document.querySelectorAll('[data-open-panel]').forEach(button => button.addEventListener('click', () => {
        openPanel(button.dataset.openPanel, true);
        document.querySelector('.profile-tabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }));
    const initialPanel = location.hash.replace('#', '');
    openPanel(panels.some(panel => panel.dataset.profilePanel === initialPanel) ? initialPanel : 'overview', false);

    const manageToggle = document.getElementById('manage-menu-toggle');
    const manageMenu = document.getElementById('manage-menu');
    function closeManageMenu() {
        manageMenu?.classList.add('hidden');
        manageToggle?.setAttribute('aria-expanded', 'false');
    }
    manageToggle?.addEventListener('click', event => {
        event.stopPropagation();
        const opening = manageMenu.classList.contains('hidden');
        manageMenu.classList.toggle('hidden', !opening);
        manageToggle.setAttribute('aria-expanded', opening ? 'true' : 'false');
    });
    document.addEventListener('click', event => {
        if (!event.target.closest('.profile-manage')) closeManageMenu();
    });

    const overlay = document.getElementById('quickInsertSection');
    const showInsert = document.getElementById('showQuickInsert');
    function setInsertOpen(open) {
        overlay?.classList.toggle('hidden', !open);
        overlay?.setAttribute('aria-hidden', open ? 'false' : 'true');
        if (open) overlay?.querySelector('input:not([type="hidden"])')?.focus();
    }
    showInsert?.addEventListener('click', () => setInsertOpen(true));
    overlay?.querySelector('.quick-insert-close')?.addEventListener('click', () => setInsertOpen(false));
    overlay?.addEventListener('click', event => { if (event.target === overlay) setInsertOpen(false); });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') { setInsertOpen(false); closeManageMenu(); } });

    const insertForm = document.getElementById('quick-insert-form');
    const dateInput = insertForm?.querySelector('input[name="date[]"]');
    if (dateInput) dateInput.valueAsDate = new Date();
    insertForm?.addEventListener('submit', event => {
        event.preventDefault();
        fetch('/insert', { method: 'POST', headers: { 'X-CSRFToken': csrf }, body: new FormData(insertForm) })
            .then(response => { if (!response.ok) throw new Error('Insert failed'); return response.text(); })
            .then(() => location.reload())
            .catch(() => alert('The result could not be added.'));
    });

    const bioDisplay = document.getElementById('bio-display');
    const bioEdit = document.getElementById('bio-edit');
    function setBioEditing(editing) {
        bioDisplay?.classList.toggle('hidden', editing);
        bioEdit?.classList.toggle('hidden', !editing);
        if (editing) document.getElementById('bio-textarea')?.focus();
    }
    document.getElementById('edit-bio-action')?.addEventListener('click', () => {
        closeManageMenu();
        openPanel('overview', true);
        setBioEditing(true);
        document.querySelector('.profile-about')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    document.getElementById('cancel-bio')?.addEventListener('click', () => setBioEditing(false));
    document.getElementById('save-bio')?.addEventListener('click', () => {
        const bio = document.getElementById('bio-textarea')?.value || '';
        fetch('/update_bio/' + encodeURIComponent(data.name), {
            method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': csrf },
            body: 'bio=' + encodeURIComponent(bio)
        }).then(response => response.json()).then(result => {
            if (!result.success) throw new Error('Save failed');
            location.reload();
        }).catch(() => alert('The bio could not be saved.'));
    });

    const performanceTable = document.querySelector('.performance-table');
    const editResultsAction = document.getElementById('edit-results-action');
    editResultsAction?.addEventListener('click', () => {
        closeManageMenu();
        openPanel('performances', true);
        const enabled = !performanceTable.classList.contains('manage-mode');
        if (!enabled) performanceTable.querySelectorAll('.cancel-btn:not(.hidden)').forEach(button => button.click());
        performanceTable.classList.toggle('manage-mode', enabled);
        editResultsAction.textContent = enabled ? 'Finish editing performances' : 'Edit performances';
    });

    const filterInput = document.getElementById('filterInput');
    const seasonFilter = document.getElementById('seasonQuickFilter');
    const eventFilter = document.getElementById('eventQuickFilter');
    const teamFilter = document.getElementById('teamQuickFilter');
    const quickFilters = Array.from(document.querySelectorAll('.quick-filter-btn[data-filter]'));
    const resultRows = Array.from(performanceTable?.querySelectorAll('.result-row') || []);
    const yearRows = Array.from(performanceTable?.querySelectorAll('.year-divider-row') || []);

    function addOptions(select, values) {
        [...new Set(values.filter(Boolean))].sort((a, b) => b.localeCompare(a, undefined, { numeric: true })).forEach(value => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = value;
            select?.appendChild(option);
        });
    }
    addOptions(seasonFilter, resultRows.map(row => row.dataset.year));
    addOptions(eventFilter, resultRows.map(row => row.dataset.event));
    addOptions(teamFilter, resultRows.map(row => row.dataset.team));

    function applyFilters() {
        const text = (filterInput?.value || '').trim().toLowerCase();
        const pressed = Object.fromEntries(quickFilters.map(button => [button.dataset.filter, button.getAttribute('aria-pressed') === 'true']));
        const visibleYears = new Set();
        let visibleCount = 0;
        resultRows.forEach(row => {
            const place = parseInt(row.dataset.place, 10);
            const visible = (!text || row.textContent.toLowerCase().includes(text)) &&
                (!seasonFilter?.value || row.dataset.year === seasonFilter.value) &&
                (!eventFilter?.value || row.dataset.event === eventFilter.value) &&
                (!teamFilter?.value || row.dataset.team === teamFilter.value) &&
                (!pressed.pr || row.dataset.isPr === 'true') &&
                (!pressed.top8 || (!Number.isNaN(place) && place <= 8)) &&
                (!pressed.stagger || row.dataset.hasStagger === 'true');
            row.style.display = visible ? '' : 'none';
            if (visible) { visibleCount += 1; visibleYears.add(row.dataset.year); }
        });
        yearRows.forEach(row => { row.style.display = visibleYears.has(row.dataset.yearDivider) ? '' : 'none'; });
        document.getElementById('performance-empty')?.classList.toggle('hidden', visibleCount !== 0);
    }
    [filterInput, seasonFilter, eventFilter, teamFilter].forEach(control => control?.addEventListener(control === filterInput ? 'input' : 'change', applyFilters));
    quickFilters.forEach(button => button.addEventListener('click', () => {
        button.setAttribute('aria-pressed', button.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
        applyFilters();
    }));
    document.getElementById('clearResultFilters')?.addEventListener('click', () => {
        if (filterInput) filterInput.value = '';
        [seasonFilter, eventFilter, teamFilter].forEach(select => { if (select) select.value = ''; });
        quickFilters.forEach(button => button.setAttribute('aria-pressed', 'false'));
        applyFilters();
    });

    function editableValue(cell) {
        if (cell.dataset.field === 'result') return cell.querySelector('.result-content')?.textContent.trim() || '';
        return cell.textContent.trim();
    }
    document.querySelectorAll('.edit-btn').forEach(button => button.addEventListener('click', () => {
        const row = button.closest('.result-row');
        row.querySelector('.edit-btn').classList.add('hidden');
        row.querySelector('.delete-btn').classList.add('hidden');
        row.querySelector('.save-btn').classList.remove('hidden');
        row.querySelector('.cancel-btn').classList.remove('hidden');
        row.querySelectorAll('.editable').forEach(cell => {
            cell.dataset.originalHtml = cell.innerHTML;
            const input = document.createElement('input');
            input.type = cell.dataset.field === 'date' ? 'date' : 'text';
            input.value = editableValue(cell);
            if (cell.dataset.field === 'result') {
                const resultContent = cell.querySelector('.result-content');
                resultContent.replaceChildren(input);
            } else cell.replaceChildren(input);
            cell.classList.add('editing');
        });
    }));
    document.querySelectorAll('.cancel-btn').forEach(button => button.addEventListener('click', () => {
        const row = button.closest('.result-row');
        row.querySelectorAll('.editable').forEach(cell => { cell.innerHTML = cell.dataset.originalHtml; cell.classList.remove('editing'); });
        row.querySelector('.edit-btn').classList.remove('hidden');
        row.querySelector('.delete-btn').classList.remove('hidden');
        row.querySelector('.save-btn').classList.add('hidden');
        row.querySelector('.cancel-btn').classList.add('hidden');
    }));
    document.querySelectorAll('.save-btn').forEach(button => button.addEventListener('click', () => {
        const row = button.closest('.result-row');
        const updates = {};
        row.querySelectorAll('.editable').forEach(cell => { const input = cell.querySelector('input'); if (input) updates[cell.dataset.field] = input.value; });
        fetch('/update_result/' + row.dataset.resultId, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(updates)
        }).then(response => response.json()).then(result => { if (!result.success) throw new Error('Save failed'); location.reload(); }).catch(() => alert('The result could not be updated.'));
    }));
    document.querySelectorAll('.delete-btn').forEach(button => button.addEventListener('click', () => {
        if (!confirm('Delete this result? This cannot be undone.')) return;
        fetch('/delete_result/' + button.dataset.resultId, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf } })
            .then(response => response.json()).then(result => { if (!result.success) throw new Error('Delete failed'); location.reload(); }).catch(() => alert('The result could not be deleted.'));
    }));

    document.getElementById('toggle-gender')?.addEventListener('click', event => {
        const display = document.getElementById('athlete-gender-display');
        const isFemale = display.textContent.trim() === 'Female';
        fetch('/update_gender/' + encodeURIComponent(data.name), {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ is_female: !isFemale })
        }).then(response => response.json()).then(result => {
            if (!result.success) throw new Error('Update failed');
            display.textContent = isFemale ? 'Male' : 'Female';
            event.currentTarget.textContent = isFemale ? 'Mark as Female' : 'Mark as Male';
            document.querySelector('.profile-hero h1')?.classList.toggle('female-text', !isFemale);
            closeManageMenu();
        }).catch(() => alert('Gender could not be updated.'));
    });
    document.getElementById('calculate-rankings')?.addEventListener('click', event => {
        const button = event.currentTarget;
        button.disabled = true;
        button.textContent = 'Recalculating…';
        fetch('/athlete/' + encodeURIComponent(data.name) + '/calculate_rankings', { method: 'POST', headers: { 'X-CSRFToken': csrf } })
            .then(response => response.json()).then(result => { if (!result.success) throw new Error('Ranking failed'); location.reload(); })
            .catch(() => { button.disabled = false; button.textContent = 'Recalculate rankings'; alert('Rankings could not be recalculated.'); });
    });

    const bestSinceContainer = document.getElementById('best-since-results');
    function renderBestSince(items) {
        bestSinceContainer.replaceChildren();
        const sorted = items.slice().sort((a, b) => (data.rankings[a.event] || Infinity) - (data.rankings[b.event] || Infinity) || a.event.localeCompare(b.event));
        sorted.forEach(item => {
            const card = document.createElement('article');
            card.className = 'event-card' + (data.rankings[item.event] ? ' is-ranked' : '');
            const top = document.createElement('div'); top.className = 'event-card-top';
            const eventName = document.createElement('span'); eventName.className = 'event-name'; eventName.textContent = item.event;
            const rank = document.createElement('span'); rank.className = 'event-rank' + (data.rankings[item.event] ? '' : ' is-unranked'); rank.textContent = data.rankings[item.event] ? '#' + data.rankings[item.event] : 'Unranked';
            top.append(eventName, rank);
            const mark = document.createElement('p'); mark.className = 'event-mark'; mark.textContent = item.result;
            const context = document.createElement('p'); context.className = 'event-context';
            const date = document.createElement('span'); date.textContent = item.date || ''; context.appendChild(date);
            card.append(top, mark, context); bestSinceContainer.appendChild(card);
        });
        bestSinceContainer.classList.toggle('hidden', sorted.length === 0);
    }
    document.getElementById('apply-best-since')?.addEventListener('click', () => {
        const since = document.getElementById('best-since-date')?.value;
        if (!since) return;
        fetch('/get_athlete_bests_since/' + encodeURIComponent(data.name) + '?since=' + encodeURIComponent(since))
            .then(response => response.json()).then(result => renderBestSince(result.success ? result.bests || [] : [])).catch(() => renderBestSince([]));
    });
    document.getElementById('clear-best-since')?.addEventListener('click', () => {
        const input = document.getElementById('best-since-date'); if (input) input.value = '';
        bestSinceContainer?.replaceChildren(); bestSinceContainer?.classList.add('hidden');
    });
})();
