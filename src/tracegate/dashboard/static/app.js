// TraceGate Dashboard App

let currentSessionId = null;
let currentEvents = []; // Store raw events for filtering
let riskChartInstance = null;
let toolsChartInstance = null;

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    loadSessions();
    loadStats();
});

// Fetch and render the list of sessions
async function loadSessions() {
    const listEl = document.getElementById('session-list');
    
    try {
        const response = await fetch('/api/sessions');
        if (!response.ok) throw new Error('Failed to fetch sessions');
        
        const sessions = await response.json();
        
        if (sessions.length === 0) {
            listEl.innerHTML = '<li class="loading-state">No sessions found.</li>';
            return;
        }
        
        listEl.innerHTML = '';
        sessions.forEach(session => {
            const li = document.createElement('li');
            li.className = `session-item ${session.id === currentSessionId ? 'active' : ''}`;
            li.onclick = () => selectSession(session.id, session.first_timestamp, session.event_count);
            
            li.innerHTML = `
                <div class="session-id">${session.id}</div>
                <div class="session-meta-mini">
                    <span>${session.first_timestamp.split('T')[1] || session.first_timestamp}</span>
                    <span>${session.event_count} events</span>
                </div>
            `;
            listEl.appendChild(li);
        });
        
    } catch (err) {
        console.error(err);
        listEl.innerHTML = '<li class="loading-state text-danger">Error loading sessions.</li>';
    }
}

// Fetch and render global stats
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) throw new Error('Failed to fetch stats');
        
        const stats = await response.json();
        
        document.getElementById('stat-sessions').textContent = stats.total_sessions;
        document.getElementById('stat-events').textContent = stats.total_events;
        
        renderCharts(stats);
    } catch (err) {
        console.error(err);
    }
}

