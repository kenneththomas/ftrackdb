// Filter functionality for index page results table
document.addEventListener('DOMContentLoaded', function() {
    const filterInput = document.getElementById('filterInput');
    const eventFilter = document.getElementById('eventFilter');
    const teamFilter = document.getElementById('teamFilter');
    const table = document.querySelector('.index-results-table');
    const rows = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');
    const loadingIndicator = document.getElementById('loadingIndicator');
    
    let filterTimeout;

    function showLoading() {
        loadingIndicator.style.display = 'block';
        loadingIndicator.setAttribute('aria-hidden', 'false');
    }

    function hideLoading() {
        loadingIndicator.style.display = 'none';
        loadingIndicator.setAttribute('aria-hidden', 'true');
    }

    function filterTable() {
        showLoading();
        
        // Clear existing timeout
        if (filterTimeout) {
            clearTimeout(filterTimeout);
        }
        
        // Debounce the filtering
        filterTimeout = setTimeout(() => {
            const searchText = filterInput.value.toLowerCase();
            const selectedEvent = eventFilter.value.toLowerCase();
            const selectedTeam = teamFilter.value.toLowerCase();
            let visibleCount = 0;

            for (let row of rows) {
                const athlete = row.dataset.athlete ? row.dataset.athlete.toLowerCase() : '';
                const meet = row.dataset.meet ? row.dataset.meet.toLowerCase() : '';
                const event = row.dataset.event ? row.dataset.event.toLowerCase() : '';
                const team = row.dataset.team ? row.dataset.team.toLowerCase() : '';

                const matchesSearch = !searchText || 
                                   athlete.includes(searchText) || 
                                   meet.includes(searchText);
                const matchesEvent = !selectedEvent || event.includes(selectedEvent);
                const matchesTeam = !selectedTeam || team.includes(selectedTeam);

                const shouldShow = matchesSearch && matchesEvent && matchesTeam;
                row.style.display = shouldShow ? '' : 'none';
                
                if (shouldShow) visibleCount++;
            }
            
            // Update aria-live region for screen readers
            const statusMessage = `Showing ${visibleCount} of ${rows.length} results`;
            updateStatusMessage(statusMessage);
            
            hideLoading();
        }, 150); // 150ms debounce
    }

    function updateStatusMessage(message) {
        let statusRegion = document.getElementById('filterStatus');
        if (!statusRegion) {
            statusRegion = document.createElement('div');
            statusRegion.id = 'filterStatus';
            statusRegion.setAttribute('aria-live', 'polite');
            statusRegion.setAttribute('aria-atomic', 'true');
            statusRegion.className = 'sr-only';
            document.body.appendChild(statusRegion);
        }
        statusRegion.textContent = message;
    }

    // Add event listeners with proper error handling
    try {
        filterInput.addEventListener('input', filterTable);
        eventFilter.addEventListener('change', filterTable);
        teamFilter.addEventListener('change', filterTable);
        
        // Add keyboard navigation
        filterInput.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                filterInput.value = '';
                filterTable();
                filterInput.focus();
            }
        });
        
    } catch (error) {
        console.error('Error setting up filters:', error);
    }
});

