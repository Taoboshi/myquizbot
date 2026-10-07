// PROFILE & LEADERBOARD COMPREHENSIVE SUITE
  // ==========================================
  state.activeProfileSubTab = 'favs';
  state.ratingActiveSubject = 'all';
  state.ratingActiveTest = 'all';

  function updateProfileFullView() {
    let totalAttempts = state.historyAttempts.length;
    let totalCorrect = 0;
    let totalAnswered = 0;
    state.historyAttempts.forEach(h => {
      totalCorrect += (h.correct || 0);
      totalAnswered += (h.total || 0);
    });
    let avgAcc = totalAnswered > 0 ? Math.round((totalCorrect / totalAnswered) * 100) : 0;
    let userXp = totalCorrect * 10;

    const LEVELS = [
      { level: 1, title: 'Новичок', minXp: 0, nextXp: 100, badgeClass: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
      { level: 2, title: 'Студент', minXp: 100, nextXp: 300, badgeClass: 'bg-blue-500/15 text-blue-300 border-blue-500/30' },
      { level: 3, title: 'Стажёр', minXp: 300, nextXp: 600, badgeClass: 'bg-teal-500/15 text-teal-300 border-teal-500/30' },
      { level: 4, title: 'Интерн', minXp: 600, nextXp: 1000, badgeClass: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30' },
      { level: 5, title: 'Практик', minXp: 1000, nextXp: 1600, badgeClass: 'bg-sky-500/15 text-sky-300 border-sky-500/30' },
      { level: 6, title: 'Ординатор', minXp: 1600, nextXp: 2500, badgeClass: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30' },
      { level: 7, title: 'Врач-специалист', minXp: 2500, nextXp: 3800, badgeClass: 'bg-purple-500/15 text-purple-300 border-purple-500/30' },
      { level: 8, title: 'Старший ординатор', minXp: 3800, nextXp: 5500, badgeClass: 'bg-violet-500/15 text-violet-300 border-violet-500/30' },
      { level: 9, title: 'Заведующий отделением', minXp: 5500, nextXp: 8000, badgeClass: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
      { level: 10, title: 'Профессор медицины', minXp: 8000, nextXp: null, badgeClass: 'bg-rose-500/20 text-rose-300 border-rose-500/40' }
    ];

    let currentLvl = LEVELS[0];
    for (let i = LEVELS.length - 1; i >= 0; i--) {
      if (userXp >= LEVELS[i].minXp) {
        currentLvl = LEVELS[i];
        break;
      }
    }

    let xpProgressPct = 100;
    let nextRankText = "Макс. ранг достигнут!";
    let levelTitle = `Уровень ${currentLvl.level} • ${userXp} XP`;

    if (currentLvl.nextXp !== null) {
      const neededForNext = currentLvl.nextXp - userXp;
      const levelSpan = currentLvl.nextXp - currentLvl.minXp;
      const currentSpanXp = userXp - currentLvl.minXp;
      xpProgressPct = Math.min(100, Math.max(5, Math.round((currentSpanXp / levelSpan) * 100)));
      nextRankText = `До след. ранга: ${neededForNext} XP`;
      levelTitle = `Уровень ${currentLvl.level} • ${userXp} / ${currentLvl.nextXp} XP`;
    }

    document.getElementById('profile-name').innerText = state.userName || 'Студент';
    document.getElementById('profile-username').innerText = state.userUsername || 'Telegram User';
    document.getElementById('profile-id').innerText = state.userId ? `ID: ${state.userId}` : 'Локальный режим';
    renderProfileAvatarElement(document.getElementById('profile-avatar'), state.userAvatar, state.userName);
    document.getElementById('profile-xp-text').innerText = `${userXp} XP`;
    document.getElementById('profile-level-title').innerText = levelTitle;
    document.getElementById('profile-next-rank-text').innerText = nextRankText;
    document.getElementById('profile-xp-bar').style.width = `${xpProgressPct}%`;

    const rankBadgeEl = document.getElementById('profile-rank-badge');
    if (rankBadgeEl) {
      rankBadgeEl.innerHTML = `<span class="opacity-75 font-mono mr-1">Ур.${currentLvl.level}</span> ${currentLvl.title}`;
      rankBadgeEl.className = `px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${currentLvl.badgeClass}`;
    }

    document.getElementById('profile-attempts-count').innerText = totalAttempts;
    document.getElementById('profile-acc-rate').innerText = `${avgAcc}%`;

    const allErrors = getAllSavedErrors();
    const allFavs = getAllSavedFavorites();
    updateProfileErrorBadge(allErrors.length);
    const profFavEl = document.getElementById('profile-fav-count');
    if (profFavEl) {
      profFavEl.innerText = allFavs.length;
      profFavEl.className = `text-xs font-bold font-mono ${allFavs.length > 0 ? 'text-amber-400' : 'text-slate-300'}`;
    }

    renderDisciplineMastery();
    switchProfileTab(state.activeProfileSubTab || 'favs');
  }

  function renderDisciplineMastery() {
    const container = document.getElementById('profile-disciplines-list');
    if (!container) return;
    container.innerHTML = '';

    // Collect subjects dynamically: from adminStore.subjects, or derived from adminStore.testsMeta
    let subjects = (adminStore.subjects && adminStore.subjects.length > 0) ? [...adminStore.subjects] : [];
    if (subjects.length === 0 && adminStore.testsMeta && adminStore.testsMeta.length > 0) {
      const seen = new Set();
      adminStore.testsMeta.forEach(t => {
        const sId = t.subject_id || 'default';
        if (!seen.has(sId)) {
          seen.add(sId);
          subjects.push({
            id: sId,
            title: t.subject_title || (sId === 'default' ? 'Общие тесты' : sId)
          });
        }
      });
    }

    // Update total tests count badge in profile disciplines header
    const totalTestsBadge = document.getElementById('profile-total-tests-label');
    if (totalTestsBadge) {
      const allTestsCount = (adminStore.testsMeta && adminStore.testsMeta.length > 0) 
        ? adminStore.testsMeta.length 
        : Object.keys(BUNDLED_TESTS || {}).length;
      totalTestsBadge.innerText = `${allTestsCount} ${allTestsCount === 1 ? 'тест' : (allTestsCount < 5 ? 'теста' : 'тестов')}`;
    }

    if (subjects.length === 0) {
      container.innerHTML = `
        <div class="p-4 rounded-2xl bg-app-surface border border-app-border text-center text-xs text-slate-400">
          Список дисциплин пуст
        </div>
      `;
      return;
    }

    subjects.forEach(sub => {
      // Dynamically find tests assigned to this subject
      const subjectTests = (adminStore.testsMeta || []).filter(t => t.subject_id === sub.id);
      const subjectTestIds = new Set(subjectTests.map(t => t.id));

      const subjectAttempts = state.historyAttempts.filter(h => {
        if (h.subjectId && h.subjectId === sub.id) return true;
        if (h.testId && subjectTestIds.has(h.testId)) return true;
        return false;
      });

      const doneTestsCount = new Set(subjectAttempts.map(h => h.testId)).size;
      const totalTestsCount = subjectTests.length || sub.tests_count || 0;
      const progressPct = totalTestsCount > 0 ? Math.min(100, Math.round((doneTestsCount / totalTestsCount) * 100)) : 0;

      let correctInSub = 0;
      let answeredInSub = 0;
      subjectAttempts.forEach(h => {
        correctInSub += (h.correct || 0);
        answeredInSub += (h.total || 0);
      });
      const subAcc = answeredInSub > 0 ? Math.round((correctInSub / answeredInSub) * 100) : 0;

      const item = document.createElement('div');
      item.className = "p-3 rounded-2xl bg-app-surface border border-app-border/70 space-y-2 cursor-pointer hover:border-brand-500/40 transition active:scale-[0.99]";
      item.onclick = () => openDisciplineStatsModal(sub.id);

      item.innerHTML = `
        <div class="flex items-center justify-between text-xs">
          <div class="flex items-center space-x-2">
            <span class="p-1 rounded-lg bg-brand-500/10 text-brand-400">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
            </span>
            <span class="font-bold text-white">${escapeHtml(sub.title || 'Дисциплина')}</span>
          </div>
          <span class="text-[11px] font-mono font-semibold text-brand-300">${totalTestsCount > 0 ? `${doneTestsCount}/${totalTestsCount} тестов` : 'Нет тестов'}</span>
        </div>
        <div class="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
          <div class="h-1.5 rounded-full bg-gradient-to-r from-brand-500 to-brand-300" style="width: ${progressPct > 0 ? Math.max(5, progressPct) : 0}%;"></div>
        </div>
        <div class="flex justify-between items-center text-[10px] text-slate-400 font-mono">
          <span>Освоено: ${progressPct}%</span>
          <span class="text-brand-400 font-semibold">${subjectAttempts.length > 0 ? `Точность: ${subAcc}%` : 'Тест не начат'}</span>
        </div>
      `;
      container.appendChild(item);
    });
  }

  function openDisciplineStatsModal(subjectId) {
    triggerHaptic('light');
    const modal = document.getElementById('modal-discipline-stats');
    const titleEl = document.getElementById('disc-modal-title');
    const bodyEl = document.getElementById('disc-modal-body');

    const subj = (adminStore.subjects || []).find(s => s.id === subjectId) || { title: 'Дисциплина' };
    if (titleEl) {
      titleEl.innerText = subj.title || 'Дисциплина';
    }

    const tests = (adminStore.testsMeta || []).filter(t => t.subject_id === subjectId);
    if (tests.length === 0) {
      bodyEl.innerHTML = '<div class="p-6 text-center text-xs text-slate-400">В этом разделе пока нет тестов.</div>';
    } else {
      let cardsHtml = tests.map(t => {
        const testAttempts = state.historyAttempts.filter(h => h.testId === t.id);
        const attemptsCount = testAttempts.length;
        let bestPct = 0;
        testAttempts.forEach(h => {
          const p = h.pct || 0;
          if (p > bestPct) bestPct = p;
        });

        const testErrors = JSON.parse(localStorage.getItem(`ohtest_errors_${t.id}`) || '[]');

        return `
          <div class="p-3.5 rounded-2xl bg-app-surface border border-app-border space-y-2">
            <div class="flex items-center justify-between">
              <h4 class="text-xs font-bold text-white">${escapeHtml(t.title || t.id)}</h4>
              <span class="text-[10px] font-mono font-bold text-brand-300">${t.questions_count || 0} вопр.</span>
            </div>
            <div class="grid grid-cols-3 gap-1.5 pt-1 text-center text-[10px]">
              <div class="p-1.5 rounded-xl bg-app-card border border-app-border/40">
                <span class="block text-slate-400">Попыток</span>
                <span class="font-bold text-white font-mono">${attemptsCount}</span>
              </div>
              <div class="p-1.5 rounded-xl bg-app-card border border-app-border/40">
                <span class="block text-slate-400">Рекорд</span>
                <span class="font-bold ${bestPct >= 80 ? 'text-brand-400' : 'text-amber-400'} font-mono">${attemptsCount > 0 ? `${bestPct}%` : '—'}</span>
              </div>
              <div class="p-1.5 rounded-xl bg-app-card border border-app-border/40">
                <span class="block text-slate-400">Ошибок</span>
                <span class="font-bold text-rose-400 font-mono">${testErrors.length}</span>
              </div>
            </div>
          </div>
        `;
      }).join('');

      bodyEl.innerHTML = `
        <div class="space-y-2">
          <div class="text-[11px] text-slate-400 px-1">Статистика освоения по тестам:</div>
          ${cardsHtml}
        </div>
      `;
    }

    modal.classList.remove('hidden');
  }

  function closeDisciplineStatsModal() {
    document.getElementById('modal-discipline-stats').classList.add('hidden');
  }

  function switchProfileTab(subtab) {
    triggerHaptic('light');
    state.activeProfileSubTab = subtab;
    ['favs', 'errors', 'history', 'rating'].forEach(t => {
      const btn = document.getElementById('ptab-btn-' + t);
      if (!btn) return;
      if (t === subtab) {
        btn.className = "py-2.5 px-1 rounded-xl bg-brand-600 text-white font-bold text-xs transition shadow-sm flex items-center justify-center gap-1.5 truncate";
      } else {
        btn.className = "py-2.5 px-1 rounded-xl text-slate-400 hover:text-white font-semibold text-xs transition flex items-center justify-center gap-1.5 truncate";
      }
    });
    renderProfileSubtab(subtab);
  }

  function renderProfileSubtab(subtab) {
    const box = document.getElementById('profile-subtab-content');
    if (!box) return;
    box.innerHTML = '';

    if (subtab === 'rating') {
      renderRatingSubtab();
    } else if (subtab === 'errors') {
      renderErrorsSubtab();
    } else if (subtab === 'favs') {
      renderFavsSubtab();
    } else if (subtab === 'history') {
      renderHistorySubtab();
    }
  }

  function renderRatingSubtab() {
    const box = document.getElementById('profile-subtab-content');
    const subjects = [
      { id: 'all', title: 'Все дисциплины' },
      ...(adminStore.subjects || [
        { id: 'luchevaya_diagnostika', title: 'Основы лучевой диагностики' },
        { id: 'oziz', title: 'ОЗ и Здравоохранение' }
      ])
    ];

    const currentSub = state.ratingActiveSubject || 'all';

    let pillsHtml = subjects.map(s => {
      const active = (s.id === currentSub);
      return `<button onclick="onSelectRatingSubject('${s.id}')" class="px-2.5 py-1.5 rounded-xl text-[11px] font-semibold transition active:scale-95 ${active ? 'bg-brand-600 text-white shadow-sm font-bold' : 'bg-app-surface text-slate-400 hover:text-white border border-app-border'}">${s.title}</button>`;
    }).join('');

    let testsInSub = [];
    if (currentSub === 'all') {
      testsInSub = adminStore.testsMeta || [];
    } else {
      testsInSub = (adminStore.testsMeta || []).filter(t => t.subject_id === currentSub);
    }

    let testsOptionsHtml = `<option value="all">Все тесты (${testsInSub.length})</option>`;
    testsInSub.forEach(t => {
      const sel = (state.ratingActiveTest === t.id) ? 'selected' : '';
      testsOptionsHtml += `<option value="${t.id}" ${sel}>${t.title}</option>`;
    });

    box.innerHTML = `
      <div class="p-4 rounded-3xl bg-app-card border border-brand-500/30 space-y-3 shadow-lg">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-bold text-white flex items-center gap-1.5">
              <svg class="w-4 h-4 text-amber-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"/></svg>
              <span>Таблица лидеров</span>
            </h3>
            <p class="text-[11px] text-slate-400">Рейтинг успеваемости по тестам</p>
          </div>
        </div>

        <div class="flex flex-wrap gap-1.5 pt-1">
          ${pillsHtml}
        </div>

        <div class="pt-1">
          <select id="rating-test-selector" onchange="onSelectRatingTest(this.value)" class="w-full bg-app-surface text-slate-200 border border-app-border rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-brand-500">
            ${testsOptionsHtml}
          </select>
        </div>
      </div>

      <div id="profile-rating-items" class="space-y-2">
        <div class="p-6 text-center text-xs text-slate-400">Загрузка данных рейтинга...</div>
      </div>
    `;

    loadProfileRating(state.ratingActiveSubject || 'all', state.ratingActiveTest || 'all');
  }

  function onSelectRatingSubject(subId) {
    triggerHaptic('light');
    state.ratingActiveSubject = subId;
    state.ratingActiveTest = 'all';
    renderRatingSubtab();
  }

  function onSelectRatingTest(testId) {
    triggerHaptic('light');
    state.ratingActiveTest = testId;
    loadProfileRating(state.ratingActiveSubject || 'all', testId);
  }

  async function loadProfileRating(subjectId, testId) {
    const container = document.getElementById('profile-rating-items');
    if (!container) return;
    container.innerHTML = '<div class="p-6 text-center text-xs text-slate-400">Загрузка данных...</div>';

    let items = [];
    try {
      let url = '/api/rating?';
      if (subjectId && subjectId !== 'all') url += `subject_id=${encodeURIComponent(subjectId)}&`;
      if (testId && testId !== 'all') url += `test_id=${encodeURIComponent(testId)}&`;

      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        items = data.items || [];
      }
    } catch(e) {}

    renderProfileRatingItems(items, subjectId, testId);
  }

  function renderProfileRatingItems(items, subjectId, testId) {
    const container = document.getElementById('profile-rating-items');
    if (!container) return;
    container.innerHTML = '';

    if (items.length === 0) {
      let myLocalAttempts = state.historyAttempts.filter(h => {
        if (subjectId === 'all' && testId === 'all') return true;
        if (testId !== 'all' && h.testId === testId) return true;
        if (subjectId !== 'all' && (h.subjectId === subjectId || (h.testId && h.testId.startsWith(subjectId)))) return true;
        return false;
      });

      let localScore = 0;
      let localTotal = 0;
      myLocalAttempts.forEach(h => {
        localScore += (h.correct || 0);
        localTotal += (h.total || 0);
      });
      let localPct = localTotal > 0 ? Math.round((localScore / localTotal) * 100) : 0;

      container.innerHTML = `
        <div class="p-6 text-center rounded-3xl bg-app-card border border-app-border space-y-3">
          <div class="w-12 h-12 mx-auto rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"/></svg>
          </div>
          <div class="text-xs font-bold text-white">В этом разделе пока нет завершённых попыток на сервере</div>
          <p class="text-[11px] text-slate-400 leading-relaxed">
            Пройдите любой тест с интернет-соединением, чтобы ваш результат закрепился на 1-м месте в таблице лидеров!
          </p>
          ${localTotal > 0 ? `
            <div class="p-3 rounded-2xl bg-brand-950/40 border border-brand-500/40 flex items-center justify-between text-left">
              <div>
                <div class="text-xs font-bold text-white">Ваш результат: ${state.userName} (Вы)</div>
                <div class="text-[10px] text-slate-400">${localScore} из ${localTotal} верно • ${myLocalAttempts.length} попыток</div>
              </div>
              <div class="text-right">
                <span class="text-xs font-bold text-brand-400 font-mono">${localPct}%</span>
              </div>
            </div>
          ` : ''}
        </div>
      `;
      return;
    }

    items.forEach((u, idx) => {
      const isMe = (state.userId && u.user_id == state.userId);
      const el = document.createElement('div');
      el.className = `p-3.5 rounded-2xl border flex items-center justify-between transition ${
        isMe
          ? 'bg-gradient-to-r from-brand-950/80 via-app-card to-app-card border-brand-500 shadow-md ring-1 ring-brand-500/30'
          : 'bg-app-card border-app-border'
      }`;

      let rankBadgeHtml = `<span class="w-6 h-6 rounded-lg flex items-center justify-center text-xs font-mono font-bold ${
        idx === 0 ? 'bg-amber-400/20 text-amber-300 border border-amber-400/40' :
        idx === 1 ? 'bg-slate-300/20 text-slate-200 border border-slate-300/40' :
        idx === 2 ? 'bg-amber-700/20 text-amber-500 border border-amber-700/40' :
        'bg-app-surface text-slate-500 border border-app-border'
      }">${idx + 1}</span>`;

      const mins = String(Math.floor((u.duration || 0) / 60)).padStart(2, '0');
      const secs = String((u.duration || 0) % 60).padStart(2, '0');
      const timeStr = u.duration > 0 ? `${mins}:${secs}` : '';

      el.innerHTML = `
        <div class="flex items-center space-x-3 min-w-0">
          <div class="shrink-0">${rankBadgeHtml}</div>
          <div class="min-w-0">
            <div class="text-xs font-bold text-white truncate flex items-center gap-1.5">
              <span>${u.name}</span>
              ${isMe ? '<span class="text-[9px] px-1.5 py-0.2 rounded bg-brand-500/30 text-brand-300 font-mono">Вы</span>' : ''}
            </div>
            <div class="text-[10px] text-slate-400 flex items-center gap-1.5 mt-0.5">
              <span>${u.score} из ${u.total} верно</span>
              ${timeStr ? `<span>•</span><span class="flex items-center gap-1"><svg class="w-3 h-3 text-slate-400 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>${timeStr}</span>` : ''}
            </div>
          </div>
        </div>
        <div class="text-right shrink-0">
          <div class="text-xs font-mono font-bold text-brand-400">${u.percent}%</div>
          <div class="text-[9px] text-slate-500 font-mono">${u.score * 10} XP</div>
        </div>
      `;
      container.appendChild(el);
    });
  }

  // Global Toast Notification (Clean floating pill)
  let toastTimer = null;
  function showToast(text) {
    let toast = document.getElementById('app-global-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'app-global-toast';
      toast.className = 'fixed top-5 left-1/2 -translate-x-1/2 z-[110] px-4 py-2.5 rounded-2xl bg-slate-900/90 text-white font-semibold text-xs border border-white/10 shadow-2xl backdrop-blur-md pointer-events-none transition-all duration-300 opacity-0 -translate-y-2';
      document.body.appendChild(toast);
    }
    toast.innerText = text;
    toast.classList.remove('opacity-0', '-translate-y-2');
    toast.classList.add('opacity-100', 'translate-y-0');

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove('opacity-100', 'translate-y-0');
      toast.classList.add('opacity-0', '-translate-y-2');
    }, 2200);
  }

  // ==========================================
  // PROFILE CUSTOMIZATION (NICKNAME & AVATAR)
  // ==========================================
  const AVATAR_PRESETS = [
    { type: 'emoji', value: '👨‍⚕️', label: 'Доктор' },
    { type: 'emoji', value: '👩‍⚕️', label: 'Доктор' },
    { type: 'emoji', value: '🩺', label: 'Стетоскоп' },
    { type: 'emoji', value: '🔬', label: 'Микроскоп' },
    { type: 'emoji', value: '🧬', label: 'ДНК' },
    { type: 'emoji', value: '💊', label: 'Пилюля' },
    { type: 'emoji', value: '🏥', label: 'Клиника' },
    { type: 'emoji', value: '🧠', label: 'Мозг' },
    { type: 'emoji', value: '🫀', label: 'Сердце' },
    { type: 'emoji', value: '🦴', label: 'Анатомия' },
    { type: 'emoji', value: '🎓', label: 'Выпускник' },
    { type: 'emoji', value: '⚡', label: 'Молния' }
  ];

  let tempEditAvatar = '';

  function renderProfileAvatarElement(containerEl, avatarVal, nameVal) {
    if (!containerEl) return;
    if (avatarVal && (avatarVal.startsWith('data:image/') || avatarVal.startsWith('http://') || avatarVal.startsWith('https://'))) {
      containerEl.innerHTML = `<img src="${avatarVal}" alt="avatar" class="w-full h-full object-cover">`;
    } else if (avatarVal) {
      containerEl.innerHTML = `<span class="text-2xl">${avatarVal}</span>`;
    } else {
      const initial = (nameVal || 'С')[0].toUpperCase();
      containerEl.innerHTML = `<span class="text-xl font-black">${initial}</span>`;
    }
  }

  function openEditProfileModal() {
    triggerHaptic('light');
    const modal = document.getElementById('modal-edit-profile');
    if (!modal) return;

    const nameInput = document.getElementById('edit-profile-name-input');
    if (nameInput) nameInput.value = state.userName || '';

    tempEditAvatar = state.userAvatar || '';
    updateEditAvatarPreview();

    // Populate Presets Grid
    const grid = document.getElementById('edit-avatar-presets-grid');
    if (grid) {
      grid.innerHTML = '';
      AVATAR_PRESETS.forEach(p => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `h-10 rounded-xl bg-app-surface border ${tempEditAvatar === p.value ? 'border-brand-500 ring-2 ring-brand-500/40 bg-brand-500/10' : 'border-app-border'} hover:border-brand-400 flex items-center justify-center text-lg active:scale-90 transition`;
        btn.innerText = p.value;
        btn.onclick = () => selectAvatarPreset(p.value);
        grid.appendChild(btn);
      });
    }

    modal.classList.remove('hidden');
  }

  function dismissKeyboard() {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }
  }

  function onModalEditBackdropClick(event) {
    if (event.target && event.target.id === 'modal-edit-profile') {
      dismissKeyboard();
    }
  }

  function closeEditProfileModal() {
    dismissKeyboard();
    triggerHaptic('light');
    const modal = document.getElementById('modal-edit-profile');
    if (modal) modal.classList.add('hidden');
  }

  function updateEditAvatarPreview() {
    const previewEl = document.getElementById('edit-avatar-preview');
    const nameInput = document.getElementById('edit-profile-name-input');
    const currentName = nameInput ? nameInput.value.trim() : (state.userName || 'С');
    renderProfileAvatarElement(previewEl, tempEditAvatar, currentName);
  }

  function onEditNameInput(val) {
    if (!tempEditAvatar) {
      updateEditAvatarPreview();
    }
  }

  function selectAvatarPreset(emoji) {
    triggerHaptic('light');
    tempEditAvatar = emoji;
    updateEditAvatarPreview();

    // Highlight selected button
    const grid = document.getElementById('edit-avatar-presets-grid');
    if (grid) {
      Array.from(grid.children).forEach(child => {
        if (child.innerText.trim() === emoji) {
          child.className = 'h-10 rounded-xl bg-app-surface border border-brand-500 ring-2 ring-brand-500/40 bg-brand-500/10 flex items-center justify-center text-lg active:scale-90 transition';
        } else {
          child.className = 'h-10 rounded-xl bg-app-surface border border-app-border hover:border-brand-400 flex items-center justify-center text-lg active:scale-90 transition';
        }
      });
    }
  }

  function handleCustomAvatarUpload(event) {
    const file = event.target?.files?.[0];
    if (!file) return;

    // Check size limit (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      showToast('⚠️ Файл слишком большой (макс. 5 МБ)');
      return;
    }

    const reader = new FileReader();
    reader.onload = function(e) {
      // Compress/resize image with canvas to save localStorage space (~120x120px)
      const img = new Image();
      img.onload = function() {
        const canvas = document.createElement('canvas');
        const size = 128;
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');

        // Draw cropped center square
        const minDim = Math.min(img.width, img.height);
        const sx = (img.width - minDim) / 2;
        const sy = (img.height - minDim) / 2;
        ctx.drawImage(img, sx, sy, minDim, minDim, 0, 0, size, size);

        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        tempEditAvatar = dataUrl;
        updateEditAvatarPreview();
        showToast('📸 Фото успешно загружено!');
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  function resetAvatarToDefault() {
    triggerHaptic('light');
    tempEditAvatar = '';
    updateEditAvatarPreview();
    const grid = document.getElementById('edit-avatar-presets-grid');
    if (grid) {
      Array.from(grid.children).forEach(child => {
        child.className = 'h-10 rounded-xl bg-app-surface border border-app-border hover:border-brand-400 flex items-center justify-center text-lg active:scale-90 transition';
      });
    }
    const fileInput = document.getElementById('edit-profile-file-input');
    if (fileInput) fileInput.value = '';
    showToast('Аватар сброшен на стандартный');
  }

  function saveUserProfileEdits() {
    dismissKeyboard();
    triggerHaptic('medium');
    const nameInput = document.getElementById('edit-profile-name-input');
    const newName = nameInput ? nameInput.value.trim() : '';

    if (!newName) {
      showToast('⚠️ Введите никнейм или имя');
      return;
    }

    state.userName = newName;
    state.userAvatar = tempEditAvatar;

    try {
      localStorage.setItem('ohtest_custom_name', newName);
      if (tempEditAvatar) {
        localStorage.setItem('ohtest_custom_avatar', tempEditAvatar);
      } else {
        localStorage.removeItem('ohtest_custom_avatar');
      }
    } catch(e) {
      console.warn('LocalStorage save failed for profile edits:', e);
    }

    // Refresh Profile Screen
    updateProfileFullView();
    closeEditProfileModal();
    showToast('✅ Профиль успешно обновлен!');
  }

  const profileErrorTestLoads = new Map();
  const profileErrorTestFailures = new Set();

  async function loadProfileErrorTest(testId) {
    if (BUNDLED_TESTS[testId]) return true;
    if (!profileErrorTestLoads.has(testId)) {
      profileErrorTestLoads.set(testId, fetch(`/api/tests/${encodeURIComponent(testId)}`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (!data || !Array.isArray(data.questions)) {
            profileErrorTestFailures.add(testId);
            return false;
          }
          BUNDLED_TESTS[testId] = { title: data.title || testId, questions: data.questions };
          return true;
        })
        .catch(() => {
          profileErrorTestFailures.add(testId);
          return false;
        }));
    }
    return profileErrorTestLoads.get(testId);
  }

  async function syncProfileNotebookFromServer() {
    if (!state.userId) return;
    try {
      const response = await fetch('/api/user/state');
      if (!response.ok) return;
      const data = await response.json();
      const serverTests = data.tests && typeof data.tests === 'object' ? data.tests : {};
      const testIds = new Set(Object.keys(serverTests));
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key?.startsWith('ohtest_favs_')) testIds.add(key.slice('ohtest_favs_'.length));
        if (key?.startsWith('ohtest_errors_')) testIds.add(key.slice('ohtest_errors_'.length));
      }

      for (const testId of testIds) {
        if (!await loadProfileErrorTest(testId)) continue;
        const remote = serverTests[testId] || {};
        const questionIds = new Set(BUNDLED_TESTS[testId].questions.map(question => String(question.id)));
        const mergeIds = (key, remoteIds) => {
          let localIds = [];
          try { localIds = JSON.parse(localStorage.getItem(key) || '[]'); } catch(e) {}
          const merged = [...new Set([...(Array.isArray(localIds) ? localIds : []), ...(Array.isArray(remoteIds) ? remoteIds : [])]
            .map(Number).filter(id => Number.isFinite(id) && questionIds.has(String(id))))];
          localStorage.setItem(key, JSON.stringify(merged));
          return merged;
        };
        const favorites = mergeIds(`ohtest_favs_${testId}`, remote.favorites);
        mergeIds(`ohtest_errors_${testId}`, remote.errors);
        if (state.activeTestId === testId) state.favorites = new Set(favorites);
      }

      if (Array.isArray(data.attempts) && data.attempts.length) {
        let localHistory = [];
        try {
          const saved = JSON.parse(localStorage.getItem('ohtest_history') || '[]');
          if (Array.isArray(saved)) localHistory = saved;
        } catch(e) {}
        const remainingLocal = [...localHistory];
        const serverHistory = data.attempts.map(attempt => {
          const matchIndex = remainingLocal.findIndex(item => item.testId === attempt.test_id && item.mode === attempt.mode &&
            Number(item.correct || 0) === Number(attempt.correct || 0) && Number(item.duration || 0) === Number(attempt.duration || 0));
          const local = matchIndex >= 0 ? remainingLocal.splice(matchIndex, 1)[0] : null;
          const test = BUNDLED_TESTS[attempt.test_id];
          const total = Math.max(Number(attempt.answered || 0), Number(local?.total || 0));
          const correct = Number(attempt.correct || 0);
          const pct = total ? Math.round(correct / total * 100) : 0;
          let date = 'Недавно';
          if (attempt.finished_at) {
            const parsed = new Date(`${String(attempt.finished_at).replace(' ', 'T')}Z`);
            if (!Number.isNaN(parsed.getTime())) date = parsed.toLocaleString('ru-RU');
          }
          return {
            ...(local || {}), serverAttemptId: attempt.attempt_id, date,
            title: local?.title || test?.title || attempt.test_id, testId: attempt.test_id,
            score: `${correct}/${total} (${pct}%)`, total, correct,
            errors: Math.max(0, Number(attempt.answered || 0) - correct),
            skipped: Math.max(0, total - Number(attempt.answered || 0)), pct,
            mode: attempt.mode, duration: Number(attempt.duration || 0),
            questionsSnapshot: local?.questionsSnapshot || []
          };
        });
        state.historyAttempts = [...remainingLocal, ...serverHistory].slice(0, 50);
        localStorage.setItem('ohtest_history', JSON.stringify(state.historyAttempts));
      }
    } catch(e) {
      console.warn('Could not sync profile notebook:', e);
    }
  }

  function getAllSavedErrors() {
    const result = [];
    const seen = new Set();
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith('ohtest_errors_')) {
          const testId = k.replace('ohtest_errors_', '');
          const qids = JSON.parse(localStorage.getItem(k) || '[]');
          const tData = BUNDLED_TESTS[testId];
          if (tData && Array.isArray(qids)) {
            qids.forEach(qid => {
              const q = tData.questions.find(item => item.id == qid);
              const key = `${testId}:${qid}`;
              if (q && !seen.has(key)) {
                seen.add(key);
                result.push({
                  testId: testId,
                  testTitle: tData.title,
                  question: q
                });
              }
            });
          }
        }
      }
    } catch(e) {}
    if (state.activeTestId && state.userErrors) {
      const tData = BUNDLED_TESTS[state.activeTestId];
      if (tData) {
        state.userErrors.forEach(qid => {
          const key = `${state.activeTestId}:${qid}`;
          if (!seen.has(key)) {
            const q = tData.questions.find(item => item.id == qid);
            if (q) {
              seen.add(key);
              result.push({
                testId: state.activeTestId,
                testTitle: tData.title,
                question: q
              });
            }
          }
        });
      }
    }
    return result;
  }

  function updateProfileErrorBadge(count) {
    const el = document.getElementById('profile-err-count');
    if (!el) return;
    const c = (count !== undefined && count !== null) ? Number(count) : getAllSavedErrors().length;
    el.innerText = c;
    el.className = `text-xs font-bold font-mono ${c > 0 ? 'text-rose-400 !text-rose-400' : 'text-slate-400'}`;
  }

  function getResolvedErrors() {
    const result = [];
    const unresolved = new Set(getAllSavedErrors().map(e => `${e.testId}:${e.question.id}`));
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith('ohtest_resolved_errors_')) {
          const testId = k.replace('ohtest_resolved_errors_', '');
          const qids = JSON.parse(localStorage.getItem(k) || '[]');
          const tData = BUNDLED_TESTS[testId];
          if (tData && Array.isArray(qids)) {
            qids.forEach(qid => {
              const q = tData.questions.find(item => item.id == qid);
              const key = `${testId}:${qid}`;
              if (q && !unresolved.has(key)) {
                unresolved.add(key);
                result.push({
                  testId: testId,
                  testTitle: tData.title,
                  question: q,
                  status: 'resolved'
                });
              }
            });
          }
        }
      }
    } catch(e) {}
    return result;
  }

  function toggleShowAllErrors(checked) {
    triggerHaptic('light');
    state.showAllErrors = checked;
    renderErrorsSubtab();
  }

  function clearResolvedErrors() {
    if (!confirm('Очистить список усвоенных (решённых) ошибок?')) return;
    try {
      const keys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith('ohtest_resolved_errors_')) {
          keys.push(k);
        }
      }
      keys.forEach(k => localStorage.removeItem(k));
    } catch(e) {}
    renderErrorsSubtab();
    updateProfileErrorBadge(getAllSavedErrors().length);
  }

  function renderErrorsSubtab() {
    const box = document.getElementById('profile-subtab-content');
    if (!box) return;
    const savedTestIds = new Set();
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && (key.startsWith('ohtest_errors_') || key.startsWith('ohtest_resolved_errors_'))) {
        const prefix = key.startsWith('ohtest_resolved_errors_') ? 'ohtest_resolved_errors_' : 'ohtest_errors_';
        const testId = key.slice(prefix.length);
        if (testId && !BUNDLED_TESTS[testId] && !profileErrorTestLoads.has(testId)) savedTestIds.add(testId);
      }
    }
    if (savedTestIds.size) {
      box.innerHTML = '<div class="p-6 text-center text-xs text-slate-400">Загружаю вопросы из истории ошибок…</div>';
      Promise.all([...savedTestIds].map(loadProfileErrorTest)).then(() => {
        if (state.activeProfileSubTab === 'errors') renderErrorsSubtab();
      });
      return;
    }
    const unavailableTests = [...profileErrorTestFailures];
    const loadWarning = unavailableTests.length
      ? `<div class="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-200">Не удалось загрузить вопросы для ${unavailableTests.length} ${unavailableTests.length === 1 ? 'теста' : 'тестов'}. Проверьте соединение и перезапустите приложение.</div>`
      : '';
    const unresolvedErrors = getAllSavedErrors().map(e => ({ ...e, status: 'unresolved' }));
    const resolvedErrors = getResolvedErrors();

    let displayList = state.showAllErrors ? [...unresolvedErrors, ...resolvedErrors] : [...unresolvedErrors];
    // Unresolved always sorted to top!
    displayList.sort((a, b) => {
      if (a.status === 'unresolved' && b.status === 'resolved') return -1;
      if (a.status === 'resolved' && b.status === 'unresolved') return 1;
      const testOrder = a.testTitle.localeCompare(b.testTitle, 'ru');
      return testOrder || Number(a.question.id) - Number(b.question.id);
    });

    if (displayList.length === 0 && !state.showAllErrors && !loadWarning) {
      box.innerHTML = `
        <div class="p-8 text-center rounded-3xl bg-app-card border border-app-border space-y-3">
          <div class="w-12 h-12 mx-auto rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
          </div>
          <div class="text-xs font-bold text-white">В блокноте нет активных ошибок!</div>
          <p class="text-[11px] text-slate-400 leading-relaxed">
            Все вопросы усвоены или ещё не решались. Вопросы с неверными ответами появятся здесь автоматически.
          </p>
          ${resolvedErrors.length > 0 ? `
            <div class="pt-2">
              <button onclick="toggleShowAllErrors(true)" class="px-3 py-1.5 rounded-xl bg-app-surface border border-app-border text-xs text-brand-300 font-semibold">
                Показать решённые ошибки (${resolvedErrors.length})
              </button>
            </div>
          ` : ''}
        </div>
      `;
      return;
    }

    let itemsHtml = displayList.map(errItem => {
      const q = errItem.question;
      const isResolved = (errItem.status === 'resolved');
      const correctText = (q.options && q.options[q.correct]) ? q.options[q.correct] : '—';

      return `
        <div class="p-4 rounded-2xl bg-app-card border ${isResolved ? 'border-brand-500/30' : 'border-rose-500/30'} space-y-2.5">
          <div class="flex justify-between items-center text-xs">
            <span class="text-[10px] font-bold ${isResolved ? 'text-brand-400 bg-brand-500/10 border border-brand-500/20' : 'text-rose-400 bg-rose-500/10 border border-rose-500/20'} px-2 py-0.5 rounded-full truncate max-w-[200px] inline-flex items-center gap-1">
              ${errItem.testTitle} • #${q.id} ${isResolved ? '✓ Усвоено' : 'Повторить'}
            </span>
            <div class="flex items-center space-x-2">
              <button onclick="solveOneError('${errItem.testId}', ${q.id})" class="px-2.5 py-1 rounded-xl ${isResolved ? 'bg-brand-600/30 hover:bg-brand-600 text-brand-200' : 'bg-rose-600/30 hover:bg-rose-600 text-rose-200'} text-[11px] font-semibold active:scale-95 transition inline-flex items-center gap-1">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3" fill="currentColor"/></svg>
                <span>${isResolved ? 'Повторить' : 'Решить'}</span>
              </button>
              <button onclick="dismissOneError('${errItem.testId}', ${q.id}, '${errItem.status}')" class="text-slate-500 hover:text-rose-400 text-xs px-1" title="Удалить">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>
          </div>
          <p onclick="openQuestionDetailModalById('${errItem.testId}', ${q.id})" class="text-xs text-white font-medium leading-relaxed cursor-pointer hover:text-brand-300 transition">${q.question}</p>
          <div class="p-2.5 rounded-xl bg-app-surface text-[11px] text-emerald-400 border border-emerald-500/20 font-medium">
            ✓ Ответ: <span class="text-slate-200">${correctText}</span>
          </div>
        </div>
      `;
    }).join('');

    box.innerHTML = `
      ${loadWarning}
      <div class="p-3.5 rounded-2xl bg-app-card border border-app-border space-y-3">
        <div class="flex items-center justify-between">
          <label class="flex items-center gap-2 cursor-pointer text-xs text-slate-200 font-semibold select-none">
            <input type="checkbox" ${state.showAllErrors ? 'checked' : ''} onchange="toggleShowAllErrors(this.checked)" class="w-4 h-4 accent-brand-500 rounded cursor-pointer">
            <span>Показать все (включая решённые)</span>
          </label>
          <span class="text-[10px] font-mono text-slate-400">Активных: ${unresolvedErrors.length}</span>
        </div>
        <div class="flex items-center justify-between pt-1 border-t border-app-border/60 text-xs">
          ${unresolvedErrors.length > 0 ? `
            <button onclick="startAllErrorsSession()" class="px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shadow-md active:scale-95 transition flex items-center gap-1.5">
              <svg class="w-3 h-3 fill-current" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              <span>Решить нерешённые (${unresolvedErrors.length})</span>
            </button>
          ` : '<span class="text-xs text-brand-400 font-semibold">✓ Все ошибки отработаны!</span>'}
          <div class="flex items-center gap-2">
            ${resolvedErrors.length > 0 ? `
              <button onclick="clearResolvedErrors()" class="text-[10px] text-slate-400 hover:text-brand-300">
                Очистить решённые
              </button>
            ` : ''}
            <button onclick="clearAllProfileErrors()" class="p-1.5 rounded-xl text-slate-500 hover:text-rose-400" title="Очистить все">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
            </button>
          </div>
        </div>
      </div>
      <div class="space-y-2.5">
        ${itemsHtml}
      </div>
    `;
  }

  function startAllErrorsSession() {
    triggerHaptic('light');
    const errors = getAllSavedErrors();
    if (errors.length === 0) return;

    const nextError = errors.find(error => error.testId !== state.activeTestId) || errors[0];
    const test = BUNDLED_TESTS[nextError.testId];
    if (!test) return;

    state.activeTestId = nextError.testId;
    state.activeTestTitle = test.title;
    state.currentTestOriginalQuestions = [...test.questions];
    try {
      state.userErrors = new Set(JSON.parse(localStorage.getItem(`ohtest_errors_${state.activeTestId}`) || '[]'));
      state.favorites = new Set(JSON.parse(localStorage.getItem(`ohtest_favs_${state.activeTestId}`) || '[]'));
    } catch(e) {
      state.userErrors = new Set();
      state.favorites = new Set();
    }
    startQuizMode('errors_solve');
  }

  function returnToProfileErrors() {
    switchTab('profile');
    switchProfileTab('errors');
  }

  function solveOneError(testId, qid) {
    triggerHaptic('light');
    const tData = BUNDLED_TESTS[testId];
    if (!tData) return;
    const q = tData.questions.find(item => item.id == qid);
    if (!q) return;

    state.activeTestId = testId;
    state.activeTestTitle = tData.title;
    state.activeQuestions = [{...q}];
    state.currentTestOriginalQuestions = [...tData.questions];
    try {
      state.userErrors = new Set(JSON.parse(localStorage.getItem(`ohtest_errors_${testId}`) || '[]'));
      state.favorites = new Set(JSON.parse(localStorage.getItem(`ohtest_favs_${testId}`) || '[]'));
    } catch(e) {
      state.userErrors = new Set();
      state.favorites = new Set();
    }
    state.currentMode = 'errors_solve';
    state.userAnswers = {};
    state.revealedAnswers = new Set();
    state.currentQIndex = 0;
    state.timerSeconds = 0;
    clearInterval(state.timerInterval);
    state.timerInterval = setInterval(() => { state.timerSeconds++; }, 1000);

    hideAllViews();
    state.homeActiveView = 'solver';
    document.getElementById('view-solver').classList.remove('hidden');
    document.getElementById('btn-grid-modal').classList.remove('hidden');
    document.getElementById('btn-fav-toggle')?.classList.remove('hidden');
    document.getElementById('btn-finish-early').classList.remove('hidden');
    updateHeaderNavState();
    renderCurrentQuestion();
    updateTelegramBackButton();
  }

  function dismissOneError(testId, qid, status) {
    try {
      if (status === 'resolved') {
        const k = `ohtest_resolved_errors_${testId}`;
        const arr = JSON.parse(localStorage.getItem(k) || '[]');
        const filtered = arr.filter(id => id != qid);
        localStorage.setItem(k, JSON.stringify(filtered));
      } else {
        const k = `ohtest_errors_${testId}`;
        const arr = JSON.parse(localStorage.getItem(k) || '[]');
        const filtered = arr.filter(id => id != qid);
        localStorage.setItem(k, JSON.stringify(filtered));
        if (state.activeTestId === testId) {
          state.userErrors.delete(qid);
        }
      }
    } catch(e) {}
    renderErrorsSubtab();
    updateProfileErrorBadge(getAllSavedErrors().length);
  }

  function clearAllProfileErrors() {
    if (!confirm('Очистить все ошибки из блокнота?')) return;
    try {
      const keys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && (k.startsWith('ohtest_errors_') || k.startsWith('ohtest_resolved_errors_'))) {
          keys.push(k);
        }
      }
      keys.forEach(k => localStorage.removeItem(k));
      state.userErrors = new Set();
    } catch(e) {}
    renderErrorsSubtab();
    updateProfileErrorBadge(0);
  }

  function getAllSavedFavorites() {
    const result = [];
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith('ohtest_favs_')) {
          const testId = k.replace('ohtest_favs_', '');
          const qids = JSON.parse(localStorage.getItem(k) || '[]');
          const tData = BUNDLED_TESTS[testId];
          if (tData && Array.isArray(qids)) {
            qids.forEach(qid => {
              const q = tData.questions.find(item => item.id == qid);
              if (q) {
                result.push({
                  testId: testId,
                  testTitle: tData.title,
                  question: q
                });
              }
            });
          }
        }
      }
    } catch(e) {}
    if (state.activeTestId && state.favorites) {
      const tData = BUNDLED_TESTS[state.activeTestId];
      if (tData) {
        state.favorites.forEach(qid => {
          const already = result.some(r => r.testId === state.activeTestId && r.question.id == qid);
          if (!already) {
            const q = tData.questions.find(item => item.id == qid);
            if (q) {
              result.push({
                testId: state.activeTestId,
                testTitle: tData.title,
                question: q
              });
            }
          }
        });
      }
    }
    return result;
  }

  function renderFavsSubtab() {
    const box = document.getElementById('profile-subtab-content');
    const favs = getAllSavedFavorites();

    if (favs.length === 0) {
      box.innerHTML = `
        <div class="p-8 text-center rounded-3xl bg-app-card border border-app-border space-y-2.5">
          <div class="w-12 h-12 mx-auto rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/></svg>
          </div>
          <div class="text-xs font-bold text-white">В избранном пока нет вопросов</div>
          <p class="text-[11px] text-slate-400 leading-relaxed">
            Нажимайте кнопку сохранения в избранное во время прохождения теста, чтобы сохранить важные вопросы для повторения.
          </p>
        </div>
      `;
      return;
    }

    let itemsHtml = favs.map(fItem => {
      const q = fItem.question;
      const correctText = (q.options && q.options[q.correct]) ? q.options[q.correct] : '—';
      return `
        <div class="p-4 rounded-2xl bg-app-card border border-amber-500/30 space-y-2.5">
          <div class="flex justify-between items-center text-xs">
            <span class="text-[10px] font-bold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full truncate max-w-[200px]">
              ${fItem.testTitle} • Вопрос #${q.id}
            </span>
            <button onclick="dismissOneFav('${fItem.testId}', ${q.id})" class="text-slate-500 hover:text-rose-400 text-xs px-1">
              Удалить
            </button>
          </div>
          <p onclick="openQuestionDetailModalById('${fItem.testId}', ${q.id})" class="text-xs text-white font-medium leading-relaxed cursor-pointer hover:text-brand-300 transition">${q.question}</p>
          <div class="p-2.5 rounded-xl bg-app-surface text-[11px] text-emerald-400 border border-emerald-500/20 font-medium">
            ✓ Ответ: <span class="text-slate-200">${correctText}</span>
          </div>
        </div>
      `;
    }).join('');

    box.innerHTML = `
      <div class="flex items-center justify-between p-3.5 rounded-2xl bg-amber-950/30 border border-amber-500/30">
        <div>
          <div class="text-xs font-bold text-white">Сохранено: ${favs.length} вопросов</div>
          <div class="text-[10px] text-slate-400">Важные вопросы для повторения</div>
        </div>
        <button onclick="startAllFavsSession()" class="px-3 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs shadow-md active:scale-95 transition flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          <span>Тренировать (${favs.length})</span>
        </button>
      </div>
      <div class="space-y-2.5">
        ${itemsHtml}
      </div>
    `;
  }

  function startAllFavsSession() {
    triggerHaptic('light');
    const favs = getAllSavedFavorites();
    if (favs.length === 0) return;

    state.favoriteReviewQueue = [...new Set(favs.map(item => item.testId))];
    startNextFavoriteGroup();
  }

  function startNextFavoriteGroup() {
    while (state.favoriteReviewQueue.length > 0) {
      const testId = state.favoriteReviewQueue.shift();
      const test = BUNDLED_TESTS[testId];
      const favs = getAllSavedFavorites().filter(item => item.testId === testId);
      if (!test || favs.length === 0) continue;

      state.activeTestId = testId;
      state.activeTestTitle = test.title;
      state.currentTestOriginalQuestions = [...test.questions];
      state.activeQuestions = favs.map(item => ({ ...item.question }));
      try {
        state.userErrors = new Set(JSON.parse(localStorage.getItem(`ohtest_errors_${testId}`) || '[]'));
        state.favorites = new Set(JSON.parse(localStorage.getItem(`ohtest_favs_${testId}`) || '[]'));
      } catch(e) {
        state.userErrors = new Set();
        state.favorites = new Set();
      }
      state.currentMode = 'all_favs';
      state.userAnswers = {};
      state.revealedAnswers = new Set();
      state.currentQIndex = 0;
      state.timerSeconds = 0;
      clearInterval(state.timerInterval);
      state.timerInterval = setInterval(() => { state.timerSeconds++; }, 1000);

      hideAllViews();
      state.homeActiveView = 'solver';
      document.getElementById('view-solver').classList.remove('hidden');
      document.getElementById('btn-grid-modal').classList.remove('hidden');
      document.getElementById('btn-fav-toggle')?.classList.remove('hidden');
      document.getElementById('btn-finish-early').classList.remove('hidden');
      document.getElementById('solver-mode-tag').innerText = 'Тренировка избранного';
      updateHeaderNavState();
      renderCurrentQuestion();
      updateTelegramBackButton();
      return;
    }

    finishFavoriteReview();
  }

  function finishFavoriteReview() {
    state.favoriteReviewQueue = [];
    switchTab('profile');
    switchProfileTab('favs');
  }

  function dismissOneFav(testId, qid) {
    try {
      const k = `ohtest_favs_${testId}`;
      const arr = JSON.parse(localStorage.getItem(k) || '[]');
      const filtered = arr.filter(id => id != qid);
      localStorage.setItem(k, JSON.stringify(filtered));
      if (state.activeTestId === testId) {
        state.favorites.delete(qid);
        state.favorites.delete(Number(qid));
        state.favorites.delete(String(qid));
        const hubFavsEl = document.getElementById('hub-q-favs');
        if (hubFavsEl) {
          hubFavsEl.innerText = state.favorites.size;
          hubFavElClass(hubFavsEl, state.favorites.size);
        }
        if (state.activeQuestions && state.activeQuestions[state.currentQIndex]) {
          updateFavUI(isQuestionFavorited(state.activeQuestions[state.currentQIndex].id));
        }
      }
    } catch(e) {}
    fetch('/api/user/favorite', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ test_id: testId, question_id: qid, is_favorite: false })
    }).catch(() => {});
    renderFavsSubtab();
    document.getElementById('profile-fav-count').innerText = getAllSavedFavorites().length;
  }

  function getModeNameRu(mode) {
    const map = {
      normal: 'По порядку',
      random: 'Вразброс',
      reverse: 'С конца',
      training: 'Тренировка',
      mini10: 'Тренировка',
      errors_solve: 'Разбор ошибок',
      all_errors: 'Все ошибки',
      all_favs: 'Избранное'
    };
    return map[mode] || mode || 'Тест';
  }

  function openViewAttemptModal(idx) {
    triggerHaptic('light');
    const attempt = state.historyAttempts[idx];
    if (!attempt) return;

    const modal = document.getElementById('modal-view-attempt');
    const titleEl = document.getElementById('view-attempt-title');
    const subtitleEl = document.getElementById('view-attempt-subtitle');
    const bodyEl = document.getElementById('view-attempt-body');

    titleEl.innerText = attempt.title || 'Попытка';
    const modeBadge = getModeNameRu(attempt.mode);

    // Compute detailed stats accurately
    let correctCount = 0;
    let errorsCount = 0;
    let skippedCount = 0;

    if (attempt.questionsSnapshot && attempt.questionsSnapshot.length > 0) {
      attempt.questionsSnapshot.forEach(q => {
        if (q.userAnswer === undefined || q.userAnswer === null) {
          skippedCount++;
        } else if (Number(q.userAnswer) === Number(q.correct)) {
          correctCount++;
        } else {
          errorsCount++;
        }
      });
    } else {
      correctCount = attempt.correct || 0;
      skippedCount = (attempt.skipped !== undefined) ? attempt.skipped : 0;
      errorsCount = (attempt.errors !== undefined) ? attempt.errors : Math.max(0, (attempt.total || 0) - correctCount - skippedCount);
    }

    const totalQuestions = attempt.total || (correctCount + errorsCount + skippedCount);
    let statsSubtitle = `${attempt.date || ''} • ${modeBadge} • Верно: ${correctCount}/${totalQuestions}`;
    if (errorsCount > 0) statsSubtitle += ` • Ошибок: ${errorsCount}`;
    if (skippedCount > 0) statsSubtitle += ` • Пропущено: ${skippedCount}`;
    subtitleEl.innerText = statsSubtitle;

    if (!attempt.questionsSnapshot || attempt.questionsSnapshot.length === 0) {
      bodyEl.innerHTML = `
        <div class="p-6 text-center text-xs text-slate-400 space-y-3">
          <div class="w-12 h-12 mx-auto rounded-2xl bg-app-surface border border-app-border flex items-center justify-center text-slate-400">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          </div>
          <div class="font-bold text-white">Детальный разбор недоступен</div>
          <p class="text-[11px] text-slate-500">Эта попытка была записана до обновления системы детализации. Для всех новых тестов сохраняется полный разбор вопросов.</p>
        </div>
      `;
    } else {
      let qListHtml = attempt.questionsSnapshot.map((q, qIndex) => {
        const userChoice = q.userAnswer;
        const isSkipped = (userChoice === undefined || userChoice === null);
        const isCorrect = (!isSkipped && Number(userChoice) === Number(q.correct));
        const isWrong = (!isSkipped && !isCorrect);

        const userOptText = (!isSkipped && q.options && q.options[userChoice] !== undefined)
          ? q.options[userChoice]
          : 'Вопрос был пропущен';
        const correctOptText = (q.options && q.options[q.correct] !== undefined) ? q.options[q.correct] : '—';

        let cardBorderClass = 'border-rose-500/30';
        let badgeHtml = '';
        let answerContainerClass = 'bg-rose-950/40 text-rose-300';
        let answerLabel = `Ваш ответ: <span class="font-semibold">${userOptText}</span>`;

        if (isCorrect) {
          cardBorderClass = 'border-emerald-500/40';
          badgeHtml = '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-mono">✓ Верно</span>';
          answerContainerClass = 'bg-emerald-950/40 text-emerald-300 border border-emerald-500/20';
        } else if (isSkipped) {
          cardBorderClass = 'border-amber-500/40';
          badgeHtml = '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/40 font-mono">⊘ Пропущен</span>';
          answerContainerClass = 'bg-amber-950/30 text-amber-300 border border-amber-500/20';
          answerLabel = '<span class="font-semibold text-amber-300">⊘ Вопрос был пропущен (без ответа)</span>';
        } else {
          cardBorderClass = 'border-rose-500/40';
          badgeHtml = '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40 font-mono">✕ Ошибка</span>';
          answerContainerClass = 'bg-rose-950/40 text-rose-300 border border-rose-500/20';
        }

        return `
          <div class="p-3.5 rounded-2xl bg-app-surface border ${cardBorderClass} text-xs space-y-2">
            <div class="flex items-center justify-between font-bold">
              <span class="text-slate-300">Вопрос #${q.id || (qIndex + 1)}</span>
              ${badgeHtml}
            </div>
            <p class="text-white font-medium leading-relaxed">${q.question}</p>
            <div class="space-y-1.5 pt-1 text-[11px]">
              <div class="p-2.5 rounded-xl ${answerContainerClass}">
                ${answerLabel}
              </div>
              ${!isCorrect ? `
                <div class="p-2.5 rounded-xl bg-emerald-950/30 text-emerald-300 border border-emerald-500/20">
                  Правильный ответ: <span class="font-semibold">${correctOptText}</span>
                </div>
              ` : ''}
            </div>
          </div>
        `;
      }).join('');

      bodyEl.innerHTML = qListHtml;
    }

    modal.classList.remove('hidden');
  }

  function closeViewAttemptModal() {
    document.getElementById('modal-view-attempt').classList.add('hidden');
  }

  function renderHistorySubtab() {
    const box = document.getElementById('profile-subtab-content');
    if (state.historyAttempts.length === 0) {
      box.innerHTML = `
        <div class="p-8 text-center rounded-3xl bg-app-card border border-app-border space-y-2.5">
          <div class="w-12 h-12 mx-auto rounded-2xl bg-app-surface border border-app-border flex items-center justify-center text-slate-400">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          </div>
          <div class="text-xs font-bold text-white">История прохождений пока пуста</div>
          <p class="text-[11px] text-slate-400 leading-relaxed">
            Пройдите любой тест в приложении, и ваша статистика, точность и детальный разбор ответов сохранятся здесь.
          </p>
        </div>
      `;
      return;
    }

    let itemsHtml = state.historyAttempts.map((h, idx) => {
      const scoreStr = h.score || `${h.correct || 0}/${h.total || 0}`;
      const pct = h.pct !== undefined ? h.pct : (h.score && h.score.includes('%') ? h.score.split('(')[1].replace('%)', '') : '');
      const mins = h.duration ? String(Math.floor(h.duration / 60)).padStart(2, '0') : '';
      const secs = h.duration ? String(h.duration % 60).padStart(2, '0') : '';
      const timeStr = (mins && secs) ? `${mins}:${secs}` : '';
      const modeLabel = getModeNameRu(h.mode);

      // Compute skipped & errors accurately
      let skipped = 0;
      let errors = 0;
      if (h.questionsSnapshot && h.questionsSnapshot.length > 0) {
        skipped = h.questionsSnapshot.filter(q => q.userAnswer === undefined || q.userAnswer === null).length;
        errors = h.questionsSnapshot.filter(q => q.userAnswer !== undefined && q.userAnswer !== null && Number(q.userAnswer) !== Number(q.correct)).length;
      } else {
        skipped = (h.skipped !== undefined) ? h.skipped : 0;
        errors = (h.errors !== undefined) ? h.errors : Math.max(0, (h.total || 0) - (h.correct || 0) - skipped);
      }

      return `
        <div class="p-3.5 rounded-2xl bg-app-card border border-app-border space-y-2.5">
          <div class="flex justify-between items-start">
            <div class="min-w-0 flex-1">
              <div class="text-xs font-bold text-white truncate">${h.title || 'Тест'}</div>
              <div class="text-[10px] text-slate-400 mt-1 flex flex-wrap items-center gap-1.5">
                <span class="px-2 py-0.5 rounded-md bg-app-surface text-brand-300 font-semibold">${modeLabel}</span>
                <span>• ${h.date || 'Недавно'}</span>
                ${timeStr ? `<span class="flex items-center gap-1">• <svg class="w-3 h-3 text-slate-400 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>${timeStr}</span>` : ''}
              </div>
            </div>
            <div class="text-right shrink-0 ml-2">
              <div class="text-xs font-mono font-bold text-brand-400">${scoreStr}</div>
              ${pct ? `<div class="text-[10px] text-slate-400 font-mono">${pct}%</div>` : ''}
            </div>
          </div>
          <div class="pt-1 flex items-center justify-end gap-2 border-t border-app-border/40">
            <button onclick="openViewAttemptModal(${idx})" class="px-2.5 py-1 rounded-xl bg-app-surface hover:bg-brand-600/30 border border-app-border text-[10px] font-semibold text-brand-300 hover:text-white active:scale-95 transition flex items-center gap-1.5">
              <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
              <span>Просмотреть попытку</span>
            </button>
            ${h.testId ? `
              <button onclick="retakeTestFromHistory('${h.testId}')" class="px-2.5 py-1 rounded-xl bg-app-surface hover:bg-slate-700 border border-app-border text-[10px] font-semibold text-slate-300 hover:text-white active:scale-95 transition flex items-center gap-1.5">
                <svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                <span>Пройти снова</span>
              </button>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');

    box.innerHTML = `
      <div class="flex justify-between items-center px-1">
        <span class="text-xs font-bold text-slate-300">Всего попыток: ${state.historyAttempts.length}</span>
        <button onclick="clearHistoryList()" class="text-[10px] text-slate-500 hover:text-rose-400">
          Очистить историю
        </button>
      </div>
      <div class="space-y-2">
        ${itemsHtml}
      </div>
    `;
  }

  function retakeTestFromHistory(testId) {
    if (BUNDLED_TESTS[testId]) {
      selectTest(testId);
    }
  }

  function clearHistoryList() {
    if (!confirm('Очистить историю прохождений?')) return;
    state.historyAttempts = [];
    localStorage.removeItem('ohtest_history');
    renderHistorySubtab();
    document.getElementById('profile-attempts-count').innerText = 0;
  }

