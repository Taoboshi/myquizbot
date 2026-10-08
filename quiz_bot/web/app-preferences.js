const preferenceDefaults = {
  autoNext: false, showTimer: true, trainingCount: 10,
  fcShuffle: false, fcAnswerFirst: false, fcRemember: true,
  textSize: 'normal', reduceMotion: false, haptic: true, restoreHome: true
};
const accountPreferenceKeys = ['autoNext', 'showTimer', 'trainingCount', 'fcShuffle', 'fcAnswerFirst', 'fcRemember'];
let appPreferences = { ...preferenceDefaults };
try {
  const saved = JSON.parse(localStorage.getItem('ohtest_preferences') || '{}');
  Object.keys(preferenceDefaults).forEach(key => {
    if (typeof saved[key] === typeof preferenceDefaults[key]) appPreferences[key] = saved[key];
  });
} catch(e) {}
let pendingPreferences = {};
try {
  const pending = JSON.parse(localStorage.getItem('ohtest_pending_preferences') || '{}');
  accountPreferenceKeys.forEach(key => {
    if (pending && typeof pending[key] === typeof preferenceDefaults[key]) pendingPreferences[key] = pending[key];
  });
} catch(e) {}
let preferenceSyncTimer;
let preferencesSyncing = false;

function persistPreferences() {
  try { localStorage.setItem('ohtest_preferences', JSON.stringify(appPreferences)); } catch(e) {}
  try { localStorage.setItem('ohtest_pending_preferences', JSON.stringify(pendingPreferences)); } catch(e) {}
}

function applyServerPreferences(values) {
  accountPreferenceKeys.forEach(key => {
    if (typeof values[key] === typeof preferenceDefaults[key] && !(key in pendingPreferences)) appPreferences[key] = values[key];
  });
  persistPreferences();
  applyPreferences();
  if (Object.keys(pendingPreferences).length) syncPreferences();
}

async function syncPreferences() {
  if (preferencesSyncing || !state.userId || !Object.keys(pendingPreferences).length) return;
  preferencesSyncing = true;
  const changes = { ...pendingPreferences };
  try {
    const response = await fetch('/api/user/preferences', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes)
    });
    if (!response.ok) throw new Error('Не удалось сохранить настройки');
    Object.entries(changes).forEach(([key, value]) => {
      if (pendingPreferences[key] === value) delete pendingPreferences[key];
    });
    persistPreferences();
    if (Object.keys(pendingPreferences).length) preferenceSyncTimer = setTimeout(syncPreferences, 250);
  } catch(e) {
    showToast('Настройки сохранены на устройстве. Синхронизация недоступна.');
  } finally {
    preferencesSyncing = false;
  }
}

function setPreference(key, value) {
  if (!(key in preferenceDefaults)) return;
  if (key === 'trainingCount') value = Math.max(1, Math.min(500, Math.round(Number(value) || 10)));
  appPreferences[key] = value;
  applyPreferences();
  if (accountPreferenceKeys.includes(key)) {
    pendingPreferences[key] = value;
    clearTimeout(preferenceSyncTimer);
    preferenceSyncTimer = setTimeout(syncPreferences, 250);
  }
  persistPreferences();
  if (key === 'fcAnswerFirst' && getCurrentActiveView() === 'view-flashcards' && !document.getElementById('fc-active-deck').classList.contains('hidden')) renderFCCard();
  if (key === 'fcRemember') {
    if (value) saveFCProgress();
    else Object.keys(localStorage).filter(name => name.startsWith('ohtest_fc_progress_')).forEach(name => localStorage.removeItem(name));
  }
}

function applyPreferences() {
  document.body.classList.toggle('reduce-motion', appPreferences.reduceMotion);
  document.body.dataset.textSize = appPreferences.textSize;
  document.getElementById('solver-timer')?.classList.toggle('hidden', !appPreferences.showTimer);
  document.querySelectorAll('[data-preference]').forEach(control => {
    const value = appPreferences[control.dataset.preference];
    if (control.type === 'checkbox') control.checked = value;
    else control.value = value;
  });
  const haptic = document.getElementById('set-haptic');
  if (haptic) haptic.checked = appPreferences.haptic;
  fcShuffleEnabled = appPreferences.fcShuffle;
  const themeSelect = document.getElementById('settings-theme-mode');
  if (themeSelect) themeSelect.value = localStorage.getItem('ohtest_theme') || 'dark';
}

