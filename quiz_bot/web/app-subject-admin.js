let selectedSubjectIconKey = 'stethoscope';
let subjectIconWasManuallySelected = false;

function renderSubjectIconPicker(selectedKey, pickerId) {
  return `<div id="${pickerId}" class="grid grid-cols-6 sm:grid-cols-8 gap-1.5">${SUBJECT_ICON_CATALOG.map(icon => `
    <button type="button" onclick="selectSubjectIcon('${icon.key}')" data-subject-icon="${icon.key}" aria-label="${icon.label}" title="${icon.label}" aria-pressed="${icon.key === selectedKey}"
      class="aspect-square rounded-xl border flex items-center justify-center transition ${icon.key === selectedKey ? 'bg-brand-500/15 border-brand-500/50 text-brand-300' : 'bg-app-card border-app-border text-slate-400 hover:text-white hover:border-brand-500/40'}">
      ${renderSubjectIcon(icon.key, '')}
    </button>`).join('')}</div>`;
}

function updateSubjectIconPicker(iconKey) {
  document.querySelectorAll('[data-subject-icon]').forEach(button => {
    const active = button.dataset.subjectIcon === iconKey;
    button.setAttribute('aria-pressed', String(active));
    button.className = `aspect-square rounded-xl border flex items-center justify-center transition ${active ? 'bg-brand-500/15 border-brand-500/50 text-brand-300' : 'bg-app-card border-app-border text-slate-400 hover:text-white hover:border-brand-500/40'}`;
  });
}

function selectSubjectIcon(iconKey) {
  if (!SUBJECT_ICON_CATALOG.some(icon => icon.key === iconKey)) return;
  selectedSubjectIconKey = iconKey;
  subjectIconWasManuallySelected = true;
  updateSubjectIconPicker(iconKey);
}

function suggestAndSelectSubjectIcon(title) {
  if (subjectIconWasManuallySelected) return;
  selectedSubjectIconKey = suggestSubjectIcon(title);
  updateSubjectIconPicker(selectedSubjectIconKey);
}

async function saveSubjectEditor(subjectId = null) {
  const title = document.getElementById(subjectId ? 'edit-subj-title' : 'new-subj-title')?.value.trim();
  if (!title) return alert('Введите название предмета!');
  const iconKey = selectedSubjectIconKey;
  const id = subjectId || title.toLowerCase().replace(/[^a-zа-я0-9]/gi, '_');
  if (!subjectId && adminStore.subjects.some(item => item.id === id)) {
    return alert('Дисциплина с таким названием уже существует.');
  }
  const subject = adminStore.subjects.find(item => item.id === id);
  const previous = subject ? { ...subject } : null;
  if (subject) {
    subject.title = title;
    subject.icon_key = iconKey;
  } else {
    adminStore.subjects.push({ id, title, emoji: '📚', icon_key: iconKey, tests_count: 0 });
  }

  try {
    const response = await fetch(`/api/admin/${subject ? 'edit' : 'add'}_subject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.userId, id, title, emoji: subject?.emoji || '📚', icon_key: iconKey })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Не удалось сохранить дисциплину');
  } catch (error) {
    if (previous) Object.assign(subject, previous);
    else adminStore.subjects = adminStore.subjects.filter(item => item.id !== id);
    alert(error.message);
    return;
  }

  triggerHaptic('light');
  openAdminModal('subjects_and_tests');
  renderHomeSubjects();
}

function openSubjectEditor(subjectId) {
  const subject = adminStore.subjects.find(item => item.id === subjectId);
  if (!subject) return;
  selectedSubjectIconKey = subject.icon_key || suggestSubjectIcon(subject.title);
  subjectIconWasManuallySelected = true;
  document.getElementById('admin-modal-tools').classList.add('hidden');
  document.getElementById('admin-modal-title').textContent = 'Изменить дисциплину';
  document.getElementById('admin-modal-body').innerHTML = `
    <div class="space-y-3">
      <label class="block text-xs font-semibold text-slate-300">Название
        <input id="edit-subj-title" class="mt-1 w-full px-3 py-2 rounded-xl bg-app-card border border-app-border text-sm text-white">
      </label>
      <div class="text-xs font-semibold text-slate-300">Значок</div>
      ${renderSubjectIconPicker(selectedSubjectIconKey, 'edit-subj-icon-picker')}
      <button type="button" onclick="saveSubjectEditor('${subjectId}')" class="w-full py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-bold text-xs">Сохранить</button>
    </div>`;
  document.getElementById('edit-subj-title').value = subject.title;
}

function editSubjectPrompt(subjectId) {
  openSubjectEditor(subjectId);
}

function addNewSubject() {
  saveSubjectEditor();
}
