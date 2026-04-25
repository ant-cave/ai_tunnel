const API_BASE = '/admin/api';

let state = {
    token: localStorage.getItem('admin_token') || null,
    currentPage: 'login',
    autoRefreshTimer: null,
    editingProvider: null,
};

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function formatDate(timestamp) {
    if (!timestamp) return '-';
    try {
        const d = new Date(timestamp);
        if (isNaN(d.getTime())) return timestamp;
        const pad = (n) => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    } catch {
        return timestamp;
    }
}

function formatUptime(seconds) {
    if (!seconds || seconds < 0) return '0秒';
    const total = Math.floor(seconds);
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const mins = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const parts = [];
    if (days > 0) parts.push(`${days}天`);
    if (hours > 0) parts.push(`${hours}小时`);
    if (mins > 0) parts.push(`${mins}分`);
    parts.push(`${secs}秒`);
    return parts.join('');
}

function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container');
    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle',
    };
    const el = document.createElement('div');
    el.className = `notification notification-${type}`;
    el.innerHTML = `
        <i class="fas ${icons[type] || icons.info}"></i>
        <span>${escapeHtml(message)}</span>
        <button class="notification-close">&times;</button>
    `;
    el.querySelector('.notification-close').addEventListener('click', () => el.remove());
    container.appendChild(el);
    setTimeout(() => {
        if (el.parentNode) {
            el.style.opacity = '0';
            el.style.transform = 'translateX(40px)';
            el.style.transition = 'all 0.3s ease';
            setTimeout(() => el.remove(), 300);
        }
    }, 4000);
}

async function apiRequest(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    const headers = { ...options.headers };
    if (state.token) {
        headers['Authorization'] = `Bearer ${state.token}`;
    }
    const fetchOptions = {
        ...options,
        headers,
    };
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
        fetchOptions.body = JSON.stringify(options.body);
    }
    try {
        const response = await fetch(url, fetchOptions);
        const data = await response.json();
        if (!response.ok) {
            const errMsg = data?.error?.message || `请求失败 (${response.status})`;
            const err = new Error(errMsg);
            err.status = response.status;
            err.data = data;
            throw err;
        }
        return data;
    } catch (err) {
        if (err.name === 'TypeError' && err.message.includes('fetch')) {
            throw new Error('无法连接到服务器，请检查网络连接');
        }
        throw err;
    }
}

function checkAuth() {
    if (!state.token) {
        navigateTo('login');
        return false;
    }
    return true;
}

async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    const loginBtn = document.getElementById('login-btn');
    if (!username || !password) {
        errorEl.classList.remove('hidden');
        errorEl.querySelector('span').textContent = '请输入用户名和密码';
        return;
    }
    errorEl.classList.add('hidden');
    loginBtn.disabled = true;
    loginBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 登录中...';
    try {
        const data = await apiRequest('/auth/login', {
            method: 'POST',
            body: { username, password },
        });
        state.token = data.token;
        localStorage.setItem('admin_token', data.token);
        showNotification(`欢迎回来，${escapeHtml(data.username)}`, 'success');
        navigateTo('dashboard');
        loadDashboard();
    } catch (err) {
        errorEl.classList.remove('hidden');
        errorEl.querySelector('span').textContent = err.message;
    } finally {
        loginBtn.disabled = false;
        loginBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i> 登录';
    }
}

function handleLogout() {
    state.token = null;
    localStorage.removeItem('admin_token');
    document.getElementById('navbar').classList.add('hidden');
    navigateTo('login');
    showNotification('已成功退出登录', 'info');
}

function navigateTo(page) {
    state.currentPage = page;
    document.querySelectorAll('.page').forEach((el) => el.classList.remove('active'));
    const pageEl = document.getElementById(`page-${page}`);
    if (pageEl) pageEl.classList.add('active');
    document.querySelectorAll('.nav-link').forEach((link) => {
        link.classList.toggle('active', link.dataset.page === page);
    });
    if (page === 'login') {
        document.getElementById('navbar').classList.add('hidden');
    } else {
        document.getElementById('navbar').classList.remove('hidden');
    }
}

