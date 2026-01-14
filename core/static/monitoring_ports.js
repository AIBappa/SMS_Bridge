/**
 * SMS Bridge v2.3 - Monitoring Ports UI
 * Handles port management interface and real-time updates
 */

// Global state
let currentStates = [];
let refreshInterval = null;

// API endpoints
const API = {
    states: '/admin/monitoring/port-states',
    history: '/admin/monitoring/port-history',
    open: (service) => `/admin/monitoring/ports/${service}/open`,
    close: (service) => `/admin/monitoring/ports/${service}/close`,
};

/**
 * Initialize the page
 */
async function init() {
    await loadPortStates();
    await loadHistory();
    
    // Auto-refresh every 10 seconds
    refreshInterval = setInterval(async () => {
        await loadPortStates();
        await loadHistory();
    }, 10000);
}

/**
 * Load port states from API
 */
async function loadPortStates() {
    try {
        const response = await fetch(API.states);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        currentStates = data.states || [];
        
        renderPortCards();
        clearError();
    } catch (error) {
        console.error('Failed to load port states:', error);
        showError('Failed to load port states. Please refresh the page.');
    }
}

/**
 * Load port history from API
 */
async function loadHistory() {
    try {
        const response = await fetch(API.history + '?limit=20');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        const history = data.history || [];
        
        renderHistory(history);
    } catch (error) {
        console.error('Failed to load history:', error);
        const tbody = document.getElementById('history-body');
        tbody.innerHTML = '<tr><td colspan="5" class="error-message">Failed to load history</td></tr>';
    }
}

/**
 * Render port cards
 */
function renderPortCards() {
    const container = document.getElementById('ports-container');
    
    if (currentStates.length === 0) {
        container.innerHTML = '<div class="loading">No monitoring services configured</div>';
        return;
    }
    
    container.innerHTML = currentStates.map(state => createPortCard(state)).join('');
    
    // Attach event listeners
    attachPortCardListeners();
}

/**
 * Create HTML for a single port card
 */
function createPortCard(state) {
    const isOpen = state.is_open;
    const timeRemaining = state.time_remaining_seconds || 0;
    
    return `
        <div class="port-card" data-service="${state.service_name}">
            <div class="port-card-header">
                <div class="port-card-title">
                    <h3>${state.service_name}</h3>
                    <span class="port-number">Port ${state.port}</span>
                </div>
                <span class="status-badge ${isOpen ? 'open' : 'closed'}">
                    ${isOpen ? 'OPEN' : 'CLOSED'}
                </span>
            </div>
            
            <p class="port-description">${state.description || 'Monitoring service'}</p>
            
            ${isOpen ? renderOpenPortInfo(state, timeRemaining) : renderClosedPortInfo(state)}
        </div>
    `;
}

/**
 * Render info for an open port
 */
function renderOpenPortInfo(state, timeRemaining) {
    const openedAt = formatDateTime(state.opened_at);
    const scheduledClose = formatDateTime(state.scheduled_close_at);
    const timeStr = formatTimeRemaining(timeRemaining);
    
    return `
        <div class="port-info">
            <p><strong>Opened:</strong> ${openedAt}</p>
            <p><strong>By:</strong> ${state.opened_by || 'unknown'}</p>
            <p><strong>Auto-closes:</strong> ${scheduledClose}</p>
            <div class="countdown" data-close-time="${state.scheduled_close_at}">
                ${timeStr}
            </div>
        </div>
        <button class="btn btn-danger close-port" data-service="${state.service_name}">
            Close Port
        </button>
    `;
}

/**
 * Render info for a closed port
 */
function renderClosedPortInfo(state) {
    return `
        <div class="duration-selector">
            <label>Duration:</label>
            <select class="duration-select" data-service="${state.service_name}">
                <option value="3600">1 hour</option>
                <option value="7200">2 hours</option>
                <option value="14400">4 hours</option>
                <option value="28800">8 hours</option>
                <option value="86400">24 hours</option>
            </select>
        </div>
        <button class="btn btn-success open-port" data-service="${state.service_name}">
            Open Port
        </button>
    `;
}

