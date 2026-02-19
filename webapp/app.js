/**
 * NightLab WebApp - Modern JavaScript
 * Telegram Mini App с крутыми анимациями
 */

// ===== Configuration =====
const CONFIG = {
    API_URL: 'https://api.nightlab.example.com',
    // API_URL: 'http://localhost:8000',
};

// ===== Global Variables =====
let tg = null;
let currentUser = null;
let initData = '';
let appsOffset = 0;
let currentFilter = 'all';
let selectedCountry = null;
let selectedBank = null;

// ===== Initialization =====
document.addEventListener('DOMContentLoaded', () => {
    initTelegramWebApp();
    setupNavigation();
    setupFilters();
    setupHapticFeedback();
    loadInitialData();
});

function initTelegramWebApp() {
    if (window.Telegram?.WebApp) {
        tg = window.Telegram.WebApp;
        tg.expand();
        tg.ready();

        // Set colors
        tg.setHeaderColor('#0a0a0f');
        tg.setBackgroundColor('#0a0a0f');

        // Get user data
        initData = tg.initData;
        currentUser = tg.initDataUnsafe?.user;

        console.log('Telegram WebApp initialized:', currentUser);
    } else {
        console.warn('Telegram WebApp not available');
        initData = 'test_mode';
        currentUser = { id: 123456, username: 'test_user' };
    }
}

function setupHapticFeedback() {
    const interactiveElements = document.querySelectorAll('button, .nav-item, .action-card, .app-card, .option-card, .filter-btn');

    interactiveElements.forEach(el => {
        el.addEventListener('click', () => {
            if (tg?.HapticFeedback) {
                tg.HapticFeedback.impactOccurred('light');
            }
        });
    });
}

// ===== Navigation =====
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const page = item.dataset.page;
            navigateTo(page);
        });
    });
}

function navigateTo(page) {
    // Update active nav item
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
    });

    // Show target page with animation
    const currentPage = document.querySelector('.page.active');
    const targetPage = document.getElementById(`page-${page}`);

    if (currentPage && targetPage && currentPage !== targetPage) {
        currentPage.classList.remove('active');
        targetPage.classList.add('active');
    }

    // Load page data
    switch(page) {
        case 'home':
            loadStats();
            break;
        case 'apps':
            appsOffset = 0;
            loadApplications();
            break;
        case 'create':
            resetForm();
            loadCountries();
            break;
        case 'notifications':
            loadNotifications();
            break;
        case 'profile':
            loadProfile();
            break;
    }

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('medium');
    }
}

// ===== Filters =====
function setupFilters() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            appsOffset = 0;
            loadApplications();

            if (tg?.HapticFeedback) {
                tg.HapticFeedback.selectionChanged();
            }
        });
    });
}

// ===== Data Loading =====
async function loadInitialData() {
    await Promise.all([
        loadStats(),
        loadUnreadCount()
    ]);
}