async function loadDashboard() {
    if (!checkAuth()) return;
    try {
        const data = await apiRequest('/dashboard');
        document.getElementById('stat-uptime').textContent = formatUptime(data.uptime);
        document.getElementById('stat-requests').textContent = (data.request_count || 0).toLocaleString();
        document.getElementById('stat-errors').textContent = (data.error_count || 0).toLocaleString();
        document.getElementById('stat-providers').textContent = data.total_providers || 0;
        const tbody = document.getElementById('dashboard-provider-body');
        if (!data.providers || data.providers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:24px;">暂无提供者</td></tr>';
            return;
        }
        tbody.innerHTML = data.providers.map((p) => `
            <tr>
                <td><strong>${escapeHtml(p.name)}</strong></td>
                <td><span class="badge badge-info">${escapeHtml(p.type || p.provider_type)}</span></td>
                <td>${p.enabled
                    ? '<span class="badge badge-success"><i class="fas fa-check-circle"></i> 启用</span>'
                    : '<span class="badge badge-danger"><i class="fas fa-ban"></i> 禁用</span>'}</td>
                <td>${p.healthy !== undefined ? (p.healthy
                    ? '<span class="badge badge-success"><i class="fas fa-heart"></i> 健康</span>'
                    : '<span class="badge badge-danger"><i class="fas fa-heart-broken"></i> 异常</span>')
                    : '<span class="badge badge-warning">未知</span>'}</td>
                <td>${p.models_count || 0}</td>
            </tr>
        `).join('');
    } catch (err) {
        showNotification(`加载仪表盘失败：${err.message}`, 'error');
    }
}