/**
 * Attach event listeners to port card buttons
 */
function attachPortCardListeners() {
    // Open port buttons
    document.querySelectorAll('.open-port').forEach(btn => {
        btn.addEventListener('click', handleOpenPort);
    });
    
    // Close port buttons
    document.querySelectorAll('.close-port').forEach(btn => {
        btn.addEventListener('click', handleClosePort);
    });
    
    // Update countdowns
    updateCountdowns();
}

/**
 * Handle opening a port
 */
async function handleOpenPort(event) {
    const button = event.target;
    const service = button.dataset.service;
    const durationSelect = document.querySelector(`.duration-select[data-service="${service}"]`);
    const duration = parseInt(durationSelect.value, 10);
    
    button.disabled = true;
    button.textContent = 'Opening...';
    
    try {
        const response = await fetch(API.open(service), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ duration_seconds: duration })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        // Reload states immediately
        await loadPortStates();
        await loadHistory();
        
        showSuccess(`Port opened for ${service}`);
    } catch (error) {
        console.error('Failed to open port:', error);
        showError(`Failed to open port: ${error.message}`);
        button.disabled = false;
        button.textContent = 'Open Port';
    }
}

/**
 * Handle closing a port
 */
async function handleClosePort(event) {
    const button = event.target;
    const service = button.dataset.service;
    
    if (!confirm(`Close ${service} port?`)) return;
    
    button.disabled = true;
    button.textContent = 'Closing...';
    
    try {
        const response = await fetch(API.close(service), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        // Reload states immediately
        await loadPortStates();
        await loadHistory();
        
        showSuccess(`Port closed for ${service}`);
    } catch (error) {
        console.error('Failed to close port:', error);
        showError(`Failed to close port: ${error.message}`);
        button.disabled = false;
        button.textContent = 'Close Port';
    }
}

/**
 * Update countdown timers
 */
function updateCountdowns() {
    document.querySelectorAll('.countdown').forEach(el => {
        const closeTime = new Date(el.dataset.closeTime);
        const now = new Date();
        const diff = Math.floor((closeTime - now) / 1000);
        
        if (diff > 0) {
            el.textContent = `Closes in ${formatTimeRemaining(diff)}`;
        } else {
            el.textContent = 'Closing...';
        }
    });
    
    // Update every second
    setTimeout(updateCountdowns, 1000);
}

/**
 * Render history table
 */
function renderHistory(history) {
    const tbody = document.getElementById('history-body');
    
    if (history.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading">No history available</td></tr>';
        return;
    }
    
    tbody.innerHTML = history.map(entry => `
        <tr>
            <td>${formatDateTime(entry.timestamp)}</td>
            <td>${entry.service_name}</td>
            <td class="action-${entry.action}">${entry.action.toUpperCase()}</td>
            <td>${entry.action_by}</td>
            <td>${entry.reason || '-'}</td>
        </tr>
    `).join('');
}

/**
 * Format datetime for display
 */
function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Format time remaining in human-readable format
 */
function formatTimeRemaining(seconds) {
    if (seconds <= 0) return '0s';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    const parts = [];
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);
    
    return parts.join(' ');
}

/**
 * Show error message
 */
function showError(message) {
    const container = document.getElementById('error-container');
    container.innerHTML = `<div class="error-message">${message}</div>`;
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        container.innerHTML = '';
    }, 5000);
}

/**
 * Show success message
 */
function showSuccess(message) {
    const container = document.getElementById('error-container');
    container.innerHTML = `<div class="success-message">${message}</div>`;
    
    // Auto-hide after 3 seconds
    setTimeout(() => {
        container.innerHTML = '';
    }, 3000);
}

/**
 * Clear error messages
 */
function clearError() {
    const container = document.getElementById('error-container');
    container.innerHTML = '';
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
});