async function loadStats() {
    try {
        const stats = await apiGet('/api/stats');

        animateCounter('stat-total-apps', stats.total_applications);
        animateCurrency('stat-turnover', stats.turnover);
        animateCounter('stat-users', stats.total_users);
        animateCounter('stat-today', stats.today_applications);
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

async function loadProfile() {
    try {
        const [profile, userStats] = await Promise.all([
            apiGet('/api/user/profile'),
            apiGet('/api/user/stats')
        ]);

        // Profile
        document.getElementById('profile-username').textContent = `@${profile.username}`;
        document.getElementById('profile-role').textContent = profile.role;
        document.getElementById('profile-balance').textContent = formatCurrency(profile.balance_uah);
        document.getElementById('profile-avatar-text').textContent = profile.username.charAt(0).toUpperCase();

        // Stats
        document.getElementById('user-stat-apps').textContent = userStats.total_applications;
        document.getElementById('user-stat-confirmed').textContent = userStats.confirmed_applications;
        document.getElementById('user-stat-spent').textContent = formatCurrency(userStats.total_spent);

        // Referral
        document.getElementById('referral-count').textContent =
            `${profile.referral_count} приглашённых`;
        document.getElementById('referral-link').value = profile.referral_link;

    } catch (error) {
        console.error('Failed to load profile:', error);
        showToast('Ошибка загрузки профиля', 'error');
    }
}

async function loadApplications() {
    const container = document.getElementById('applications-list');

    try {
        const params = new URLSearchParams({
            limit: '20',
            offset: appsOffset.toString()
        });

        if (currentFilter !== 'all') {
            params.append('status', currentFilter);
        }

        const apps = await apiGet(`/api/applications?${params}`);

        if (appsOffset === 0) {
            container.innerHTML = '';
        }

        if (apps.length === 0 && appsOffset === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📄</div>
                    <p>У вас пока нет заявок</p>
                </div>
            `;
            document.getElementById('load-more').style.display = 'none';
            return;
        }

        apps.forEach((app, index) => {
            const card = createAppCard(app);
            card.style.animationDelay = `${index * 0.05}s`;
            card.classList.add('animated');
            container.appendChild(card);
        });

        document.getElementById('load-more').style.display =
            apps.length === 20 ? 'block' : 'none';

    } catch (error) {
        console.error('Failed to load applications:', error);
        container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
    }
}

function createAppCard(app) {
    const card = document.createElement('div');
    card.className = 'app-card';
    card.onclick = () => showAppDetails(app.id);

    card.innerHTML = `
        <div class="app-header">
            <span class="app-id">#${app.id}</span>
            <span class="app-status status-${app.status}">${app.status_label}</span>
        </div>
        <div class="app-details">
            <div class="app-detail">
                <span class="app-detail-label">Банк</span>
                <span class="app-detail-value">${app.bank_name}</span>
            </div>
            <div class="app-detail">
                <span class="app-detail-label">Сумма</span>
                <span class="app-detail-value">${formatCurrency(app.amount_uah)}</span>
            </div>
            <div class="app-detail">
                <span class="app-detail-label">Код</span>
                <span class="app-detail-value">${app.payment_code}</span>
            </div>
            <div class="app-detail">
                <span class="app-detail-label">Дата</span>
                <span class="app-detail-value">${formatDate(app.created_at)}</span>
            </div>
        </div>
    `;

    return card;
}

function loadMoreApps() {
    appsOffset += 20;
    loadApplications();
}

async function showAppDetails(appId) {
    try {
        const app = await apiGet(`/api/application/${appId}`);

        document.getElementById('modal-title').textContent = `Заявка #${app.id}`;

        const statusClass = `status-${app.status}`;

        document.getElementById('modal-body').innerHTML = `
            <div class="app-detail-row">
                <span class="detail-label">Статус</span>
                <span class="app-status ${statusClass}">${app.status_label}</span>
            </div>
            <div class="app-detail-row">
                <span class="detail-label">Банк</span>
                <span class="detail-value">${app.bank_name}</span>
            </div>
            <div class="app-detail-row">
                <span class="detail-label">Сумма</span>
                <span class="detail-value">${formatCurrency(app.amount_uah)}</span>
            </div>
            <div class="app-detail-row">
                <span class="detail-label">Код платежа</span>
                <span class="detail-value"><code>${app.payment_code}</code></span>
            </div>
            <div class="app-detail-row">
                <span class="detail-label">Создана</span>
                <span class="detail-value">${formatDateTime(app.created_at)}</span>
            </div>
            ${app.requisites ? `
                <div class="app-detail-row" style="flex-direction: column; align-items: flex-start;">
                    <span class="detail-label">Реквизиты</span>
                    <div class="requisites-box">${app.requisites}</div>
                </div>
            ` : ''}
            ${app.expires_at ? `
                <div class="app-detail-row">
                    <span class="detail-label">Истекает</span>
                    <span class="detail-value">${formatDateTime(app.expires_at)}</span>
                </div>
            ` : ''}
        `;

        document.getElementById('app-modal').classList.add('active');

        if (tg?.HapticFeedback) {
            tg.HapticFeedback.impactOccurred('medium');
        }

    } catch (error) {
        console.error('Failed to load app details:', error);
        showToast('Ошибка загрузки деталей', 'error');
    }
}

function closeModal() {
    document.getElementById('app-modal').classList.remove('active');
}

async function loadNotifications() {
    const container = document.getElementById('notifications-list');

    try {
        const notifications = await apiGet('/api/notifications?limit=50');

        if (notifications.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🔔</div>
                    <p>Нет уведомлений</p>
                </div>
            `;
            return;
        }

        container.innerHTML = notifications.map((n, index) => `
            <div class="notification-card ${n.is_read ? '' : 'unread'}"
                 onclick="markNotificationRead(${n.id})"
                 style="animation-delay: ${index * 0.05}s">
                <div class="notification-icon">${getNotificationIcon(n.type)}</div>
                <div class="notification-content">
                    <div class="notification-title">${n.title}</div>
                    <div class="notification-message">${n.message}</div>
                    <div class="notification-time">${formatDateTime(n.created_at)}</div>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Failed to load notifications:', error);
        container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
    }
}

async function markNotificationRead(id) {
    try {
        await apiPost(`/api/notifications/${id}/read`, {});
        loadNotifications();
        loadUnreadCount();
    } catch (error) {
        console.error('Failed to mark notification as read:', error);
    }
}

async function loadUnreadCount() {
    try {
        const { count } = await apiGet('/api/notifications/unread-count');
        const badge = document.getElementById('notif-badge');
        badge.textContent = count;
        badge.style.display = count > 0 ? 'flex' : 'none';
    } catch (error) {
        console.error('Failed to load unread count:', error);
    }
}

// ===== Create Application =====
async function loadCountries() {
    const container = document.getElementById('countries-list');
    container.innerHTML = '<div class="loading-spinner">Загрузка...</div>';

    try {
        const countries = await apiGet('/api/countries');

        container.innerHTML = countries.map((c, index) => `
            <div class="option-card" onclick="selectCountry(${c.id}, '${c.name}')" style="animation-delay: ${index * 0.05}s">
                <div class="option-icon">🌍</div>
                <span class="option-text">${c.name}</span>
            </div>
        `).join('');

    } catch (error) {
        console.error('Failed to load countries:', error);
        container.innerHTML = '<div class="loading-spinner">Ошибка загрузки</div>';
    }
}

async function selectCountry(id, name) {
    selectedCountry = { id, name };

    // Update UI
    document.querySelectorAll('#countries-list .option-card').forEach(card => {
        card.classList.remove('selected');
    });
    event.currentTarget.classList.add('selected');

    // Load banks
    await loadBanks(id);

    // Go to next step with delay for animation
    setTimeout(() => goToStep(2), 300);

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.selectionChanged();
    }
}

async function loadBanks(countryId) {
    const container = document.getElementById('banks-list');
    container.innerHTML = '<div class="loading-spinner">Загрузка банков...</div>';

    try {
        const banks = await apiGet(`/api/banks?country_id=${countryId}`);

        container.innerHTML = banks.map((b, index) => `
            <div class="option-card" onclick="selectBank(${b.id}, '${b.name}')" style="animation-delay: ${index * 0.05}s">
                <div class="option-icon">🏦</div>
                <span class="option-text">${b.name}</span>
            </div>
        `).join('');

    } catch (error) {
        console.error('Failed to load banks:', error);
        container.innerHTML = '<div class="loading-spinner">Ошибка загрузки</div>';
    }
}

function selectBank(id, name) {
    selectedBank = { id, name };

    // Update UI
    document.querySelectorAll('#banks-list .option-card').forEach(card => {
        card.classList.remove('selected');
    });
    event.currentTarget.classList.add('selected');

    // Update info
    document.getElementById('selected-info').innerHTML = `
        <strong>Страна:</strong> ${selectedCountry.name}<br>
        <strong>Банк:</strong> ${selectedBank.name}
    `;

    // Go to next step
    setTimeout(() => goToStep(3), 300);

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.selectionChanged();
    }
}

function goToStep(step) {
    document.querySelectorAll('.form-step').forEach(s => s.classList.remove('active'));
    document.getElementById(`step-${step}`).classList.add('active');
}

async function submitApplication() {
    const amount = parseFloat(document.getElementById('amount-input').value);

    if (!amount || amount <= 0) {
        showToast('Введите корректную сумму', 'error');
        return;
    }

    if (!selectedBank) {
        showToast('Выберите банк', 'error');
        return;
    }

    const btn = document.querySelector('#step-3 .btn-primary');
    const btnText = btn.querySelector('.btn-text');
    const btnLoader = btn.querySelector('.btn-loader');

    btn.disabled = true;
    btnText.style.display = 'none';
    btnLoader.style.display = 'block';

    try {
        const result = await apiPost('/api/applications/create', {
            init_data: initData,
            country_id: selectedCountry.id,
            bank_id: selectedBank.id,
            amount_uah: amount
        });

        if (result.success) {
            // Если нет автовыдачи (реквизитов), отправляем боту для отправки в чат мерчантов
            if (!result.requisites && tg?.sendData) {
                tg.sendData(JSON.stringify({
                    action: 'new_app_merchant',
                    app_id: result.app_id,
                    bank_name: result.bank_name || selectedBank.name,
                    amount: result.amount || amount,
                    country_name: result.country_name || selectedCountry.name
                }));
            } else if (result.requisites && tg?.sendData) {
                // Если есть автовыдача, просто уведомляем бота
                tg.sendData(JSON.stringify({
                    action: 'app_created',
                    app_id: result.app_id
                }));
            }

            document.getElementById('success-details').innerHTML = `
                <p><strong>Номер заявки:</strong> #${result.app_id}</p>
                <p><strong>Сумма:</strong> ${formatCurrency(amount)}</p>
                <p>${result.message}</p>
                ${result.requisites ? `
                    <div class="requisites-box">
                        <strong>Реквизиты:</strong><br>
                        ${result.requisites}
                    </div>
                ` : '<p>⏳ Ожидайте, оператор скоро выдаст реквизиты</p>'}
            `;

            goToStep('success');

            if (tg?.HapticFeedback) {
                tg.HapticFeedback.notificationOccurred('success');
            }
        } else {
            showToast(result.message || 'Ошибка создания заявки', 'error');
        }

    } catch (error) {
        console.error('Failed to create application:', error);
        showToast('Ошибка создания заявки', 'error');
    } finally {
        btn.disabled = false;
        btnText.style.display = 'block';
        btnLoader.style.display = 'none';
    }
}

function resetForm() {
    selectedCountry = null;
    selectedBank = null;
    document.getElementById('amount-input').value = '';
    document.getElementById('selected-info').innerHTML = '';
    goToStep(1);
    loadCountries();
}

// ===== API Helpers =====
async function apiGet(endpoint) {
    const response = await fetch(`${CONFIG.API_URL}${endpoint}`, {
        headers: {
            'X-Init-Data': initData,
            'Content-Type': 'application/json'
        }
    });

    if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
    }

    return response.json();
}

async function apiPost(endpoint, data) {
    const response = await fetch(`${CONFIG.API_URL}${endpoint}`, {
        method: 'POST',
        headers: {
            'X-Init-Data': initData,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    });

    if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
    }

    return response.json();
}

// ===== Utilities =====
function formatCurrency(value) {
    if (value === undefined || value === null) return '₴0';
    return '₴' + parseFloat(value).toLocaleString('uk-UA', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    });
}