async function loadProviders() {
    if (!checkAuth()) return;
    try {
        const data = await apiRequest('/providers');
        const tbody = document.getElementById('provider-body');
        if (!data.providers || data.providers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px;">暂无提供者，点击上方按钮添加</td></tr>';
            return;
        }
        tbody.innerHTML = data.providers.map((p) => `
            <tr>
                <td><strong>${escapeHtml(p.name)}</strong></td>
                <td><span class="badge badge-info">${escapeHtml(p.provider_type)}</span></td>
                <td>${p.enabled
                    ? '<span class="badge badge-success"><i class="fas fa-check-circle"></i> 启用</span>'
                    : '<span class="badge badge-danger"><i class="fas fa-ban"></i> 禁用</span>'}</td>
                <td>${p.is_healthy !== undefined ? (p.is_healthy
                    ? '<span class="badge badge-success"><i class="fas fa-heart"></i> 健康</span>'
                    : '<span class="badge badge-danger"><i class="fas fa-heart-broken"></i> 异常</span>')
                    : '<span class="badge badge-warning">未知</span>'}</td>
                <td>${(p.models && p.models.length) || 0}</td>
                <td>
                    <div class="actions-cell">
                        <button class="btn btn-sm btn-edit" onclick="showEditProviderModal('${escapeHtml(p.name)}')" title="编辑">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-delete" onclick="deleteProvider('${escapeHtml(p.name)}')" title="删除">
                            <i class="fas fa-trash"></i>
                        </button>
                        <button class="btn btn-sm btn-toggle" onclick="toggleProvider('${escapeHtml(p.name)}')" title="${p.enabled ? '禁用' : '启用'}">
                            <i class="fas ${p.enabled ? 'fa-pause' : 'fa-play'}"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (err) {
        showNotification(`加载提供者列表失败：${err.message}`, 'error');
    }
}

function showAddProviderModal() {
    state.editingProvider = null;
    document.getElementById('modal-title').innerHTML = '<i class="fas fa-plus-circle"></i> 添加提供者';
    document.getElementById('provider-form').reset();
    document.getElementById('provider-original-name').value = '';
    document.getElementById('provider-enabled').checked = true;
    document.getElementById('provider-name').disabled = false;
    document.getElementById('provider-modal').classList.remove('hidden');
}

async function showEditProviderModal(name) {
    try {
        const data = await apiRequest('/providers');
        const provider = data.providers.find((p) => p.name === name);
        if (!provider) {
            showNotification(`提供者 ${name} 不存在`, 'error');
            return;
        }
        state.editingProvider = provider;
        document.getElementById('modal-title').innerHTML = '<i class="fas fa-edit"></i> 编辑提供者';
        document.getElementById('provider-original-name').value = provider.name;
        document.getElementById('provider-name').value = provider.name;
        document.getElementById('provider-name').disabled = true;
        document.getElementById('provider-type').value = provider.provider_type;
        document.getElementById('provider-base-url').value = provider.base_url || '';
        document.getElementById('provider-api-key').value = '';
        document.getElementById('provider-api-key').placeholder = '留空则不修改';
        document.getElementById('provider-models').value = (provider.models || []).join(',');
        document.getElementById('provider-enabled').checked = provider.enabled;
        document.getElementById('provider-modal').classList.remove('hidden');
    } catch (err) {
        showNotification(`获取提供者信息失败：${err.message}`, 'error');
    }
}

async function saveProvider() {
    const name = document.getElementById('provider-name').value.trim();
    const providerType = document.getElementById('provider-type').value;
    const baseUrl = document.getElementById('provider-base-url').value.trim();
    const apiKey = document.getElementById('provider-api-key').value;
    const modelsStr = document.getElementById('provider-models').value.trim();
    const enabled = document.getElementById('provider-enabled').checked;
    const originalName = document.getElementById('provider-original-name').value;
    if (!name) {
        showNotification('请填写提供者名称', 'warning');
        return;
    }
    const models = modelsStr ? modelsStr.split(',').map((m) => m.trim()).filter(Boolean) : [];
    const body = {
        name,
        provider_type: providerType,
        base_url: baseUrl,
        models,
        enabled,
    };
    if (apiKey) body.api_key = apiKey;
    const isEdit = !!originalName;
    try {
        if (isEdit) {
            await apiRequest(`/providers/${encodeURIComponent(originalName)}`, {
                method: 'PUT',
                body,
            });
            showNotification(`提供者 ${name} 更新成功`, 'success');
        } else {
            await apiRequest('/providers', {
                method: 'POST',
                body,
            });
            showNotification(`提供者 ${name} 添加成功`, 'success');
        }
        closeModal();
        loadProviders();
    } catch (err) {
        showNotification(`${isEdit ? '更新' : '添加'}提供者失败：${err.message}`, 'error');
    }
}

async function deleteProvider(name) {
    if (!confirm(`确定要删除提供者 "${name}" 吗？此操作不可撤销。`)) return;
    try {
        await apiRequest(`/providers/${encodeURIComponent(name)}`, { method: 'DELETE' });
        showNotification(`提供者 ${name} 已删除`, 'success');
        loadProviders();
    } catch (err) {
        showNotification(`删除提供者失败：${err.message}`, 'error');
    }
}

async function toggleProvider(name) {
    try {
        const data = await apiRequest(`/providers/${encodeURIComponent(name)}/toggle`, { method: 'POST' });
        showNotification(data.message || `提供者 ${name} 状态已切换`, 'success');
        loadProviders();
    } catch (err) {
        showNotification(`切换提供者状态失败：${err.message}`, 'error');
    }
}

function closeModal() {
    document.getElementById('provider-modal').classList.add('hidden');
    state.editingProvider = null;
}

async function loadConfig() {
    if (!checkAuth()) return;
    try {
        const data = await apiRequest('/config');
        const config = data.config;
        if (config.server) {
            document.getElementById('config-host').value = config.server.host || '';
            document.getElementById('config-port').value = config.server.port || '';
            document.getElementById('config-workers').value = config.server.workers || '';
            document.getElementById('config-max-connections').value = config.server.max_connections || '';
            document.getElementById('config-keep-alive').value = config.server.keep_alive_timeout || '';
            document.getElementById('config-request-timeout').value = config.server.request_timeout || '';
        }
        if (config.security) {
            document.getElementById('config-rate-limit').value = config.security.rate_limit || '';
            document.getElementById('config-allowed-origins').value = (config.security.allowed_origins || []).join(',');
            document.getElementById('config-encryption-enabled').checked = config.security.encryption_enabled !== false;
        }
        if (config.logging) {
            document.getElementById('config-log-level').value = config.logging.level || 'INFO';
            document.getElementById('config-log-file').value = config.logging.file || '';
            document.getElementById('config-log-max-size').value = config.logging.max_size ? Math.round(config.logging.max_size / (1024 * 1024)) : '';
            document.getElementById('config-log-backup-count').value = config.logging.backup_count || '';
        }
    } catch (err) {
        showNotification(`加载配置失败：${err.message}`, 'error');
    }
}

async function saveConfig() {
    const config = {
        server: {
            host: document.getElementById('config-host').value.trim(),
            port: parseInt(document.getElementById('config-port').value) || 8080,
            workers: parseInt(document.getElementById('config-workers').value) || 4,
            max_connections: parseInt(document.getElementById('config-max-connections').value) || 1000,
            keep_alive_timeout: parseInt(document.getElementById('config-keep-alive').value) || 60,
            request_timeout: parseInt(document.getElementById('config-request-timeout').value) || 30,
        },
        security: {
            rate_limit: parseInt(document.getElementById('config-rate-limit').value) || 100,
            allowed_origins: document.getElementById('config-allowed-origins').value.split(',').map((s) => s.trim()).filter(Boolean),
            encryption_enabled: document.getElementById('config-encryption-enabled').checked,
        },
        logging: {
            level: document.getElementById('config-log-level').value,
            file: document.getElementById('config-log-file').value.trim() || null,
            max_size: (parseInt(document.getElementById('config-log-max-size').value) || 10) * 1024 * 1024,
            backup_count: parseInt(document.getElementById('config-log-backup-count').value) || 5,
        },
    };
    try {
        await apiRequest('/config', {
            method: 'PUT',
            body: config,
        });
        showNotification('配置已保存成功', 'success');
        loadConfig();
    } catch (err) {
        showNotification(`保存配置失败：${err.message}`, 'error');
    }
}

async function loadLogs() {
    if (!checkAuth()) return;
    const level = document.getElementById('log-level').value;
    const search = document.getElementById('log-search').value.trim();
    const params = new URLSearchParams({ limit: '200' });
    if (level) params.set('level', level);
    if (search) params.set('search', search);
    try {
        const data = await apiRequest(`/logs?${params.toString()}`);
        const tbody = document.getElementById('log-body');
        const emptyEl = document.getElementById('log-empty');
        if (!data.logs || data.logs.length === 0) {
            tbody.innerHTML = '';
            emptyEl.classList.remove('hidden');
            return;
        }
        emptyEl.classList.add('hidden');
        const levelColors = {
            DEBUG: 'badge-info',
            INFO: 'badge-success',
            WARNING: 'badge-warning',
            ERROR: 'badge-danger',
            CRITICAL: 'badge-danger',
        };
        tbody.innerHTML = data.logs.map((log) => {
            const levelBadge = levelColors[log.level] || 'badge-info';
            return `
                <tr>
                    <td>${escapeHtml(formatDate(log.timestamp))}</td>
                    <td><span class="badge ${levelBadge}">${escapeHtml(log.level)}</span></td>
                    <td>${escapeHtml(log.name)}</td>
                    <td>${escapeHtml(log.message)}</td>
                    <td style="font-size:11px;color:var(--text-muted)">${escapeHtml(log.filename || '')}${log.lineno ? `:${log.lineno}` : ''}</td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        showNotification(`加载日志失败：${err.message}`, 'error');
    }
}

async function loadStatus() {
    if (!checkAuth()) return;
    try {
        const data = await apiRequest('/status');
        document.getElementById('status-running').innerHTML = `<span class="badge badge-success"><i class="fas fa-circle"></i> 运行中</span>`;
        document.getElementById('status-version').textContent = data.version || '-';
        document.getElementById('status-host').textContent = data.settings?.host || '-';
        document.getElementById('status-port').textContent = data.settings?.port || '-';
        const sslEnabled = data.settings?.ssl_enabled;
        document.getElementById('status-ssl').innerHTML = sslEnabled
            ? `<span class="badge badge-success"><i class="fas fa-check"></i> 已启用</span>`
            : `<span class="badge badge-danger"><i class="fas fa-times"></i> 未启用</span>`;
        document.getElementById('status-log-level').textContent = data.settings?.log_level || '-';
        document.getElementById('status-rate-limit').textContent = data.settings?.rate_limit
            ? `${data.settings.rate_limit} 次/分钟`
            : '-';
        const router = data.router || {};
        document.getElementById('router-total-providers').textContent = router.total_providers ?? '-';
        document.getElementById('router-healthy-providers').textContent = router.healthy_providers ?? '-';
        document.getElementById('router-enabled-providers').textContent = router.enabled_providers ?? '-';
        document.getElementById('router-active-connections').textContent = router.active_connections ?? '-';
    } catch (err) {
        showNotification(`加载系统状态失败：${err.message}`, 'error');
    }
}

async function restartService() {
    if (!confirm('确定要重启服务吗？重启期间服务将暂时不可用。')) return;
    try {
        const data = await apiRequest('/restart', { method: 'POST' });
        showNotification(data.message || '重启请求已发送', 'success');
        setTimeout(() => loadStatus(), 2000);
    } catch (err) {
        showNotification(`重启失败：${err.message}`, 'error');
    }
}

function setupAutoRefresh() {
    const checkbox = document.getElementById('auto-refresh');
    checkbox.addEventListener('change', () => {
        if (state.autoRefreshTimer) {
            clearInterval(state.autoRefreshTimer);
            state.autoRefreshTimer = null;
        }
        if (checkbox.checked) {
            state.autoRefreshTimer = setInterval(() => {
                if (state.currentPage === 'logs') loadLogs();
            }, 5000);
            showNotification('已开启自动刷新（5秒间隔）', 'info');
        } else {
            showNotification('已关闭自动刷新', 'info');
        }
    });
}

function setupNavigation() {
    document.querySelectorAll('.nav-link').forEach((link) => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.dataset.page;
            navigateTo(page);
            switch (page) {
                case 'dashboard':
                    loadDashboard();
                    break;
                case 'providers':
                    loadProviders();
                    break;
                case 'config':
                    loadConfig();
                    break;
                case 'logs':
                    loadLogs();
                    break;
                case 'status':
                    loadStatus();
                    break;
            }
        });
    });
}

function setupAuth() {
    if (state.token) {
        document.getElementById('navbar').classList.remove('hidden');
        navigateTo('dashboard');
        loadDashboard();
    } else {
        navigateTo('login');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('login-form').addEventListener('submit', handleLogin);
    document.getElementById('logout-btn').addEventListener('click', handleLogout);
    document.getElementById('add-provider-btn').addEventListener('click', showAddProviderModal);
    document.getElementById('modal-save').addEventListener('click', saveProvider);
    document.getElementById('modal-cancel').addEventListener('click', closeModal);
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('modal-overlay').addEventListener('click', closeModal);
    document.getElementById('save-config-btn').addEventListener('click', saveConfig);
    document.getElementById('refresh-logs-btn').addEventListener('click', loadLogs);
    document.getElementById('restart-btn').addEventListener('click', restartService);
    document.getElementById('log-level').addEventListener('change', loadLogs);
    document.getElementById('log-search').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') loadLogs();
    });
    document.getElementById('provider-form').addEventListener('submit', (e) => {
        e.preventDefault();
        saveProvider();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });
    setupNavigation();
    setupAutoRefresh();
    setupAuth();
});
