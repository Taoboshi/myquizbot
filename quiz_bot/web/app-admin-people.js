const adminPeople = { screen: null, search: '', filter: 'all', sort: 'recent', page: 0, listScroll: 0, listBodyScroll: 0,
  uid: null, tab: 'overview', testId: '', days: '0', detailPage: 0, data: null, request: 0, busy: false };
let adminPeopleSearchTimer;

function initializeAdminPeople() {
  const root = document.getElementById('view-admin');
  const overview = document.createElement('div');
  overview.id = 'admin-overview';
  overview.className = 'space-y-4';
  while (root.firstChild) overview.append(root.firstChild);
  root.append(overview);
  const workspace = document.createElement('div');
  workspace.id = 'admin-people-workspace';
  workspace.className = 'hidden admin-workspace';
  workspace.addEventListener('click', handleAdminPeopleClick);
  root.append(workspace);
}

function resetAdminPeopleScreen() {
  adminPeople.screen = null;
  adminPeople.request++;
  document.getElementById('admin-overview')?.classList.remove('hidden');
  document.getElementById('admin-people-workspace')?.classList.add('hidden');
}

function adminPeopleShell(screen) {
  adminPeople.screen = screen;
  document.getElementById('admin-overview').classList.add('hidden');
  document.getElementById('admin-people-workspace').classList.remove('hidden');
  updateHeaderNavState();
  updateTelegramBackButton();
}

async function adminPeopleFetch(url, payload) {
  const response = await fetch(url, payload ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : {});
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) throw new Error(data.error || 'Не удалось выполнить действие');
  return data;
}

function adminPeopleOptions(values, selected) {
  return values.map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');
}

