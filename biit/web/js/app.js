(() => {
  'use strict';

  const TOKEN = document.querySelector('meta[name="biit-token"]').content;
  const main = document.getElementById('main');
  const toastEl = document.getElementById('toast');
  let state = null;          // last /api/state
  let currentView = 'home';

  // ---------- helpers ----------
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const icon = (name) =>
    `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${window.BIIT_ICONS[name] || ''}</svg>`;

  // "2026-2027" after Arabic letters is drawn reversed by the bidi algorithm; isolate it.
  const bidi = (text) => esc(text).replace(/\d{4}-\d{4}/g, '<span class="ltr">$&</span>');
  // A folder name is one unit: English names read left-to-right as a whole.
  const folderName = (name) => /[\u0600-\u06FF]/.test(name)
    ? `<bdi dir="rtl">${bidi(name)}</bdi>` : `<span class="ltr">${esc(name)}</span>`;
  const driveName = (d) => `<span class="ltr">${esc(d.letter)}:${d.label ? ' (' + esc(d.label) + ')' : ''}</span>`;

  const gb = (bytes) => {
    const v = bytes / 1024 ** 3;
    return (v >= 100 ? Math.round(v) : v.toFixed(1)) + ' GB';
  };

  async function api(method, path, body) {
    let res;
    try {
      res = await fetch(path, {
        method,
        headers: { 'X-Biit-Token': TOKEN, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new Error('انقطع الاتصال بالتطبيق. أغلق النافذة وافتح التطبيق من جديد.');
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(typeof data.detail === 'string' ? data.detail : 'تعذر تنفيذ الطلب.');
      err.fields = data.fields || {};
      throw err;
    }
    return data;
  }

  let toastTimer;
  function toast(text, bad = false) {
    toastEl.textContent = text;
    toastEl.className = 'toast show' + (bad ? ' bad' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toastEl.className = 'toast'), 2600);
  }

  const settingsComplete = (s) => Boolean(s.school_name && s.teacher_name);
  const locationReady = (l) => l.status === 'ok' || l.status === 'moved';
  const semesterName = (n) => (n === 1 ? 'الفصل الأول' : 'الفصل الثاني');

  // ---------- home ----------
  async function viewHome() {
    state = await api('GET', '/api/state');
    const s = state.settings, loc = state.location, saved = state.settings_saved || {};
    const names = await api('GET',
      `/api/naming?academic_year=${encodeURIComponent(s.academic_year)}&semester=${s.semester}&naming_lang=${s.naming_lang}`);

    const steps = [
      {
        title: 'بيانات المدرسة والعام الدراسي', view: 'settings', done: settingsComplete(s),
        text: settingsComplete(s)
          ? bidi(`${s.school_name}، ${semesterName(s.semester)} ${s.academic_year}`)
          : 'اكتب اسم المدرسة واسم المعلم ليظهرا في البطاقات والاستمارات.',
      },
      {
        title: 'موقع الإنشاء على هذا الجهاز', view: 'location', done: locationReady(loc),
        text: locationReady(loc)
          ? `القرص ${driveName(loc)}، المتاح <span class="ltr">${gb(loc.free)}</span>`
          : loc.status === 'unset' ? 'اختر القرص الذي تُنشأ عليه مجلدات الطلبة.'
          : 'القرص المحفوظ غير متاح الآن. اختر قرصًا آخر.',
      },
      { title: 'الصفوف والشعب', view: 'sections', done: false, text: 'أنشئ شعبة لكل صف تريد تجهيزه.' },
      { title: 'قوائم الطلبة', view: 'roster', done: false, text: 'استورد كشوف الطلبة لربط الأسماء بالشعب.' },
      { title: 'توزيع الأجهزة', view: 'devices', done: false, text: 'مراجعة التوزيع التلقائي للطلبة على الأجهزة.' },
      { title: 'إنشاء المجلدات', view: 'treegen', done: false, text: 'فحص الخطة ثم إنشاء مجلدات الطلبة دفعة واحدة.' },
    ];

    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>تنظيم مجلدات الطلبة لمادة تقنية المعلومات</h1>
          <p>تظهر تسمية مجلد الصف الثاني عشر بعد حفظ العام الدراسي والفصل في الإعدادات.</p>
        </header>

        <div class="folder">
          <span class="folder-tab">مجلد الفصل الدراسي</span>
          <div class="folder-body">
            <div class="folder-name ${saved.academic_year && saved.semester ? '' : 'empty'}">${saved.academic_year && saved.semester ? folderName(names.grades['12']) : 'لم تُخزن بعد'}</div>
            <dl class="folder-meta">
              <div><dt>الموقع</dt><dd class="${locationReady(loc) ? '' : 'empty'}">${locationReady(loc) ? driveName(loc) : 'لم يُحدد بعد'}</dd></div>
              <div><dt>المدرسة</dt><dd class="${s.school_name ? '' : 'empty'}">${esc(s.school_name) || 'لم تُخزن بعد'}</dd></div>
              <div><dt>المعلم</dt><dd class="${s.teacher_name ? '' : 'empty'}">${esc(s.teacher_name) || 'لم تُخزن بعد'}</dd></div>
              <div><dt>أجهزة المختبر</dt><dd class="${saved.device_count ? '' : 'empty'}">${saved.device_count ? `${s.device_count} جهازًا` : 'لم تُخزن بعد'}</dd></div>
            </dl>
          </div>
        </div>

        <h2 class="steps-title">خطوات التجهيز</h2>
        <ol class="steps">
          ${steps.map((st, i) => st.later ? `
            <li class="step later">
              <span class="step-no">${i + 1}</span>
              <div><h3>${st.title}</h3></div>
              <span class="step-note">تُضاف في مرحلة قادمة</span>
            </li>` : `
            <li class="step ${st.done ? 'done' : 'todo'}">
              <span class="step-no">${st.done ? icon('check') : i + 1}</span>
              <div><h3>${st.title}</h3><p>${st.text}</p></div>
              <button class="btn ghost" data-go="${st.view}">${st.done ? 'تعديل' : 'ابدأ'}</button>
            </li>`).join('')}
        </ol>
      </section>`;
  }

  // ---------- location ----------
  let chosenLetter = null;
  let pickerOpen = false;

  function locationNotice(loc) {
    if (loc.status === 'ok') return `
      <div class="notice ok">${icon('circle-check')}
        <div><strong>تُنشأ المجلدات على القرص ${driveName(loc)}</strong>
        <p>المساحة المتاحة <span class="ltr">${gb(loc.free)}</span> من <span class="ltr">${gb(loc.total)}</span>. الاختيار محفوظ لهذا الجهاز.</p></div>
        ${pickerOpen ? '' : '<button class="btn ghost" id="change">' + icon('pencil') + 'تغيير</button>'}
      </div>`;
    if (loc.status === 'moved') return `
      <div class="notice warn">${icon('info')}
        <div><strong>تغيّر حرف القرص المحفوظ من <span class="ltr">${esc(loc.previous_letter)}:</span> إلى <span class="ltr">${esc(loc.letter)}:</span></strong>
        <p>هو القرص نفسه (${esc(loc.label) || 'بلا اسم'})، وحُدّث الحرف تلقائيًا. تأكد منه قبل الإنشاء.</p></div>
        ${pickerOpen ? '' : '<button class="btn ghost" id="change">' + icon('pencil') + 'تغيير</button>'}
      </div>`;
    if (loc.status === 'missing') return `
      <div class="notice bad">${icon('triangle-alert')}
        <div><strong>القرص المحفوظ ${driveName(loc)} غير موصول الآن</strong>
        <p>صِل القرص ثم حدّث القائمة، أو اختر قرصًا آخر من القائمة.</p></div>
      </div>`;
    if (loc.status === 'readonly') return `
      <div class="notice bad">${icon('triangle-alert')}
        <div><strong>لا يمكن إنشاء مجلدات على القرص المحفوظ <span class="ltr">${esc(loc.letter)}:</span></strong>
        <p>القرص للقراءة فقط أو أن الحساب الحالي لا يملك صلاحية الكتابة عليه. اختر قرصًا آخر.</p></div>
      </div>`;
    return '';
  }

  function driveRow(d, loc) {
    const used = d.total ? Math.round(((d.total - d.free) / d.total) * 100) : 0;
    const saved = locationReady(loc) && loc.letter === d.letter;
    const tags = [
      d.system ? 'قرص النظام' : d.kind === 'removable' ? 'وسيط قابل للإزالة' : 'قرص ثابت',
    ];
    return `
      <label class="drive ${d.writable ? '' : 'off'}">
        <input type="radio" name="drive" value="${esc(d.letter)}" ${d.writable ? '' : 'disabled'}
               ${chosenLetter === d.letter ? 'checked' : ''}>
        <span class="drive-letter">${esc(d.letter)}:</span>
        <span>
          <span class="drive-name">${esc(d.label) || 'بلا اسم'}</span>
          <span class="drive-tags">
            <span>${tags[0]}</span>
            ${saved ? '<span class="tag">المحفوظ</span>' : ''}
            ${d.recommended && !saved ? '<span class="tag pick">موصى به</span>' : ''}
            ${d.writable ? '' : '<span class="tag bad">لا يقبل الكتابة</span>'}
          </span>
        </span>
        <span class="drive-usage">
          <span class="usage-text"><span>المتاح <b class="ltr">${gb(d.free)}</b></span><span class="ltr">${gb(d.total)}</span></span>
          <span class="bar ${used >= 90 ? 'low' : ''}"><i style="width:${used}%"></i></span>
        </span>
      </label>`;
  }

  async function viewLocation() {
    const { drives, location: loc } = await api('GET', '/api/drives');
    const ready = locationReady(loc);
    if (!ready) pickerOpen = true;
    if (chosenLetter === null || !drives.some((d) => d.letter === chosenLetter && d.writable)) {
      chosenLetter = ready ? loc.letter : (drives.find((d) => d.recommended) || {}).letter || null;
    }
    const removablePicked = drives.some((d) => d.letter === chosenLetter && d.kind === 'removable');
    const unchanged = ready && chosenLetter === loc.letter;

    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>موقع الإنشاء</h1>
          <p>القرص الذي تُنشأ عليه مجلدات الطلبة في هذا الجهاز. يُحفظ الاختيار ويُعرض عليك للتأكيد قبل كل إنشاء.</p>
        </header>
        ${locationNotice(loc)}
        ${pickerOpen ? `
          <div class="drives-head">
            <h2>الأقراص الموجودة في هذا الجهاز</h2>
            <button class="btn ghost" id="refresh">${icon('refresh-cw')}تحديث القائمة</button>
          </div>
          ${drives.length ? `<div class="drives" role="radiogroup" aria-label="الأقراص">${drives.map((d) => driveRow(d, loc)).join('')}</div>` : `
            <div class="notice bad">${icon('triangle-alert')}<div><strong>لم يُعثر على أي قرص</strong>
            <p>تأكد من أن الأقراص غير مقفلة بالتشفير ثم حدّث القائمة.</p></div></div>`}
          ${removablePicked ? `<div class="notice warn" style="margin-top:14px">${icon('usb')}
            <div><strong>اخترت وسيطًا قابلًا للإزالة</strong>
            <p>يصلح لتجهيز المجلدات ثم نسخها إلى الأجهزة. لا تفصله أثناء الإنشاء، ولا تعتمد عليه مكانًا دائمًا لأعمال الطلبة.</p></div></div>` : ''}
          <div class="actions">
            <button class="btn" id="save-loc" ${chosenLetter && !unchanged ? '' : 'disabled'}>${icon('check')}حفظ الموقع</button>
            ${ready ? '<button class="btn ghost" id="cancel-loc">إلغاء</button>' : ''}
          </div>
          <p class="hint">الأفضل اختيار قرص غير قرص النظام إن وُجد، حتى لا تُفقد أعمال الطلبة عند إعادة تثبيت ويندوز. إن كان في الجهاز قرص <span class="ltr">C:</span> فقط فهو الخيار الوحيد.</p>
        ` : ''}
      </section>`;
  }

  // ---------- settings ----------
  let previewTimer;

  function readForm(form) {
    const f = new FormData(form);
    return {
      school_name: f.get('school_name'), teacher_name: f.get('teacher_name'),
      academic_year: f.get('academic_year'), semester: Number(f.get('semester')),
      naming_lang: f.get('naming_lang'), device_count: Number(f.get('device_count')),
    };
  }

  async function refreshPreview(form) {
    const d = readForm(form);
    const box = document.getElementById('tree');
    try {
      const { grades } = await api('GET',
        `/api/naming?academic_year=${encodeURIComponent(d.academic_year)}&semester=${d.semester}&naming_lang=${d.naming_lang}`);
      box.dir = d.naming_lang === 'ar' ? 'rtl' : 'ltr';
      box.innerHTML = ['5', '11', '12'].map((g) => `<li>${icon('folder')}${folderName(grades[g])}</li>`).join('');
    } catch {
      box.innerHTML = '<li>أكمل العام الدراسي لتظهر المعاينة</li>';
    }
  }

  async function viewSettings() {
    state = await api('GET', '/api/state');
    const s = state.settings, lim = state.limits;
    const field = (name, label, value, help = '', attrs = '') => `
      <div class="field" data-field="${name}">
        <label for="${name}">${label}</label>
        <input type="text" id="${name}" name="${name}" value="${esc(value)}" autocomplete="off" ${attrs}>
        ${help ? `<p class="help">${help}</p>` : ''}<p class="error" hidden></p>
      </div>`;
    const seg = (name, options, value) => `
      <div class="seg">${options.map(([v, t]) => `
        <input type="radio" id="${name}-${v}" name="${name}" value="${v}" ${String(value) === String(v) ? 'checked' : ''}>
        <label for="${name}-${v}">${t}</label>`).join('')}</div>`;

    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>الإعدادات</h1>
          <p>تُستخدم هذه البيانات في تسمية المجلدات وفي ترويسة الاستمارات والبطاقات.</p>
        </header>
        <form id="settings-form" class="settings" novalidate>
          <div>
            <fieldset class="fieldset">
              <legend>المدرسة والمعلم</legend>
              ${field('school_name', 'اسم المدرسة', s.school_name, '', 'maxlength="80"')}
              ${field('teacher_name', 'اسم المعلم', s.teacher_name, '', 'maxlength="80"')}
            </fieldset>

            <fieldset class="fieldset">
              <legend>العام والفصل</legend>
              <div class="row">
                ${field('academic_year', 'العام الدراسي', s.academic_year, 'مثال: <span class="ltr">2026-2027</span>', 'dir="ltr" inputmode="numeric" maxlength="9"')}
                <div class="field" data-field="semester">
                  <span class="label">الفصل الدراسي</span>
                  ${seg('semester', [[1, 'الأول'], [2, 'الثاني']], s.semester)}
                </div>
              </div>
            </fieldset>

            <fieldset class="fieldset">
              <legend>المجلدات والمختبر</legend>
              <div class="field" data-field="naming_lang">
                <span class="label">لغة تسمية المجلدات</span>
                ${seg('naming_lang', [['en', 'English'], ['ar', 'العربية']], s.naming_lang)}
                <p class="help">تسري على المجلدات التي تُنشأ بعد الحفظ، ولا تغيّر أسماء مجلدات موجودة.</p>
              </div>
              <div class="field" data-field="device_count">
                <label for="device_count">عدد أجهزة المختبر</label>
                <div class="count">
                  <span>${lim.min_devices}</span>
                  <input type="range" id="device_count" name="device_count" min="${lim.min_devices}" max="${lim.max_devices}" value="${s.device_count}">
                  <span>${lim.max_devices}</span>
                  <output id="count-out">${s.device_count}</output>
                </div>
                <p class="error" hidden></p>
              </div>
            </fieldset>

            <div class="actions"><button class="btn" type="submit">${icon('check')}حفظ الإعدادات</button></div>
          </div>

          <aside class="preview folder">
            <span class="folder-tab">معاينة التسمية</span>
            <div class="folder-body">
              <ul class="tree" id="tree"></ul>
              <p>أسماء مجلدات الفصل للصفوف الخامس والحادي عشر والثاني عشر.</p>
            </div>
          </aside>
        </form>
        <div class="folder developer-contact">
          <span class="folder-tab">تواصل مع المطوّر</span>
          <div class="folder-body">
            <p class="hint">أرسل بلاغًا عن مشكلة في التطبيق. ستُفتح رسالة بريد جاهزة، ويرجى إرفاق لقطة شاشة توضّح المشكلة قبل إرسالها.</p>
            <form id="developer-contact-form">
              <div class="field"><label for="developer-report">وصف المشكلة</label><textarea id="developer-report" class="text-input" rows="4" required maxlength="2000" placeholder="اكتب الخطوات التي أدت إلى المشكلة وما ظهر لك"></textarea></div>
              <label class="keep-line"><input id="developer-screenshot-confirm" type="checkbox" required> سأرفق لقطة شاشة في رسالة البريد قبل إرسالها</label>
              <div class="actions"><button class="btn" type="submit">${icon('clipboard-list')}إعداد بلاغ بالبريد الإلكتروني</button></div>
            </form>
            <p class="help">البريد: <a href="mailto:mahmoud.isma3el@gmail.com">mahmoud.isma3el@gmail.com</a></p>
          </div>
        </div>
      </section>`;
    refreshPreview(document.getElementById('settings-form'));
  }

  async function saveSettings(form) {
    form.querySelectorAll('.field').forEach((el) => {
      el.classList.remove('invalid');
      const e = el.querySelector('.error');
      if (e) e.hidden = true;
    });
    try {
      await api('PUT', '/api/settings', readForm(form));
      toast('حُفظت الإعدادات');
    } catch (err) {
      const entries = Object.entries(err.fields || {});
      entries.forEach(([name, msg]) => {
        const el = form.querySelector(`[data-field="${name}"]`);
        if (!el) return;
        el.classList.add('invalid');
        const e = el.querySelector('.error');
        if (e) { e.innerHTML = bidi(msg); e.hidden = false; }
      });
      if (entries.length) form.querySelector('.invalid input, .invalid select')?.focus();
      toast(err.message, true);
    }
  }

  // ---------- roster ----------
  let rosterState = { students: [], warnings: [], errors: [], sectionGrade: '', sectionLabel: '' };

  async function viewRoster() {
    const { sections } = await api('GET', '/api/sections');
    const sectionOpts = sections.map((s) =>
      `<option value="${esc(s.grade)}__${esc(s.label)}" ${
        rosterState.sectionGrade === s.grade && rosterState.sectionLabel === s.label ? 'selected' : ''
      }>${esc(s.grade)} - ${esc(s.label)}</option>`).join('');

    const savedSections = sections.length ? `<div class="saved-rosters">
      <h2>القوائم المحفوظة</h2>
      <p class="hint">اعرض أي شعبة محفوظة وصحّح أسماء جميع طلبتها، حتى الأسماء التي لم تُعلّم للمراجعة.</p>
      <div class="sections-list">${sections.map((s) => `<div class="section-card" data-grade="${esc(s.grade)}" data-label="${esc(s.label)}">
        <div class="section-info"><span class="section-grade">الصف ${esc(s.grade)}</span><span class="section-label">${esc(s.label)}</span><span class="section-count">${(s.students || []).length} طالبًا</span></div>
        <button class="btn ghost icon-btn roster-toggle" title="عرض القائمة" aria-expanded="false">${icon('chevron-down')}</button>
        <ol class="section-students" hidden>${(s.students || []).map((st, i) => `<li data-index="${i}">
          <span class="sec-name${st.suspect ? ' suspect' : ''}">${esc(st.name)}</span>
          <button class="btn ghost icon-only edit-student" title="تصحيح الاسم">${icon('pencil')}</button></li>`).join('')}</ol>
      </div>`).join('')}</div></div>` : '<p class="hint">لا توجد قوائم محفوظة بعد.</p>';

    const listHtml = rosterState.students.length
      ? `<div class="roster-result">
          ${rosterState.errors.length ? `<div class="notice bad">${icon('alert-circle')}<div>${rosterState.errors.map(esc).join('<br>')}</div></div>` : ''}
          ${rosterState.warnings.length ? `<div class="notice warn">${icon('triangle-alert')}<div><strong>تنبيهات</strong><ul>${rosterState.warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul></div></div>` : ''}
          <div class="roster-meta">
            <span>${icon('users')} <strong>${rosterState.students.length}</strong> طالبًا</span>
            ${sections.length ? `<div class="field" data-field="section_target">
              <label for="section-target">إضافة إلى شعبة</label>
              <div class="roster-assign-row">
                <select id="section-target" class="select">
                  <option value="">— اختر شعبة —</option>
                  ${sectionOpts}
                </select>
                <button class="btn" id="assign-roster">${icon('check')}إضافة</button>
              </div>
            </div>` : `<p class="hint">أنشئ شعبة أولًا في تبويب <strong>الصفوف والشعب</strong> لتتمكن من ربط هذه القائمة.</p>`}
          </div>
          <ol class="student-list">
            ${rosterState.students.map((st, i) =>
              `<li class="student-row ${st.suspect ? 'suspicious' : ''}" data-index="${i}">
                <span class="student-no">${i + 1}</span>
                <span class="student-name">${esc(st.name)}</span>
                ${st.suspect ? `<span class="badge warn">قد يحتاج مراجعة</span>` : ''}
                <button class="btn ghost icon-only roster-edit" title="تصحيح الاسم">${icon('pencil')}</button>
              </li>`).join('')}
          </ol>
        </div>`
      : '';

    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>قوائم الطلبة</h1>
          <p>استورد قائمة طلبة من ملف Excel لربطها بشعبة وتوزيع الأجهزة.</p>
        </header>

        <div class="upload-zone" id="drop-zone" role="button" tabindex="0" aria-label="منطقة رفع الملفات">
          <input type="file" id="roster-file" accept=".xlsx,.xls,.pdf" hidden>
          <input type="file" id="roster-files" accept=".xlsx,.xls,.pdf" multiple hidden>
          ${icon('upload')}
          <p>اسحب كشوف الطلبة هنا أو</p>
          <div class="upload-actions">
            <button class="btn ghost" id="browse-file">ملف واحد</button>
            <button class="btn" id="browse-files">${icon('layers')}كل الصفوف دفعة واحدة</button>
          </div>
          <p class="hint">xlsx أو pdf — الاستيراد الجماعي يقرأ الصف والشعبة من ترويسة كل ملف وينشئ شعبةً له</p>
        </div>
        <div id="roster-import-status"></div>
        ${listHtml}${savedSections}
      </section>`;
  }

  async function importRoster(file) {
    const statusEl = document.getElementById('roster-import-status');
    statusEl.innerHTML = `<div class="notice">${icon('circle-dashed')} <div>جارٍ المعالجة…</div></div>`;
    const form = new FormData();
    form.append('file', file);
    let res;
    try {
      res = await fetch('/api/roster/import', {
        method: 'POST',
        headers: { 'X-Biit-Token': TOKEN },
        body: form,
      });
    } catch {
      statusEl.innerHTML = `<div class="notice bad">${icon('triangle-alert')}<div>انقطع الاتصال بالتطبيق.</div></div>`;
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      statusEl.innerHTML = `<div class="notice bad">${icon('triangle-alert')}<div>${esc(typeof data.detail === 'string' ? data.detail : 'تعذرت القراءة.')}</div></div>`;
      return;
    }
    rosterState.students = data.students || [];
    rosterState.warnings = data.warnings || [];
    rosterState.errors = data.errors || [];
    if (data.grade && data.label) {
      rosterState.sectionGrade = data.grade;
      rosterState.sectionLabel = data.label;
    }
    statusEl.innerHTML = '';
    show('roster', true);
  }

  async function importRosterBatch(files) {
    const statusEl = document.getElementById('roster-import-status');
    statusEl.innerHTML = `<div class="notice">${icon('circle-dashed')} <div>جارٍ قراءة ${files.length} ملفًا…</div></div>`;
    const form = new FormData();
    [...files].forEach((f) => form.append('files', f));
    let res;
    try {
      res = await fetch('/api/roster/import-batch', {
        method: 'POST', headers: { 'X-Biit-Token': TOKEN }, body: form,
      });
    } catch {
      statusEl.innerHTML = `<div class="notice bad">${icon('triangle-alert')}<div>انقطع الاتصال بالتطبيق.</div></div>`;
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      statusEl.innerHTML = `<div class="notice bad">${icon('triangle-alert')}<div>${esc(typeof data.detail === 'string' ? data.detail : 'تعذرت القراءة.')}</div></div>`;
      return;
    }
    const done = data.imported || [];
    const skipped = data.skipped || [];
    const flagged = done.reduce((n, r) => n + r.suspect, 0);
    statusEl.innerHTML = `
      ${done.length ? `<div class="notice ok">${icon('circle-check')}<div>
        <strong>أُنشئت ${done.length} شعبة</strong>
        <ul class="batch-list">${done.map((r) => `<li><span class="ltr">${esc(r.grade)} ${esc(r.label)}</span> — ${r.count} طالبًا${r.suspect ? ` · ${r.suspect} بحاجة مراجعة` : ''}</li>`).join('')}</ul>
      </div></div>` : ''}
      ${skipped.length ? `<div class="notice warn">${icon('triangle-alert')}<div>
        <strong>${skipped.length} ملفًا لم يُستورد</strong>
        <ul class="batch-list">${skipped.map((r) => `<li>${esc(r.file)} — ${esc(r.reason)}</li>`).join('')}</ul>
      </div></div>` : ''}
      ${flagged ? `<div class="notice warn">${icon('triangle-alert')}<div>
        <strong>${flagged} اسمًا بحاجة مراجعة</strong>
        <p>افتح <strong>الصفوف والشعب</strong> وصحّح الأسماء المعلّمة قبل إنشاء المجلدات.</p>
      </div></div>` : ''}`;
  }

  // ---------- sections ----------
  async function viewSections() {
    const { sections } = await api('GET', '/api/sections');
    const grades = ['1','2','3','4','5','6','7','8','9','10','11','12'];

    const sectionCards = sections.length
      ? sections.map((s) => {
          const students = s.students || [];
          const flagged = students.filter((st) => st.suspect).length;
          return `
          <div class="section-card" data-grade="${esc(s.grade)}" data-label="${esc(s.label)}">
            <div class="section-info">
              <span class="section-grade">الصف ${esc(s.grade)}</span>
              <span class="section-label">${esc(s.label)}</span>
              <span class="section-count">${students.length} طالبًا</span>
              ${flagged ? `<span class="section-flag">${icon('triangle-alert')}${flagged} بحاجة مراجعة</span>` : ''}
            </div>
            <div class="section-actions">
              <button class="btn ghost icon-btn roster-toggle" ${students.length ? '' : 'disabled'}
                title="عرض الطلبة" aria-expanded="false">${icon('chevron-down')}</button>
              <button class="btn ghost icon-btn" data-delete-section="${esc(s.grade)}__${esc(s.label)}" title="حذف الشعبة" aria-label="حذف ${esc(s.grade)} - ${esc(s.label)}">
                ${icon('trash-2')}
              </button>
            </div>
            <ol class="section-students" hidden>${students.map((st, i) => `
              <li data-index="${i}">
                <span class="sec-name${st.suspect ? ' suspect' : ''}"
                  ${st.suspect ? 'title="قد يكون الاسم ناقصًا بسبب ترميز الـ PDF"' : ''}>${esc(st.name)}</span>
                <button class="btn ghost icon-only edit-student" title="تصحيح الاسم">${icon('pencil')}</button>
              </li>`).join('')}</ol>
          </div>`;
        }).join('')
      : `<div class="empty-state">${icon('layers')}<p>لا توجد شعب بعد. أنشئ شعبة أدناه.</p></div>`;

    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>الصفوف والشعب</h1>
          <p>أنشئ شعبة لكل صف تريد تجهيزه، ثم ارتبط بها قائمة الطلبة.</p>
        </header>

        <div class="sections-list" id="sections-list">${sectionCards}</div>

        <div class="folder">
          <span class="folder-tab">إضافة شعبة جديدة</span>
          <div class="folder-body">
            <form id="new-section-form" class="add-section-form" novalidate>
              <div class="row">
                <div class="field" data-field="grade">
                  <label for="new-grade">الصف</label>
                  <select id="new-grade" name="grade" class="select" required>
                    <option value="">— اختر —</option>
                    ${grades.map((g) => `<option value="${g}">${g}</option>`).join('')}
                  </select>
                  <p class="error" hidden></p>
                </div>
                <div class="field" data-field="label">
                  <label for="new-label">رمز الشعبة</label>
                  <input type="text" id="new-label" name="label" placeholder="مثال: أ أو 5-1" maxlength="10" autocomplete="off">
                  <p class="error" hidden></p>
                </div>
              </div>
              <div class="actions">
                <button class="btn" type="submit">${icon('plus')}إضافة شعبة</button>
              </div>
            </form>
          </div>
        </div>
      </section>`;
  }

  // ---------- devices ----------
  async function viewDevices() {
    const all = await api('GET', '/api/devices');
    const sections = all.sections;
    if (!sections.length) {
      main.innerHTML = `
        <section class="view">
          <header class="view-head"><h1>توزيع الأجهزة</h1></header>
          <div class="empty-state">${icon('monitor')}<p>لا توجد شعب. أنشئ شعبة أولًا في <strong>الصفوف والشعب</strong>.</p>
          <button class="btn ghost" data-go="sections">${icon('layers')}انتقل إلى الصفوف والشعب</button></div>
        </section>`;
      return;
    }

    const deviceCount = all.device_count;

    const tabsHtml = sections.map((s, i) =>
      `<button class="tab-btn ${i === 0 ? 'active' : ''}" data-tab="${i}">${esc(s.grade)} ${esc(s.label)}</button>`
    ).join('');

    const panels = sections.map((s, i) => {
      const active = i === 0 ? ' active' : '';
      if (!(s.students || []).length) {
        return `<div class="tab-panel${active}" data-panel="${i}">
          <div class="empty-state">${icon('users')}<p>لا يوجد طلبة في هذه الشعبة. استورد قائمة من <strong>قوائم الطلبة</strong>.</p></div></div>`;
      }
      return `<div class="tab-panel${active}" data-panel="${i}" data-grade="${s.grade}" data-label="${esc(s.label)}">
        ${devicePanel(s, s, deviceCount)}</div>`;
    });

    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>توزيع الأجهزة</h1>
          <p>التوزيع تلقائي على ${deviceCount} جهازًا. عطّل جهازًا خارج الخدمة أو ثبّت طالبًا على جهاز بعينه، ويتدفّق الباقون حوله.</p>
        </header>
        <div class="tabs">${tabsHtml}</div>
        <div class="tab-panels">${panels.join('')}</div>
      </section>`;
  }

  function devicePanel(section, plan, deviceCount) {
    // The roster is the spine: a teacher reads down the student list and says
    // which machine each one sits at. Devices are the choice, not the rows.
    const students = section.students || [];
    const disabled = new Set((plan.config.disabled || []).map(Number));
    const pinned = plan.config.pinned || {};
    const deviceOf = new Map();          // student key -> {no, seat}
    plan.slots.forEach((r) => {
      if (r.primary) deviceOf.set(r.primary.key, { no: r.device_no, seat: 1 });
      if (r.secondary) deviceOf.set(r.secondary.key, { no: r.device_no, seat: 2 });
    });
    const pinnedOf = new Map(Object.entries(pinned).map(([no, key]) => [key, Number(no)]));

    const chips = Array.from({ length: deviceCount }, (_, i) => i + 1).map((no) => `
      <button class="dev-chip${disabled.has(no) ? ' is-off' : ''}" data-device="${no}" data-off="${disabled.has(no) ? '1' : '0'}"
        title="${disabled.has(no) ? `جهاز ${no} خارج الخدمة — اضغط لإعادته` : `جهاز ${no} يعمل — اضغط لتعطيله`}">${no}</button>`).join('');

    const rows = students.map((st, i) => {
      const at = deviceOf.get(st.key);
      const pin = pinnedOf.get(st.key) || '';
      const opts = [`<option value=""${pin ? '' : ' selected'}>تلقائي</option>`]
        .concat(Array.from({ length: deviceCount }, (_, k) => k + 1)
          .filter((no) => !disabled.has(no))
          .map((no) => `<option value="${no}"${no === pin ? ' selected' : ''}>جهاز ${no}</option>`))
        .join('');
      return `<tr class="${pin ? 'is-pinned' : ''}${at ? '' : ' is-unseated'}">
        <td class="seat-no ltr">${i + 1}</td>
        <td class="seat-name${st.suspect ? ' suspect' : ''}">${esc(st.name)}</td>
        <td class="seat-at">${at
          ? `<span class="ltr">جهاز ${at.no}</span>${at.seat === 2 ? '<span class="seat-tag">مقعد ثانٍ</span>' : ''}`
          : '<span class="empty">بلا جهاز</span>'}</td>
        <td class="seat-pick"><select class="pin-sel" data-key="${esc(st.key)}" aria-label="جهاز ${esc(st.name)}">${opts}</select></td>
      </tr>`;
    }).join('');

    const dead = disabled.size;
    const pins = Object.keys(pinned).length;
    const notes = [];
    if (plan.unseated > 0) notes.push(`<div class="notice warn">${icon('triangle-alert')}<div>
      <strong>${plan.unseated} طالبًا بلا جهاز</strong>
      <p>الأجهزة العاملة لا تتسع للجميع حتى بطالبَين لكل جهاز. أعِد تشغيل جهاز معطّل أو عدّل العدد في <strong>الإعدادات</strong>.</p></div></div>`);
    else if (students.length > deviceCount - dead) notes.push(`<div class="notice">${icon('info')}<div>
      <strong>الطلبة (${students.length}) أكثر من الأجهزة العاملة (${deviceCount - dead})</strong>
      <p>الأجهزة الأولى تستوعب طالبَين، ويُوضَّح ذلك بوسم «مقعد ثانٍ».</p></div></div>`);

    return `${notes.join('')}
      <div class="dev-strip">
        <span class="dev-strip-label">أجهزة المختبر<br><span class="dim">اضغط رقمًا لتعطيله</span></span>
        <div class="dev-chips">${chips}</div>
      </div>
      <div class="panel-bar">
        <span class="dim">${dead ? `${dead} جهازًا خارج الخدمة · ` : ''}${pins ? `${pins} طالبًا مثبّتًا` : 'لا تثبيت يدوي'}</span>
        <button class="btn ghost" id="reset-pins" ${pins ? '' : 'disabled'}>${icon('refresh-cw')}إلغاء التثبيت اليدوي</button>
      </div>
      <table class="devices-table seats-table">
        <thead><tr><th></th><th>الطالب</th><th>الجهاز</th><th>تثبيت على</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function openNameEditor(li) {
    const current = li.querySelector('.sec-name').textContent;
    li.classList.add('editing');
    li.innerHTML = `
      <input type="text" class="name-input" value="${esc(current)}" autocomplete="off" aria-label="تصحيح اسم الطالب">
      <button class="btn icon-only name-save" title="حفظ">${icon('check')}</button>
      <button class="btn ghost icon-only name-cancel" title="إلغاء">${icon('x')}</button>`;
    const input = li.querySelector('.name-input');
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  function editImportedName(li) {
    const i = Number(li.dataset.index);
    const current = rosterState.students[i]?.name || '';
    li.innerHTML = `<span class="student-no">${i + 1}</span>
      <input class="name-input roster-name-input" value="${esc(current)}" aria-label="تصحيح اسم الطالب">
      <button class="btn icon-only roster-name-save" title="حفظ">${icon('check')}</button>
      <button class="btn ghost icon-only roster-name-cancel" title="إلغاء">${icon('x')}</button>`;
    li.querySelector('input')?.focus();
  }

  function saveImportedName(li) {
    const i = Number(li.dataset.index);
    const name = li.querySelector('.roster-name-input')?.value.trim().replace(/\s+/g, ' ');
    if (!name || name.split(' ').length < 2) return toast('الاسم يجب أن يتكوّن من كلمتين على الأقل.', true);
    rosterState.students[i] = { ...rosterState.students[i], name };
    show('roster', true);
    toast('حُفظ التصحيح في القائمة المستوردة.');
  }

  async function commitName(li) {
    const card = li.closest('.section-card');
    const returnView = li.closest('.saved-rosters') ? 'roster' : 'sections';
    const name = li.querySelector('.name-input').value.trim();
    try {
      await api('PATCH',
        `/api/sections/${card.dataset.grade}/${encodeURIComponent(card.dataset.label)}/students/${li.dataset.index}`,
        { name });
      toast('حُفظ الاسم.');
      show(returnView, true);
    } catch (err) {
      toast(err.message || 'تعذّر حفظ الاسم.', true);
    }
  }

  async function saveDeviceLayout(panel, mutate) {
    const grade = panel.dataset.grade;
    const label = panel.dataset.label;
    const url = `/api/sections/${grade}/${encodeURIComponent(label)}/devices`;
    const cur = await api('GET', url);
    const next = mutate({
      disabled: [...(cur.config.disabled || [])],
      pinned: { ...(cur.config.pinned || {}) },
    });
    const plan = await api('PUT', url, next);
    const section = { students: (await api('GET', `/api/sections`)).sections
      .find((s) => String(s.grade) === grade && s.label === label)?.students || [] };
    panel.innerHTML = devicePanel(section, plan, plan.slots.length);
  }

  // ---------- treegen ----------
  let treegenState = { plan: null, selectedSection: '', mode: 'matrix', iconsEnabled: false, lastCreated: null };

  async function viewTreegen() {
    const { sections } = await api('GET', '/api/sections');
    // Location can be changed after the app's initial state was loaded.
    // Refresh it here so this screen does not keep showing a stale "unset" state.
    state = await api('GET', '/api/state');
    const loc = state.location;
    const locOk = locationReady(loc);

    if (!sections.length) {
      main.innerHTML = `
        <section class="view">
          <header class="view-head"><h1>إنشاء المجلدات</h1></header>
          <div class="empty-state">${icon('folder-tree')}<p>أنشئ شعبة وأضف إليها طلبة أولًا.</p>
          <button class="btn ghost" data-go="sections">${icon('layers')}انتقل إلى الصفوف والشعب</button></div>
        </section>`;
      return;
    }

    const sectionsWithStudents = sections.filter((s) => s.students?.length > 0);
    if (!sectionsWithStudents.length) {
      main.innerHTML = `
        <section class="view">
          <header class="view-head"><h1>إنشاء المجلدات</h1></header>
          <div class="empty-state">${icon('users')}<p>لا يوجد طلبة في أي شعبة. استورد قائمة أولًا.</p>
          <button class="btn ghost" data-go="roster">${icon('users')}قوائم الطلبة</button></div>
        </section>`;
      return;
    }

    const selOpts = sectionsWithStudents.map((s) =>
      `<option value="${esc(s.grade)}__${esc(s.label)}" ${treegenState.selectedSection === `${s.grade}__${s.label}` ? 'selected' : ''}>${esc(s.grade)} - ${esc(s.label)} (${s.students.length} طالبًا)</option>`
    ).join('');

    const planHtml = treegenState.plan ? (() => {
      const p = treegenState.plan;
      const previewDirs = p.new_dirs || [];
      const remaining = p.new_count - previewDirs.length;
      return `
        <div class="tree-plan folder">
          <span class="folder-tab">${p.mode === 'matrix' ? 'خطة الشجرة الشاملة' : 'خطة الشعبة'}</span>
          <div class="folder-body">
            <dl class="folder-meta">
              <div><dt>مجلدات جديدة</dt><dd><span class="ltr">${p.new_count}</span></dd></div>
              <div><dt>موجودة مسبقًا</dt><dd><span class="ltr">${p.existing_count}</span></dd></div>
              ${p.mode === 'matrix' ? `<div><dt>الشعب</dt><dd><span class="ltr">${p.section_count}</span></dd></div>` : ''}
              <div><dt>الأجهزة المستخدمة</dt><dd><span class="ltr">${p.device_count}</span></dd></div>
              <div><dt>الطلبة في القوائم</dt><dd><span class="ltr">${p.total_students}</span></dd></div>
              <div><dt>الموقع</dt><dd>${locOk ? driveName(loc) : '<span class="bad">غير محدد</span>'}</dd></div>
            </dl>
            <div class="tree-path-row">
              <span>مسار الشجرة</span>
              <button class="tree-path-link" data-open-tree data-path="${esc(p.root)}" title="اضغط لفتح موقع الشجرة">${icon('folder')}${esc(p.root)}</button>
              <small>اضغط على المسار لفتحه في مستكشف الملفات.</small>
            </div>
            <ul class="tree tree-preview">
              ${previewDirs.map((d) => `<li>${icon('folder-plus')} ${folderName(d)}</li>`).join('')}
              ${remaining > 0 ? `<li class="tree-more">… و${remaining} مجلدًا آخر</li>` : ''}
            </ul>
            <div class="icon-pick">
              <label class="icon-check"><input id="tree-icons" type="checkbox" ${treegenState.iconsEnabled ? 'checked' : ''}>
                <span><strong>تطبيق أيقونات الأجهزة والشعب</strong><small>اختياري — تُولّد من أرقامها وتبقى مع المجلد عند نقله.</small></span></label>
              <div class="generated-icon-samples" aria-label="نماذج الأيقونات">
                <span class="generated-icon device-sample">PC01</span><span class="sample-caption">مجلد الجهاز</span>
                <span class="generated-icon section-sample">G12-01</span><span class="sample-caption">مجلد الصف والشعبة</span>
                <span class="sample-note">تدرج لوني حسب الجهاز أو الصف والشعبة</span>
              </div>
            </div>
            ${p.new_count === 0 ? `<div class="notice ok">${icon('check-circle-2')}<div>جميع المجلدات موجودة بالفعل. يمكنك تطبيق الأيقونات دون إعادة إنشاء الشجرة.</div></div>` : ''}
            <div class="actions">
              ${p.new_count ? `<button class="btn" id="execute-tree">${icon('folder-plus')}إنشاء ${p.new_count} مجلد</button>` : ''}
              ${p.new_count === 0 && treegenState.iconsEnabled ? `<button class="btn" id="execute-tree">${icon('folder')}تطبيق الأيقونات</button>` : ''}
              <button class="btn ghost" id="replan-tree">${icon('refresh-cw')}إعادة الفحص</button>
            </div>
          </div>
        </div>`;
    })() : '';

    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>إنشاء المجلدات</h1>
          <p>رتّب المجلدات حسب أجهزة المختبر، ثم اجمع تحت كل جهاز شعبه وطلبتها. لن تُحذف المجلدات أو الملفات الموجودة.</p>
        </header>

        ${!locOk ? `<div class="notice bad">${icon('triangle-alert')}<div><strong>لم يُحدد موقع الإنشاء</strong>
          <p>حدد القرص أولًا.</p></div>
          <button class="btn ghost" data-go="location">${icon('hard-drive')}تحديد الموقع</button></div>` : ''}

        <div class="folder">
          <span class="folder-tab">اختر طريقة الإنشاء</span>
          <div class="folder-body">
            <div class="tree-modes">
              <button class="tree-mode${treegenState.mode === 'matrix' ? ' active' : ''}" data-tree-mode="matrix">
                <strong>الشجرة الشاملة</strong><span>كل الشعب المرتبطة، مجمعة حسب الجهاز.</span></button>
              <button class="tree-mode${treegenState.mode === 'section' ? ' active' : ''}" data-tree-mode="section">
                <strong>شعبة واحدة</strong><span>إنشاء أو استكمال شعبة محددة فقط.</span></button>
            </div>
            ${treegenState.mode === 'section' ? `<div class="field">
              <label for="treegen-section">الشعبة</label>
              <div class="roster-assign-row">
                <select id="treegen-section" class="select">
                  <option value="">— اختر —</option>
                  ${selOpts}
                </select>
              </div>
            </div>` : `<p class="tree-mode-hint">سيشمل الفحص كل الشعب التي تحتوي على قوائم طلبة، مع احترام توزيع الأجهزة وتعطيل الأجهزة المحفوظ.</p>`}
            <div class="actions"><button class="btn ghost" id="plan-tree" ${locOk ? '' : 'disabled'}>${icon('eye')}فحص الشجرة</button></div>
          </div>
        </div>

        <div id="tree-plan-area">${planHtml}</div>
        ${treegenState.lastCreated ? `<div class="tree-created notice ok">
          ${icon('circle-check')}<div><strong>اكتمل الإنشاء.</strong>
            <button class="tree-path-link" data-open-tree data-path="${esc(treegenState.lastCreated.path)}">${icon('folder')}${esc(treegenState.lastCreated.path)}</button>
            <small>اضغط على المسار لعرض الشجرة في مستكشف الملفات.</small>
          </div></div>` : ''}
      </section>`;
  }

  // ---------- router ----------
  // ------------------------------------------------------------ deploy view
  const deployState = { section: '', pkg: null, settingsOpen: false, method: 'network' };

  async function viewDeploy() {
    const meta = await api('GET', '/api/deploy/settings');
    const inbox = await api('GET', '/api/collect/inbox');
    const s = meta.settings;
    if (!meta.sections.length) {
      main.innerHTML = `<section class="view"><header class="view-head"><h1>النشر والتجميع</h1></header>
        <div class="empty-state">${icon('layers')}<p>لا توجد شعب بطلبة بعد. ابدأ من <strong>الصفوف والشعب</strong>.</p></div></section>`;
      return;
    }
    if (!deployState.section || !meta.sections.some((x) => `${x.grade}__${x.label}` === deployState.section)) {
      deployState.section = `${meta.sections[0].grade}__${meta.sections[0].label}`;
    }
    const secOpts = meta.sections.map((x) =>
      `<option value="${x.grade}__${esc(x.label)}"${`${x.grade}__${x.label}` === deployState.section ? ' selected' : ''}>${esc(x.grade)} - ${esc(x.label)} (${x.students} طالبًا)</option>`).join('');
    const usbOpts = meta.removable.length
      ? meta.removable.map((d) => `<option value="${esc(d.root)}">${esc(d.letter)} ${esc(d.label || '')}</option>`).join('')
      : '<option value="">لا يوجد قرص فلاش</option>';
    const pkg = deployState.pkg;
    const copyBox = (id, val, title) => `
      <div class="cmd-row"><span class="cmd-title">${title}</span>
        <input type="text" class="cmd-input ltr" id="${id}" readonly value="${esc(val)}">
        <button class="btn ghost icon-only copy-cmd" data-copy="${id}" title="نسخ">${icon('clipboard-list')}</button></div>`;

    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>النشر والتجميع</h1>
          <p>انشر مجلدات كل جهاز إليه هو فقط، ثم اجمع الأعمال. ثلاثة مسارات حسب بنية المختبر — الأساس المضمون هو الفلاش، والشبكة أسرع متى ثبت وصول أجهزة الطلبة إلى جهازك.</p>
        </header>

        <div class="deploy-bar">
          <label>الشعبة <select id="dep-section">${secOpts}</select></label>
          <button class="btn ghost" id="dep-settings-toggle">${icon('settings')}إعدادات المسارات</button>
        </div>
        <div class="deploy-settings" id="dep-settings" ${deployState.settingsOpen ? '' : 'hidden'}>
          <label>مجلد الإسقاط على هذا الجهاز<input id="ds-drop" class="ltr" value="${esc(s.drop_root)}"></label>
          <label>مسار المشاركة كما تراه أجهزة الطلبة<input id="ds-unc" class="ltr" value="${esc(s.share_unc)}"></label>
          <label>نمط رقم الجهاز في اسم المضيف<input id="ds-pattern" class="ltr" value="${esc(s.hostname_pattern)}"></label>
          <label>القسم المستهدف على أجهزة الطلبة<input id="ds-target" class="ltr" value="${esc(s.target_root)}"></label>
          <button class="btn" id="dep-save-settings">${icon('check')}حفظ</button>
        </div>

        <div class="method-picker" role="radiogroup" aria-label="وسيلة النشر">
          ${[
            { id: 'network', title: 'الشبكة', note: 'مجلد مشارك على جهازك — الأسرع متى ثبت الوصول', ic: 'hard-drive' },
            { id: 'usb', title: 'الفلاش', note: 'الأساس المضمون — لا يحتاج شبكة إطلاقًا', ic: 'usb' },
            { id: 'veyon', title: 'Veyon', note: 'كل الأجهزة بنقرة — يبني على حزمة الشبكة', ic: 'monitor' },
          ].map((m) => `
          <button class="method-opt${deployState.method === m.id ? ' active' : ''}" data-method="${m.id}" role="radio" aria-checked="${deployState.method === m.id}">
            ${icon(m.ic)}<span class="opt-title">${m.title}</span><span class="opt-note">${m.note}</span>
          </button>`).join('')}
        </div>

        ${deployState.method === 'network' ? `
        <div class="method">
          <ol class="method-steps">
            <li><strong>مرة واحدة لكل مختبر:</strong> شارك مجلد الإسقاط من موجه أوامر بصلاحية مسؤول: <code class="ltr">net share biitdrop=${esc(s.drop_root)} /grant:everyone,CHANGE</code></li>
            <li><strong>مرة واحدة لكل جهاز طالب:</strong> افتح <code class="ltr">${esc(s.share_unc)}</code> وأدخل حساب جهاز المعلم مع «تذكّر بياناتي».</li>
            <li>اضغط <strong>إنشاء الحزمة</strong> هنا.</li>
            <li>على كل جهاز طالب شغّل <code class="ltr">deploy.bat</code> من مجلد الحزمة — ينسخ مجلدات وملفات ذلك الجهاز فقط، ولا يستبدل الملفات الموجودة.</li>
            <li>للتجميع لاحقًا شغّل <code class="ltr">collect.bat</code> — يرسل الأعمال إلى صندوق الوارد أدناه.</li>
          </ol>
          <div class="method-act">
            <button class="btn" id="dep-build-net">${icon('folder-plus')}إنشاء الحزمة في المجلد المشارك</button>
            ${pkg && pkg.transport === 'network' ? `<span class="ok-line">${icon('circle-check')}حزمة ${esc(pkg.label)}: ${pkg.devices.length} جهازًا · شغّل على الطالب: <code class="ltr">${esc(pkg.deploy_unc)}</code></span>` : ''}
          </div>
        </div>` : ''}

        ${deployState.method === 'usb' ? `
        <div class="method">
          <ol class="method-steps">
            <li>اختر القرص واضغط <strong>تصدير إلى الفلاش</strong>.</li>
            <li>على كل جهاز طالب شغّل من الفلاش <code class="ltr">BiTT\\deploy\\${esc(deployState.section.split('__')[1] || '')}\\deploy.bat</code>.</li>
            <li>للتجميع شغّل <code class="ltr">collect.bat</code> من الفلاش نفسه — الأعمال تُحفظ عليه.</li>
            <li>أعد الفلاش إلى هذا الجهاز واضغط <strong>استيراد التجميع</strong> أسفل الشاشة.</li>
          </ol>
          <div class="method-act">
            <select id="dep-usb-drive" ${meta.removable.length ? '' : 'disabled'}>${usbOpts}</select>
            <button class="btn" id="dep-build-usb" ${meta.removable.length ? '' : 'disabled'}>${icon('usb')}تصدير إلى الفلاش</button>
            ${pkg && pkg.transport === 'usb' ? `<span class="ok-line">${icon('circle-check')}صُدّرت حزمة ${esc(pkg.label)} (${pkg.devices.length} جهازًا) إلى <code class="ltr">${esc(pkg.package_root)}</code></span>` : ''}
          </div>
        </div>` : ''}

        ${deployState.method === 'veyon' ? `
        <div class="method">
          <ol class="method-steps">
            <li>أنشئ حزمة الشبكة أولًا (الزر أدناه) — Veyon لا ينقل ملفات، بل يشغّل سكربت الحزمة على كل جهاز دفعة واحدة.</li>
            <li>في Veyon Master حدد كل الأجهزة ثم <strong>تشغيل تطبيق</strong> والصق أمر النشر.</li>
            <li>في نهاية الحصة كرر الأمر بأمر التجميع.</li>
            <li>جهاز اسمه خارج نمط الترقيم: شغّل عليه <code class="ltr">deploy.bat</code> يدويًا أول مرة ليُسأل عن رقمه ويحفظه.</li>
          </ol>
          <div class="method-act method-cmds">
            ${pkg && pkg.transport === 'network'
              ? copyBox('cmd-dep', pkg.veyon_deploy, 'أمر النشر') + copyBox('cmd-col', pkg.veyon_collect, 'أمر التجميع')
              : `<button class="btn" id="dep-build-net">${icon('folder-plus')}إنشاء حزمة الشبكة</button>
                 <span class="dim">الأمران يظهران هنا بعد إنشائها.</span>`}
          </div>
        </div>` : ''}

        <div class="inbox-head">
          <h2>وارد التجميع</h2>
          <div>
            <button class="btn ghost" id="dep-import-usb" ${meta.removable.length ? '' : 'disabled'}>${icon('usb')}استيراد التجميع من الفلاش</button>
            <button class="btn ghost" id="dep-refresh">${icon('refresh-cw')}تحديث</button>
          </div>
        </div>
        ${inbox.batches.length ? inbox.batches.map((b) => `
          <div class="inbox-batch">
            <div class="inbox-meta"><strong class="ltr">${esc(b.label)}</strong><span class="ltr dim">${esc(b.date)}</span>
              ${b.missing.length ? `<span class="inbox-missing">${icon('triangle-alert')}لم يسلّم: ${b.missing.map((n) => `جهاز ${n}`).join('، ')}</span>`
                                 : `<span class="ok-line">${icon('circle-check')}اكتمل التسليم</span>`}</div>
            <div class="inbox-devices">${b.devices.map((d) => `<span class="inbox-chip ltr" title="${d.files} ملفًا">جهاز ${String(d.device_no).padStart(2, '0')} · ${d.files}</span>`).join('')}</div>
          </div>`).join('')
        : `<p class="dim">لم يصل شيء بعد. ما يرسله الطلبة عبر collect.bat أو تستورده من الفلاش يظهر هنا مبوّبًا بالشعبة واليوم، مع تسمية الأجهزة المتخلفة.</p>`}
      </section>`;
  }

  async function buildPackage(transport) {
    const [grade, label] = deployState.section.split('__');
    const body = { grade, label, transport };
    if (transport === 'usb') body.usb_root = document.getElementById('dep-usb-drive')?.value;
    try {
      const r = await api('POST', '/api/deploy/package', body);
      deployState.pkg = { ...r, transport };
      toast(`أُنشئت حزمة ${label} — ${r.folder_count} مجلدًا و${r.file_count || 0} ملفًا لـ${r.devices.length} جهازًا.`);
    } catch (err) {
      toast(err.message || 'تعذّر إنشاء الحزمة.', true);
    }
    show('deploy', true);
  }

  function copyCmd(id) {
    const el = document.getElementById(id);
    el.select();
    try { document.execCommand('copy'); } catch { /* fallback below */ }
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(el.value).catch(() => {});
    toast('نُسخ الأمر.');
  }

  // ------------------------------------------------------------ reports view
  const reportsState = { tab: 'guide', section: '', query: '', matches: null, device: null };

  async function viewReports() {
    const { guide, settings } = await api('GET', '/api/reports/distribution');
    if (!guide.length) {
      main.innerHTML = `<section class="view"><header class="view-head"><h1>التقارير والتحليل</h1></header>
        <div class="empty-state">${icon('clipboard-list')}<p>لا بيانات بعد — التقارير تُشتق من الشعب وتوزيع الأجهزة.</p></div></section>`;
      return;
    }
    const key = (g) => `${g.grade}__${g.label}`;
    if (!reportsState.section || !guide.some((g) => key(g) === reportsState.section)) {
      reportsState.section = key(guide[0]);
    }
    const current = guide.find((g) => key(g) === reportsState.section);
    const secOpts = guide.map((g) =>
      `<option value="${key(g)}"${key(g) === reportsState.section ? ' selected' : ''}>${esc(g.grade)} - ${esc(g.label)}</option>`).join('');
    const tabBtn = (id, label) =>
      `<button class="tab-btn ${reportsState.tab === id ? 'active' : ''}" data-rtab="${id}">${label}</button>`;
    const dev = (r) => r.device_no == null ? '<span class="empty">بلا جهاز</span>'
      : `جهاز ${String(r.device_no).padStart(2, '0')}${r.seat === 2 ? ' <span class="seat-tag">مقعد ثانٍ</span>' : ''}`;

    let body = '';
    if (reportsState.tab === 'guide') {
      body = `
        <div class="report-bar">
          <label>الشعبة <select id="rep-section">${secOpts}</select></label>
          <button class="btn" id="rep-print">${icon('printer')}طباعة</button>
        </div>
        <div id="print-area">
          <div class="print-head">
            <strong>دليل توزيع الطلبة على أجهزة المختبر</strong>
            <span>الشعبة: ${esc(current.grade)} - ${esc(current.label)}</span>
            ${settings.school_name ? `<span>${esc(settings.school_name)}</span>` : ''}
            <span class="ltr">${esc(settings.academic_year)} · ف${esc(settings.semester)}</span>
          </div>
          <table class="report-table">
            <thead><tr><th>م</th><th>اسم الطالب</th><th>الجهاز</th></tr></thead>
            <tbody>${current.rows.map((r) => `<tr><td class="ltr c">${r.no}</td><td>${esc(r.name)}</td><td>${dev(r)}</td></tr>`).join('')}</tbody>
          </table>
        </div>`;
    } else if (reportsState.tab === 'student') {
      const m = reportsState.matches;
      body = `
        <div class="report-bar">
          <div class="search-wrap">${icon('search')}<input id="rep-query" type="text" placeholder="اكتب جزءًا من اسم الطالب…" value="${esc(reportsState.query)}"></div>
          <button class="btn" id="rep-search">بحث</button>
        </div>
        ${m === null ? '' : !m.length ? `<p class="dim">لا نتائج لـ«${esc(reportsState.query)}».</p>` : m.map((x) => `
          <div class="student-hit">
            <div class="hit-name">${esc(x.name)}</div>
            <div class="hit-meta">
              <span>الشعبة <strong class="ltr">${esc(x.grade)} - ${esc(x.label)}</strong></span>
              <span>${x.device_no == null ? 'بلا جهاز' : `الجهاز <strong class="ltr">جهاز ${String(x.device_no).padStart(2, '0')}</strong>`}${x.shared_with ? ` · يشاركه ${esc(x.shared_with)}` : ''}</span>
              ${x.collected_files != null ? `<span>آخر تجميع: <strong>${x.collected_files}</strong> ملفًا</span>` : ''}
            </div>
            ${x.path ? `<code class="hit-path ltr">${esc(x.path)}</code>` : '<span class="dim">المسار يظهر بعد تحديد موقع الإنشاء.</span>'}
          </div>`).join('')}`;
    } else {
      const d = reportsState.device;
      body = `
        <div class="report-bar">
          <label>الشعبة <select id="rep-section">${secOpts}</select></label>
          ${d && d.date ? `<span class="dim">آخر تجميع: <span class="ltr">${esc(d.date)}</span></span>` : '<span class="dim">لا تجميع مستلمًا لهذه الشعبة بعد</span>'}
        </div>
        ${d ? `<table class="report-table">
          <thead><tr><th>الجهاز</th><th>الطلبة</th><th>الملفات الواصلة</th></tr></thead>
          <tbody>${d.rows.map((r) => `<tr class="${r.disabled ? 'is-off' : ''}">
            <td class="ltr">جهاز ${String(r.device_no).padStart(2, '0')}</td>
            <td>${r.disabled ? '<span class="dim">خارج الخدمة</span>' : r.students.map(esc).join(' · ') || '<span class="empty">فارغ</span>'}</td>
            <td class="ltr c">${r.disabled || !r.students.length ? '—' : r.files}</td>
          </tr>`).join('')}</tbody>
        </table>` : ''}`;
    }

    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>التقارير والتحليل</h1>
          <p>كل تقرير يُشتق لحظيًا من الربط القائم: القوائم، توزيع الأجهزة، وما وصل في وارد التجميع.</p>
        </header>
        <div class="tabs">${tabBtn('guide', 'دليل التوزيع')}${tabBtn('student', 'بحث عن طالب')}${tabBtn('devices', 'تقرير الأجهزة')}</div>
        ${body}
      </section>`;
  }

  async function loadDeviceReport() {
    const [grade, label] = reportsState.section.split('__');
    reportsState.device = await api('GET', `/api/reports/devices/${grade}/${encodeURIComponent(label)}`);
  }

  // -------------------------------------------------------- maintenance view
  const maintState = { plan: null, resetWord: '' };

  async function viewMaintenance() {
    const plan = maintState.plan;
    main.innerHTML = `
      <section class="view">
        <header class="view-head">
          <h1>تهيئة وأرشفة</h1>
          <p>الأرشفة تنقل أشجار الصفوف 1-11 جانبًا تمهيدًا لفصل جديد، والتهيئة تعيد التطبيق لنقطة الصفر. ملفات الطلبة على الأقراس لا تمسّها التهيئة أبدًا.</p>
        </header>

        <div class="method">
          <div class="method-head"><span class="method-key">${icon('archive')}</span><h2>أرشفة الشجرة</h2><span class="method-note">الثاني عشر يبقى في مكانه</span></div>
          <p class="maint-text">تنقل مجلدات الفصول من موقع الإنشاء إلى <code class="ltr">الأرشيف\\&lt;تاريخ اليوم&gt;</code> على نفس القرص — نقل لحظي، لا نسخ ولا حذف. وارد التجميع لا يُمس.</p>
          <div class="method-act">
            <button class="btn ghost" id="maint-plan">${icon('eye')}معاينة ما سيُنقل</button>
            ${plan ? `<button class="btn" id="maint-archive" ${plan.moves.length ? '' : 'disabled'}>${icon('archive')}نفّذ الأرشفة (${plan.moves.length})</button>` : ''}
          </div>
          ${plan ? (plan.error ? `<p class="dim">${esc(plan.error)}</p>` : `
            <div class="maint-plan">
              ${plan.moves.length ? `<p><strong>وجهة الأرشفة</strong></p><code class="ltr archive-destination">${esc(plan.dest)}</code>
                <p class="dim">مسارات النقل من موقع الإنشاء إلى الوجهة:</p>
                <ul>${plan.moves.map((m) => `<li><code class="ltr">${esc(m.source)}</code><span aria-hidden="true"> ← </span><code class="ltr">${esc(m.target)}</code></li>`).join('')}</ul>` : '<p class="dim">لا أشجار 1-11 في موقع الإنشاء.</p>'}
              ${plan.kept.length ? `<p class="keep-line">${icon('shield')}يبقى دون نقل: ${plan.kept.map(esc).join('، ')}</p>` : ''}
            </div>`) : ''}
        </div>

        <div class="method maint-danger">
          <div class="method-head"><span class="method-key">${icon('triangle-alert')}</span><h2>تهيئة التطبيق</h2><span class="method-note">لا رجوع عنها</span></div>
          <p class="maint-text">تمسح الشعب والإعدادات وإعدادات النشر وموقع الإنشاء وتخصيصات الأدوات المساعدة، ويعود التطبيق لحالة أول تشغيل. المجلدات المنشأة على الأقراص وما في وارد التجميع تبقى كما هي.</p>
          <div class="method-act">
            <input id="maint-word" type="text" placeholder="اكتب: تهيئة" autocomplete="off" value="${esc(maintState.resetWord)}">
            <button class="btn danger" id="maint-reset" ${maintState.resetWord === 'تهيئة' ? '' : 'disabled'}>${icon('trash-2')}تهيئة التطبيق</button>
          </div>
        </div>
      </section>`;
  }

  // --------------------------------------------------------- folder protection
  const protectionState = { data: null, plan: null, folder: '', scope: 'current', custom: '' };
  async function viewProtection() {
    protectionState.data = await api('GET', '/api/protection/state');
    const p = protectionState.data;
    main.innerHTML = `<section class="view">
      <header class="view-head"><h1>حماية المجلدات</h1>
        <p>امنع الحذف العرضي مع إبقاء القراءة والكتابة داخل المجلد. تحفظ الأداة نسخة من صلاحيات NTFS قبل كل تعديل.</p></header>
      <div class="notice ${p.admin ? 'ok' : 'warn'}">${icon(p.admin ? 'circle-check' : 'shield')}
        <div><strong>${p.admin ? 'التطبيق يعمل بصلاحيات مسؤول' : 'سيجرب التطبيق صلاحيات الحساب الحالي أولاً'}</strong>
          <p>إذا لم يسمح Windows للحساب بتعديل الأذونات، سيطلب حساباً مسؤولاً. يلزم أن يكون المجلد على NTFS أو ReFS؛ عدم وجود برنامج حماية لا يغير صلاحيات Windows. نظام قرصك الحالي: ${esc(p.file_system || 'لم يتحدد بعد')}.</p></div></div>
      <div class="folder"><span class="folder-tab">حماية مجلد</span><div class="folder-body">
        <div class="field"><label for="protect-folder">المجلد المستهدف</label><div class="inline-field">
          <input id="protect-folder" class="text-input ltr" placeholder="اختر مجلدًا أو اكتب مساره" value="${esc(protectionState.folder || protectionState.plan?.folder || '')}">
          <button class="btn ghost" id="protect-browse">${icon('folder')}استعراض</button></div></div>
        <div class="row protection-options">
          <div class="field"><label for="protect-scope">تطبيق الحماية على</label><select id="protect-scope" class="select">
            <option value="current" ${protectionState.scope === 'current' ? 'selected' : ''}>المستخدم الحالي (${esc(p.identity)})</option><option value="everyone" ${protectionState.scope === 'everyone' ? 'selected' : ''}>كل المستخدمين</option><option value="custom" ${protectionState.scope === 'custom' ? 'selected' : ''}>حساب محدد</option></select></div>
          <div class="field" id="protect-custom-field" ${protectionState.scope === 'custom' ? '' : 'hidden'}><label for="protect-custom">اسم الحساب مثل DOMAIN\\User</label><input id="protect-custom" class="text-input ltr" value="${esc(protectionState.custom)}"></div>
        </div>
        <div class="actions"><button class="btn ghost" id="protect-plan">${icon('eye')}معاينة الحماية</button>
          <button class="btn" id="protect-backup">${icon('archive')}نسخ الصلاحيات فقط</button></div>
        ${protectionState.plan ? `<div class="notice warn protection-preview"><div><strong>معاينة العملية</strong>
          <p>المجلد: <code class="ltr">${esc(protectionState.plan.folder)}</code></p>
          <p>الحساب: <code class="ltr">${esc(protectionState.plan.identity)}</code></p>
          <p>نظام الملفات: <code>${esc(protectionState.plan.file_system || 'غير معروف')}</code></p>
          <p>${esc(protectionState.plan.action)}. يمكنك استعادة الأذونات الأصلية من سجل النسخ أدناه.</p></div>
          <button class="btn" id="protect-apply">${icon('shield')}طبّق الحماية</button></div>` : ''}
      </div></div>
      <div class="folder"><span class="folder-tab">نسخ الصلاحيات واستعادتها</span><div class="folder-body">
        <p class="hint">عند تطبيق الحماية تُحفظ نسخة أصلية تلقائيًا. الاستعادة تعيد أذونات المجلد من النسخة المحددة.</p>
        ${p.backups.length ? `<div class="protection-backups">${p.backups.map((b) => `<div class="protection-backup">
          <div><strong>${b.locked ? 'حماية' : 'نسخة صلاحيات'}</strong><span class="ltr">${esc(b.folder)}</span>
            <small>${esc(b.identity || '—')} · ${esc(b.created_at)} · ${esc(b.status || 'جاهز')}${b.restored ? ' · تمت الاستعادة' : ''}</small>
            ${b.error ? `<small>${esc(b.error)}</small>` : ''}</div>
          <button class="btn ghost" data-protect-restore="${esc(b.id)}" ${b.restored || b.status === 'فشل' ? 'disabled' : ''}>استعادة الأذونات</button>
        </div>`).join('')}</div>` : '<p class="empty">لا توجد نسخ محفوظة بعد.</p>'}
      </div></div>
      <div class="folder"><span class="folder-tab">كلمة مرور الاستعادة</span><div class="folder-body">
        <p class="hint">كلمة مرور اختيارية داخل التطبيق. لا تستبدل حماية حساب Windows أو صلاحيات المسؤول.</p>
        <div class="row"><div class="field"><label for="protect-old-password">كلمة المرور الحالية ${p.password_enabled ? '' : '(اتركها فارغة عند أول تعيين)'}</label><input id="protect-old-password" type="password" class="text-input"></div>
          <div class="field"><label for="protect-new-password">كلمة مرور جديدة</label><input id="protect-new-password" type="password" class="text-input" minlength="6"></div></div>
        <div class="actions"><button class="btn" id="protect-set-password">${icon('shield')}حفظ كلمة المرور</button>
          ${p.password_enabled ? '<button class="btn ghost" id="protect-remove-password">إزالة كلمة المرور</button>' : ''}</div>
      </div></div>
    </section>`;
  }

  // ---------------------------------------------------------- folder moves
  const transferState = { sections: [], section: '', data: null, source: '', target: '', selected: [] };
  async function viewTransfers() {
    const response = await api('GET', '/api/sections');
    transferState.sections = (response.sections || []).filter((s) => s.students?.length);
    if (!transferState.sections.some((s) => `${s.grade}__${s.label}` === transferState.section))
      transferState.section = transferState.sections[0] ? `${transferState.sections[0].grade}__${transferState.sections[0].label}` : '';
    const sectionOptions = transferState.sections.map((s) => `<option value="${s.grade}__${esc(s.label)}" ${transferState.section === `${s.grade}__${s.label}` ? 'selected' : ''}>${s.grade} - ${esc(s.label)} (${s.students.length} طالبًا)</option>`).join('');
    let loadError = '';
    if (transferState.section) {
      const [grade, label] = transferState.section.split('__');
      try { transferState.data = await api('GET', `/api/transfers/state?${new URLSearchParams({ grade, label })}`); }
      catch (err) { transferState.data = null; loadError = err.message; }
    } else transferState.data = null;
    const data = transferState.data;
    if (data) {
      const occupied = data.devices.filter((d) => d.students.length);
      if (!occupied.some((d) => String(d.device_no) === transferState.source)) transferState.source = String(occupied[0]?.device_no || '');
      const targets = data.devices.filter((d) => !d.disabled && String(d.device_no) !== transferState.source);
      if (!targets.some((d) => String(d.device_no) === transferState.target)) transferState.target = String(targets[0]?.device_no || '');
      const sourceStudents = data.students.filter((s) => String(s.device_no) === transferState.source);
      transferState.selected = transferState.selected.filter((i) => sourceStudents.some((s) => s.index === i));
      const sourceOptions = occupied.map((d) => `<option value="${d.device_no}" ${String(d.device_no) === transferState.source ? 'selected' : ''}>جهاز ${String(d.device_no).padStart(2, '0')} · ${d.students.length} طالب</option>`).join('');
      const targetOptions = targets.map((d) => `<option value="${d.device_no}" ${String(d.device_no) === transferState.target ? 'selected' : ''}>جهاز ${String(d.device_no).padStart(2, '0')} · ${d.students.length}/2</option>`).join('');
      const studentRows = sourceStudents.map((s) => `<label class="transfer-student"><input type="checkbox" class="transfer-student-check" value="${s.index}" ${transferState.selected.includes(s.index) ? 'checked' : ''} ${s.folder_exists ? '' : 'disabled'}><span>${esc(s.name)}</span>${s.folder_exists ? '' : '<small>المجلد غير موجود</small>'}</label>`).join('');
      main.innerHTML = `<section class="view"><header class="view-head"><h1>نقل مجلدات الطلبة</h1><p>انقل مجلداً من جهاز إلى جهاز آخر داخل الشجرة الشاملة. يتحدث توزيع الأجهزة المحفوظ بعد النقل.</p></header>
        <div class="folder"><span class="folder-tab">اختيار الشعبة والأجهزة</span><div class="folder-body">
          <div class="field"><label for="transfer-section">الصف والشعبة</label><select id="transfer-section" class="select">${sectionOptions}</select></div>
          <div class="row"><div class="field"><label for="transfer-source">من الجهاز</label><select id="transfer-source" class="select">${sourceOptions}</select></div>
            <div class="field"><label for="transfer-target">إلى الجهاز</label><select id="transfer-target" class="select">${targetOptions}</select></div></div>
          <div class="notice warn">يستقبل الجهاز طالبين كحد أقصى. إذا كان الجهاز معطلاً، انقل مجلد الطالب إلى جهاز صالح.</div>
        </div></div>
        <div class="folder"><span class="folder-tab">مجلدات الطلبة على جهاز ${esc(transferState.source || '—')}</span><div class="folder-body">
          <div class="actions"><button class="btn ghost" id="transfer-select-all">تحديد الجميع على الجهاز</button></div>
          ${studentRows || '<p class="empty">لا يوجد طلبة موزعون على هذا الجهاز.</p>'}
          <div class="actions"><button class="btn" id="transfer-execute" ${transferState.selected.length && transferState.target ? '' : 'disabled'}>نقل المحدد (${transferState.selected.length})</button></div>
          <p class="help ltr">${esc(data.root)}</p>
        </div></div></section>`;
      return;
    }
    main.innerHTML = `<section class="view"><header class="view-head"><h1>نقل مجلدات الطلبة</h1><p>انقل مجلد الطالب بين أجهزة الشعبة بعد إنشاء الشجرة الشاملة.</p></header>
      ${transferState.sections.length ? `<div class="folder"><span class="folder-tab">اختيار الشعبة</span><div class="folder-body"><div class="field"><label for="transfer-section">الصف والشعبة</label><select id="transfer-section" class="select">${sectionOptions}</select></div>
        <div class="notice ${loadError ? 'warn' : 'bad'}">${esc(loadError || 'أنشئ الشجرة الشاملة أولاً من شاشة إنشاء المجلدات حتى تظهر مجلدات الأجهزة هنا.')}</div></div></div>` : '<div class="empty-state"><p>أضف قوائم الطلبة أولاً لاستخدام نقل المجلدات.</p><button class="btn ghost" data-go="roster">قوائم الطلبة</button></div>'}</section>`;
  }

  // --------------------------------------------------------- project forms
  const projectFormsState = { data: null, section: '', groupSize: null, groups: null, result: null, mode: 'auto', manualGroups: [] };
  async function viewProjectForms() {
    projectFormsState.data = await api('GET', '/api/project-forms/state');
    const d = projectFormsState.data;
    const customization = d.customization;
    if (projectFormsState.groupSize == null) projectFormsState.groupSize = Number(customization.project_form_group_size) || 5;
    const semester = Number(d.settings.semester);
    const semesterName = semester === 1 ? 'الأول' : 'الثاني';
    const year = d.settings.academic_year;
    const firstTopic = (semester - 1) * 2 + 1;
    const secondTopic = firstTopic + 1;
    if (!projectFormsState.section || !d.sections.some((s) => `${s.grade}__${s.label}` === projectFormsState.section))
      projectFormsState.section = d.sections[0] ? `${d.sections[0].grade}__${d.sections[0].label}` : '';
    const options = d.sections.map((s) => `<option value="${s.grade}__${esc(s.label)}" ${projectFormsState.section === `${s.grade}__${s.label}` ? 'selected' : ''}>${s.grade} - ${esc(s.label)} (${s.students} طالبًا)</option>`).join('');
    const groups = projectFormsState.groups;
    const currentSection = d.sections.find((s) => `${s.grade}__${s.label}` === projectFormsState.section);
    const assignedManual = new Set(projectFormsState.manualGroups.flat());
    const unassignedManual = (currentSection?.roster || []).filter((student) => !assignedManual.has(student.index));
    main.innerHTML = `<section class="view">
      <header class="view-head"><h1>استمارات المشاريع</h1>
        <p>تخصيص وإنشاء استمارات مجموعات الصف الثاني عشر. الفصل والعام الدراسي مأخوذان من الإعدادات العامة.</p></header>
      <div class="folder"><span class="folder-tab">تخصيص استمارة الفصل ${semesterName}</span><div class="folder-body">
        <div class="notice ok project-term-context">العام الدراسي <bdi class="ltr">${esc(year)}</bdi> · الفصل الدراسي ${semesterName}</div>
        <div class="row">
          <div class="field"><label for="project-topic-a">اسم المشروع الأول</label><input id="project-topic-a" class="text-input" maxlength="80" value="${esc(customization[`project_form_topic_${firstTopic}`])}" placeholder="اتركه فارغًا للإبقاء على اسم القالب"></div>
          <div class="field"><label for="project-topic-b">اسم المشروع الثاني</label><input id="project-topic-b" class="text-input" maxlength="80" value="${esc(customization[`project_form_topic_${secondTopic}`])}" placeholder="اتركه فارغًا للإبقاء على اسم القالب"></div>
        </div>
        <div class="row">
          <div class="field"><label for="project-section-format">الشعبة</label><input id="project-section-format" class="text-input ltr" maxlength="80" value="${esc(customization.project_form_section_format)}"><p class="help">مثال على اسم الشعبة: 12-2</p></div>
          <div class="field"><label for="project-group-format">رمز المجموعة</label><input id="project-group-format" class="text-input ltr" maxlength="80" value="${esc(customization.project_form_group_format)}"><p class="help">مثال على رمز المجموعة: 12-2_G03</p></div>
          <div class="field"><label for="project-custom-group-size">عدد أعضاء المجموعة</label><select id="project-custom-group-size" class="select">${[1,2,3,4,5].map(n => `<option value="${n}" ${Number(customization.project_form_group_size) === n ? 'selected' : ''}>${n}</option>`).join('')}</select></div>
        </div>
        <div class="actions"><button class="btn" id="project-customization-save">${icon('check')}حفظ تخصيص الاستمارة</button></div>
      </div></div>
      ${d.sections.length ? `<div class="folder"><span class="folder-tab">تجهيز الاستمارات</span><div class="folder-body">
        <div class="row"><div class="field"><label for="project-section">الشعبة</label><select id="project-section" class="select">${options}</select></div>
          <div class="field"><label for="project-group-size">عدد الطلبة في المجموعة (1–5)</label><select id="project-group-size" class="select">${[1,2,3,4,5].map(n => `<option value="${n}" ${projectFormsState.groupSize === n ? 'selected' : ''}>${n}</option>`).join('')}</select></div></div>
        <div class="project-mode-picker"><strong>طريقة إنشاء المجموعات</strong><div class="actions">
          <button class="btn ${projectFormsState.mode === 'auto' ? '' : 'ghost'}" data-project-mode="auto">توزيع تلقائي أبجدي</button>
          <button class="btn ${projectFormsState.mode === 'manual' ? '' : 'ghost'}" data-project-mode="manual">اختيار أعضاء المجموعات</button></div></div>
        ${projectFormsState.mode === 'manual' ? `<div class="manual-project-groups"><div class="field"><label for="project-manual-members">الطلبة غير المضافين إلى مجموعة</label>
          <select id="project-manual-members" class="select" multiple size="${Math.min(8, Math.max(4, unassignedManual.length))}">${unassignedManual.map((st) => `<option value="${st.index}">${esc(st.name)}</option>`).join('')}</select>
          <p class="help">اختر من طالب إلى 5، ثم أضفهم إلى مجموعة. يُرتب الأعضاء أبجدياً عند تجهيز الاستمارة.</p></div>
          <div class="actions"><button class="btn ghost" id="project-add-manual-group" ${unassignedManual.length ? '' : 'disabled'}>إضافة المحددين إلى مجموعة</button></div>
          <div class="project-groups">${projectFormsState.manualGroups.map((indices, i) => `<div class="project-group"><strong>المجموعة ${i + 1}</strong><span>${indices.map((index) => esc(currentSection.roster.find((st) => st.index === index)?.name || '')).sort((a,b) => a.localeCompare(b, 'ar')).join('، ')}</span><button class="btn ghost" data-project-remove-group="${i}">إزالة</button></div>`).join('') || '<p class="empty">لم تُنشأ مجموعات بعد.</p>'}</div>
          <p class="help">أضف جميع طلبة الشعبة مرة واحدة فقط قبل المعاينة.</p></div>` : ''}
        <div class="field"><label>مجلد حفظ الملفات</label><div class="inline-field"><input class="text-input ltr" id="project-output" readonly value="${esc(d.output_directory)}" placeholder="اختر مجلدًا للحفظ">
          <button class="btn ghost" id="project-output-browse">${icon('folder')}اختيار مجلد</button></div></div>
        <div class="actions"><button class="btn" id="project-preview">${icon('eye')}معاينة توزيع المجموعات</button>
          ${groups?.length && d.output_directory ? `<button class="btn" id="project-generate">${icon('folder-plus')}إنشاء ${groups.length} استمارة</button>` : ''}</div>
        ${groups ? `<div class="project-groups"><h2>${groups.length} مجموعة · الفصل ${semesterName} · ${esc(year)}</h2>
          ${groups.map(g => `<div class="project-group"><strong>المجموعة ${g.group}</strong><span>${g.students.map(esc).join('، ')}</span></div>`).join('')}</div>` : ''}
        ${projectFormsState.result ? `<div class="notice ok">${icon('circle-check')}<div><strong>أُنشئت الاستمارات في</strong><code class="ltr">${esc(projectFormsState.result.output_directory)}</code>
          <ul>${projectFormsState.result.created.map(f => `<li>مجموعة ${f.group}: ${esc(f.students.join('، '))}</li>`).join('')}</ul></div></div>` : ''}
      </div></div>` : `<div class="empty-state">${icon('clipboard-list')}<p>أنشئ شعبة للصف الثاني عشر واستورد قائمتها لبدء تجهيز الاستمارات.</p><button class="btn ghost" data-go="roster">قوائم الطلبة</button></div>`}
    </section>`;
  }

  // --------------------------------------------------------- student cards
  const cardFields = [
    ['activity1', 'نشاط عملي 1', 10], ['activity2', 'نشاط عملي 2', 10],
    ['practical_test', 'اختبار عملي', 10], ['short_test', 'اختبار قصير', 10],
    ['projects', 'المشاريع', 20],
  ];
  const cardsState = { records: [], index: 0, imported: false, sectionLabel: '', classInfo: '', style: 'classic', styles: {} };
  function chosenCardRecords() {
    return cardsState.records;
  }
  function cardMarkup(record, student, printable = false) {
    const s = cardsState.settings || {};
    const total = cardFields.reduce((n, f) => n + (Number(record.scores[f[0]]) || 0), 0);
    const semesterName = Number(s.semester) === 1 ? 'الأول' : 'الثاني';
    return `<article class="student-card-paper card-style-${esc(cardsState.style)}">
      <header class="card-header"><div class="card-brand"><strong>${esc(s.school_name || 'اسم المدرسة')}</strong><span>بطاقة أعمال الطالب</span></div>
        <div class="card-term"><span>العام الدراسي ${esc(s.academic_year || '')}</span><span>الفصل الدراسي ${semesterName}</span></div></header>
      <h2 class="card-student-name">${esc(student?.name || record.official_name || '')}</h2>
      <div class="student-card-meta"><span>${esc(cardsState.classInfo || 'الصف الثاني عشر')}</span>${cardsState.sectionLabel ? `<span>الشعبة: ${esc(cardsState.sectionLabel)}</span>` : ''}<span>الفصل ${semesterName}</span></div>
      <table><thead><tr><th>أداة التقويم</th><th>الدرجة</th><th>النهاية العظمى</th></tr></thead><tbody>
        ${cardFields.map(([key,label,max]) => `<tr><td>${label}</td><td>${printable ? esc(record.scores[key] ?? '—') : `<input type="number" class="card-score" data-score="${key}" min="0" max="${max}" step="0.5" value="${esc(record.scores[key] ?? '')}" aria-label="${label}">`}</td><td>${max}</td></tr>`).join('')}
      </tbody><tfoot><tr class="card-total"><th>المجموع الكلي</th><th>${total}</th><th>60</th></tr></tfoot></table>
      <footer class="card-teacher"><span>معلم المادة</span><strong>${esc(s.teacher_name || 'اسم المعلم')}</strong></footer>
    </article>`;
  }
  async function viewStudentCards() {
    const all = await api('GET', '/api/project-forms/state');
    cardsState.settings = all.settings;
    let mapping = '';
    if (cardsState.imported) {
      mapping = `<div class="card-mapping"><h2>البطاقات المستخرجة (${cardsState.records.length})</h2>
        <p class="hint">تُنشأ البطاقات مباشرة من الأسماء والدرجات الواردة في سجل التقويم.</p>
        <div class="field card-style-picker"><label for="cards-style">نمط البطاقة لهذه الشعبة</label><select id="cards-style" class="select">${Object.entries(cardsState.styles).map(([id,label]) => `<option value="${esc(id)}" ${cardsState.style === id ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select><p class="help">يُحفظ اختيار النمط لكل شعبة على حدة.</p></div>
        <div class="actions"><button class="btn" id="cards-preview">${icon('eye')}معاينة البطاقات</button>
          ${cardsState.records.length ? '<button class="btn ghost" id="cards-print">طباعة / حفظ PDF</button>' : ''}</div>
      </div>`;
      const matched = chosenCardRecords();
      if (matched.length) {
        const active = matched[Math.min(cardsState.index, matched.length - 1)];
        mapping += `<div class="cards-preview-tools"><button class="btn ghost" id="card-prev" ${cardsState.index <= 0 ? 'disabled' : ''}>السابق</button>
          <span>${cardsState.index + 1} / ${matched.length}</span><button class="btn ghost" id="card-next" ${cardsState.index >= matched.length - 1 ? 'disabled' : ''}>التالي</button></div>
          <div class="card-current">${cardMarkup(active)}</div>
          <div id="cards-print-set">${matched.map(r => cardMarkup(r, null, true)).join('')}</div>`;
      }
    }
    main.innerHTML = `<section class="view"><header class="view-head"><h1>بطاقة أعمال الطالب</h1>
      <p>أداة مستقلة: استورد سجل التقويم للفصل ${all.settings.semester} لإنشاء بطاقة لكل اسم فيه، دون الحاجة إلى قوائم الطلبة في التطبيق.</p></header>
      <div class="folder"><span class="folder-tab">استيراد سجل التقويم</span><div class="folder-body">
        <div class="field"><label for="cards-file">سجل التقويم (.xlsx)</label><input type="file" id="cards-file" accept=".xlsx"></div>
        <p class="hint">تُقرأ درجات النشاطين والاختبار العملي والقصير والمشاريع فقط. تُستخدم الأسماء كما وردت في السجل.</p>
        <div id="cards-status"></div>
      </div></div>${mapping}
    </section>`;
  }

  async function importAssessmentFile(file) {
    const status = document.getElementById('cards-status');
    status.innerHTML = `<div class="notice">${icon('circle-dashed')}<div>جارٍ قراءة الأسماء والدرجات من السجل…</div></div>`;
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/student-cards/import', {
        method: 'POST', headers: { 'X-Biit-Token': TOKEN }, body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'تعذرت قراءة الدرجات.');
      cardsState.records = data.records || []; cardsState.sectionLabel = data.section_label || '';
      cardsState.classInfo = data.class_info || '';
      const keyQuery = new URLSearchParams({ class_info: cardsState.classInfo, section_label: cardsState.sectionLabel });
      const styleData = await api('GET', `/api/student-cards/style?${keyQuery}`);
      cardsState.style = styleData.style; cardsState.styles = styleData.styles;
      cardsState.index = 0; cardsState.imported = true;
      await viewStudentCards();
      toast(`تم استخراج ${cardsState.records.length} بطاقة من السجل.`);
    } catch (err) {
      status.innerHTML = `<div class="notice bad">${icon('triangle-alert')}<div>${esc(err.message)}</div></div>`;
    }
  }

  const views = { home: viewHome, location: viewLocation, settings: viewSettings, roster: viewRoster, sections: viewSections, devices: viewDevices, transfers: viewTransfers, treegen: viewTreegen, deploy: viewDeploy, reports: viewReports, maintenance: viewMaintenance, protection: viewProtection, projectForms: viewProjectForms, studentCards: viewStudentCards };

  async function show(name, keepScroll = false) {
    currentView = name;
    document.querySelectorAll('.nav-item[data-view]').forEach((b) => {
      const on = b.dataset.view === name;
      b.classList.toggle('active', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    try {
      await views[name]();
    } catch (err) {
      main.innerHTML = `<section class="view"><div class="notice bad">${icon('triangle-alert')}
        <div><strong>تعذر عرض الصفحة</strong><p>${esc(err.message)}</p></div>
        <button class="btn ghost" data-go="${name}">إعادة المحاولة</button></div></section>`;
    }
    if (!keepScroll) main.scrollTop = 0;
  }

  window.BIIT_RUNTIME = { api, esc, icon, main, toast, show };

  // ---------- events ----------
  document.querySelector('.side').addEventListener('click', (e) => {
    const b = e.target.closest('.nav-item[data-view]');
    if (b) { pickerOpen = false; chosenLetter = null; show(b.dataset.view); }
  });

  document.getElementById('quit').addEventListener('click', async () => {
    try { await api('POST', '/api/shutdown'); } catch { /* already closed */ }
    document.body.innerHTML = '<p style="padding:48px;font-size:18px">أُغلق التطبيق. يمكنك إغلاق هذه الصفحة.</p>';
  });

  main.addEventListener('click', async (e) => {
    // nav: data-go
    const go = e.target.closest('[data-go]');
    if (go) { pickerOpen = false; chosenLetter = null; return show(go.dataset.go); }

    // tabs (devices view)
    const tab = e.target.closest('.tab-btn[data-tab]');
    if (tab) {
      const idx = tab.dataset.tab;
      main.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === idx));
      main.querySelectorAll('.tab-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === idx));
      return;
    }

    const btn = e.target.closest('button');
    if (!btn) return;

    // Folder protection
    if (btn.id === 'protect-browse') {
      const r = await api('POST', '/api/dialog/folder', { title: 'اختر المجلد المراد حمايته' });
      if (r.path) { protectionState.folder = r.path; document.getElementById('protect-folder').value = r.path; protectionState.plan = null; main.querySelector('.protection-preview')?.remove(); }
      return;
    }
    if (btn.id === 'protect-plan') {
      try {
        protectionState.folder = document.getElementById('protect-folder').value;
        protectionState.scope = document.getElementById('protect-scope').value;
        protectionState.custom = document.getElementById('protect-custom')?.value || '';
        protectionState.plan = await api('POST', '/api/protection/plan', {
          folder: protectionState.folder, scope: protectionState.scope, custom: protectionState.custom,
        });
        await viewProtection();
      } catch (err) { toast(err.message, true); protectionState.plan = null; await viewProtection(); }
      return;
    }
    if (btn.id === 'protect-apply') {
      if (!confirm('سيتم حفظ نسخة من الصلاحيات ثم منع حذف المجلد ومحتوياته. هل تريد المتابعة؟')) return;
      try {
        await api('POST', '/api/protection/lock', {
          folder: document.getElementById('protect-folder').value,
          scope: document.getElementById('protect-scope').value,
          custom: document.getElementById('protect-custom')?.value || '',
        });
        toast('طُبقت الحماية وحُفظت نسخة الاستعادة.'); protectionState.plan = null; await viewProtection();
      } catch (err) { toast(err.message, true); protectionState.plan = null; await viewProtection(); }
      return;
    }
    if (btn.id === 'protect-backup') {
      const folder = document.getElementById('protect-folder').value;
      if (!folder || !confirm('سيتم إنشاء نسخة من صلاحيات هذا المجلد. متابعة؟')) return;
      try { await api('POST', '/api/protection/backup', { folder }); toast('حُفظت نسخة الصلاحيات.'); await viewProtection(); }
      catch (err) { toast(err.message, true); await viewProtection(); }
      return;
    }
    const restoreBtn = btn.closest('[data-protect-restore]');
    if (restoreBtn) {
      const password = document.getElementById('protect-old-password')?.value || '';
      if (!confirm('ستُعاد صلاحيات المجلد من النسخة المحفوظة. متابعة؟')) return;
      try {
        await api('POST', `/api/protection/restore/${encodeURIComponent(restoreBtn.dataset.protectRestore)}`, { password });
        toast('استُعيدت صلاحيات المجلد.'); await viewProtection();
      } catch (err) { toast(err.message, true); }
      return;
    }
    if (btn.id === 'protect-set-password') {
      try {
        await api('PUT', '/api/protection/password', {
          old_password: document.getElementById('protect-old-password').value,
          new_password: document.getElementById('protect-new-password').value,
        });
        toast('حُفظت كلمة المرور.'); await viewProtection();
      } catch (err) { toast(err.message, true); }
      return;
    }
    if (btn.id === 'protect-remove-password') {
      try {
        await api('DELETE', '/api/protection/password', { password: document.getElementById('protect-old-password').value });
        toast('أزيلت كلمة المرور.'); await viewProtection();
      } catch (err) { toast(err.message, true); }
      return;
    }

    if (btn.id === 'transfer-select-all') {
      transferState.selected = [...main.querySelectorAll('.transfer-student-check:not(:disabled)')].map((input) => Number(input.value));
      return viewTransfers();
    }
    if (btn.id === 'transfer-execute') {
      if (!transferState.section || !transferState.selected.length || !transferState.target) return;
      if (!confirm(`نقل ${transferState.selected.length} مجلد إلى الجهاز ${transferState.target} وتحديث التوزيع؟`)) return;
      const [grade, label] = transferState.section.split('__');
      try {
        const result = await api('POST', '/api/transfers/execute', {
          grade: Number(grade), label, student_indices: transferState.selected,
          target_device: Number(transferState.target),
        });
        transferState.selected = [];
        toast(`نُقل ${result.moved.length} مجلد وتم تحديث توزيع الأجهزة.`);
        return viewTransfers();
      } catch (err) { toast(err.message, true); return; }
    }

    // Project form generation
    const projectMode = btn.closest('[data-project-mode]');
    if (projectMode) {
      projectFormsState.mode = projectMode.dataset.projectMode;
      projectFormsState.groups = null; projectFormsState.result = null;
      return viewProjectForms();
    }
    if (btn.id === 'project-add-manual-group') {
      const selected = [...document.getElementById('project-manual-members').selectedOptions].map((option) => Number(option.value));
      if (!selected.length || selected.length > 5) { toast('اختر من طالب واحد إلى خمسة للمجموعة.', true); return; }
      projectFormsState.manualGroups.push(selected);
      projectFormsState.groups = null; projectFormsState.result = null;
      return viewProjectForms();
    }
    const removeManualGroup = btn.closest('[data-project-remove-group]');
    if (removeManualGroup) {
      projectFormsState.manualGroups.splice(Number(removeManualGroup.dataset.projectRemoveGroup), 1);
      projectFormsState.groups = null; projectFormsState.result = null;
      return viewProjectForms();
    }
    if (btn.id === 'project-output-browse') {
      try {
        const r = await api('POST', '/api/project-forms/output', {});
        if (r.path) { projectFormsState.data.output_directory = r.path; projectFormsState.groups = null; await viewProjectForms(); }
      } catch (err) { toast(err.message, true); }
      return;
    }
    if (btn.id === 'project-customization-save') {
      const customization = { ...projectFormsState.data.customization };
      const firstTopic = (Number(projectFormsState.data.settings.semester) - 1) * 2 + 1;
      customization[`project_form_topic_${firstTopic}`] = document.getElementById('project-topic-a').value.trim();
      customization[`project_form_topic_${firstTopic + 1}`] = document.getElementById('project-topic-b').value.trim();
      customization.project_form_section_format = document.getElementById('project-section-format').value.trim();
      customization.project_form_group_format = document.getElementById('project-group-format').value.trim();
      customization.project_form_group_size = Number(document.getElementById('project-custom-group-size').value);
      try {
        const saved = await api('PUT', '/api/project-forms/customization', customization);
        projectFormsState.data.customization = saved.customization;
        projectFormsState.groupSize = saved.customization.project_form_group_size;
        projectFormsState.groups = null;
        projectFormsState.result = null;
        toast('حُفظ تخصيص استمارة هذا الفصل.');
        await viewProjectForms();
      } catch (err) { toast(err.message, true); }
      return;
    }
    if (btn.id === 'project-preview') {
      const [grade, label] = projectFormsState.section.split('__');
      try {
        const r = await api('POST', '/api/project-forms/preview', {
          grade: Number(grade), label, group_size: Number(document.getElementById('project-group-size').value),
          manual: projectFormsState.mode === 'manual', manual_groups: projectFormsState.manualGroups,
        });
        projectFormsState.groupSize = Number(document.getElementById('project-group-size').value);
        projectFormsState.groups = r.groups; projectFormsState.result = null; await viewProjectForms();
      } catch (err) { toast(err.message, true); }
      return;
    }
    if (btn.id === 'project-generate') {
      if (!confirm('إنشاء ملفات Excel جديدة دون الكتابة فوق الملفات الموجودة؟')) return;
      const [grade, label] = projectFormsState.section.split('__');
      try {
        projectFormsState.result = await api('POST', '/api/project-forms/generate', {
          grade, label, group_size: Number(document.getElementById('project-group-size').value),
          output_directory: document.getElementById('project-output').value,
          manual: projectFormsState.mode === 'manual', manual_groups: projectFormsState.manualGroups,
        });
        toast(`أُنشئت ${projectFormsState.result.group_count} استمارة.`); await viewProjectForms();
      } catch (err) { toast(err.message, true); }
      return;
    }

    // Student card preview and print-to-PDF
    if (btn.id === 'cards-preview') { cardsState.index = 0; return viewStudentCards(); }
    if (btn.id === 'card-prev') { cardsState.index = Math.max(0, cardsState.index - 1); return viewStudentCards(); }
    if (btn.id === 'card-next') { cardsState.index = Math.min(chosenCardRecords().length - 1, cardsState.index + 1); return viewStudentCards(); }
    if (btn.id === 'cards-print') { window.print(); return; }

    if (btn.hasAttribute('data-open-tree')) {
      btn.disabled = true;
      api('POST', '/api/tree/open', { path: btn.dataset.path })
        .then(() => toast('فُتح مسار الشجرة'))
        .catch((err) => toast(err.message, true))
        .finally(() => { if (btn.isConnected) btn.disabled = false; });
      return;
    }

    // reports
    const rtab = btn.closest('[data-rtab]');
    if (rtab) {
      reportsState.tab = rtab.dataset.rtab;
      if (reportsState.tab === 'devices') await loadDeviceReport();
      return show('reports', true);
    }
    if (btn.id === 'rep-print') { window.print(); return; }
    if (btn.id === 'rep-search') {
      reportsState.query = document.getElementById('rep-query').value.trim();
      reportsState.matches = reportsState.query
        ? (await api('GET', `/api/reports/student?q=${encodeURIComponent(reportsState.query)}`)).matches
        : null;
      return show('reports', true);
    }

    // maintenance
    if (btn.id === 'maint-plan') {
      maintState.plan = await api('GET', '/api/maintenance/archive/plan');
      return show('maintenance', true);
    }
    if (btn.id === 'maint-archive') {
      try {
        const r = await api('POST', '/api/maintenance/archive');
        toast(r.failed.length
          ? `نُقل ${r.moved.length} وتعذّر ${r.failed.length} — أغلق أي ملف مفتوح وأعد المحاولة.`
          : `أُرشف ${r.moved.length} مجلدًا.`, r.failed.length > 0);
      } catch (err) { toast(err.message || 'تعذّرت الأرشفة.', true); }
      maintState.plan = null;
      return show('maintenance', true);
    }
    if (btn.id === 'maint-reset') {
      try {
        await api('POST', '/api/maintenance/reset', { confirm: maintState.resetWord });
        maintState.resetWord = '';
        toast('أُعيد التطبيق إلى الإعدادات الافتراضية.');
        state = null;
        return show('home', true);
      } catch (err) { toast(err.message || 'تعذّرت التهيئة.', true); return; }
    }

    // deploy & collect
    if (btn.id === 'dep-settings-toggle') {
      deployState.settingsOpen = !deployState.settingsOpen;
      document.getElementById('dep-settings').hidden = !deployState.settingsOpen;
      return;
    }
    if (btn.id === 'dep-save-settings') {
      try {
        await api('PUT', '/api/deploy/settings', {
          drop_root: document.getElementById('ds-drop').value,
          share_unc: document.getElementById('ds-unc').value,
          hostname_pattern: document.getElementById('ds-pattern').value,
          target_root: document.getElementById('ds-target').value,
        });
        deployState.pkg = null;   // paths changed; an old package may mislead
        toast('حُفظت الإعدادات.');
      } catch (err) { toast(err.message || 'تعذّر الحفظ.', true); }
      return show('deploy', true);
    }
    const methodOpt = btn.closest('.method-opt');
    if (methodOpt) { deployState.method = methodOpt.dataset.method; return show('deploy', true); }
    if (btn.id === 'dep-build-net') return buildPackage('network');
    if (btn.id === 'dep-build-usb') return buildPackage('usb');
    if (btn.id === 'dep-refresh') return show('deploy', true);
    if (btn.id === 'dep-import-usb') {
      try {
        const r = await api('POST', '/api/collect/import-usb',
          { usb_root: document.getElementById('dep-usb-drive')?.value });
        toast(`استُورد ${r.copied} ملفًا${r.skipped ? ` — ${r.skipped} موجود مسبقًا` : ''}.`);
      } catch (err) { toast(err.message || 'تعذّر الاستيراد.', true); }
      return show('deploy', true);
    }
    const copyBtn = btn.closest('.copy-cmd');
    if (copyBtn) return copyCmd(copyBtn.dataset.copy);

    // sections: show or hide a section's students
    const rosterToggle = btn.closest('.roster-toggle');
    if (rosterToggle) {
      const list = rosterToggle.closest('.section-card').querySelector('.section-students');
      const open = list.hidden;
      list.hidden = !open;
      rosterToggle.setAttribute('aria-expanded', String(open));
      rosterToggle.classList.toggle('is-open', open);
      return;
    }

    // sections: correct a name the PDF mangled
    const editBtn = btn.closest('.edit-student');
    if (editBtn) return openNameEditor(editBtn.closest('li'));

    const saveName = btn.closest('.name-save');
    if (saveName) return commitName(saveName.closest('li'));

    const cancelName = btn.closest('.name-cancel');
    if (cancelName) return show(cancelName.closest('.saved-rosters') ? 'roster' : 'sections', true);

    // devices: take a machine out of service, or put it back
    const devChip = btn.closest('.dev-chip');
    if (devChip) {
      const no = Number(devChip.dataset.device);
      const off = devChip.dataset.off === '1';
      return saveDeviceLayout(devChip.closest('.tab-panel'), (cfg) => {
        cfg.disabled = off ? cfg.disabled.filter((d) => Number(d) !== no)
                           : [...cfg.disabled, no];
        if (!off) delete cfg.pinned[String(no)];   // a dead machine holds nobody
        return cfg;
      });
    }

    // devices: drop every manual pin, keep machines that are out of service
    if (btn.id === 'reset-pins') {
      return saveDeviceLayout(btn.closest('.tab-panel'), (cfg) => ({ ...cfg, pinned: {} }));
    }

    // location buttons
    if (btn.id === 'change') { pickerOpen = true; return show('location', true); }
    if (btn.id === 'cancel-loc') { pickerOpen = false; chosenLetter = null; return show('location'); }
    if (btn.id === 'refresh') { await show('location', true); return toast('حُدّثت القائمة'); }
    if (btn.id === 'save-loc') {
      btn.disabled = true;
      try {
        await api('PUT', '/api/location', { letter: chosenLetter });
        pickerOpen = false;
        await show('location');
        toast('حُفظ الموقع');
      } catch (err) {
        toast(err.message, true);
        show('location', true);
      }
      return;
    }

    // roster buttons
    if (btn.id === 'browse-file') { document.getElementById('roster-file')?.click(); return; }
    if (btn.id === 'browse-files') { document.getElementById('roster-files')?.click(); return; }
    if (btn.id === 'assign-roster') {
      const sel = document.getElementById('section-target');
      if (!sel?.value) { toast('اختر شعبة أولًا', true); return; }
      const [grade, label] = sel.value.split('__');
      api('PUT', `/api/sections/${encodeURIComponent(grade)}/${encodeURIComponent(label)}`, { students: rosterState.students })
        .then(() => { rosterState.sectionGrade = grade; rosterState.sectionLabel = label; toast('رُبطت القائمة بالشعبة'); show('roster', true); })
        .catch((err) => toast(err.message, true));
      return;
    }
    const rosterEdit = btn.closest('.roster-edit');
    if (rosterEdit) return editImportedName(rosterEdit.closest('.student-row'));
    const rosterSave = btn.closest('.roster-name-save');
    if (rosterSave) return saveImportedName(rosterSave.closest('.student-row'));
    const rosterCancel = btn.closest('.roster-name-cancel');
    if (rosterCancel) return show('roster', true);

    // sections: delete
    const delBtn = btn.closest('[data-delete-section]');
    if (delBtn) {
      const [grade, label] = delBtn.dataset.deleteSection.split('__');
      if (!confirm(`حذف الشعبة ${grade} ${label}؟`)) return;
      api('DELETE', `/api/sections/${encodeURIComponent(grade)}/${encodeURIComponent(label)}`)
        .then(() => { toast('حُذفت الشعبة'); show('sections'); })
        .catch((err) => toast(err.message, true));
      return;
    }

    // treegen buttons
    if (btn.id === 'plan-tree') {
      const request = { mode: treegenState.mode };
      if (treegenState.mode === 'section') {
        const sel = document.getElementById('treegen-section');
        if (!sel?.value) { toast('اختر شعبة أولًا', true); return; }
        treegenState.selectedSection = sel.value;
        const [grade, label] = sel.value.split('__');
        Object.assign(request, { grade, label });
      }
      api('POST', '/api/tree/plan', request)
        .then((plan) => { treegenState.plan = plan; show('treegen', true); })
        .catch((err) => toast(err.message, true));
      return;
    }
    const treeMode = btn.closest('[data-tree-mode]');
    if (treeMode) {
      treegenState.mode = treeMode.dataset.treeMode;
      treegenState.plan = null;
      show('treegen', true);
      return;
    }
    if (btn.id === 'execute-tree') {
      btn.disabled = true;
      const request = { mode: treegenState.mode,
                        icons: !!document.getElementById('tree-icons')?.checked };
      if (treegenState.mode === 'section') {
        const [grade, label] = treegenState.selectedSection.split('__');
        Object.assign(request, { grade, label });
      }
      api('POST', '/api/tree/create', request)
        .then((res) => {
          treegenState.plan = null;
          treegenState.lastCreated = { path: res.root };
          const issueCount = (res.errors || []).length + (res.icon_errors || []).length;
          toast(`أُنشئ ${res.created} مجلدًا، وتُخطّي ${res.skipped}${issueCount ? ` — تعذّر ${issueCount}` : ''}`, issueCount > 0);
          show('treegen', true);
        })
        .catch((err) => { btn.disabled = false; toast(err.message, true); });
      return;
    }
    if (btn.id === 'replan-tree') {
      const request = { mode: treegenState.mode };
      if (treegenState.mode === 'section') {
        const [grade, label] = treegenState.selectedSection.split('__');
        Object.assign(request, { grade, label });
      }
      api('POST', '/api/tree/plan', request)
        .then((plan) => { treegenState.plan = plan; show('treegen', true); })
        .catch((err) => toast(err.message, true));
      return;
    }
  });

  main.addEventListener('change', (e) => {
    if (e.target.name === 'drive') { chosenLetter = e.target.value; show('location', true); }
    if (e.target.id === 'roster-file') { const f = e.target.files?.[0]; if (f) importRoster(f); }
    if (e.target.id === 'roster-files') { const fs = e.target.files; if (fs?.length) importRosterBatch(fs); }
    if (e.target.id === 'protect-scope') {
      protectionState.scope = e.target.value;
      const field = document.getElementById('protect-custom-field');
      if (field) field.hidden = e.target.value !== 'custom';
      protectionState.plan = null;
      main.querySelector('.protection-preview')?.remove();
    }
    if (e.target.id === 'protect-folder') protectionState.folder = e.target.value;
    if (e.target.id === 'protect-custom') protectionState.custom = e.target.value;
    if (e.target.id === 'project-section') {
      projectFormsState.section = e.target.value; projectFormsState.groups = null; projectFormsState.result = null; projectFormsState.manualGroups = []; show('projectForms', true);
    }
    if (e.target.id === 'project-group-size') { projectFormsState.groupSize = Number(e.target.value); projectFormsState.groups = null; }
    if (e.target.id === 'transfer-section') {
      transferState.section = e.target.value; transferState.data = null; transferState.source = ''; transferState.target = ''; transferState.selected = []; show('transfers', true);
    }
    if (e.target.id === 'transfer-source') {
      transferState.source = e.target.value; transferState.selected = []; show('transfers', true);
    }
    if (e.target.id === 'transfer-target') transferState.target = e.target.value;
    if (e.target.classList.contains('transfer-student-check')) {
      const index = Number(e.target.value);
      transferState.selected = e.target.checked
        ? [...new Set([...transferState.selected, index])]
        : transferState.selected.filter((item) => item !== index);
      const button = document.getElementById('transfer-execute');
      if (button) { button.disabled = !transferState.selected.length || !transferState.target; button.textContent = `نقل المحدد (${transferState.selected.length})`; }
    }
    if (e.target.id === 'cards-file' && e.target.files?.[0]) importAssessmentFile(e.target.files[0]);
    if (e.target.id === 'cards-style') {
      cardsState.style = e.target.value;
      api('PUT', '/api/student-cards/style', {
        class_info: cardsState.classInfo, section_label: cardsState.sectionLabel,
        style: cardsState.style,
      }).then(() => toast('حُفظ نمط البطاقة لهذه الشعبة.'))
        .catch((err) => toast(err.message, true));
    }
    if (e.target.id === 'treegen-section') { treegenState.plan = null; treegenState.selectedSection = e.target.value; }
    if (e.target.id === 'tree-icons') {
      treegenState.iconsEnabled = e.target.checked;
      show('treegen', true);
    }

    if (e.target.id === 'dep-section') { deployState.section = e.target.value; deployState.pkg = null; show('deploy', true); }

    if (e.target.id === 'rep-section') {
      reportsState.section = e.target.value;
      if (reportsState.tab === 'devices') loadDeviceReport().then(() => show('reports', true));
      else show('reports', true);
    }

    // devices: fix this student to one machine, or hand the seat back to auto
    if (e.target.classList.contains('pin-sel')) {
      const key = e.target.dataset.key;
      const no = e.target.value;
      saveDeviceLayout(e.target.closest('.tab-panel'), (cfg) => {
        // One student, one machine — and one machine holds one pin.
        Object.keys(cfg.pinned).forEach((d) => {
          if (cfg.pinned[d] === key || d === no) delete cfg.pinned[d];
        });
        if (no) cfg.pinned[no] = key;
        return cfg;
      });
    }
  });

  main.addEventListener('input', (e) => {
    if (e.target.id === 'maint-word') {
      maintState.resetWord = e.target.value.trim();
      document.getElementById('maint-reset').disabled = maintState.resetWord !== 'تهيئة';
      return;
    }
    if (e.target.id === 'protect-folder' || e.target.id === 'protect-custom') {
      if (e.target.id === 'protect-folder') protectionState.folder = e.target.value;
      else protectionState.custom = e.target.value;
      protectionState.plan = null;
      main.querySelector('.protection-preview')?.remove();
      return;
    }
    const score = e.target.closest('.card-score');
    if (score) {
      const record = chosenCardRecords()[cardsState.index];
      if (!record) return;
      const key = score.dataset.score;
      const max = cardFields.find((f) => f[0] === key)?.[2] || 0;
      const value = score.value === '' ? null : Math.min(max, Math.max(0, Number(score.value) || 0));
      if (value !== null) score.value = value;
      record.scores[key] = value;
      const total = cardFields.reduce((n, f) => n + (Number(record.scores[f[0]]) || 0), 0);
      const currentTotal = main.querySelector('.card-current .card-total th:nth-child(2)');
      if (currentTotal) currentTotal.textContent = total;
      main.querySelectorAll('#cards-print-set .student-card-paper').forEach((paper, i) => {
        const item = chosenCardRecords()[i];
        if (!item) return;
        cardFields.forEach(([field], j) => {
          const cell = paper.querySelectorAll('tbody tr')[j]?.children[1];
          if (cell) cell.textContent = item.scores[field] ?? '—';
        });
        const sum = cardFields.reduce((n, f) => n + (Number(item.scores[f[0]]) || 0), 0);
        const cell = paper.querySelector('.card-total th:nth-child(2)');
        if (cell) cell.textContent = sum;
      });
      return;
    }
    const form = e.target.closest('#settings-form');
    if (!form) return;
    if (e.target.id === 'device_count') document.getElementById('count-out').textContent = e.target.value;
    if (['academic_year', 'semester', 'naming_lang'].includes(e.target.name)) {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(() => refreshPreview(form), 200);
    }
  });

  main.addEventListener('submit', (e) => {
    if (e.target.id === 'settings-form') { e.preventDefault(); saveSettings(e.target); }
    if (e.target.id === 'developer-contact-form') {
      e.preventDefault();
      const description = document.getElementById('developer-report').value.trim();
      const subject = encodeURIComponent('بلاغ عن مشكلة في تطبيق مساعد معلم التقنية');
      const body = encodeURIComponent(`وصف المشكلة:\n${description}\n\nيرجى إرفاق لقطة شاشة توضّح المشكلة قبل إرسال الرسالة.`);
      window.location.href = `mailto:mahmoud.isma3el@gmail.com?subject=${subject}&body=${body}`;
      toast('فُتحت رسالة البريد. أرفق لقطة الشاشة ثم أرسل البلاغ.');
      return;
    }
    if (e.target.id === 'new-section-form') {
      e.preventDefault();
      const form = e.target;
      const grade = form.grade.value.trim();
      const label = form.label.value.trim();
      form.querySelectorAll('.field').forEach((el) => {
        el.classList.remove('invalid');
        const err = el.querySelector('.error');
        if (err) err.hidden = true;
      });
      if (!grade) {
        const f = form.querySelector('[data-field="grade"]');
        f?.classList.add('invalid');
        const err = f?.querySelector('.error');
        if (err) { err.textContent = 'اختر الصف'; err.hidden = false; }
        return;
      }
      if (!label) {
        const f = form.querySelector('[data-field="label"]');
        f?.classList.add('invalid');
        const err = f?.querySelector('.error');
        if (err) { err.textContent = 'اكتب رمز الشعبة'; err.hidden = false; }
        return;
      }
      api('PUT', `/api/sections/${encodeURIComponent(grade)}/${encodeURIComponent(label)}`, { students: [] })
        .then(() => { toast(`أُضيفت الشعبة ${grade} ${label}`); show('sections'); })
        .catch((err) => toast(err.message, true));
    }
  });

  // drag-and-drop for roster
  main.addEventListener('dragover', (e) => { if (e.target.closest('#drop-zone')) e.preventDefault(); });
  main.addEventListener('drop', (e) => {
    const zone = e.target.closest('#drop-zone');
    if (!zone) return;
    e.preventDefault();
    // One file opens the review list; several go straight to one section each.
    const files = e.dataTransfer.files;
    if (!files?.length) return;
    if (files.length === 1) importRoster(files[0]); else importRosterBatch(files);
  });

  // ---------- start ----------
  document.querySelectorAll('i[data-icon]').forEach((el) => (el.outerHTML = icon(el.dataset.icon)));
  api('GET', '/api/state').then((s) => {
    if (s.mode === 'browser') document.getElementById('quit').hidden = false;
  }).catch(() => {});
  show('home');
})();