function renderCharts(stats) {
    Chart.defaults.color = '#94A3B8';
    Chart.defaults.font.family = "'Inter', sans-serif";
    
    // Risk Chart
    const riskCtx = document.getElementById('riskChart');
    if (riskCtx && stats.risk_distribution) {
        if (riskChartInstance) riskChartInstance.destroy();
        
        const labels = Object.keys(stats.risk_distribution);
        const data = Object.values(stats.risk_distribution);
        
        // Match CSS variables roughly
        const colors = {
            'critical': '#EF4444',
            'high': '#F59E0B',
            'medium': '#FCD34D',
            'low': '#10B981',
            'none': '#3B82F6'
        };
        const bgColors = labels.map(l => colors[l] || '#64748B');
        
        riskChartInstance = new Chart(riskCtx, {
            type: 'doughnut',
            data: {
                labels: labels.map(l => l.toUpperCase()),
                datasets: [{
                    data: data,
                    backgroundColor: bgColors,
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right' }
                }
            }
        });
    }
    
    // Tools Chart
    const toolsCtx = document.getElementById('toolsChart');
    if (toolsCtx && stats.tool_counts) {
        if (toolsChartInstance) toolsChartInstance.destroy();
        
        // Sort and take top 5
        const sortedTools = Object.entries(stats.tool_counts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5);
            
        toolsChartInstance = new Chart(toolsCtx, {
            type: 'bar',
            data: {
                labels: sortedTools.map(t => t[0]),
                datasets: [{
                    label: 'Calls',
                    data: sortedTools.map(t => t[1]),
                    backgroundColor: 'rgba(59, 130, 246, 0.7)',
                    borderColor: '#3B82F6',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                    x: { grid: { display: false } }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }
}

// Select a session and load its timeline
async function selectSession(sessionId, timestamp, count) {
    currentSessionId = sessionId;
    
    // Update UI
    document.getElementById('welcome-state').classList.add('hidden');
    document.getElementById('timeline-filters').classList.remove('hidden');
    const container = document.getElementById('timeline-container');
    container.classList.remove('hidden');
    container.innerHTML = '<div class="loading-state">Loading timeline...</div>';
    
    // Reset filters
    document.getElementById('filter-risk').value = 'all';
    document.getElementById('filter-action').value = 'all';
    document.getElementById('filter-tool').value = '';
    
    document.getElementById('current-session-title').textContent = sessionId;
    document.getElementById('current-session-meta').textContent = `Started: ${timestamp} • ${count} events`;
    
    // Update active state in sidebar
    document.querySelectorAll('.session-item').forEach(el => {
        el.classList.remove('active');
        if (el.querySelector('.session-id').textContent === sessionId) {
            el.classList.add('active');
        }
    });
    
    try {
        const response = await fetch(`/api/sessions/${sessionId}`);
        if (!response.ok) throw new Error('Failed to fetch session details');
        
        currentEvents = await response.json();
        renderTimeline(currentEvents);
    } catch (err) {
        console.error(err);
        container.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><h2>Failed to load session</h2><p>${err.message}</p></div>`;
    }
}

function applyFilters() {
    if (!currentEvents || currentEvents.length === 0) return;
    
    const riskFilter = document.getElementById('filter-risk').value;
    const actionFilter = document.getElementById('filter-action').value;
    const toolFilter = document.getElementById('filter-tool').value.toLowerCase();
    
    // Group events by tool call ID to filter the WHOLE call block
    const calls = {};
    const systemEvents = [];
    
    currentEvents.forEach(evt => {
        if (evt.event_type === 'session_start' || evt.event_type === 'session_end') {
            systemEvents.push(evt);
            return;
        }
        const id = evt.payload?.id;
        if (!id) return;
        if (!calls[id]) calls[id] = [];
        calls[id].push(evt);
    });
    
    // Rebuild a filtered list of events
    let filteredEvents = [...systemEvents];
    
    Object.values(calls).forEach(events => {
        const policyEvt = events.find(e => e.event_type === 'policy_decision');
        const callEvt = events.find(e => e.event_type === 'tool_call');
        
        const toolName = policyEvt?.payload?.name || callEvt?.payload?.name || '';
        const action = policyEvt?.payload?.action || '';
        const risk = policyEvt?.payload?.risk_level || 'none';
        
        let pass = true;
        if (riskFilter !== 'all' && risk !== riskFilter) pass = false;
        if (actionFilter !== 'all' && action !== actionFilter) pass = false;
        if (toolFilter && !toolName.toLowerCase().includes(toolFilter)) pass = false;
        
        if (pass) {
            filteredEvents = filteredEvents.concat(events);
        }
    });
    
    renderTimeline(filteredEvents);
}

// Render the timeline events
function renderTimeline(events) {
    const container = document.getElementById('timeline-container');
    container.innerHTML = '';
    
    if (events.length === 0) {
        container.innerHTML = '<div class="loading-state">Session is empty.</div>';
        return;
    }
    
    // Group events by tool call ID for better visualization
    const calls = {};
    const orderedCalls = [];
    
    events.forEach(evt => {
        if (evt.event_type === 'session_start' || evt.event_type === 'session_end') {
            orderedCalls.push({ type: 'system', data: evt });
            return;
        }
        
        const id = evt.payload?.id;
        if (!id) return;
        
        if (!calls[id]) {
            calls[id] = { id, events: [] };
            orderedCalls.push({ type: 'call', id: id });
        }
        calls[id].events.push(evt);
    });
    
    orderedCalls.forEach((item, index) => {
        const el = document.createElement('div');
        el.className = 'timeline-item';
        // Staggered animation delay
        el.style.animationDelay = `${Math.min(index * 0.05, 0.5)}s`;
        
        if (item.type === 'system') {
            el.innerHTML = renderSystemEvent(item.data);
        } else {
            el.innerHTML = renderToolCall(calls[item.id].events);
        }
        
        container.appendChild(el);
    });
}

function renderSystemEvent(evt) {
    const isStart = evt.event_type === 'session_start';
    const title = isStart ? 'Session Started' : 'Session Ended';
    const time = evt.timestamp ? evt.timestamp.split('T')[1].substring(0, 8) : '';
    
    let details = '';
    if (isStart) {
        details = `Server: ${evt.payload?.server_command || 'unknown'} | Policy: ${evt.payload?.policy_path || 'none'}`;
    } else {
        details = `Exit code: ${evt.payload?.exit_code || 0} | Total events: ${evt.payload?.total_events || 'unknown'}`;
    }
    
    return `
        <div class="timeline-dot dot-system"></div>
        <div class="timeline-content" style="border-style: dashed; padding: 0.75rem 1.25rem;">
            <div class="timeline-header" style="margin-bottom: 0;">
                <div class="timeline-title" style="color: var(--text-muted); font-size: 0.875rem;">
                    ${isStart ? '▶️' : '⏹️'} ${title}
                    <span style="font-weight: normal; margin-left: 0.5rem;">${details}</span>
                </div>
                <div class="timeline-time">${time}</div>
            </div>
        </div>
    `;
}

function renderToolCall(events) {
    // Find the relevant sub-events
    const callEvt = events.find(e => e.event_type === 'tool_call');
    const policyEvt = events.find(e => e.event_type === 'policy_decision');
    const resultEvt = events.find(e => e.event_type === 'tool_result');
    const durationEvt = events.find(e => e.event_type === 'request_duration');
    const approvalEvt = events.find(e => e.event_type === 'human_approval');
    
    // We need at least a policy decision or a tool call
    if (!callEvt && !policyEvt) return '';
    
    const time = (callEvt || policyEvt).timestamp.split('T')[1].substring(0, 8);
    const toolName = policyEvt?.payload?.name || callEvt?.payload?.name || 'unknown';
    const action = policyEvt?.payload?.action || 'unknown';
    const risk = policyEvt?.payload?.risk_level || 'none';
    const riskTags = policyEvt?.payload?.risk_tags || [];
    
    // Determine status and dot color
    let dotClass = 'dot-info';
    let statusBadge = '';
    
    if (action === 'deny') {
        dotClass = 'dot-danger';
        statusBadge = '<span class="badge badge-solid bg-danger">Denied</span>';
    } else if (action === 'ask') {
        if (approvalEvt) {
            const approved = approvalEvt.payload?.approved;
            if (approved) {
                dotClass = 'dot-warning';
                statusBadge = '<span class="badge badge-outline text-warning" style="border-color: currentColor">Approved by User</span>';
            } else {
                dotClass = 'dot-danger';
                statusBadge = '<span class="badge badge-solid bg-danger">Denied by User</span>';
            }
        } else {
            dotClass = 'dot-warning';
            statusBadge = '<span class="badge badge-outline text-warning">Pending Approval</span>';
        }
    } else if (action === 'allow') {
        dotClass = 'dot-success';
        statusBadge = '<span class="badge badge-outline text-success" style="border-color: currentColor">Allowed</span>';
    }
    
    if (resultEvt?.payload?.error) {
        dotClass = 'dot-danger';
        statusBadge += ' <span class="badge badge-solid bg-danger">Error</span>';
    }
    
    // Build Risk Badges
    let riskHtml = '';
    if (risk === 'critical' || risk === 'high') {
        riskHtml = `<span class="badge badge-solid bg-danger">Risk: ${risk.toUpperCase()}</span>`;
    } else if (risk === 'medium') {
        riskHtml = `<span class="badge badge-solid bg-warning">Risk: ${risk.toUpperCase()}</span>`;
    }
    
    // Check for rate limit block
    if (policyEvt?.payload?.message && policyEvt.payload.message.includes("rate limit exceeded")) {
        riskHtml += `<span class="badge badge-solid bg-warning" style="margin-left: 0.25rem;">Rate Limited</span>`;
    }
    
    riskTags.forEach(tag => {
        riskHtml += `<span class="badge badge-outline text-muted" style="margin-left: 0.25rem;">${tag}</span>`;
    });
    
    // Format JSON Arguments (Collapsible)
    let argsHtml = '';
    if (callEvt && callEvt.payload?.arguments) {
        argsHtml = `<div class="json-tree-container" style="margin-top: 0.75rem;">${buildJsonTree(callEvt.payload.arguments)}</div>`;
    }
    
    // Result Snippet (Collapsible)
    let resultHtml = '';
    if (resultEvt) {
        if (resultEvt.payload?.error) {
            resultHtml = `<div style="margin-top: 0.75rem; color: var(--status-danger); font-size: 0.8125rem;">Error: ${JSON.stringify(resultEvt.payload.error)}</div>`;
        } else if (resultEvt.payload?.result) {
            let resObj = resultEvt.payload.result;
            // Sometimes result is a stringified JSON
            if (typeof resObj === 'string') {
                try { resObj = JSON.parse(resObj); } catch(e) {}
            }
            if (typeof resObj === 'object' && resObj !== null) {
                resultHtml = `<div class="json-tree-container result-tree" style="margin-top: 0.75rem; opacity: 0.8;">
                    <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">Result:</div>
                    ${buildJsonTree(resObj)}
                </div>`;
            } else {
                const resStr = String(resObj);
                const truncated = resStr.length > 200 ? resStr.substring(0, 200) + '...' : resStr;
                resultHtml = `<div style="margin-top: 0.75rem; color: var(--text-muted); font-size: 0.8125rem; white-space: pre-wrap; font-family: var(--font-mono); background: rgba(0,0,0,0.2); padding: 0.5rem; border-radius: 4px;">↳ ${escapeHtml(truncated)}</div>`;
            }
        }
    }
    
    // Reason message
    const message = policyEvt?.payload?.message ? `<div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.5rem;">Rule: ${policyEvt.payload.rule_id || 'default'} &mdash; ${policyEvt.payload.message}</div>` : '';
    
    // Full raw data for modal
    const rawData = JSON.stringify(events, null, 2);
    
    return `
        <div class="timeline-dot ${dotClass}"></div>
        <div class="timeline-content">
            <div class="timeline-header">
                <div class="timeline-title">
                    <span class="tool-name">${toolName}</span>
                    ${statusBadge}
                    ${riskHtml}
                </div>
                <div class="timeline-time">${time}</div>
            </div>
            ${message}
            ${argsHtml}
            ${resultHtml}
            <div class="timeline-footer">
                <div class="duration">
                    ${durationEvt ? `⏱ ${durationEvt.payload.duration_ms}ms` : ''}
                </div>
                <button class="view-raw-btn" onclick='showRawJson(${JSON.stringify(rawData).replace(/'/g, "&#39;")})'>View Raw JSON</button>
            </div>
        </div>
    `;
}

// Helpers
function escapeHtml(unsafe) {
    return (unsafe || '').toString()
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
}

function syntaxHighlight(json) {
    json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
        let cls = 'code-number';
        if (/^"/.test(match)) {
            if (/:$/.test(match)) {
                cls = 'code-key';
            } else {
                cls = 'code-string';
            }
        } else if (/true|false/.test(match)) {
            cls = 'code-boolean';
        } else if (/null/.test(match)) {
            cls = 'code-null';
        }
        return '<span class="' + cls + '">' + match + '</span>';
    });
}

function buildJsonTree(obj, isLast = true) {
    if (obj === null) return `<span class="code-null">null</span>${isLast ? '' : ','}`;
    if (typeof obj === 'boolean') return `<span class="code-boolean">${obj}</span>${isLast ? '' : ','}`;
    if (typeof obj === 'number') return `<span class="code-number">${obj}</span>${isLast ? '' : ','}`;
    if (typeof obj === 'string') return `<span class="code-string">"${escapeHtml(obj)}"</span>${isLast ? '' : ','}`;
    
    if (Array.isArray(obj)) {
        if (obj.length === 0) return `[]${isLast ? '' : ','}`;
        let html = `<details open><summary><span class="tree-bracket">[</span></summary><div class="tree-content">`;
        obj.forEach((item, index) => {
            html += `<div class="tree-row">${buildJsonTree(item, index === obj.length - 1)}</div>`;
        });
        html += `</div><span class="tree-bracket">]</span>${isLast ? '' : ','}</details>`;
        return html;
    }
    
    if (typeof obj === 'object') {
        const keys = Object.keys(obj);
        if (keys.length === 0) return `{}${isLast ? '' : ','}`;
        
        let html = `<details open><summary><span class="tree-bracket">{</span></summary><div class="tree-content">`;
        keys.forEach((key, index) => {
            html += `<div class="tree-row"><span class="code-key">"${escapeHtml(key)}"</span>: ${buildJsonTree(obj[key], index === keys.length - 1)}</div>`;
        });
        html += `</div><span class="tree-bracket">}</span>${isLast ? '' : ','}</details>`;
        return html;
    }
    
    return String(obj);
}

function showRawJson(jsonStr) {
    document.getElementById('modal-json').innerHTML = syntaxHighlight(jsonStr);
    document.getElementById('json-modal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('json-modal').classList.add('hidden');
}