function adminPeopleDate(value) {
  if (!value) return 'Нет данных';
  const text = String(value);
  const date = new Date(text.includes('T') ? text : text.replace(' ', 'T') + 'Z');
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function adminPeopleAvatar(user) {
  if (user.avatar && /^(data:image\/|https?:\/\/)/.test(user.avatar)) return `<img src="${escapeHtml(user.avatar)}" alt="" loading="lazy">`;
  return escapeHtml(user.avatar || user.name.slice(0,1));
}

async function openAdminPeople() {
  adminPeopleShell('list');
  const root = document.getElementById('admin-people-workspace');
  root.innerHTML = `<h2>Пользователи</h2><div class="admin-people-controls">
    <input type="search" id="people-search" aria-label="Поиск пользователей" placeholder="Имя, @username или ID" value="${escapeHtml(adminPeople.search)}">
    <select id="people-filter" aria-label="Фильтр пользователей">${adminPeopleOptions([
      ['all','Все пользователи'],['active7','Активны за 7 дней'],['active30','Активны за 30 дней'],
      ['inactive30','Не заходили 30 дней'],['blocked','Заблокированные'],['with_attempts','Есть попытки'],['with_access','Есть персональный доступ']
    ], adminPeople.filter)}</select>
    <select id="people-sort" aria-label="Сортировка пользователей">${adminPeopleOptions([['recent','По активности'],['attempts','По попыткам'],['errors','По ошибкам'],['accuracy','По точности']], adminPeople.sort)}</select>
    </div><div id="people-list" aria-live="polite"></div><div id="people-pagination" class="admin-pagination"></div>`;
  root.querySelector('#people-search').addEventListener('input', event => {
    adminPeople.search = event.target.value;
    adminPeople.page = 0;
    adminPeople.request++;
    clearTimeout(adminPeopleSearchTimer);
    adminPeopleSearchTimer = setTimeout(loadAdminPeople, 300);
  });
  ['filter','sort'].forEach(key => root.querySelector(`#people-${key}`).addEventListener('change', event => {
    adminPeople[key] = event.target.value;
    adminPeople.page = 0;
    loadAdminPeople();
  }));
  await loadAdminPeople();
}

async function loadAdminPeople() {
  if (adminPeople.screen !== 'list') return;
  const version = ++adminPeople.request;
  const list = document.getElementById('people-list');
  list.innerHTML = '<p class="admin-muted">Загрузка…</p>';
  const params = new URLSearchParams({ search: adminPeople.search, tab: adminPeople.filter, sort: adminPeople.sort, page: adminPeople.page });
  try {
    const data = await adminPeopleFetch(`/api/admin/people?${params}`);
    if (version !== adminPeople.request || adminPeople.screen !== 'list') return;
    list.innerHTML = `<p class="admin-muted">Найдено: ${data.total}</p>` + (data.items.length ? data.items.map(user => `
      <button class="admin-person-row" data-action="person" data-uid="${user.user_id}">
        <span class="admin-person-avatar">${adminPeopleAvatar(user)}</span>
        <span class="admin-person-copy"><strong>${escapeHtml(user.name)}</strong>
        <span>${escapeHtml(user.username ? '@'+user.username+' · ' : '')}ID: ${user.user_id}</span>
        <span>Последний визит: ${adminPeopleDate(user.last_seen_at)}</span>
        <span>${user.attempts_count} попыток · ${user.active_errors} ошибок${user.access_count ? ' · Доступов: '+user.access_count : ''}</span></span>
        <span class="admin-person-status ${user.is_blocked ? 'admin-danger' : 'admin-muted'}">${user.is_blocked ? 'Блокировка' : '›'}</span>
      </button>`).join('') : '<p class="admin-empty">Пользователи не найдены</p>');
    document.getElementById('people-pagination').innerHTML = paginationButtons(adminPeople.page, data.has_more, 'list-page');
  } catch(error) {
    if (version === adminPeople.request) list.innerHTML = `<p class="admin-danger">${escapeHtml(error.message)}</p><button data-action="reload-list" class="admin-command">Повторить</button>`;
  }
}

function paginationButtons(page, more, action) {
  return `<button class="admin-command" data-action="${action}" data-page="${page-1}" ${page ? '' : 'disabled'} aria-label="Предыдущая страница">←</button><span>Страница ${page+1}</span><button class="admin-command" data-action="${action}" data-page="${page+1}" ${more ? '' : 'disabled'} aria-label="Следующая страница">→</button>`;
}

async function openAdminPerson(uid, keepTab = false) {
  if (!keepTab) {
    adminPeople.listScroll = window.scrollY;
    adminPeople.listBodyScroll = document.getElementById('app-body').scrollTop;
    adminPeople.tab = 'overview';
    adminPeople.testId = '';
    adminPeople.days = '0';
    adminPeople.detailPage = 0;
  }
  adminPeople.uid = uid;
  adminPeopleShell('person');
  const version = ++adminPeople.request;
  const root = document.getElementById('admin-people-workspace');
  root.innerHTML = '<p class="admin-muted">Загрузка пользователя…</p>';
  try {
    const params = new URLSearchParams({ test_id: adminPeople.tab==='learning' ? adminPeople.testId : '', days: adminPeople.tab==='learning' ? adminPeople.days : '0', page: adminPeople.detailPage });
    const data = await adminPeopleFetch(`/api/admin/people/${uid}?${params}`);
    if (version !== adminPeople.request || adminPeople.screen !== 'person') return;
    adminPeople.data = data;
    renderAdminPerson();
    if (!keepTab) window.scrollTo(0,0);
  } catch(error) {
    if (version === adminPeople.request) root.innerHTML = `<p class="admin-danger">${escapeHtml(error.message)}</p><button class="admin-command" data-action="reload-person">Повторить</button>`;
  }
}

function renderAdminPerson() {
  const {user, stats} = adminPeople.data;
  const root = document.getElementById('admin-people-workspace');
  const tabs = [['overview','Обзор'],['learning','Обучение'],['access','Доступ'],['messages','Сообщения'],['manage','Управление'],['notes','Заметки']];
  root.innerHTML = `<div class="admin-person-heading"><span class="admin-person-avatar">${adminPeopleAvatar(user)}</span>
    <div><h2>${escapeHtml(user.name)}</h2><p class="admin-muted">${escapeHtml(user.username ? '@'+user.username+' · ' : '')}ID: ${user.user_id}</p></div></div>
    <div class="admin-person-tabs" role="tablist">${tabs.map(([id,title]) => `<button role="tab" aria-selected="${adminPeople.tab===id}" data-action="tab" data-tab="${id}">${title}</button>`).join('')}</div>
    <div id="person-content"></div>`;
  const content = root.querySelector('#person-content');
  if (adminPeople.tab === 'overview') {
    const accuracy = stats.answered ? Math.round(stats.correct*100/stats.answered) : 0;
    content.innerHTML = `<dl class="admin-details">
      <dt>Имя в Telegram</dt><dd>${escapeHtml(user.telegram_name || 'Не указано')}</dd>
      <dt>Регистрация</dt><dd>${adminPeopleDate(user.created_at)}</dd><dt>Последний визит</dt><dd>${adminPeopleDate(user.last_seen_at)}</dd>
      <dt>Доступ к приложению</dt><dd class="${user.is_blocked ? 'admin-danger' : 'admin-success'}">${user.is_blocked ? 'Заблокирован' : 'Открыт'}</dd>
      ${user.is_blocked ? `<dt>Причина</dt><dd>${escapeHtml(user.blocked_reason)}</dd><dt>До</dt><dd>${user.blocked_until ? adminPeopleDate(user.blocked_until) : 'Без срока'}</dd>` : ''}
      <dt>Попыток</dt><dd>${stats.attempts_total}</dd><dt>Завершено</dt><dd>${stats.finished || 0}</dd>
      <dt>Точность</dt><dd>${accuracy}%</dd><dt>Активных ошибок</dt><dd>${stats.active_errors}</dd></dl>`;
  } else if (adminPeople.tab === 'learning') {
    const data = adminPeople.data;
    content.innerHTML = `<select id="person-test-filter" aria-label="Фильтр по тесту">${adminPeopleOptions([['','Все тесты'], ...data.tests.map(test => [test.test_id,test.test_title])],adminPeople.testId)}</select>
      <select id="person-period-filter" aria-label="Период обучения">${adminPeopleOptions([['0','За всё время'],['7','За 7 дней'],['30','За 30 дней']],adminPeople.days)}</select>
      <h3>Попытки <span class="admin-muted">${stats.attempts_total}</span></h3>` + (data.attempts.map(attempt => `<div class="admin-record"><strong>${escapeHtml(attempt.test_title)}</strong>
      <p>${attempt.correct || 0}/${attempt.answered || 0} · ${attempt.finished_at ? 'Завершена' : 'Не завершена'} · ${adminPeopleDate(attempt.started_at)}</p>
      <p class="admin-muted">${escapeHtml(({normal:'По порядку',random:'Вразброс',training:'Тренировка',errors:'Разбор ошибок'})[attempt.mode] || attempt.mode || '')} · ${Math.round((attempt.duration_seconds || 0)/60)} мин</p></div>`).join('') || '<p class="admin-empty">Попыток нет</p>') +
      `<h3>Ошибки <span class="admin-muted">${stats.active_errors}</span></h3>` + (data.errors.map(error => `<div class="admin-record"><strong>${escapeHtml(error.test_title)} · №${error.question_index+1}</strong><p>${escapeHtml(error.question_text)}</p><p class="admin-danger">Ошибок: ${error.wrong_count}</p></div>`).join('') || '<p class="admin-empty">Ошибок нет</p>') +
      `<div class="admin-pagination">${paginationButtons(adminPeople.detailPage, Math.max(stats.attempts_total,stats.active_errors)>(adminPeople.detailPage+1)*25,'detail-page')}</div>`;
    content.querySelector('#person-test-filter').onchange = event => {
      adminPeople.testId=event.target.value; adminPeople.detailPage=0; openAdminPerson(user.user_id,true);
    };
    content.querySelector('#person-period-filter').onchange = event => {
      adminPeople.days=event.target.value; adminPeople.detailPage=0; openAdminPerson(user.user_id,true);
    };
  } else if (adminPeople.tab === 'access') {
    const accesses = adminPeople.data.access;
    content.innerHTML = `<h3>Персональные доступы</h3>` + (accesses.map(test => `<div class="admin-record admin-access-row"><div><strong>${escapeHtml(test.test_title)}</strong><p class="admin-muted">${test.access_source==='code' ? 'По коду' : 'Выдан администратором'} · ${adminPeopleDate(test.granted_at)}</p></div><button class="admin-command admin-danger" data-action="revoke" data-test="${escapeHtml(test.test_id)}">Отозвать</button></div>`).join('') || '<p class="admin-empty">Персональных доступов нет</p>') +
      `<h3>Выдать доступ</h3><select id="person-grant-test" aria-label="Тест для выдачи доступа">${adminPeopleOptions([['','Выберите тест'],...adminStore.testsMeta.filter(test=>['private','code'].includes(test.access_type) && !accesses.some(access=>access.test_id===test.id)).map(test=>[test.id,test.title])],'')}</select><button class="admin-command admin-primary" data-action="grant">Выдать доступ</button>`;
  } else if (adminPeople.tab === 'messages') {
    content.innerHTML = `<textarea id="person-message" rows="4" maxlength="4096" aria-label="Сообщение пользователю" placeholder="Сообщение в Telegram"></textarea><button class="admin-command admin-primary" data-action="message">Отправить</button><h3>История отправок</h3>` +
      (adminPeople.data.messages.map(message => `<div class="admin-record"><p>${escapeHtml(message.text)}</p><p class="${message.status==='sent' ? 'admin-success' : 'admin-danger'}">${message.status==='sent' ? 'Отправлено' : 'Не отправлено'} · ${adminPeopleDate(message.created_at)}</p>${message.error ? `<p class="admin-muted">${escapeHtml(message.error)}</p>` : ''}</div>`).join('') || '<p class="admin-empty">Сообщений пока нет</p>') +
      `<div class="admin-pagination">${paginationButtons(adminPeople.detailPage,adminPeople.data.message_count>(adminPeople.detailPage+1)*25,'detail-page')}</div>`;
  } else if (adminPeople.tab === 'notes') {
    content.innerHTML = `<textarea id="person-note" rows="7" maxlength="5000" aria-label="Внутренняя заметка" placeholder="Заметка администратора">${escapeHtml(adminPeople.data.note.note || '')}</textarea><button class="admin-command admin-primary" data-action="note">Сохранить</button>${adminPeople.data.note.updated_at ? `<p class="admin-muted">Обновлено: ${adminPeopleDate(adminPeople.data.note.updated_at)}</p>` : ''}`;
  } else if (adminPeople.tab === 'manage') {
    content.innerHTML = `<h3>Блокировка</h3>` + (user.is_blocked ? `<p>${escapeHtml(user.blocked_reason)}</p><button class="admin-command" data-action="unblock">Разблокировать</button>` :
      `<input id="person-block-reason" maxlength="500" aria-label="Причина блокировки" placeholder="Причина блокировки"><select id="person-block-days" aria-label="Срок блокировки">${adminPeopleOptions([['1','На сутки'],['7','На 7 дней'],['30','На 30 дней'],['0','Без срока']],'7')}</select><button class="admin-command admin-danger" data-action="block">Заблокировать</button>`) +
      `<h3>Сброс данных</h3><select id="person-reset-kind" aria-label="Данные для сброса">${adminPeopleOptions([['errors','Ошибки'],['favorites','Избранное'],['history','История и рейтинг'],['all','Весь учебный прогресс']],'errors')}</select>
      <select id="person-reset-test" aria-label="Область сброса">${adminPeopleOptions([['','Во всех тестах'],...adminStore.testsMeta.map(test=>[test.id,test.title])],'')}</select><button class="admin-command admin-danger" data-action="reset">Сбросить выбранные данные</button>`;
  }
}

async function handleAdminPeopleClick(event) {
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled || adminPeople.busy) return;
  const action = button.dataset.action;
  if (action === 'person') return openAdminPerson(Number(button.dataset.uid));
  if (action === 'reload-list') return loadAdminPeople();
  if (action === 'reload-person') return openAdminPerson(adminPeople.uid,true);
  if (action === 'list-page') { adminPeople.page=Number(button.dataset.page); await loadAdminPeople(); window.scrollTo(0,0); return; }
  if (action === 'detail-page') { adminPeople.detailPage=Number(button.dataset.page); return openAdminPerson(adminPeople.uid,true); }
  if (action === 'tab') {
    if (!confirmAdminPersonDraft()) return;
    adminPeople.tab=button.dataset.tab; adminPeople.detailPage=0;
    return openAdminPerson(adminPeople.uid,true);
  }
  const value = id => document.getElementById(id)?.value || '';
  const payload = {action};
  if (action === 'note') payload.text=value('person-note');
  if (action === 'message') {
    payload.text=value('person-message');
    if (!payload.text.trim()) return showToast('Введите сообщение');
    if (!confirm(`Отправить сообщение пользователю ${adminPeople.data.user.name}?`)) return;
  }
  if (action === 'block') {
    payload.reason=value('person-block-reason'); payload.days=Number(value('person-block-days'));
    if (!payload.reason.trim()) return showToast('Укажите причину блокировки');
    if (!confirm('Заблокировать доступ пользователя к приложению и боту?')) return;
  }
  if (action === 'unblock' && !confirm('Разблокировать пользователя?')) return;
  if (action === 'grant') {
    payload.test_id=value('person-grant-test');
    if (!payload.test_id) return showToast('Выберите тест');
  }
  if (action === 'revoke') {
    payload.test_id=button.dataset.test;
    if (!confirm('Отозвать персональный доступ? Общедоступные тесты останутся открытыми.')) return;
  }
  if (action === 'reset') {
    payload.kind=value('person-reset-kind'); payload.test_id=value('person-reset-test');
    const kind=document.getElementById('person-reset-kind').selectedOptions[0].textContent;
    const scope=document.getElementById('person-reset-test').selectedOptions[0].textContent;
    if (!confirm(`Пользователь: ${adminPeople.data.user.name}\nУдалить: ${kind}\nОбласть: ${scope}\nОтменить удаление нельзя. Имя, настройки и доступы сохранятся.`)) return;
    payload.confirmed=true;
  }
  adminPeople.busy=true;
  button.disabled=true;
  try {
    await adminPeopleFetch(`/api/admin/people/${adminPeople.uid}/action`,payload);
    showToast(action==='message' ? 'Сообщение отправлено' : 'Изменения сохранены');
    await openAdminPerson(adminPeople.uid,true);
  } catch(error) {
    showToast(error.message);
    if (action==='message') await openAdminPerson(adminPeople.uid,true);
  } finally { adminPeople.busy=false; button.disabled=false; }
}