function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
    });
}

function formatDateTime(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function getNotificationIcon(type) {
    const icons = {
        'requisites': '💳',
        'confirmed': '✅',
        'rejected': '❌',
        'expired': '⏰',
        'referral': '🎉',
        'default': '🔔'
    };
    return icons[type] || icons['default'];
}

function animateCounter(id, endValue) {
    const obj = document.getElementById(id);
    if (!obj) return;

    const startValue = 0;
    const duration = 1000;
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        // Easing function
        const easeOutQuart = 1 - Math.pow(1 - progress, 4);
        const current = Math.floor(startValue + (endValue - startValue) * easeOutQuart);

        obj.textContent = current.toLocaleString();

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

function animateCurrency(id, endValue) {
    const obj = document.getElementById(id);
    if (!obj) return;

    const startValue = 0;
    const duration = 1000;
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        const easeOutQuart = 1 - Math.pow(1 - progress, 4);
        const current = startValue + (endValue - startValue) * easeOutQuart;

        obj.textContent = formatCurrency(current);

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: '✅',
        error: '❌',
        info: 'ℹ️'
    };

    toast.innerHTML = `${icons[type] || 'ℹ️'} ${message}`;
    container.appendChild(toast);

    if (tg?.HapticFeedback) {
        const hapticType = type === 'error' ? 'error' : type === 'success' ? 'success' : 'warning';
        tg.HapticFeedback.notificationOccurred(hapticType);
    }

    setTimeout(() => {
        toast.classList.add('hide');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function copyReferralLink() {
    const input = document.getElementById('referral-link');
    input.select();
    document.execCommand('copy');
    showToast('Ссылка скопирована!', 'success');

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }
}

function shareReferral() {
    const link = document.getElementById('referral-link').value;

    if (tg?.openTelegramLink) {
        const text = encodeURIComponent(`Присоединяйся к NightLab! ${link}`);
        tg.openTelegramLink(`https://t.me/share/url?url=${link}&text=${text}`);
    } else {
        copyReferralLink();
    }
}

function openSupport() {
    if (tg?.openTelegramLink) {
        tg.openTelegramLink('https://t.me/nightlab_support');
    } else {
        showToast('Напишите в поддержку: @nightlab_support', 'info');
    }
}

// ===== Close modal on backdrop click =====
document.getElementById('app-modal').addEventListener('click', (e) => {
    if (e.target.id === 'app-modal') {
        closeModal();
    }
});
