let selectedSubjectIconKey = 'stethoscope';
let subjectIconWasManuallySelected = false;

function renderSubjectIconPicker(selectedKey, pickerId) {
  const selected = SUBJECT_ICON_CATALOG.find(icon => icon.key === selectedKey) || SUBJECT_ICON_CATALOG[0];
  return `<div id="${pickerId}" class="subject-icon-picker">
    <div class="subject-icon-selection">
      <span class="subject-icon-preview" data-icon-preview>${renderSubjectIcon(selected.key)}</span>
      <span data-icon-selection-label aria-live="polite">${selected.label}</span>
    </div>
    <div class="subject-icon-filters">
      <input type="search" data-icon-search aria-label="Поиск значка предмета" placeholder="Поиск значка" oninput="filterSubjectIconPicker(this)">
      <select data-icon-group aria-label="Группа значков" onchange="filterSubjectIconPicker(this)">
        <option value="">Все группы</option>
        ${SUBJECT_ICON_GROUPS.map(group => `<option value="${group.key}">${group.label}</option>`).join('')}
      </select>
    </div>
    <div class="subject-icon-grid" role="group" aria-label="Значки предметов">${SUBJECT_ICON_CATALOG.map(icon => `
    <button type="button" onclick="selectSubjectIcon('${icon.key}')" data-subject-icon="${icon.key}" aria-label="${icon.label}" title="${icon.label}" aria-pressed="${icon.key === selectedKey}"
      class="subject-icon-option">
      ${renderSubjectIcon(icon.key, '')}
    </button>`).join('')}</div>
    <p class="subject-icon-empty" hidden>Значки не найдены</p>
  </div>`;
}

function filterSubjectIconPicker(control) {
  const picker = control.closest('.subject-icon-picker');
  const query = picker.querySelector('[data-icon-search]').value.trim().toLocaleLowerCase().replaceAll('ё', 'е');
  const group = picker.querySelector('[data-icon-group]').value;
  let visible = 0;
  picker.querySelectorAll('[data-subject-icon]').forEach(button => {
    const icon = SUBJECT_ICON_CATALOG.find(item => item.key === button.dataset.subjectIcon);
    const matches = (!group || icon.group === group) && `${icon.label} ${icon.key}`.toLocaleLowerCase().replaceAll('ё', 'е').includes(query);
    button.hidden = !matches;
    if (matches) visible++;
  });
  picker.querySelector('.subject-icon-empty').hidden = visible > 0;
}

function updateSubjectIconPicker(iconKey) {
  document.querySelectorAll('[data-subject-icon]').forEach(button => {
    const active = button.dataset.subjectIcon === iconKey;
    button.setAttribute('aria-pressed', String(active));
  });
  const selected = SUBJECT_ICON_CATALOG.find(icon => icon.key === iconKey);
  if (!selected) return;
  document.querySelectorAll('.subject-icon-picker').forEach(picker => {
    picker.querySelector('[data-icon-preview]').innerHTML = renderSubjectIcon(iconKey);
    picker.querySelector('[data-icon-selection-label]').textContent = selected.label;
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
