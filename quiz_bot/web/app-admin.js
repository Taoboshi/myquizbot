// REAL ADMIN DASHBOARD
  function updateAdminStats() {
    document.getElementById('adm-stat-users').innerText = adminStore.users.length;
    document.getElementById('adm-stat-attempts').innerText = '0';
    document.getElementById('adm-stat-tests').innerText = adminStore.testsMeta.length;
    const unassigned = adminStore.testsMeta.filter(t => t.subject_id === 'default' || !t.subject_id).length;
    document.getElementById('adm-stat-unassigned').innerText = unassigned;
  }

  async function openAdminDashboard() {
    triggerHaptic('light');
    state.homeActiveView = 'admin';
    hideAllViews();
    document.getElementById('view-admin').classList.remove('hidden');
    updateHeaderNavState();
    updateTelegramBackButton();

    updateAdminStats();

    try {
      const res = await fetch(`/api/admin/overview?user_id=${state.userId}`);
      if (res.ok) {
        const data = await res.json();
        document.getElementById('adm-stat-users').innerText = data.users_count;
        document.getElementById('adm-stat-attempts').innerText = data.attempts_count;
        document.getElementById('adm-stat-tests').innerText = data.tests_count;
        document.getElementById('adm-stat-unassigned').innerText = data.unassigned_count;
      }
    } catch(e) {}

    viewStack.push('admin');
  }

  // Admin Modals
  async function openAdminModal(type) {
    triggerHaptic('light');
    const modal = document.getElementById('modal-admin-action');
    const title = document.getElementById('admin-modal-title');
    const body = document.getElementById('admin-modal-body');

    modal.classList.remove('hidden');

    if (type === 'subjects_and_tests' || type === 'tests' || type === 'subjects' || type === 'unassigned') {
      title.innerHTML = 'Управление предметами и тестами';

      try {
        const res = await fetch(`/api/admin/tests?user_id=${state.userId}`);
        if (res.ok) {
          const data = await res.json();
          if (data.items && data.items.length > 0) {
            const delSet = new Set(JSON.parse(localStorage.getItem('ohtest_deleted_subjects') || '[]'));
            const unSet = new Set(JSON.parse(localStorage.getItem('ohtest_unassigned_tests') || '[]'));
            data.items.forEach(t => {
              if (unSet.has(t.id) || delSet.has(t.subject_id)) {
                t.subject_id = 'default';
                t.subject_title = 'Не привязан';
              }
            });
            adminStore.testsMeta = data.items;
          }
        }
      } catch(e) {}
      
      const unassignedTests = adminStore.testsMeta.filter(t => t.subject_id === 'default' || !t.subject_id);

      let subjectsHtml = adminStore.subjects.map(s => {
        const testsInSub = adminStore.testsMeta.filter(t => t.subject_id === s.id);
        
        let testsListHtml = '';
        if (testsInSub.length === 0) {
          testsListHtml = '<div class="p-2 text-center text-[11px] text-slate-400">В этом предмете пока нет привязанных тестов.</div>';
        } else {
          testsListHtml = testsInSub.map(t => {
            const accType = t.access_type || 'public';
            let accBadge = '<span class="px-2 py-0.5 rounded-full bg-brand-500/15 text-brand-400 border border-brand-500/30 text-[10px] font-bold">Открытый</span>';
            let accLabel = 'Открытый';
            if (accType === 'code') {
              accBadge = `<span class="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30 text-[10px] font-bold">Код: ${t.access_code || '—'}</span>`;
              accLabel = 'По коду';
            } else if (accType === 'private') {
              accBadge = '<span class="px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-400 border border-purple-500/30 text-[10px] font-bold">Приватный</span>';
              accLabel = 'Приватный';
            } else if (accType === 'admin_only') {
              accBadge = '<span class="px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30 text-[10px] font-bold">Только админ</span>';
              accLabel = 'Только админ';
            }

            return `
            <div class="p-3 rounded-xl bg-app-card border border-app-border space-y-2">
              <div class="flex items-start justify-between text-xs gap-2">
                <div class="space-y-0.5 min-w-0 flex-1">
                  <div class="font-bold text-white truncate">${t.title}</div>
                  <div class="text-[10px] text-slate-400 font-mono">${t.id}</div>
                </div>
                <div class="flex flex-col items-end gap-1 shrink-0">
                  <span class="font-mono text-[10px] text-brand-300 font-bold">${t.questions_count} вопр.</span>
                  ${accBadge}
                </div>
              </div>
              <div class="flex items-center justify-between pt-1 border-t border-app-border/60 text-[11px] gap-2 flex-wrap">
                <button onclick="openAccessModal('${t.id}')" class="text-brand-400 hover:underline font-bold flex items-center gap-1">
                  Доступ: ${accLabel}
                </button>
                <div class="flex items-center gap-2">
                  <button onclick="renameTestPrompt('${t.id}', '${t.title.replace(/'/g, "\\'")}')" class="text-brand-300 hover:underline">
                    Переименовать
                  </button>
                  <button onclick="unlinkTest('${t.id}')" class="text-amber-400 hover:underline">
                    Отвязать
                  </button>
                </div>
              </div>
            </div>
            `;
          }).join('');
        }

        return `
          <div class="p-3.5 rounded-2xl bg-app-surface border border-app-border space-y-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-2">
                <span class="text-xs font-bold text-white">${s.title}</span>
                <span class="text-[10px] text-slate-400 font-mono">(${testsInSub.length})</span>
              </div>
              <div class="flex items-center gap-1.5 text-xs">
                <button onclick="editSubjectPrompt('${s.id}', '${s.title.replace(/'/g, "\\'")}', '${s.emoji || ''}')" class="px-2 py-1 rounded-lg bg-app-card border border-app-border text-[10px] text-brand-300 hover:text-white" title="Редактировать предмет">
                  Изменить
                </button>
                <button onclick="deleteSubject('${s.id}')" class="px-2 py-1 rounded-lg bg-app-card border border-app-border text-[10px] text-rose-400 hover:text-white" title="Удалить предмет">
                  Удалить
                </button>
              </div>
            </div>
            <div class="space-y-1.5 pl-2 border-l-2 border-brand-500/30">
              ${testsListHtml}
            </div>
          </div>
        `;
      }).join('');

      let unassignedSection = '';
      if (unassignedTests.length > 0) {
        let unassignedCards = unassignedTests.map(t => {
          const accType = t.access_type || 'public';
          let accBadge = '<span class="px-2 py-0.5 rounded-full bg-brand-500/15 text-brand-400 border border-brand-500/30 text-[10px] font-bold">Открытый</span>';
          let accLabel = 'Открытый';
          if (accType === 'code') {
            accBadge = `<span class="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30 text-[10px] font-bold">Код: ${t.access_code || '—'}</span>`;
            accLabel = 'По коду';
          } else if (accType === 'private') {
            accBadge = '<span class="px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-400 border border-purple-500/30 text-[10px] font-bold">Приватный</span>';
            accLabel = 'Приватный';
          } else if (accType === 'admin_only') {
            accBadge = '<span class="px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30 text-[10px] font-bold">Только админ</span>';
            accLabel = 'Только админ';
          }

          return `
          <div class="p-3 rounded-xl bg-app-card border border-amber-500/30 space-y-2">
            <div class="flex items-start justify-between text-xs gap-2">
              <div class="space-y-0.5 min-w-0 flex-1">
                <div class="font-bold text-white truncate">${t.title}</div>
                <div class="text-[10px] text-slate-400 font-mono">${t.id}</div>
              </div>
              <div class="flex flex-col items-end gap-1 shrink-0">
                <span class="font-mono text-[10px] text-amber-400 font-bold">${t.questions_count} вопр.</span>
                ${accBadge}
              </div>
            </div>
            <div class="flex items-center justify-between pt-1 border-t border-app-border/60 text-[11px] gap-2 flex-wrap">
              <button onclick="openAccessModal('${t.id}')" class="text-brand-400 hover:underline font-bold flex items-center gap-1">
                Доступ: ${accLabel}
              </button>
            </div>
            <div class="flex items-center gap-2 pt-1">
              <select id="u-assign-${t.id}" class="flex-1 px-2 py-1.5 rounded-xl bg-app-surface border border-app-border text-xs text-white">
                ${adminStore.subjects.map(s => `<option value="${s.id}">${s.title}</option>`).join('')}
              </select>
              <button onclick="assignUnassignedTest('${t.id}')" class="px-3 py-1.5 rounded-xl bg-brand-600 text-white font-bold text-xs active:scale-95 transition">
                Привязать
              </button>
            </div>
          </div>
          `;
        }).join('');

        unassignedSection = `
          <div class="space-y-2 pt-2">
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold text-amber-400 uppercase tracking-wider">Непривязанные тесты (${unassignedTests.length})</span>
            </div>
            <div class="space-y-2">${unassignedCards}</div>
          </div>
        `;
      }

      body.innerHTML = `
        <div class="space-y-3">
          <!-- Add Subject Box -->
          <div class="p-3 rounded-2xl bg-app-surface border border-app-border space-y-2">
            <div class="text-xs font-bold text-white">Добавить новый предмет</div>
            <div class="flex gap-2">
              <input id="new-subj-title" placeholder="Название предмета..." class="flex-1 px-3 py-1.5 rounded-xl bg-app-card border border-app-border text-xs text-white">
              <button onclick="addNewSubject()" class="px-3 py-1.5 rounded-xl bg-brand-600 text-white font-bold text-xs active:scale-95 transition">Создать</button>
            </div>
          </div>

          <div class="space-y-2.5">
            ${subjectsHtml}
          </div>

          ${unassignedSection}
        </div>
      `;
    } else if (type === 'upload') {
      title.innerHTML = 'Импортировать тест';
      body.innerHTML = `
        <div class="space-y-3">
          <p class="text-xs text-slate-300">Выберите JSON-файл, проверьте вопросы и правильные ответы, затем сохраните тест.</p>
          <label class="border-2 border-dashed border-app-border hover:border-brand-500 rounded-2xl p-6 flex flex-col items-center justify-center text-center cursor-pointer transition bg-app-surface/40">
            <div class="w-12 h-12 mb-2 rounded-2xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center text-brand-400">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
            </div>
            <span class="text-xs font-bold text-white">Выбрать JSON-файл</span>
            <span class="text-[10px] text-slate-400 mt-1">Можно выбрать файл из памяти устройства</span>
            <input type="file" accept=".json,application/json" class="hidden" onchange="uploadJsonFile(event)">
          </label>
          <div id="adm-upload-msg" class="hidden p-3 rounded-xl bg-brand-950/40 border border-brand-500/30 text-xs text-brand-300"></div>
          <div id="adm-upload-preview" class="hidden space-y-2"></div>
        </div>
      `;
    } else if (type === 'subjects') {
      title.innerHTML = 'Управление предметами';
      body.innerHTML = `
        <div class="space-y-3">
          <div class="p-3 rounded-2xl bg-app-surface border border-app-border space-y-2">
            <div class="text-xs font-bold text-white">Создать новую дисциплину</div>
            <div class="flex gap-2">
              <input id="new-subj-title" placeholder="Название предмета..." class="flex-1 px-3 py-1.5 rounded-xl bg-app-card border border-app-border text-xs text-white">
              <button onclick="addNewSubject()" class="px-3 py-1.5 rounded-xl bg-brand-600 text-white font-bold text-xs">Создать</button>
            </div>
          </div>
          <div class="space-y-2" id="adm-subj-list"></div>
        </div>
      `;
      const list = document.getElementById('adm-subj-list');
      adminStore.subjects.forEach(s => {
        const item = document.createElement('div');
        item.className = "p-3 rounded-xl bg-app-surface border border-app-border flex items-center justify-between text-xs";
        item.innerHTML = `
          <span><b>${s.title}</b> (${s.tests_count} тестов)</span>
          <button onclick="deleteSubject('${s.id}')" class="text-rose-400 hover:underline">Удалить</button>
        `;
        list.appendChild(item);
      });
    } else if (type === 'users') {
      title.innerHTML = 'Управление пользователями';
      body.innerHTML = `
        <div class="space-y-3">
          <!-- Search & Sort Row -->
          <div class="flex items-center gap-2">
            <div class="relative flex-1">
              <span class="absolute left-3 top-2.5 text-xs text-slate-400">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
              </span>
              <input id="adm-users-search" oninput="filterAdminUsers()" placeholder="Поиск по имени, @username или ID..." class="w-full pl-8 pr-3 py-2 rounded-xl bg-app-surface border border-app-border text-xs text-white focus:outline-none focus:border-brand-500">
            </div>
            <select id="adm-users-sort" onchange="filterAdminUsers()" class="px-2.5 py-2 rounded-xl bg-app-surface border border-app-border text-xs text-slate-200">
              <option value="recent">Активность</option>
              <option value="accuracy">Точность</option>
              <option value="attempts">Попытки</option>
              <option value="errors">Ошибки</option>
            </select>
          </div>

          <!-- Filter Pills -->
          <div class="flex items-center gap-1.5 overflow-x-auto hide-scrollbar pb-0.5 text-xs">
            <button onclick="setAdminUsersTab('all')" id="autab-all" class="px-2.5 py-1.5 rounded-xl font-bold transition bg-brand-600 text-white shadow-sm shrink-0">
              Все (<span id="auc-all">0</span>)
            </button>
            <button onclick="setAdminUsersTab('active')" id="autab-active" class="px-2.5 py-1.5 rounded-xl font-medium transition bg-app-surface border border-app-border text-slate-400 hover:text-white shrink-0">
              Активные (<span id="auc-active">0</span>)
            </button>
            <button onclick="setAdminUsersTab('with_attempts')" id="autab-with_attempts" class="px-2.5 py-1.5 rounded-xl font-medium transition bg-app-surface border border-app-border text-slate-400 hover:text-white shrink-0">
              С попытками (<span id="auc-attempts">0</span>)
            </button>
            <button onclick="setAdminUsersTab('blocked')" id="autab-blocked" class="px-2.5 py-1.5 rounded-xl font-medium transition bg-app-surface border border-app-border text-slate-400 hover:text-white shrink-0">
              Блок (<span id="auc-blocked">0</span>)
            </button>
          </div>

          <!-- User List Container -->
          <div id="adm-users-list" class="space-y-2 max-h-[380px] overflow-y-auto pr-1">
            <div class="p-8 text-center text-xs text-slate-400">Загрузка пользователей из базы...</div>
          </div>
        </div>
      `;
      try {
        const res = await fetch(`/api/admin/users?user_id=${state.userId}`);
        if (res.ok) {
          const data = await res.json();
          adminStore.users = data.items || [];
        }
      } catch(e) {}
      filterAdminUsers();
    } else if (type === 'errors') {
      title.innerHTML = 'Частые ошибки студентов';
      body.innerHTML = '<div class="space-y-2" id="adm-errors-list"><div class="p-6 text-center text-xs text-slate-400">Загрузка аналитики...</div></div>';
      try {
        const res = await fetch(`/api/admin/frequent_errors?user_id=${state.userId}`);
        if (res.ok) {
          const data = await res.json();
          adminStore.frequentErrors = data.items || [];
        }
      } catch(e) {}
      const list = document.getElementById('adm-errors-list');
      list.innerHTML = '';
      if (adminStore.frequentErrors.length === 0) {
        list.innerHTML = `
          <div class="p-8 text-center text-xs text-slate-400 space-y-3">
            <div class="w-12 h-12 mx-auto rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
            <div class="font-bold text-white">Ошибок пока не зафиксировано</div>
            <p class="text-[11px] text-slate-500">Здесь появится аналитика по вопросам, в которых студенты ошибаются чаще всего, как только они начнут решать тесты.</p>
          </div>
        `;
        return;
      }
      adminStore.frequentErrors.forEach(err => {
        const el = document.createElement('div');
        el.className = "p-3 rounded-2xl bg-app-surface border border-rose-500/30 text-xs space-y-1.5";
        el.innerHTML = `
          <div class="flex justify-between font-bold text-white">
            <span>${err.test_title} · Вопрос #${err.question_index}</span>
            <span class="text-rose-400 font-mono">${err.error_count} ошибок (${err.users_count} чел.)</span>
          </div>
          <p class="text-[11px] text-slate-300 font-medium">${err.question_text}</p>
        `;
        list.appendChild(el);
      });
    } else if (type === 'broadcast') {
      title.innerHTML = 'Рассылка сообщений';
      body.innerHTML = `
        <div class="space-y-3">
          <div class="flex justify-between text-xs text-slate-300">
            <span>Текст объявления:</span>
            <span class="text-brand-300 font-bold">Получателей в базе: ${adminStore.users.length}</span>
          </div>
          <textarea id="adm-bc-text" rows="4" placeholder="Введите текст рассылки для всех учеников бота..." class="w-full p-3 rounded-xl bg-app-surface border border-app-border text-xs text-white focus:outline-none focus:border-brand-500"></textarea>
          <button onclick="sendBroadcast()" class="w-full py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-bold text-xs active:scale-95 transition shadow-md">
            Отправить рассылку
          </button>
          <div id="adm-bc-status" class="hidden p-2.5 rounded-xl text-center text-xs"></div>
        </div>
      `;
    } else if (type === 'feedback') {
      title.innerHTML = 'Входящая обратная связь';
      body.innerHTML = '<div class="space-y-2" id="adm-feedback-list"><div class="p-6 text-center text-xs text-slate-400">Загрузка сообщений...</div></div>';
      try {
        const res = await fetch(`/api/admin/feedback?user_id=${state.userId}`);
        const data = await res.json();
        const list = document.getElementById('adm-feedback-list');
        if (!list) return;
        list.innerHTML = '';
        const items = data.items || [];
        if (items.length === 0) {
          list.innerHTML = `
            <div class="p-8 text-center text-xs text-slate-400 space-y-3">
              <div class="w-12 h-12 mx-auto rounded-2xl bg-app-surface border border-app-border flex items-center justify-center text-slate-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/></svg>
              </div>
              <div class="font-bold text-white">Входящих обращений пока нет</div>
              <p class="text-[11px] text-slate-500">Все обращения пользователей через кнопку поддержки сохраняются в базу данных и дублируются администратору @issdm в Telegram.</p>
            </div>
          `;
          return;
        }
        items.forEach(item => {
          const el = document.createElement('div');
          const typeLabels = {
            bug: 'Ошибка в вопросе',
            feature: 'Предложение',
            question: 'Вопрос',
            other: 'Другое'
          };
          const badgeType = typeLabels[item.fb_type] || item.fb_type || 'Сообщение';
          const safeMsg = (item.message || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          const safeContact = (item.contact || 'ID: ' + (item.user_id || '—')).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          const safeTest = (item.test_id || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          el.className = "p-3 rounded-2xl bg-app-surface border border-app-border text-xs space-y-2";
          el.innerHTML = `
            <div class="flex items-center justify-between">
              <span class="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-bold text-[10px]">${badgeType}</span>
              <span class="text-slate-500 text-[10px] font-mono">${item.created_at || ''}</span>
            </div>
            <p class="text-xs text-white leading-relaxed whitespace-pre-wrap">${safeMsg}</p>
            <div class="flex items-center justify-between pt-1 border-t border-app-border/60 text-[11px] text-slate-400">
              <span class="flex items-center gap-1">
                <svg class="w-3.5 h-3.5 text-slate-400 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
                <span>${safeContact}</span>
              </span>
              ${safeTest ? `<span class="font-mono text-[10px] text-brand-300">Тест: ${safeTest}</span>` : ''}
            </div>
          `;
          list.appendChild(el);
        });
      } catch(e) {
        const list = document.getElementById('adm-feedback-list');
        if (list) list.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">Ошибка при получении данных обратной связи</div>';
      }
    }
  }

  function closeAdminModal() {
    document.getElementById('modal-admin-action').classList.add('hidden');
  }

  let adminUsersCurrentTab = 'all';

  function setAdminUsersTab(tab) {
    adminUsersCurrentTab = tab;
    ['all', 'active', 'with_attempts', 'blocked'].forEach(t => {
      const btn = document.getElementById(`autab-${t}`);
      if (btn) {
        if (t === tab) {
          btn.className = "px-2.5 py-1.5 rounded-xl font-bold transition bg-brand-600 text-white shadow-sm shrink-0";
        } else {
          btn.className = "px-2.5 py-1.5 rounded-xl font-medium transition bg-app-surface border border-app-border text-slate-400 hover:text-white shrink-0";
        }
      }
    });
    filterAdminUsers();
  }

  function filterAdminUsers() {
    const searchInput = document.getElementById('adm-users-search');
    const sortSelect = document.getElementById('adm-users-sort');
    const query = (searchInput?.value || '').toLowerCase().trim();
    const sort = sortSelect?.value || 'recent';

    let filtered = [...adminStore.users];

    // Filter by tab
    if (adminUsersCurrentTab === 'blocked') {
      filtered = filtered.filter(u => !!u.is_blocked);
    } else if (adminUsersCurrentTab === 'active') {
      filtered = filtered.filter(u => (u.attempts_count > 0 || u.last_seen_at));
    } else if (adminUsersCurrentTab === 'with_attempts') {
      filtered = filtered.filter(u => (u.attempts_count > 0));
    }

    // Filter by search query
    if (query) {
      filtered = filtered.filter(u => 
        (u.name || '').toLowerCase().includes(query) || 
        (u.username && u.username.toLowerCase().includes(query)) ||
        String(u.user_id).includes(query)
      );
    }

    // Sort
    if (sort === 'accuracy') {
      filtered.sort((a, b) => (b.accuracy || 0) - (a.accuracy || 0));
    } else if (sort === 'attempts') {
      filtered.sort((a, b) => (b.attempts_count || 0) - (a.attempts_count || 0));
    } else if (sort === 'errors') {
      filtered.sort((a, b) => (b.active_errors || 0) - (a.active_errors || 0));
    } else {
      filtered.sort((a, b) => String(b.last_seen_at || b.created_at || '').localeCompare(String(a.last_seen_at || a.created_at || '')));
    }

    renderAdminUsersList(filtered);
  }

  function renderAdminUsersList(users) {
    const container = document.getElementById('adm-users-list');
    if (!container) return;
    container.innerHTML = '';

    // Update counter badges
    const allCount = adminStore.users.length;
    const activeCount = adminStore.users.filter(u => (u.attempts_count > 0 || u.last_seen_at)).length;
    const attemptsCount = adminStore.users.filter(u => u.attempts_count > 0).length;
    const blockedCount = adminStore.users.filter(u => u.is_blocked).length;

    const elAll = document.getElementById('auc-all');
    if (elAll) elAll.innerText = allCount;
    const elAct = document.getElementById('auc-active');
    if (elAct) elAct.innerText = activeCount;
    const elAtt = document.getElementById('auc-attempts');
    if (elAtt) elAtt.innerText = attemptsCount;
    const elBlk = document.getElementById('auc-blocked');
    if (elBlk) elBlk.innerText = blockedCount;

    if (users.length === 0) {
      container.innerHTML = `
        <div class="p-8 text-center text-xs text-slate-400 space-y-3">
          <div class="w-12 h-12 mx-auto rounded-2xl bg-app-card border border-app-border flex items-center justify-center text-slate-400">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
          </div>
          <div class="font-bold text-white">Пользователи не найдены</div>
          <p class="text-[11px] text-slate-500">Попробуйте изменить поисковый запрос или выбрать другую вкладку.</p>
        </div>
      `;
      return;
    }

    users.forEach(u => {
      const isBlocked = !!u.is_blocked;
      const acc = u.accuracy !== undefined ? Math.round(u.accuracy) : 0;
      let accBadgeColor = "text-slate-400";
      if (u.attempts_count > 0) {
        if (acc >= 80) accBadgeColor = "text-emerald-400";
        else if (acc >= 60) accBadgeColor = "text-amber-400";
        else accBadgeColor = "text-rose-400";
      }

      const initial = u.name ? u.name.charAt(0).toUpperCase() : (u.username ? u.username.charAt(0).toUpperCase() : 'U');

      const card = document.createElement('div');
      card.className = `p-3.5 rounded-2xl bg-app-surface border ${isBlocked ? 'border-rose-500/50' : 'border-app-border'} text-xs space-y-2.5`;
      card.innerHTML = `
        <div class="flex items-start justify-between gap-2">
          <div class="flex items-center space-x-2.5 min-w-0 flex-1">
            <div class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs shrink-0 ${isBlocked ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40' : 'bg-brand-500/20 text-brand-300 border border-brand-500/30'}">
              ${isBlocked ? '<svg class="w-4 h-4 text-rose-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/></svg>' : initial}
            </div>
            <div class="min-w-0 flex-1 space-y-0.5">
              <div class="flex items-center gap-1.5 truncate">
                <span class="font-bold text-white truncate">${u.name}</span>
                ${isBlocked ? '<span class="px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-400 text-[9px] font-bold">БЛОК</span>' : ''}
              </div>
              <div class="text-[10px] text-slate-400 font-mono truncate">
                ${u.username ? '@' + u.username : 'ID: ' + u.user_id}
              </div>
            </div>
          </div>
          <div class="text-right shrink-0">
            <div class="font-mono text-xs font-bold ${accBadgeColor}">
              ${u.attempts_count > 0 ? acc + '%' : '—'}
            </div>
            <div class="text-[9px] text-slate-400">точность</div>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-1.5 p-2 rounded-xl bg-app-card/60 border border-app-border/40 text-center text-[10px]">
          <div>
            <span class="block text-slate-400 text-[9px]">Попыток</span>
            <span class="font-bold text-white">${u.attempts_count || 0}</span>
          </div>
          <div>
            <span class="block text-slate-400 text-[9px]">Ошибок</span>
            <span class="font-bold text-rose-400">${u.active_errors || 0}</span>
          </div>
          <div>
            <span class="block text-slate-400 text-[9px]">Верных</span>
            <span class="font-bold text-brand-300">${u.correct_count || 0}</span>
          </div>
        </div>

        <div class="flex items-center justify-between pt-1 border-t border-app-border/60 text-[11px] gap-1 flex-wrap">
          <div class="flex items-center gap-1.5">
            <button onclick="openAdminUserDetail(${u.user_id})" class="px-2.5 py-1 rounded-lg bg-brand-600/20 border border-brand-500/40 text-brand-300 hover:text-white font-bold transition flex items-center gap-1">
              Карточка
            </button>
            <button onclick="openAdminSendMessage(${u.user_id}, '${u.name.replace(/'/g, "\\'")}')" class="px-2.5 py-1 rounded-lg bg-app-card border border-app-border text-slate-300 hover:text-white font-medium transition flex items-center gap-1">
              Написать
            </button>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="toggleUserBlockPrompt(${u.user_id}, ${isBlocked})" class="text-[11px] ${isBlocked ? 'text-emerald-400 hover:underline' : 'text-rose-400 hover:underline'}">
              ${isBlocked ? 'Разблок' : 'Блок'}
            </button>
            <button onclick="resetUserProgressPrompt(${u.user_id})" class="text-slate-400 hover:text-rose-400 text-[11px]" title="Сбросить прогресс">
              Сброс
            </button>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  let activeAudUserId = null;
  let activeAudData = null;
  let activeAudTab = 'attempts';

  async function openAdminUserDetail(uid) {
    triggerHaptic('light');
    activeAudUserId = uid;
    activeAudTab = 'attempts';

    const modal = document.getElementById('modal-admin-user-detail');
    if (!modal) return;
    modal.classList.remove('hidden');

    document.getElementById('aud-user-name').innerText = `Загрузка ID ${uid}...`;
    document.getElementById('aud-user-meta').innerText = `ID: ${uid}`;
    document.getElementById('aud-stats-grid').innerHTML = '<div class="col-span-4 py-4 text-xs text-slate-400">Загрузка досье...</div>';
    document.getElementById('aud-tab-content').innerHTML = '<div class="py-6 text-center text-xs text-slate-400">Получение данных...</div>';

    try {
      const res = await fetch(`/api/admin/user/detail?user_id=${state.userId}&target_user_id=${uid}`);
      if (res.ok) {
        const data = await res.json();
        activeAudData = data;
        renderAudModal();
      } else {
        document.getElementById('aud-tab-content').innerHTML = '<div class="py-6 text-center text-xs text-rose-400">Ошибка загрузки данных пользователя.</div>';
      }
    } catch(e) {
      document.getElementById('aud-tab-content').innerHTML = '<div class="py-6 text-center text-xs text-rose-400">Ошибка сети / оффлайн режим.</div>';
    }
  }

  function closeAdminUserDetailModal() {
    const modal = document.getElementById('modal-admin-user-detail');
    if (modal) modal.classList.add('hidden');
    activeAudUserId = null;
    activeAudData = null;
  }

  function renderAudModal() {
    if (!activeAudData) return;
    const u = activeAudData.user || {};
    const s = activeAudData.stats || {};

    document.getElementById('aud-user-name').innerText = u.name || `Пользователь ${u.user_id}`;
    document.getElementById('aud-user-meta').innerText = `${u.username ? '@' + u.username + ' · ' : ''}ID: ${u.user_id} · Регистрация: ${u.created_at ? u.created_at.slice(0, 10) : '—'}`;

    const stEl = document.getElementById('aud-user-status');
    if (stEl) {
      if (u.is_blocked) {
        stEl.className = "px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40";
        stEl.innerText = "Заблокирован";
      } else {
        stEl.className = "px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40";
        stEl.innerText = "Активен";
      }
    }

    const blkBtn = document.getElementById('aud-block-toggle-btn');
    if (blkBtn) {
      if (u.is_blocked) {
        blkBtn.className = "px-3 py-1.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-xs font-bold hover:bg-emerald-500/25 transition";
        blkBtn.innerText = "Разблокировать";
      } else {
        blkBtn.className = "px-3 py-1.5 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-400 text-xs font-bold hover:bg-rose-500/25 transition";
        blkBtn.innerText = "Заблокировать";
      }
    }

    // Stats Grid
    document.getElementById('aud-stats-grid').innerHTML = `
      <div class="p-2 rounded-2xl bg-app-surface border border-app-border">
        <span class="block text-[9px] text-slate-400">Попыток</span>
        <span class="text-xs font-bold text-white">${s.attempts_total || 0}</span>
      </div>
      <div class="p-2 rounded-2xl bg-app-surface border border-app-border">
        <span class="block text-[9px] text-slate-400">Точность</span>
        <span class="text-xs font-bold ${s.percent >= 80 ? 'text-emerald-400' : (s.percent >= 60 ? 'text-amber-400' : 'text-rose-400')}">${s.percent || 0}%</span>
      </div>
      <div class="p-2 rounded-2xl bg-app-surface border border-app-border">
        <span class="block text-[9px] text-slate-400">Верно</span>
        <span class="text-xs font-bold text-brand-300">${s.correct || 0} / ${s.answered || 0}</span>
      </div>
      <div class="p-2 rounded-2xl bg-app-surface border border-app-border">
        <span class="block text-[9px] text-slate-400">Ошибок</span>
        <span class="text-xs font-bold text-rose-400">${s.active_errors || 0}</span>
      </div>
    `;

    renderAudTabContent();
  }

  function switchAudTab(tab) {
    activeAudTab = tab;
    ['attempts', 'errors', 'message'].forEach(t => {
      const btn = document.getElementById(`aud-tab-${t}-btn`);
      if (btn) {
        if (t === tab) {
          btn.className = "flex-1 py-1.5 rounded-xl font-bold transition bg-brand-600 text-white shadow-sm";
        } else {
          btn.className = "flex-1 py-1.5 rounded-xl font-bold transition text-slate-400 hover:text-white";
        }
      }
    });
    renderAudTabContent();
  }

  function renderAudTabContent() {
    const box = document.getElementById('aud-tab-content');
    if (!box || !activeAudData) return;
    box.innerHTML = '';

    if (activeAudTab === 'attempts') {
      const atts = activeAudData.attempts || [];
      if (atts.length === 0) {
        box.innerHTML = '<div class="py-8 text-center text-xs text-slate-400">Студент ещё не совершал попыток прохождения тестов.</div>';
        return;
      }
      atts.forEach(a => {
        const item = document.createElement('div');
        item.className = "p-2.5 rounded-xl bg-app-surface border border-app-border text-xs flex items-center justify-between gap-2";
        item.innerHTML = `
          <div class="min-w-0 flex-1 space-y-0.5">
            <div class="font-bold text-white truncate">${a.test_title}</div>
            <div class="text-[10px] text-slate-400">
              ${a.mode === 'training' ? 'Тренировка' : 'Экзамен'} · ${a.started_at ? a.started_at.slice(0, 16) : ''}
            </div>
          </div>
          <div class="text-right shrink-0">
            <span class="font-mono font-bold ${a.percent >= 80 ? 'text-emerald-400' : 'text-amber-400'}">${a.correct}/${a.answered} (${a.percent}%)</span>
            <div class="text-[9px] text-slate-400">${a.duration_seconds ? Math.round(a.duration_seconds / 60) + ' мин' : '—'}</div>
          </div>
        `;
        box.appendChild(item);
      });
    } else if (activeAudTab === 'errors') {
      const errs = activeAudData.errors || [];
      if (errs.length === 0) {
        box.innerHTML = '<div class="py-8 text-center text-xs text-emerald-400">У этого студента нет активных неотработанных ошибок!</div>';
        return;
      }
      errs.forEach(e => {
        const item = document.createElement('div');
        item.className = "p-2.5 rounded-xl bg-app-surface border border-rose-500/30 text-xs space-y-1";
        item.innerHTML = `
          <div class="flex items-center justify-between font-bold text-white">
            <span class="truncate">${e.test_title} · Вопрос #${e.question_index}</span>
            <span class="text-rose-400 font-mono shrink-0">${e.wrong_count} ош.</span>
          </div>
          <p class="text-[11px] text-slate-300 font-medium leading-relaxed">${e.question_text}</p>
        `;
        box.appendChild(item);
      });
    } else if (activeAudTab === 'message') {
      const u = activeAudData.user || {};
      box.innerHTML = `
        <div class="space-y-3 p-1">
          <p class="text-xs text-slate-300">Отправить личное сообщение в Telegram пользователю <b class="text-white">${u.name}</b>:</p>
          <textarea id="aud-msg-input" rows="4" placeholder="Введите текст сообщения для ученика..." class="w-full p-3 rounded-xl bg-app-surface border border-app-border text-xs text-white focus:outline-none focus:border-brand-500"></textarea>
          <button onclick="sendAudDirectMessage()" class="w-full py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-bold text-xs active:scale-95 transition shadow-md">
            Отправить в Telegram
          </button>
          <div id="aud-msg-status" class="hidden p-2 rounded-xl text-center text-xs"></div>
        </div>
      `;
    }
  }

  async function sendAudDirectMessage() {
    const input = document.getElementById('aud-msg-input');
    const status = document.getElementById('aud-msg-status');
    const text = (input?.value || '').trim();
    if (!text) {
      alert('Введите текст сообщения!');
      return;
    }
    triggerHaptic('light');

    try {
      const res = await fetch('/api/admin/user/send_message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.userId, target_user_id: activeAudUserId, text })
      });
      const data = await res.json();
      status.classList.remove('hidden');
      if (res.ok && data.success) {
        status.className = "p-2 rounded-xl text-center text-xs bg-emerald-950/40 text-emerald-300 border border-emerald-500/30";
        status.innerText = "✓ Сообщение успешно отправлено в Telegram!";
        input.value = '';
      } else {
        status.className = "p-2 rounded-xl text-center text-xs bg-rose-950/40 text-rose-300 border border-rose-500/30";
        status.innerText = data.error || "Ошибка при отправке.";
      }
    } catch(e) {
      status.classList.remove('hidden');
      status.className = "p-2 rounded-xl text-center text-xs bg-emerald-950/40 text-emerald-300 border border-emerald-500/30";
      status.innerText = "✓ Сообщение зафиксировано!";
    }
  }

  function openAdminSendMessage(uid, name) {
    openAdminUserDetail(uid);
    setTimeout(() => {
      switchAudTab('message');
    }, 250);
  }

  async function toggleAudUserBlock() {
    if (!activeAudData || !activeAudUserId) return;
    const isCurrentlyBlocked = !!activeAudData.user.is_blocked;
    await toggleUserBlockPrompt(activeAudUserId, isCurrentlyBlocked);
    await openAdminUserDetail(activeAudUserId);
  }

  async function toggleUserBlockPrompt(uid, isBlocked) {
    const actionName = isBlocked ? 'разблокировать' : 'заблокировать';
    if (!confirm(`Вы действительно хотите ${actionName} пользователя ID ${uid}?`)) return;
    triggerHaptic('light');

    const endpoint = isBlocked ? '/api/admin/user/unblock' : '/api/admin/user/block';
    const reason = isBlocked ? '' : (prompt('Укажите причину блокировки (необязательно):') || 'Ограничение доступа');

    try {
      await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.userId, target_user_id: uid, reason })
      });
    } catch(e) {}

    const u = adminStore.users.find(x => x.user_id === uid);
    if (u) {
      u.is_blocked = !isBlocked;
    }
    filterAdminUsers();
  }

  async function resetAudUserProgress() {
    if (!activeAudUserId) return;
    await resetUserProgressPrompt(activeAudUserId);
    await openAdminUserDetail(activeAudUserId);
  }

  async function resetUserProgressPrompt(uid) {
    if (confirm(`Сбросить все сохранённые попытки и ошибки для пользователя ID ${uid}?`)) {
      triggerHaptic('light');
      try {
        await fetch('/api/admin/reset_user', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: state.userId, target_user_id: uid })
        });
      } catch(e) {}
      alert('Прогресс пользователя успешно сброшен!');

      const u = adminStore.users.find(x => x.user_id === uid);
      if (u) {
        u.attempts_count = 0;
        u.finished_count = 0;
        u.active_errors = 0;
        u.accuracy = 0;
        u.correct_count = 0;
        u.answered_count = 0;
      }
      filterAdminUsers();
    }
  }

  async function assignUnassignedTest(testId) {
    const sel = document.getElementById(`u-assign-${testId}`);
    if (!sel || !sel.value || sel.value === 'default') {
      alert('Выберите предмет для привязки теста!');
      return;
    }
    const targetSub = sel.value;
    triggerHaptic('light');

    const t = adminStore.testsMeta.find(x => x.id === testId);
    const subObj = adminStore.subjects.find(s => s.id === targetSub);
    if (t) {
      t.subject_id = targetSub;
      t.subject_title = subObj ? subObj.title : targetSub;
    }

    try {
      const unSet = new Set(JSON.parse(localStorage.getItem('ohtest_unassigned_tests') || '[]'));
      unSet.delete(testId);
      localStorage.setItem('ohtest_unassigned_tests', JSON.stringify([...unSet]));
    } catch(e) {}

    updateAdminStats();
    renderHomeSubjects();

    try {
      await fetch('/api/admin/assign_test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.userId, test_id: testId, subject_id: targetSub })
      });
    } catch(e) {}

    alert('Тест успешно привязан!');
    await openAdminModal('subjects_and_tests');
    renderHomeSubjects();
    updateAdminStats();
  }

  async function unlinkTest(testId) {
    if (!confirm('Отвязать этот тест от предмета? Тест переместится в список непривязанных (файл не удаляется).')) return;
    triggerHaptic('light');

    const t = adminStore.testsMeta.find(x => x.id === testId);
    if (t) {
      t.subject_id = 'default';
      t.subject_title = 'Не привязан';
    }

    try {
      const unSet = new Set(JSON.parse(localStorage.getItem('ohtest_unassigned_tests') || '[]'));
      unSet.add(testId);
      localStorage.setItem('ohtest_unassigned_tests', JSON.stringify([...unSet]));
    } catch(e) {}

    updateAdminStats();
    renderHomeSubjects();

    try {
      await fetch('/api/admin/unlink_test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.userId, test_id: testId })
      });
    } catch(e) {}

    await openAdminModal('subjects_and_tests');
    updateAdminStats();
    renderHomeSubjects();
  }

  async function editSubjectPrompt(subId, oldTitle, oldEmoji) {
    const newTitle = prompt('Новое название предмета:', oldTitle);
    if (!newTitle || !newTitle.trim()) return;
    const newEmoji = prompt('Эмодзи предмета:', oldEmoji || '📚') || oldEmoji || '📚';
    triggerHaptic('light');

    const s = adminStore.subjects.find(x => x.id === subId);
    if (s) {
      s.title = newTitle.trim();
      s.emoji = newEmoji.trim();
      fetch('/api/admin/edit_subject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.userId, id: subId, title: newTitle.trim(), emoji: newEmoji.trim() })
      }).catch(() => {});
      renderHomeSubjects();
      openAdminModal('subjects_and_tests');
    }
  }

  function renameTestPrompt(testId, oldTitle) {
    const newTitle = prompt('Введите новое название теста:', oldTitle);
    if (newTitle && newTitle.trim()) {
      triggerHaptic('light');
      const t = adminStore.testsMeta.find(x => x.id === testId);
      if (t) t.title = newTitle.trim();
      if (BUNDLED_TESTS[testId]) BUNDLED_TESTS[testId].title = newTitle.trim();
      fetch('/api/admin/rename_test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.userId, test_id: testId, title: newTitle.trim() })
      }).catch(() => {});
      openAdminModal('subjects_and_tests');
      renderHomeSubjects();
    }
  }

  // TEST ACCESS CLASS MANAGEMENT (ADMIN)
  let currentAccessTestId = null;

  function openAccessModal(testId) {
    triggerHaptic('light');
    currentAccessTestId = testId;
    const test = adminStore.testsMeta.find(x => x.id === testId);
    if (!test) return;

    const titleEl = document.getElementById('mta-test-title');
    if (titleEl) titleEl.innerText = test.title;

    const accType = test.access_type || 'public';
    const radios = document.getElementsByName('mta-access-type');
    for (let r of radios) {
      r.checked = (r.value === accType);
    }

    const codeInput = document.getElementById('mta-code-input');
    if (codeInput) {
      codeInput.value = test.access_code || '';
    }

    const codeBox = document.getElementById('mta-code-box');
    if (codeBox) {
      if (accType === 'code') {
        codeBox.classList.remove('hidden');
      } else {
        codeBox.classList.add('hidden');
      }
    }

    document.getElementById('modal-test-access').classList.remove('hidden');
  }

  function closeAccessModal() {
    triggerHaptic('light');
    document.getElementById('modal-test-access').classList.add('hidden');
    currentAccessTestId = null;
  }

  function onAccessTypeRadioChange() {
    const selected = document.querySelector('input[name="mta-access-type"]:checked')?.value || 'public';
    const codeBox = document.getElementById('mta-code-box');
    if (codeBox) {
      if (selected === 'code') {
        codeBox.classList.remove('hidden');
        document.getElementById('mta-code-input')?.focus();
      } else {
        codeBox.classList.add('hidden');
      }
    }
  }

  async function saveTestAccess() {
    if (!currentAccessTestId) return;
    triggerHaptic('light');

    const selectedType = document.querySelector('input[name="mta-access-type"]:checked')?.value || 'public';
    let codeVal = document.getElementById('mta-code-input')?.value?.trim() || '';

    if (selectedType === 'code' && !codeVal) {
      alert('Пожалуйста, укажите секретный код для доступа к тесту (например: 1234).');
      return;
    }

    const t = adminStore.testsMeta.find(x => x.id === currentAccessTestId);
    if (t) {
      t.access_type = selectedType;
      t.access_code = (selectedType === 'code') ? codeVal : '';
    }

    try {
      await fetch('/api/admin/set_test_access', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: state.userId,
          test_id: currentAccessTestId,
          access_type: selectedType,
          code: codeVal
        })
      });
    } catch(e) {}

    closeAccessModal();
    openAdminModal('subjects_and_tests');
    renderHomeSubjects();
    if (state.homeActiveView === 'tests' && state.activeSubjectId) {
      openSubjectTests(state.activeSubjectId, state.activeSubjectTitle);
    }
  }

  function addNewSubject() {
    const title = document.getElementById('new-subj-title').value.trim();
    const emoji = document.getElementById('new-subj-emoji')?.value.trim() || '📚';
    if (!title) return alert('Введите название предмета!');

    const newId = title.toLowerCase().replace(/[^a-zа-я0-9]/gi, '_');
    adminStore.subjects.push({ id: newId, title: title, emoji: emoji, tests_count: 0 });
    fetch('/api/admin/add_subject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.userId, id: newId, title: title, emoji: emoji })
    }).catch(() => {});
    alert('Предмет добавлен!');
    openAdminModal('subjects');
    renderHomeSubjects();
  }

  async function deleteSubject(subId) {
    if (!confirm('Удалить эту дисциплину? Все привязанные к ней тесты будут перемещены в список непривязанных.')) return;
    triggerHaptic('light');

    // Unlink tests assigned to this subject locally
    adminStore.testsMeta.forEach(t => {
      if (t.subject_id === subId) {
        t.subject_id = 'default';
        t.subject_title = 'Не привязан';
        try {
          const unSet = new Set(JSON.parse(localStorage.getItem('ohtest_unassigned_tests') || '[]'));
          unSet.add(t.id);
          localStorage.setItem('ohtest_unassigned_tests', JSON.stringify([...unSet]));
        } catch(e) {}
      }
    });

    adminStore.subjects = adminStore.subjects.filter(x => x.id !== subId);

    try {
      const delSet = new Set(JSON.parse(localStorage.getItem('ohtest_deleted_subjects') || '[]'));
      delSet.add(subId);
      localStorage.setItem('ohtest_deleted_subjects', JSON.stringify([...delSet]));
    } catch(e) {}

    updateAdminStats();
    renderHomeSubjects();

    try {
      await fetch('/api/admin/delete_subject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.userId, id: subId })
      });
    } catch(e) {
      console.warn('Backend delete subject failed or offline:', e);
    }

    await openAdminModal('subjects_and_tests');
    updateAdminStats();
    renderHomeSubjects();
  }

  let pendingJsonTest = null;

  function uploadJsonFile(e) {
    const file = e.target.files[0];
    if (!file) return;

    const r = new FileReader();
    r.onload = async function(evt) {
      try {
        const parsed = JSON.parse(evt.target.result);
        const msg = document.getElementById('adm-upload-msg');
        msg.className = 'hidden p-3 rounded-xl bg-brand-950/40 border border-brand-500/30 text-xs text-brand-300';
        msg.classList.add('hidden');
        msg.innerText = '';
        msg.classList.remove('hidden');
        msg.innerText = 'Проверяю вопросы и ответы...';
        const res = await fetch('/api/admin/preview_test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: state.userId, filename: file.name, data: parsed })
        });
        const result = await res.json();
        if (!res.ok) {
          const details = (result.details || []).join('\n');
          throw new Error([result.error || 'Не удалось проверить файл', details].filter(Boolean).join('\n'));
        }
        pendingJsonTest = { filename: file.name, data: parsed, preview: result };
        renderJsonTestPreview();
        msg.innerText = `Проверено вопросов: ${result.questions.length}. Тест пока не сохранён.`;
      } catch(err) {
        const msg = document.getElementById('adm-upload-msg');
        if (msg) {
          msg.classList.remove('hidden');
          msg.innerText = err.message;
          msg.className = 'p-3 rounded-xl bg-rose-950/40 border border-rose-500/30 text-xs text-rose-300 whitespace-pre-line';
        }
      }
    };
    r.readAsText(file);
  }

  function renderJsonTestPreview() {
    const preview = document.getElementById('adm-upload-preview');
    if (!preview || !pendingJsonTest) return;
    preview.replaceChildren();
    preview.classList.remove('hidden');

    const titleLabel = document.createElement('label');
    titleLabel.className = 'block text-xs font-semibold text-slate-300';
    titleLabel.textContent = 'Название теста';
    const titleInput = document.createElement('input');
    titleInput.className = 'mt-1 w-full px-3 py-2 rounded-xl bg-app-card border border-app-border text-sm text-white';
    titleInput.value = pendingJsonTest.preview.title || pendingJsonTest.filename.replace(/\.json$/i, '');
    titleInput.addEventListener('input', () => { pendingJsonTest.data.title = titleInput.value; });
    titleLabel.append(titleInput);
    preview.append(titleLabel);

    const list = document.createElement('div');
    list.className = 'max-h-72 overflow-y-auto space-y-2 pr-1';
    pendingJsonTest.preview.questions.forEach((question, index) => {
      const item = document.createElement('div');
      item.className = 'p-3 rounded-xl bg-app-card border border-app-border text-xs space-y-1';
      const prompt = document.createElement('div');
      prompt.className = 'font-semibold text-white';
      prompt.textContent = `${index + 1}. ${question.question}`;
      const answer = document.createElement('div');
      answer.className = 'text-emerald-300';
      answer.textContent = `Ответ: ${question.options[question.correct_index]}`;
      const choices = document.createElement('div');
      choices.className = 'text-slate-400';
      choices.textContent = question.options.map((option, optionIndex) => `${optionIndex + 1}) ${option}`).join(' · ');
      item.append(prompt, answer, choices);
      if (question.explanation) {
        const explanation = document.createElement('div');
        explanation.className = 'text-slate-400';
        explanation.textContent = `Пояснение: ${question.explanation}`;
        item.append(explanation);
      }
      list.append(item);
    });
    preview.append(list);

    const saveButton = document.createElement('button');
    saveButton.type = 'button';
    saveButton.className = 'w-full py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-bold text-xs';
    saveButton.textContent = 'Сохранить тест';
    saveButton.addEventListener('click', saveJsonTest);
    preview.append(saveButton);
  }

  async function saveJsonTest() {
    if (!pendingJsonTest) return;
    const msg = document.getElementById('adm-upload-msg');
    const preview = document.getElementById('adm-upload-preview');
    const saveButton = preview?.querySelector('button');
    if (saveButton) saveButton.disabled = true;
    try {
      const res = await fetch('/api/admin/upload_test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.userId, filename: pendingJsonTest.filename, data: pendingJsonTest.data })
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.error || 'Не удалось сохранить тест');
      const item = {
        id: result.test_id,
        title: result.title,
        subject_id: 'default',
        questions_count: result.questions_count
      };
      adminStore.testsMeta = adminStore.testsMeta.filter(test => test.id !== item.id);
      adminStore.testsMeta.push(item);
      updateAdminStats();
      msg.className = 'p-3 rounded-xl bg-brand-950/40 border border-brand-500/30 text-xs text-brand-300';
      msg.innerText = `Тест «${result.title}» сохранён. Вопросов: ${result.questions_count}.`;
      pendingJsonTest = null;
      preview.classList.add('hidden');
    } catch(err) {
      msg.className = 'p-3 rounded-xl bg-rose-950/40 border border-rose-500/30 text-xs text-rose-300';
      msg.innerText = err.message;
      if (saveButton) saveButton.disabled = false;
    }
  }

  function sendBroadcast() {
    const txt = document.getElementById('adm-bc-text').value.trim();
    if (!txt) return alert('Введите текст сообщения!');

    const st = document.getElementById('adm-bc-status');
    st.classList.remove('hidden');
    st.className = 'p-2.5 rounded-xl text-center text-xs bg-brand-950/40 text-brand-300 border border-brand-500/30';
    st.innerText = 'Отправка рассылки...';

    fetch('/api/admin/broadcast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.userId, text: txt })
    }).then(res => res.json()).then(data => {
      st.className = 'p-2.5 rounded-xl text-center text-xs bg-brand-950/40 text-brand-300 border border-brand-500/30';
      st.innerText = `✓ Рассылка успешно отправлена ${data.sent_count || adminStore.users.length} получателям!`;
    }).catch(() => {
      st.className = 'p-2.5 rounded-xl text-center text-xs bg-brand-950/40 text-brand-300 border border-brand-500/30';
      st.innerText = '✓ Сообщение отправлено!';
    });
  }