function preferenceRow(key, title, description, options) {
  const control = options
    ? `<select data-preference="${key}" aria-label="${title}" onchange="setPreference('${key}', this.value)">${options.map(([value, text]) => `<option value="${value}">${text}</option>`).join('')}</select>`
    : key === 'trainingCount'
      ? `<input type="number" data-preference="${key}" aria-label="${title}" min="1" max="500" inputmode="numeric" onchange="setPreference('${key}', this.value)">`
      : `<input type="checkbox" role="switch" data-preference="${key}" aria-label="${title}" onchange="setPreference('${key}', this.checked)">`;
  return `<label class="settings-row"><span class="settings-row-copy"><span class="settings-row-title">${title}</span><span class="settings-row-description">${description}</span></span>${control}</label>`;
}

function settingsAction(title, description, action, dangerous = false) {
  return `<button type="button" class="settings-row settings-action ${dangerous ? 'settings-danger' : ''}" onclick="${action}"><span class="settings-row-copy"><span class="settings-row-title">${title}</span><span class="settings-row-description">${description}</span></span><span aria-hidden="true">${renderInterfaceIcon('chevron-right')}</span></button>`;
}

function initializeSettingsSections() {
  const root = document.getElementById('view-tab-settings');
  const theme = document.getElementById('theme-accent-settings-block');
  const haptic = document.getElementById('set-haptic').closest('div.flex');
  const rating = document.getElementById('set-hide-rating').closest('div.flex');
  const support = root.querySelector('button[onclick="openSupportChat()"]')?.parentElement.parentElement;
  const about = root.querySelector('div.text-center');
  const admin = document.getElementById('settings-admin-block');
  const sections = [
    ['appearance', 'Оформление', 'Тема, цвет и размер текста', 'palette'],
    ['learning', 'Обучение', 'Ответы, таймер и тренировка', 'book-open'],
    ['comfort', 'Удобство', 'Вибрация и навигация', 'vibrate'],
    ['profile', 'Профиль и рейтинг', 'Профиль, рейтинг и данные', 'user-round-cog'],
    ['help', 'Помощь', 'Поддержка и версия приложения', 'circle-help']
  ];
  const menu = document.createElement('div');
  menu.id = 'settings-sections-menu';
  menu.className = 'settings-menu';
  const pages = document.createElement('div');
  pages.id = 'settings-section-pages';
  pages.className = 'hidden';
  sections.forEach(([id, title, description, icon]) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'settings-section-link';
    button.onclick = () => openSettingsSection(id);
    button.innerHTML = `<span class="settings-section-icon">${renderInterfaceIcon(icon)}</span><span class="settings-row-copy"><span class="settings-row-title">${title}</span><span class="settings-row-description">${description}</span></span><span aria-hidden="true">${renderInterfaceIcon('chevron-right')}</span>`;
    menu.append(button);
    const page = document.createElement('div');
    page.dataset.settingsSection = id;
    page.className = 'settings-page hidden';
    page.innerHTML = `<h2 class="text-base font-bold text-white mb-4">${title}</h2>`;
    pages.append(page);
  });
  const page = id => pages.querySelector(`[data-settings-section="${id}"]`);
  const themeRow = theme.querySelector('#theme-segmented-ctrl').parentElement;
  themeRow.querySelector('#theme-segmented-ctrl').remove();
  const themeControl = document.createElement('select');
  themeControl.id = 'settings-theme-mode';
  themeControl.setAttribute('aria-label', 'Тема оформления');
  themeControl.innerHTML = '<option value="dark">Тёмная</option><option value="light">Светлая</option><option value="system">Как на устройстве</option>';
  themeControl.onchange = () => setThemeMode(themeControl.value);
  themeRow.append(themeControl);
  themeRow.className = 'settings-row';
  page('appearance').append(theme);
  page('appearance').insertAdjacentHTML('beforeend',
    preferenceRow('textSize', 'Размер текста', 'Размер подписей и текста вопросов', [['normal', 'Обычный'], ['large', 'Крупный'], ['larger', 'Очень крупный']]) +
    preferenceRow('reduceMotion', 'Меньше анимаций', 'Минимум движения при переходах') +
    settingsAction('Сбросить настройки приложения', 'Вернуть параметры к исходным значениям', 'resetAppPreferences()', true));
  page('learning').insertAdjacentHTML('beforeend',
    preferenceRow('autoNext', 'Переходить к следующему вопросу', 'После ответа, с короткой паузой') +
    preferenceRow('showTimer', 'Показывать таймер', 'Время прохождения теста') +
    preferenceRow('trainingCount', 'Вопросов в тренировке', 'Предлагаемое количество при запуске'));
  page('comfort').append(haptic);
  haptic.className = 'settings-row';
  haptic.firstElementChild.className = 'settings-row-copy';
  haptic.querySelector('.font-bold').className = 'settings-row-title';
  haptic.querySelector('.text-\\[10px\\]').className = 'settings-row-description';
  haptic.querySelector('.settings-row-title').textContent = 'Вибрация';
  haptic.querySelector('#set-haptic').onchange = event => setPreference('haptic', event.target.checked);
  haptic.querySelector('#set-haptic').setAttribute('aria-label', 'Вибрация');
  haptic.querySelector('#set-haptic').setAttribute('role', 'switch');
  page('comfort').insertAdjacentHTML('beforeend', preferenceRow('restoreHome', 'Запоминать экран главной', 'Возвращаться к месту, где остановились'));
  page('profile').insertAdjacentHTML('beforeend', settingsAction('Имя и аватарка', 'Изменить профиль', 'openEditProfileModal()'));
  page('profile').append(rating);
  rating.className = 'settings-row';
  rating.firstElementChild.className = 'settings-row-copy';
  rating.querySelector('.font-bold').className = 'settings-row-title';
  rating.querySelector('.text-\\[10px\\]').className = 'settings-row-description';
  rating.querySelector('#set-hide-rating').setAttribute('aria-label', 'Скрыть профиль из рейтинга');
  rating.querySelector('#set-hide-rating').setAttribute('role', 'switch');
  page('profile').insertAdjacentHTML('beforeend', settingsAction('Сбросить результаты рейтинга', 'Удалить попытки и рекорды на сервере. Избранное сохранится.', 'resetMyRatingProgress()', true));
  page('profile').insertAdjacentHTML('beforeend',
    settingsAction('Сбросить локальный прогресс', 'Удалить попытки, ошибки и избранные вопросы на этом устройстве. Серверный рейтинг и настройки сохранятся.', 'clearLocalAppCache()', true));
  page('help').append(support, about);
  about.querySelector('div:last-child').textContent = 'Подготовка к вузовским тестам';
  admin.replaceChildren();
  admin.insertAdjacentHTML('beforeend', settingsAction('Администрирование', 'Управление предметами, тестами и пользователями', 'openAdminDashboard()'));
  menu.append(admin);
  root.replaceChildren(menu, pages);
  applyPreferences();
  const options = document.querySelector('#modal-fc-options .divide-y');
  options.insertAdjacentHTML('afterbegin',
    preferenceRow('fcAnswerFirst', 'Начинать с ответа', 'Показывать ответ на лицевой стороне карточки') +
    preferenceRow('fcRemember', 'Запоминать прогресс', 'Продолжать набор на этом устройстве'));
  applyPreferences();
}

function openSettingsSection(section) {
  state.settingsSection = section;
  document.getElementById('settings-sections-menu').classList.toggle('hidden', Boolean(section));
  document.getElementById('settings-section-pages').classList.toggle('hidden', !section);
  document.querySelectorAll('[data-settings-section]').forEach(page => page.classList.toggle('hidden', page.dataset.settingsSection !== section));
  document.getElementById('app-body').scrollTop = 0;
  window.scrollTo(0, 0);
  updateHeaderNavState();
  updateTelegramBackButton();
}

function resetAppPreferences() {
  if (!confirm('Вернуть стандартные настройки приложения?')) return;
  Object.entries(preferenceDefaults).forEach(([key, value]) => setPreference(key, value));
  setThemeMode('dark');
  setAccentColor('green');
  showToast('Стандартные настройки восстановлены');
}

window.addEventListener('DOMContentLoaded', initializeSettingsSections);
window.addEventListener('online', syncPreferences);
matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
  if (localStorage.getItem('ohtest_theme') === 'system') setThemeMode('system', true);
});