async function backAdminPeople() {
  if (adminPeople.busy) return;
  if (adminPeople.screen==='person') {
    if (!confirmAdminPersonDraft()) return;
    await openAdminPeople();
    window.scrollTo(0,adminPeople.listScroll);
    document.getElementById('app-body').scrollTop=adminPeople.listBodyScroll;
  } else {
    resetAdminPeopleScreen();
    updateHeaderNavState(); updateTelegramBackButton();
  }
}

function confirmAdminPersonDraft() {
  const note=document.getElementById('person-note');
  const message=document.getElementById('person-message');
  const dirty=(note && note.value !== (adminPeople.data.note.note || '')) || (message && message.value.trim());
  return !dirty || confirm('Уйти без сохранения введённого текста?');
}

function applyProgressResets(markers) {
  const key=`ohtest_reset_markers_${state.userId}`;
  let seen={};
  try { seen=JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch(e) {}
  let changed=false;
  markers.forEach(marker => {
    const id=marker.test_id+':'+marker.kind;
    if (seen[id]===marker.version) return;
    const matches=testId => !marker.test_id || marker.test_id===testId;
    Object.keys(localStorage).forEach(name => {
      const patterns={errors:['ohtest_errors_','ohtest_resolved_errors_'],favorites:['ohtest_favs_'],all:['ohtest_errors_','ohtest_resolved_errors_','ohtest_favs_','ohtest_fc_progress_']};
      (patterns[marker.kind] || []).forEach(prefix => { if (name.startsWith(prefix) && matches(name.slice(prefix.length))) localStorage.removeItem(name); });
    });
    if (['history','all'].includes(marker.kind)) {
      state.historyAttempts=state.historyAttempts.filter(item=>!matches(item.testId));
      localStorage.setItem('ohtest_history',JSON.stringify(state.historyAttempts));
      if (state.activeAttempt && matches(state.activeAttempt.testId)) {
        state.activeAttempt=null;
        localStorage.removeItem('ohtest_active_attempt');
        renderActiveAttemptBanner(); updateHubResumeButton();
      }
    }
    if (matches(state.activeTestId)) {
      if (['errors','all'].includes(marker.kind)) { state.userErrors=new Set(); state.revealedAnswers=new Set(); }
      if (['favorites','all'].includes(marker.kind)) state.favorites=new Set();
      if (['history','all'].includes(marker.kind)) {
        state.userAnswers={}; state.currentQIndex=0; state.timerSeconds=0;
        clearInterval(state.timerInterval);
        if (['solver','result'].includes(state.homeActiveView)) state.homeActiveView='hub';
      }
      if (marker.kind==='all') {
        fcLearned=[]; fcReview=[]; fcHistoryStack=[]; fcIndex=0;
        state.activeQuestions=[...state.currentTestOriginalQuestions];
        if (state.homeActiveView==='flashcards') {
          document.getElementById('fc-finish-screen').classList.add('hidden');
          document.getElementById('fc-active-deck').classList.remove('hidden');
          renderFCCard();
        }
      }
    }
    seen[id]=marker.version; changed=true;
  });
  if (changed) { localStorage.setItem(key,JSON.stringify(seen)); updateProfileFullView(); }
}

window.addEventListener('DOMContentLoaded',initializeAdminPeople);
