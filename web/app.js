'use strict';

history.replaceState(null, '', '/');
const $ = s => document.querySelector(s),
  $$ = s => [...document.querySelectorAll(s)];
const S = {
  view: 'all',
  album: null,
  folder: null,
  kind: '',
  search: '',
  sort: 'newest',
  filters: Object.fromEntries(['origin','camera','extension','focal','aperture'].map(key => [key,{mode:'include',values:[]}])),
  inspectedId: null,
  viewSizeMode: 'fit',
  items: [],
  total: 0,
  selected: new Set(),
  selecting: false,
  loading: false,
  version: 0,
  overview: null,
  viewerIndex: 0,
  catalog: null,
  addIds: [],
  formMode: 'create'
};
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) I18n.text(n, text);
  return n;
}
async function api(path, body) {
  const options = body === undefined ? {} : {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Gallery-Request': '1'
    },
    body: JSON.stringify(body)
  };
  options.headers = {
    ...(options.headers || {})
  };
  if (S.catalog) options.headers['X-Gallery-Catalog'] = S.catalog;
  let r;
  try {
    r = await fetch(path, options);
  } catch (e) {
    const message = T("本机图库连接已断开。请关闭旧窗口，重新双击桌面的\u201C拾光图库\u201D。不需要连接互联网。");
    let notice = $('#connectionNotice');
    if (!notice) {
      notice = el('div', 'connection-notice', message);
      notice.id = 'connectionNotice';
      notice.setAttribute('role', 'alert');
      document.body.append(notice);
    }
    notice.classList.remove('hidden');
    throw I18n.error(message);
  }
  $('#connectionNotice')?.classList.add('hidden');
  const j = await r.json();
  if (r.status === 409) {
    location.reload();
    throw I18n.error(j.error || T("照片来源已改变，正在刷新窗口。"));
  }
  if (!r.ok) throw I18n.error(j.error || T("操作失败"));
  return j;
}
function toast(message) {
  I18n.text($('#toast'), message);
  $('#toast').classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $('#toast').classList.remove('show'), 3200);
}
function guard(fn) {
  return async (...args) => {
    try {
      return await fn(...args);
    } catch (e) {
      toast(I18n.errorText(e));
    }
  };
}
const number = n => I18n.number(n);
const album = () => S.overview?.albums.find(a => a.id === S.album);
function thumb(id) {
  return '/image/' + S.catalog + '/' + id;
}
function image(id, alt) {
  const im = el('img');
  im.src = thumb(id);
  im.alt = alt || '';
  im.loading = 'lazy';
  im.decoding = 'async';
  im.onerror = () => {
    const fallback = el('div', 'broken-photo');
    fallback.append(el('span', '', '▧'), el('div', '', alt || T("暂时无法预览")));
    im.replaceWith(fallback);
  };
  return im;
}
function dateLabel(date) {
  return I18n.date(date);
}
async function overview() {
  const wasRunning = S.overview?.status.running;
  const next = await api('/api/overview');
  if (S.catalog && next.catalog !== S.catalog) {
    location.reload();
    throw I18n.error(T("照片来源已改变，正在刷新窗口。"));
  }
  S.catalog = next.catalog;
  S.overview = next;
  const o = S.overview;
  I18n.text($('#allCount'), number(o.count));
  I18n.text($('#favoriteCount'), number(o.favorites));
  I18n.text($('#rootPath'), I18n.root(o));
  renderNav();
  const b = $('#scanBanner');
  b.classList.toggle('hidden', !o.status.running && !o.status.error);
  b.classList.toggle('error', !!o.status.error);
  I18n.text(b, o.status.running ? T("正在整理照片索引 \xB7 已读取 {0} 张，原照片保留在原处", number(o.status.processed)) : T(o.status.error || ''));
  $('#refresh').disabled = o.status.running;
  updateHeader();
  if (wasRunning && !o.status.running) await load(true);
}
function renderNav() {
  const nav = $('#albumNav');
  nav.replaceChildren();
  if (!S.overview.albums.length) {
    nav.append(el('div', 'nav-empty', T("把喜欢的瞬间放在一起。\n从新建一个相册开始。")));
    return;
  }
  for (const a of S.overview.albums) {
    const b = el('button', 'album-link' + (S.view === 'album' && S.album === a.id ? ' active' : ''));
    b.append(el('i', 'album-dot'), el('span', 'album-name', a.name), el('small', '', number(a.count)));
    I18n.attr(b, "title", a.name);
    b.onclick = () => navigate('album', a.id);
    nav.append(b);
  }
}
function updateHeader() {
  let title = T("全部照片"),
    sub = T("{0} 张照片 \xB7 按日期浏览", number(S.total)),
    eyebrow = T("每一个瞬间，都在这里");
  if (S.view === 'favorites') {
    title = T("个人收藏");
    eyebrow = T("把偏爱的瞬间留下");
  }
  if (S.view === 'folders') {
    title = T("文件夹");
    sub = T("{0} 个文件夹 \xB7 沿用原来的整理方式", number(S.overview?.folders.length));
    eyebrow = T("熟悉的位置，新的看法");
  }
  if (S.view === 'albums') {
    title = T("我的相册");
    sub = T("{0} 个相册 \xB7 一张照片，可以有多个归属", number(S.overview?.albums.length));
    eyebrow = T("让照片拥有自己的故事");
  }
  if (S.view === 'album') {
    title = album()?.name || T("相册");
    sub = T("{0} 张照片 \xB7 分组不会移动原文件", number(S.total));
    eyebrow = T("属于这个主题的瞬间");
  }
  if (S.view === 'folder') {
    title = S.folder === '.' ? T("图片根目录") : S.folder;
    sub = T("{0} 张照片 \xB7 包含子文件夹", number(S.total));
    eyebrow = I18n.concat(T("文件夹 / "), I18n.root(S.overview) || T("照片目录"));
  }
  I18n.text($('#title'), title);
  I18n.text($('#subtitle'), sub);
  I18n.text($('#eyebrow'), eyebrow);
  $('#albumMore').classList.toggle('hidden', S.view !== 'album');
  updateFolderRenameHeader();
  const collections = ['albums', 'folders'].includes(S.view);
  $('.toolbar').classList.toggle('hidden', collections);
  $('#photoTools').classList.toggle('hidden', collections);
  $('#galleryInspector').classList.toggle('hidden', collections);
  $('#filterToggle').classList.toggle('hidden', S.view !== 'all');
  $('#filterPanel').classList.toggle('hidden', S.view !== 'all' || $('#filterToggle').getAttribute('aria-expanded') !== 'true');
  document.body.classList.toggle('has-photo-tools', !collections);
  I18n.text($('#footerCount'), collections ? I18n.root(S.overview) || T("照片目录") : T("已显示 {0} / {1}", number(S.items.length), number(S.total)));
  $$('[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === S.view || b.dataset.view === 'folders' && S.view === 'folder' || b.dataset.view === 'albums' && S.view === 'album'));
}
async function navigate(view, id) {
  S.view = view;
  S.album = view === 'album' ? Number(id) : null;
  S.folder = view === 'folder' ? id : null;
  S.selected.clear();
  S.selecting = false;
  S.search = '';
  $('#search').value = '';
  renderNav();
  selectionUI();
  await load(true);
  window.scrollTo({
    top: 0
  });
}
function empty(title, text, button) {
  const box = el('div', 'empty-state');
  box.append(el('div', 'empty-symbol', '✳'), el('h2', '', title), el('p', '', text));
  if (button) {
    const b = el('button', 'primary', button.label);
    b.onclick = button.click;
    box.append(b);
  }
  return box;
}
function renderCollections() {
  const box = $('#content');
  box.replaceChildren();
  const folders = S.view === 'folders',
    rows = folders ? S.overview.folders : S.overview.albums;
  if (!rows.length) {
    box.append(empty(folders ? T("还没有照片文件夹") : T("你的第一个相册，从这里开始"), folders ? T("点击左下角刷新，读取所选照片文件夹。") : T("旅行、家人、日常，给同一张照片不同的归属。"), {
      label: T("＋ 新建相册"),
      click: () => newAlbum()
    }));
    return;
  }
  const grid = el('div', 'collections-grid');
  for (const r of rows) {
    const b = el('button', 'collection-card'),
      cover = el('div', 'collection-cover' + (!r.cover ? ' empty' : ''));
    if (r.cover) cover.append(image(r.cover, r.name));else cover.append(el('span','material-symbols-outlined',folders ? 'folder' : 'collections'));
    cover.append(el('span', 'corner', folders ? T("文件夹") : T("相册")));
    b.append(cover, el('div', 'collection-name', r.name === '.' ? T("图片根目录") : r.name), el('div', 'collection-count', T("{0} 张照片", number(r.count))));
    b.onclick = () => navigate(folders ? 'folder' : 'album', folders ? r.name : r.id);
    if (folders) b.dataset.folder = r.name;
    grid.append(b);
  }
  box.append(grid);
}
async function load(reset = false) {
  if (!reset && (S.loading || S.restoring)) return;
  if (reset) {
    collapsedDates.clear();
    S.version++;
    S.items = [];
    S.total = 0;
    S.loading = false;
    $('#content').replaceChildren(el('div', 'loading-dots', T("正在读取照片\u2026")));
  }
  const version = S.version;
  if (['albums', 'folders'].includes(S.view)) {
    renderCollections();
    updateHeader();
    $('#loadMore').classList.add('hidden');
    return;
  }
  S.loading = true;
  try {
    const q = photoQuery();
    q.set('offset', S.items.length);
    q.set('limit', 120);
    const result = await api('/api/photos?' + q);
    if (version !== S.version) return;
    S.items.push(...result.items);
    S.total = result.total;
    renderPhotos();
    updateHeader();
  } finally {
    if (version === S.version) S.loading = false;
  }
}
const collapsedDates = new Set();
function toggleDateGroup(group) {
  finishRange(true);
  const date = group.dataset.date,
    head = group.querySelector('.date-heading'),
    before = head.getBoundingClientRect().top;
  const collapsed = !collapsedDates.has(date);
  if (collapsed) collapsedDates.add(date);else collapsedDates.delete(date);
  group.classList.toggle('collapsed', collapsed);
  group.querySelector('.photo-grid').classList.toggle('hidden', collapsed);
  const button = group.querySelector('.date-toggle');
  button.setAttribute('aria-expanded', String(!collapsed));
  I18n.text(button, collapsed ? T("\u25B8 展开") : T("\u25BE 收起"));
  I18n.attr(button, 'aria-label', T("{0} {1}的照片", collapsed ? T("展开") : T("收起"), dateLabel(date)));
  // A pinned date may be thousands of pixels past its original position.
  // Keep that date at the same screen position when the group shrinks.
  window.scrollBy(0, head.getBoundingClientRect().top - before);
}
function createDateGroup(date) {
  const group = el('section', 'date-group' + (collapsedDates.has(date) ? ' collapsed' : ''));
  group.dataset.date = date;
  const head = el('div', 'date-heading'),
    title = el('h2', '', dateLabel(date)),
    button = el('button', 'date-toggle', collapsedDates.has(date) ? T("\u25B8 展开") : T("\u25BE 收起"));
  const grid = el('div', 'photo-grid' + (collapsedDates.has(date) ? ' hidden' : ''));
  grid.id = 'day-' + date;
  button.setAttribute('aria-controls', grid.id);
  button.setAttribute('aria-expanded', String(!collapsedDates.has(date)));
  I18n.attr(button, 'aria-label', T("{0} {1}的照片", collapsedDates.has(date) ? T("展开") : T("收起"), dateLabel(date)));
  button.onclick = () => toggleDateGroup(group);
  head.append(title, button);
  group.append(head, grid);
  return group;
}
function renderPhotos() {
  const box = $('#content');
  box.replaceChildren();
  if (!S.items.length) {
    let message = S.search ? T("换个关键词试试，支持文件名、文件夹名和日期。") : S.overview?.status.running ? T("照片正在陆续加入，稍后会自动更新。") : S.view === 'album' ? T("去\u201C全部照片\u201D选择照片，再点\u201C加入相册\u201D。") : S.view === 'favorites' ? T("打开照片，点右上角的爱心即可收藏。") : T("点击左下角刷新，读取所选文件夹中的照片。");
    box.append(empty(S.view === 'album' ? T("这个相册还没有照片") : S.search ? T("没有找到匹配照片") : T("这里还没有照片"), message, S.view === 'album' ? {
      label: T("去选择照片"),
      click: () => navigate('all')
    } : null));
  }
  let day = null,
    grid = null;
  for (let i = 0; i < S.items.length; i++) {
    const p = S.items[i],
      date = p.taken.slice(0, 10);
    if (date !== day) {
      day = date;
      const group = createDateGroup(date);
      grid = group.querySelector('.photo-grid');
      box.append(group);
    }
    const card = el('article', 'photo-card' + (S.selected.has(p.id) ? ' selected' : '') + (S.inspectedId === p.id ? ' inspected' : ''));
    card.tabIndex = 0;
    I18n.attr(card, 'aria-label', p.name);
    card.dataset.id = p.id;
    card.append(image(p.id, p.name), el('div', 'photo-shade'));
    if (p.kind === 'RAW' || ['.heic', '.heif'].includes(p.extension)) card.append(el('span', 'format-badge', p.kind === 'RAW' ? 'RAW' : 'HEIC'));
    const check = el('button', 'select-check', S.selected.has(p.id) ? '✓' : '');
    I18n.attr(check, 'aria-label', I18n.concat(T("选择 "), p.name));
    check.setAttribute('aria-pressed', String(S.selected.has(p.id)));
    check.onclick = e => {
      e.stopPropagation();
      toggleSelect(p.id);
    };
    card.append(check);
    if (p.favorite) card.append(el('span', 'favorite-mark material-symbols-outlined', 'favorite'));
    card.append(el('span', 'photo-name', p.name));
    card.onclick = e => {
      if (e.detail > 1) return;
      if (S.selecting) toggleSelect(p.id);
      else {
        S.inspectedId = p.id;
        paintGalleryInspector(p);
        $$('.photo-card.inspected').forEach(node => node.classList.remove('inspected'));
        card.classList.add('inspected');
      }
    };
    card.ondblclick = () => guard(() => showViewer(i))();
    card.onkeydown = e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (S.selecting) toggleSelect(p.id);
        else { S.inspectedId = p.id; paintGalleryInspector(p); card.classList.add('inspected'); }
      }
      if (e.key === ' ') {
        e.preventDefault();
        toggleSelect(p.id);
      }
    };
    grid.append(card);
  }
  $('#loadMore').classList.toggle('hidden', S.items.length >= S.total);
  paintGalleryInspector(S.items.find(p => p.id === S.inspectedId) || S.items[0]);
  selectionUI();
}
let inspectorRequest = 0;
function paintGalleryInspector(photo) {
  const panel = $('#galleryInspector'), picture = $('#inspectorImage'), details = $('#inspectorDetails');
  if (!panel || !picture || !details) return;
  const capture = $('#inspectorCapture'), request = ++inspectorRequest;
  if (!photo) {
    I18n.text($('#inspectorName'), T('这里还没有照片'));
    I18n.text($('#inspectorPosition'), '');
    picture.removeAttribute('src');
    details.replaceChildren();
    capture.replaceChildren();
    PhotoHistogram.draw($('#inspectorHistogram'), null);
    return;
  }
  I18n.text($('#inspectorName'), photo.name);
  const index = S.items.findIndex(p => p.id === photo.id);
  I18n.text($('#inspectorPosition'), index < 0 ? '' : `${number(index + 1)} / ${number(S.total)}`);
  const properties = [[T('日期'), I18n.date(photo.taken, 'datetime')],
    [T('格式'), photo.extension.slice(1).toUpperCase()],
    [T('文件大小'), (photo.size / 1024 / 1024).toFixed(1) + ' MB'],
    [T('所在文件夹'), photo.folder === '.' ? S.overview?.root || '' : photo.folder]];
  if (photo.width && photo.height) properties.splice(2, 0, [T('尺寸'), `${photo.width} × ${photo.height}`]);
  details.replaceChildren(...properties.flatMap(([label, value]) => [el('dt', '', label), el('dd', '', value)]));
  capture.replaceChildren(el('dd','metadata-loading',T('正在读取拍摄参数…')));
  guard(async () => {
    const metadata = await api('/api/photo-info?id=' + photo.id);
    if (request !== inspectorRequest) return;
    capture.replaceChildren(...metadata.fields.map(([label,value]) => [el('dt','',T(label)),el('dd','',I18n.metadata(label,value))]).flat());
  })();
  picture.alt = photo.name;
  picture.onload = () => {
    try { PhotoHistogram.draw($('#inspectorHistogram'), PhotoHistogram.sample(picture)); }
    catch { PhotoHistogram.draw($('#inspectorHistogram'), null); }
  };
  picture.onerror = () => PhotoHistogram.draw($('#inspectorHistogram'), null);
  picture.src = thumb(photo.id);
}
function toggleSelect(id) {
  if (!S.selecting) resetSelectionHistory();
  const before = new Set(S.selected);
  S.selecting = true;
  S.selected.has(id) ? S.selected.delete(id) : S.selected.add(id);
  paintGalleryInspector(S.items.find(p => p.id === id));
  recordSelection(before);
  selectionUI();
  for (const card of $$('.photo-card')) {
    const selected = S.selected.has(Number(card.dataset.id));
    card.classList.toggle('selected', selected);
    const b = card.querySelector('.select-check');
    I18n.text(b, selected ? '✓' : '');
    b.setAttribute('aria-pressed', String(selected));
  }
}
function selectionUI() {
  document.body.classList.toggle('selecting', S.selecting);
  $('#photoTools').classList.toggle('expanded', S.selecting);
  $('#selectMode').setAttribute('aria-pressed', String(S.selecting));
  I18n.text($('#selectMode'), S.selecting ? T("完成选择") : T("选择照片"));
  $('#selectionBar').classList.toggle('hidden', !S.selecting);
  I18n.text($('#selectedCount'), T("已选 {0} 张", number(S.selected.size)));
  $('#addToAlbum').disabled = !S.selected.size;
  $('#removeFromAlbum').classList.toggle('hidden', S.view !== 'album');
  $('#removeFromAlbum').disabled = !S.selected.size;
  for (const id of ['copySelected', 'shareSelected', 'deleteSelected']) $('#' + id).disabled = !S.selected.size;
  paintViewerSelection();
}
function newAlbum(mode = 'create') {
  S.formMode = mode;
  I18n.text($('#albumDialogTitle'), mode === 'rename' ? T("重命名相册") : T("新建相册"));
  $('#albumName').value = mode === 'rename' ? album().name : '';
  I18n.text($('#albumFormError'), '');
  $('#albumDialog').showModal();
  $('#albumName').focus();
}
function chooseAlbum(ids) {
  S.addIds = [...ids];
  I18n.text($('#addDescription'), T("将 {0} 张照片加入相册，原文件保持不变。", number(ids.length)));
  const list = $('#albumChoices');
  list.replaceChildren();
  for (const a of S.overview.albums) {
    const b = el('button', 'album-choice');
    if (a.cover) b.append(image(a.cover, ''));else b.append(el('i', 'album-choice-icon material-symbols-outlined', 'collections'));
    b.append(el('span', '', a.name), el('small', '', T("{0} 张", number(a.count))));
    b.onclick = guard(async () => {
      await api('/api/albums/add', {
        album: a.id,
        ids: S.addIds
      });
      $('#addDialog').close();
      toast(T("已加入「{0}」", a.name));
      await overview();
      if (S.view === 'album') await load(true);
    });
    list.append(b);
  }
  $('#addDialog').showModal();
}
function photoQuery() {
  const q = new URLSearchParams({
    sort: S.sort,
    kind: S.kind,
    search: S.search
  });
  if (S.view === 'all') for (const [key,state] of Object.entries(S.filters)) if (state.values.length) {
    q.set('filter_' + key,JSON.stringify(state.values));
    q.set('mode_' + key,state.mode);
  }
  if (S.view === 'favorites') q.set('favorite', '1');
  if (S.album) q.set('album', S.album);
  if (S.folder) q.set('folder', S.folder);
  return q;
}
let viewerRequest = 0,
  currentHistogram = null,
  viewerSession = null;
let viewerSessionSerial = 0;
function startViewerSession() {
  viewerSession = {
    key: ++viewerSessionSerial,
    query: photoQuery().toString(),
    total: S.total,
    initial: S.items.slice(),
    pages: new Map(),
    pending: new Map(),
    view: S.view,
    lastPhoto: null
  };
}
async function viewerPhoto(index, session = viewerSession) {
  if (!session || index < 0 || index >= session.total) return null;
  if (session.initial[index]) return session.initial[index];
  const offset = Math.floor(index / 64) * 64;
  if (!session.pages.has(offset)) {
    if (!session.pending.has(offset)) {
      const q = new URLSearchParams(session.query);
      q.set('offset', offset);
      q.set('limit', 64);
      const pending = api('/api/photos?' + q).then(result => {
        session.pages.set(offset, result.items);
        if (session.pages.size > 12) session.pages.delete(session.pages.keys().next().value);
        return result.items;
      }).finally(() => session.pending.delete(offset));
      session.pending.set(offset, pending);
    }
    const rows = await session.pending.get(offset);
    return rows[index - offset] || null;
  }
  return session.pages.get(offset)[index - offset] || null;
}
// A bounded, decoded thumbnail cache shared by the strip and its single hover preview.
const film = {
  session: null,
  rows: new Map(),
  cache: new Map(),
  queue: [],
  active: 0,
  inflight: new Set(),
  start: 0,
  count: 15,
  index: -1,
  target: -1,
  anchor: null,
  drag: null,
  wheel: 0,
  raf: 0,
  slots: new Map(),
  preview: null
};
const seek = {
  index: -1,
  dragging: false
};
function filmRange(center, count, total) {
  return Math.max(0, Math.min(total - 1, Math.round(center))) - Math.floor(count / 2);
}
function filmReset(session) {
  for (const [key, entry] of film.cache) if (entry.error) film.cache.delete(key);
  film.session = session;
  film.rows.clear();
  film.queue = [];
  film.start = 0;
  film.index = -1;
  film.target = -1;
  film.drag = null;
  film.slots.clear();
  film.preview = null;
  $('#filmRail').replaceChildren();
  $('#seekHoverPreview').replaceChildren();
  hideSeekPreview();
}
function filmEntry(index) {
  const p = film.rows.get(index);
  return p ? film.cache.get(p.id + ':' + p.mtime) : null;
}
function filmPlan(center) {
  const session = film.session;
  if (!session) return;
  const wanted = [];
  for (let d = 0; d <= 7; d++) for (const i of d ? [center + d, center - d] : [center]) wanted.push(i);
  for (let i = film.start; i < film.start + film.count; i++) wanted.push(i);
  for (let d = 1; d <= 5; d++) wanted.push(film.start - d, film.start + film.count - 1 + d);
  film.queue = [...new Set(wanted)].filter(i => i >= 0 && i < session.total && !filmEntry(i));
  filmPump();
}
function filmPump() {
  while (film.active < 2 && film.queue.length && film.session) {
    const index = film.queue.shift(),
      session = film.session;
    if (film.inflight.has(session.key + ':' + index) || filmEntry(index)) continue;
    const job = session.key + ':' + index;
    film.inflight.add(job);
    film.active++;
    (async () => {
      const photo = await viewerPhoto(index, session);
      if (!photo || session !== film.session) return;
      film.rows.set(index, photo);
      const key = photo.id + ':' + photo.mtime;
      let entry = film.cache.get(key);
      if (!entry) {
        entry = {
          key,
          photo,
          image: new Image(),
          ready: false,
          error: false
        };
        film.cache.set(key, entry);
        // Reuse the same thumbnail URL as the photo grid; never request RAW full decode here.
        entry.image.decoding = 'async';
        entry.promise = new Promise(resolve => {
          entry.image.onload = async () => {
            try {
              await entry.image.decode();
            } catch {}
            entry.ready = entry.image.naturalWidth > 0;
            resolve();
          };
          entry.image.onerror = () => {
            entry.error = true;
            resolve();
          };
          entry.image.src = thumb(photo.id);
        });
      }
      await entry.promise;
      if (session === film.session) {
        filmPaintSoon();
        filmTrim();
      }
    })().catch(() => {
      if (session === film.session) filmPaintSoon();
    }).finally(() => {
      film.inflight.delete(job);
      film.active--;
      filmPump();
    });
  }
}
function filmTrim() {
  const protectedKeys = new Set();
  for (const [i, p] of film.rows) if (i >= film.start - 5 && i < film.start + film.count + 5 || Math.abs(i - film.index) <= 7) protectedKeys.add(p.id + ':' + p.mtime);
  for (const [key, entry] of film.cache) {
    if (film.cache.size <= 96) break;
    if ((entry.ready || entry.error) && !protectedKeys.has(key)) film.cache.delete(key);
  }
}
function filmPaintSoon() {
  if (!film.raf) film.raf = requestAnimationFrame(() => {
    film.raf = 0;
    filmPaint();
  });
}
function filmDraw(node, index) {
  const p = film.rows.get(index),
    entry = filmEntry(index),
    canvas = node.querySelector('canvas'),
    status = node.querySelector('.film-status');
  node.dataset.index = index;
  if (p) {
    I18n.attr(node, "title", p.name);
    I18n.attr(node, 'aria-label', T("第 {0} 张：{1}", number(index + 1), p.name));
  }
  if (entry?.ready) {
    if (canvas.dataset.photo !== entry.key) {
      const ctx = canvas.getContext('2d'),
        im = entry.image;
      // Keep native proportions in the canvas. The compact row fills its tiles;
      // the single enlarged hover card preserves the photo's aspect ratio.
      canvas.width = im.naturalWidth;
      canvas.height = im.naturalHeight;
      ctx.drawImage(im, 0, 0);
      canvas.dataset.photo = entry.key;
    }
    I18n.text(status, '');
    node.dataset.ready = 'true';
    // Recent visible thumbnails remain hot while distant ones can be evicted.
    film.cache.delete(entry.key);
    film.cache.set(entry.key, entry);
  } else {
    if (canvas.dataset.photo) {
      canvas.width = 320;
      delete canvas.dataset.photo;
    }
    I18n.text(status, entry?.error ? T("无法预览") : '…');
    node.dataset.ready = 'false';
  }
}
function filmCard(tag, cls, index) {
  const n = el(tag, cls);
  n.dataset.index = index;
  n.append(el('canvas'), el('span', 'film-status', '…'));
  return n;
}
function filmPaint() {
  if (!film.session || !$('#viewer').open) return;
  const rail = $('#filmRail'),
    desired = new Set();
  rail.style.setProperty('--film-slots', film.count);
  for (let i = film.start; i < film.start + film.count; i++) {
    const valid = i >= 0 && i < film.session.total;
    desired.add(i);
    let n = film.slots.get(i);
    if (!n) {
      n = valid ? filmCard('button', 'film-cell', i) : el('div', 'film-gap');
      if (valid) {
        n.type = 'button';
        n.onclick = e => {
          if (e.detail === 0) guard(() => activateFilmPhoto(i))();
        };
      } else n.setAttribute('aria-hidden', 'true');
      film.slots.set(i, n);
    }
    if (valid) {
      n.classList.toggle('current', i === S.viewerIndex);
      n.classList.toggle('hovered', i === film.index);
      n.classList.toggle('target', i === film.target);
      n.setAttribute('aria-current', i === S.viewerIndex ? 'true' : 'false');
      filmDraw(n, i);
      paintFilmSelection(n, i);
    }
    if (rail.children[i - film.start] !== n) rail.insertBefore(n, rail.children[i - film.start] || null);
  }
  for (const [i, n] of film.slots) if (!desired.has(i)) {
    n.remove();
    film.slots.delete(i);
  }
  const center = film.start + Math.floor(film.count / 2);
  $('#filmEarlier').disabled = center <= 0;
  $('#filmLater').disabled = center >= film.session.total - 1;
  I18n.text($('#filmWindow'), T("附近 {0}\u2013{1} 张", number(Math.max(0, film.start) + 1), number(Math.min(film.session.total, film.start + film.count))));
  if (film.index >= 0) filmPaintPreview();
}
function filmWindow(index, recenter = false) {
  if (film.session !== viewerSession) filmReset(viewerSession);
  if (!film.session) return;
  const row = $('#filmRail').parentElement,
    width = Math.max(0, row.clientWidth - $('#filmEarlier').offsetWidth - $('#filmLater').offsetWidth - 2 * (parseFloat(getComputedStyle(row).columnGap) || 0)),
    oldCount = film.count,
    oldCenter = film.start + Math.floor(oldCount / 2);
  let capacity = Math.max(3, Math.min(25, Math.floor(width / 42) || 15));
  if (capacity % 2 === 0) capacity--;
  film.count = Math.min(capacity, film.session.total % 2 ? film.session.total : film.session.total + 1);
  // An odd slot count and blank edge slots keep the selected photo exactly centered.
  if (recenter) film.start = filmRange(index, film.count, film.session.total);else if (oldCount !== film.count) film.start = filmRange(oldCenter, film.count, film.session.total);
  filmPaint();
  filmPlan(index);
}
function filmPaintPreview() {
  const index = film.index,
    wrap = $('#photoSeekWrap'),
    preview = $('#seekHoverPreview');
  if (!film.session || index < 0 || index >= film.session.total) return;
  let node = film.preview;
  if (!node) {
    node = filmCard('div', 'film-hover-card', index);
    const caption = el('div', 'film-hover-caption'),
      name = el('span', 'film-hover-name'),
      meta = el('span', 'film-hover-meta');
    name.id = 'seekPreviewName';
    meta.id = 'seekPreviewMeta';
    caption.append(name, meta);
    node.append(caption);
    film.preview = node;
    preview.append(node);
  }
  const rect = wrap.getBoundingClientRect(),
    railRect = $('#filmRail').getBoundingClientRect(),
    cell = film.slots.get(index)?.getBoundingClientRect(),
    width = Math.max(80, Math.min(272, wrap.clientWidth - 12)),
    minCenter = Math.min(width / 2 + 6, wrap.clientWidth / 2),
    maxCenter = Math.max(minCenter, wrap.clientWidth - minCenter),
    anchor = film.anchor ?? (cell ? cell.left + cell.width / 2 : rect.left + wrap.clientWidth / 2),
    x = Math.max(minCenter, Math.min(maxCenter, anchor - rect.left));
  preview.style.bottom = Math.max(0, wrap.clientHeight - (railRect.top - rect.top) + 10) + 'px';
  node.style.left = x + 'px';
  node.style.width = width + 'px';
  filmDraw(node, index);
  const p = film.rows.get(index);
  I18n.text(node.querySelector('.film-hover-name'), p ? p.name : T("缩略图正在准备"));
  I18n.text(node.querySelector('.film-hover-meta'), `${number(index + 1)} / ${number(film.session.total)}${p ? ' · ' + p.taken.slice(0, 10) : ''}`);
  preview.classList.remove('hidden');
  preview.setAttribute('aria-hidden', 'false');
}
function paintSeek(index) {
  const total = viewerSession?.total || 0,
    bar = $('#photoSeek');
  bar.max = Math.max(0, total - 1);
  bar.disabled = total <= 1;
  bar.value = index;
  bar.style.setProperty('--seek-progress', (total > 1 ? index / (total - 1) * 100 : 0) + '%');
  I18n.attr(bar, 'aria-valuetext', T("第 {0} 张，共 {1} 张", number(index + 1), number(total)));
  I18n.text($('#seekPosition'), `${number(index + 1)} / ${number(total)}`);
  if (film.session !== viewerSession) filmReset(viewerSession);
  film.target = index;
  filmWindow(index, true);
}
function hideSeekPreview() {
  seek.index = -1;
  film.index = -1;
  film.anchor = null;
  $('#seekHoverPreview').classList.add('hidden');
  $('#seekHoverPreview').setAttribute('aria-hidden', 'true');
  for (const node of film.slots.values()) node.classList.remove('hovered');
}
function previewSeek(index, pointerX = null) {
  if (!viewerSession) return;
  index = Math.max(0, Math.min(viewerSession.total - 1, index));
  seek.index = index;
  if (film.session !== viewerSession) filmReset(viewerSession);
  film.index = index;
  film.anchor = pointerX;
  filmPaint();
  filmPlan(index);
  filmPaintPreview();
}
const seekBar = $('#photoSeek'),
  filmRail = $('#filmRail');
function filmIndexAt(x) {
  let best = film.start,
    distance = Infinity;
  for (const [index, node] of film.slots) {
    if (index < 0 || index >= film.session.total) continue;
    const r = node.getBoundingClientRect(),
      d = Math.abs(x - r.left - r.width / 2);
    if (d < distance) {
      distance = d;
      best = index;
    }
  }
  return best;
}
filmRail.onpointermove = e => {
  if (film.session) previewSeek(filmIndexAt(e.clientX), e.clientX);
};
filmRail.onpointerdown = e => {
  if (e.button !== 0 || !film.session) return;
  e.preventDefault();
  film.drag = e.pointerId;
  filmRail.setPointerCapture(e.pointerId);
  previewSeek(filmIndexAt(e.clientX), e.clientX);
};
filmRail.onpointerup = e => {
  if (film.drag !== e.pointerId) return;
  const index = filmIndexAt(e.clientX);
  film.drag = null;
  if (filmRail.hasPointerCapture(e.pointerId)) filmRail.releasePointerCapture(e.pointerId);
  guard(() => activateFilmPhoto(index))();
};
filmRail.onpointercancel = () => {
  film.drag = null;
  hideSeekPreview();
};
filmRail.onlostpointercapture = () => {
  film.drag = null;
};
filmRail.onpointerleave = () => {
  if (film.drag === null) hideSeekPreview();
};
function filmShift(amount) {
  if (!film.session) return;
  film.start = filmRange(film.start + Math.floor(film.count / 2) + amount, film.count, film.session.total);
  hideSeekPreview();
  filmPaint();
  filmPlan(film.start + Math.floor(film.count / 2));
}
filmRail.addEventListener('wheel', e => {
  if (!film.session) return;
  e.preventDefault();
  film.wheel += (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY) * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 120 : 1);
  if (Math.abs(film.wheel) >= 35) {
    const steps = Math.sign(film.wheel) * Math.min(5, Math.floor(Math.abs(film.wheel) / 35));
    film.wheel = 0;
    filmShift(steps);
    previewSeek(filmIndexAt(e.clientX), e.clientX);
  }
}, {
  passive: false
});
$('#filmEarlier').onclick = () => filmShift(-Math.max(1, film.count - 2));
$('#filmLater').onclick = () => filmShift(Math.max(1, film.count - 2));
// Coarse positioning changes on actual input, never on incidental mouse hover.
seekBar.onpointermove = () => {
  if (seek.dragging) previewSeek(Number(seekBar.value));
};
seekBar.onpointerdown = () => {
  seek.dragging = true;
  hideSeekPreview();
};
seekBar.onpointerup = () => {
  seek.dragging = false;
};
seekBar.onpointercancel = () => {
  seek.dragging = false;
  hideSeekPreview();
  if (viewerSession && $('#viewer').open) guard(() => showViewer(S.viewerIndex))();
};
seekBar.onpointerleave = () => {
  if (!seek.dragging) hideSeekPreview();
};
document.addEventListener('pointerup', () => {
  if (seek.dragging) {
    seek.dragging = false;
    if (!seekBar.matches(':hover')) hideSeekPreview();
  }
});
window.addEventListener('blur', () => {
  seek.dragging = false;
  film.drag = null;
  hideSeekPreview();
});
seekBar.onblur = hideSeekPreview;
seekBar.oninput = () => {
  viewerRequest++;
  const index = Number(seekBar.value);
  paintSeek(index);
  previewSeek(index);
};
seekBar.onchange = guard(async () => {
  const index = Number(seekBar.value);
  try {
    await showViewer(index);
  } catch (e) {
    paintSeek(S.viewerIndex);
    throw e;
  }
});
new ResizeObserver(() => {
  if (viewerSession && $('#viewer').open) filmWindow(film.index >= 0 ? film.index : S.viewerIndex);
}).observe(filmRail);
$('#viewer').addEventListener('close', () => {
  const session = viewerSession;
  viewerRequest++;
  viewerSession = null;
  seek.dragging = false;
  filmReset(null);
  guard(() => restoreViewerPosition(session))();
});
function renderHistogram() {
  PhotoHistogram.draw($('#histogramCanvas'), currentHistogram, $('#histogramLog').checked);
}
$('#histogramLog').onchange = renderHistogram;
async function showViewer(index) {
  if (index < 0) return;
  if (!$('#viewer').open) {
    startViewerSession();
    $('#viewer').showModal();
  }
  const session = viewerSession;
  if (!session || index >= session.total) return;
  const request = ++viewerRequest,
    p = await viewerPhoto(index, session);
  if (request !== viewerRequest || session !== viewerSession || !$('#viewer').open) return;
  if (!p) throw I18n.error(T("照片列表已变化，请关闭大图后重新打开"));
  S.viewerIndex = index;
  S.viewerPhoto = p;
  S.inspectedId = p.id;
  paintGalleryInspector(p);
  session.lastPhoto = p;
  session.lastIndex = index;
  paintSeek(index);
  paintViewerSelection();
  guard(() => renderSeekTimeline(session))();
  I18n.text($('#seekDate'), I18n.date(p.taken, 'datetime'));
  I18n.text($('#viewerName'), p.name);
  I18n.text($('#viewerIndex'), `${index + 1} / ${number(session.total)}`);
  I18n.text($('#viewerFavorite'), p.favorite ? 'favorite' : 'favorite_border');
  $('#previous').disabled = index === 0;
  $('#next').disabled = index + 1 >= session.total;
  beginPhotoQuality();
  resetViewerZoom(false);
  $('#previewError').classList.add('hidden');
  $('#fullImage').classList.remove('hidden');
  $('#fullImage').alt = p.name;
  currentHistogram = null;
  renderHistogram();
  I18n.text($('#histogramStatus'), T("正在读取预览\u2026"));
  $('#fullImage').onload = () => {
    if (request !== viewerRequest) return;
    resetViewerZoom(true);
    qualityImageLoaded();
    try {
      currentHistogram = PhotoHistogram.sample($('#fullImage'));
      renderHistogram();
      I18n.text($('#histogramStatus'), Q.mode === 'full' ? T("基于全分辨率显示画面采样") : T("基于快速预览采样 \xB7 非 RAW 原始数据"));
    } catch (e) {
      I18n.text($('#histogramStatus'), T("此预览暂时无法计算直方图"));
    }
  };
  $('#fullImage').onerror = () => {
    if (request !== viewerRequest) return;
    $('#fullImage').classList.add('hidden');
    $('#previewError').classList.remove('hidden');
    I18n.text($('#histogramStatus'), T("无可用预览，无法计算直方图"));
  };
  $('#fullImage').src = thumb(p.id) + '?size=large&v=' + p.mtime;
  const info = $('#photoDetails');
  info.replaceChildren();
  const props = [[T("日期"), I18n.date(p.taken, 'datetime')], [T("日期依据"), T(p.date_source)], [T("格式"), p.extension.slice(1).toUpperCase()], [T("文件大小"), (p.size / 1024 / 1024).toFixed(1) + ' MB'], [T("所在文件夹"), p.folder === '.' ? S.overview.root : p.folder]];
  if (p.width && p.height) props.splice(3, 0, [T("尺寸"), `${p.width} × ${p.height}`]);
  for (const [k, v] of props) info.append(el('dt', '', k), el('dd', '', v));
  $('#captureDetails').replaceChildren(el('dd', 'metadata-loading', T("正在读取拍摄参数\u2026")));
  I18n.text($('#captureNote'), '');
  if (!$('#viewer').open) $('#viewer').showModal();
  try {
    const details = await api('/api/photo-info?id=' + p.id);
    if (request !== viewerRequest) return;
    const box = $('#captureDetails');
    box.replaceChildren();
    for (const [k, v] of details.fields) {
      box.append(el('dt', '', T(k)), el('dd', v === '未记录' ? 'not-recorded' : '', I18n.metadata(k, v)));
    }
    Q.depth = details.bit_depth;
    const decodeOutput = el('dd', '', '');
    decodeOutput.id = 'decodeOutput';
    box.append(el('dt', '', T("当前输出")), decodeOutput);
    paintQuality();
    I18n.text($('#captureNote'), T(details.warning || details.note));
    if (!p.width && details.width && details.height) info.append(el('dt', '', T("尺寸")), el('dd', '', `${details.width} × ${details.height}`));
  } catch (e) {
    if (request !== viewerRequest) return;
    $('#captureDetails').replaceChildren(el('dd', 'not-recorded', T("拍摄参数暂时无法读取")));
    I18n.text($('#captureNote'), I18n.errorText(e));
  }
}
$$('[data-view]').forEach(b => b.onclick = guard(() => navigate(b.dataset.view)));
$('#refresh').onclick = guard(async () => {
  await api('/api/scan', {});
  await overview();
  toast(T("已开始刷新图库"));
});
$('#newAlbum').onclick = $('#newAlbumSide').onclick = () => newAlbum();
$('#selectMode').onclick = () => {
  finishRange(true);
  resetSelectionHistory();
  S.selecting = !S.selecting;
  if (!S.selecting) S.selected.clear();
  paintSelectedCards();
};
$('#clearSelection').onclick = () => clearPhotoSelection();
$('#selectLoaded').onclick = () => selectLoadedPhotos();
$('#addToAlbum').onclick = () => chooseAlbum([...S.selected]);
$('#removeFromAlbum').onclick = guard(async () => {
  await api('/api/albums/remove', {
    album: S.album,
    ids: [...S.selected]
  });
  S.selected.clear();
  await overview();
  await load(true);
  toast(T("已从此相册移除，原照片仍保留"));
});
$('#loadMore').onclick = guard(() => load());
$$('[data-kind]').forEach(b => b.onclick = guard(async () => {
  S.kind = b.dataset.kind;
  $$('[data-kind]').forEach(x => x.classList.toggle('active', x === b));
  S.selected.clear();
  await load(true);
}));
$('#sort').onchange = guard(async () => {
  S.sort = $('#sort').value;
  await load(true);
});
$('#search').oninput = () => {
  clearTimeout(S.searchTimer);
  S.searchTimer = setTimeout(guard(async () => {
    S.search = $('#search').value.trim();
    S.selected.clear();
    await load(true);
  }), 250);
};
$$('[data-close]').forEach(b => b.onclick = () => $('#' + b.dataset.close).close());
$('#albumForm').onsubmit = async e => {
  e.preventDefault();
  try {
    const name = $('#albumName').value.trim();
    if (S.formMode === 'rename') await api('/api/albums/rename', {
      album: S.album,
      name
    });else {
      const result = await api('/api/albums/create', {
        name
      });
      if (S.formMode === 'createAndAdd') {
        await api('/api/albums/add', {
          album: result.id,
          ids: S.addIds
        });
        $('#addDialog').close();
      }
    }
    $('#albumDialog').close();
    await overview();
    if (['albums', 'album'].includes(S.view)) await load(true);
    toast(S.formMode === 'rename' ? T("相册已重命名") : T("相册已创建"));
  } catch (e) {
    I18n.text($('#albumFormError'), I18n.errorText(e));
  }
};
$('#createAndAdd').onclick = () => newAlbum('createAndAdd');
$('#albumMore').onclick = () => {
  I18n.text($('#albumSettingsName'), album().name);
  $('#settingsDialog').showModal();
};
$('#renameAlbum').onclick = () => {
  $('#settingsDialog').close();
  newAlbum('rename');
};
$('#deleteAlbum').onclick = () => {
  $('#settingsDialog').close();
  $('#confirmDialog').showModal();
};
$('#confirmDeleteAlbum').onclick = guard(async () => {
  await api('/api/albums/delete', {
    album: S.album
  });
  $('#confirmDialog').close();
  await overview();
  await navigate('albums');
  toast(T("相册已删除，原照片未改动"));
});
$('#viewerClose').onclick = () => $('#viewer').close();
$('#previous').onclick = guard(() => showViewer(S.viewerIndex - 1));
$('#next').onclick = guard(() => showViewer(S.viewerIndex + 1));
$('#viewerAdd').onclick = () => chooseAlbum([S.viewerPhoto.id]);
$('#viewerFavorite').onclick = guard(async () => {
  const p = S.viewerPhoto;
  await api('/api/favorite', {
    ids: [p.id],
    value: !p.favorite
  });
  p.favorite = !p.favorite;
  const gridPhoto = S.items.find(x => x.id === p.id);
  if (gridPhoto) gridPhoto.favorite = p.favorite;
  I18n.text($('#viewerFavorite'), p.favorite ? 'favorite' : 'favorite_border');
  await overview();
  renderPhotos();
});
$('#reveal').onclick = guard(() => api('/api/reveal', {
  id: S.viewerPhoto.id
}));
document.addEventListener('keydown', e => {
  if (e.target.matches('input,textarea,select') || !$('#viewer').open || $$('dialog[open]').some(d => d !== $('#viewer'))) return;
  if (e.key === 'ArrowLeft') {
    e.preventDefault();
    guard(() => showViewer(S.viewerIndex - 1))();
  }
  if (e.key === 'ArrowRight') {
    e.preventDefault();
    guard(() => showViewer(S.viewerIndex + 1))();
  }
});
let lastAuto = 0;
new IntersectionObserver(entries => {
  if (entries[0].isIntersecting && S.items.length > 0 && S.items.length < S.total && !S.loading && !S.restoring && Date.now() - lastAuto > 600) {
    lastAuto = Date.now();
    guard(() => load())();
  }
}, {
  rootMargin: '300px'
}).observe($('#sentinel'));
let initialized = false,
  refreshing = false;
async function refreshConnection() {
  if (refreshing) return;
  refreshing = true;
  try {
    const before = S.overview?.status.running;
    await overview();
    if (!initialized || before && S.overview.status.running && S.items.length === 0) await load(true);
    initialized = true;
  } finally {
    refreshing = false;
  }
}
I18n.ready.then(() => guard(refreshConnection)());
setInterval(guard(refreshConnection), 5000);
const F = {
  mode: null,
  prepared: null,
  job: null,
  timer: null,
  running: false
};
let copyIds = [],
  clipboardBusy = false;
function chooseCopy(ids) {
  copyIds = [...ids];
  I18n.text($('#copyDescription'), T("已选 {0} 张照片", number(ids.length)));
  $('#copyImageClipboard').disabled = ids.length !== 1 || clipboardBusy;
  I18n.text($('#copyClipboardNote'), ids.length === 1 ? T("复制后，在聊天输入框按 Ctrl+V 粘贴。RAW 复制浏览预览；动图复制首帧。") : T("图片剪贴板一次复制一张。请只选一张，或使用下面的批量文件复制。"));
  I18n.text($('#copyError'), '');
  $('#copyDialog').showModal();
}
async function copyImageClipboard(id) {
  if (clipboardBusy) return;
  clipboardBusy = true;
  const b = $('#copyImageClipboard');
  b.disabled = true;
  I18n.text(b, T("正在复制图片\u2026"));
  try {
    const r = await api('/api/clipboard/image', {
      id
    });
    if ($('#copyDialog').open) $('#copyDialog').close();
    toast(T("{0}已复制到剪贴板（{1} \xD7 {2}），请在输入框按 Ctrl+V", r.preview ? T("RAW 预览图") : T("图片"), r.width, r.height));
  } finally {
    clipboardBusy = false;
    b.disabled = copyIds.length !== 1;
    I18n.text(b, T("复制图片到剪贴板"));
  }
}
$('#copyImageClipboard').onclick = async () => {
  try {
    I18n.text($('#copyError'), '');
    await copyImageClipboard(copyIds[0]);
  } catch (e) {
    I18n.text($('#copyError'), I18n.errorText(e));
  }
};
$('#copyToFolder').onclick = guard(async () => {
  const ids = [...copyIds];
  $('#copyDialog').close();
  await openFileAction('copy', ids);
});
$('#copyDialog').addEventListener('cancel', e => {
  if (clipboardBusy) e.preventDefault();
});
document.addEventListener('keydown', e => {
  if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'c' || e.altKey || e.shiftKey || e.target.matches('input,textarea,select,[contenteditable]')) return;
  if (!$('#viewer').open || $$('dialog[open]').some(d => d !== $('#viewer')) || !S.viewerPhoto || window.getSelection()?.toString()) return;
  e.preventDefault();
  guard(() => copyImageClipboard(S.viewerPhoto.id))();
});
const sizeLabel = n => n >= 1024 ** 3 ? (n / 1024 ** 3).toFixed(2) + ' GB' : (n / 1024 ** 2).toFixed(1) + ' MB';
async function openFileAction(mode, ids) {
  if (F.running) {
    $('#jobDialog').showModal();
    return;
  }
  F.prepared = await api('/api/files/prepare', {
    ids
  });
  F.mode = mode;
  const p = F.prepared,
    recycle = mode === 'recycle';
  I18n.text($('#fileTitle'), recycle ? T("删除原照片？") : mode === 'copy' ? T("复制照片") : T("导出分享包"));
  I18n.text($('#fileDescription'), T("已选 {0} 张 \xB7 原文件共 {1}", number(p.count), sizeLabel(p.bytes)));
  $('#fileNames').replaceChildren(...p.names.map(n => el('li', '', n)));
  if (p.count > p.names.length) $('#fileNames').append(el('li', '', T("以及另外 {0} 张照片", number(p.count - p.names.length))));
  $('#fileDestination').classList.toggle('hidden', recycle);
  if (!$('#destinationPath').value) $('#destinationPath').value = p.default_destination;
  I18n.text($('#fileWarning'), recycle ? T("这会把当前照片来源中选中的原文件放入 Windows 回收站，并从全部照片及所有相册中隐藏。可在回收站还原后刷新图库。若只想取消分组，请返回选择\u201C从此相册移除\u201D。") : mode === 'copy' ? T("复制完整原文件，保留文件名和时间。同名文件自动加序号，不覆盖已有文件。") : T("将完整原文件打包为 ZIP，包含原有照片信息和 RAW。仅保存到本机，生成后由你发送给他人。"));
  I18n.text($('#confirmFile'), recycle ? T("放入回收站") : mode === 'copy' ? T("开始复制") : T("生成 ZIP"));
  $('#confirmFile').className = recycle ? 'danger' : 'primary';
  I18n.text($('#fileError'), '');
  $('#fileDialog').showModal();
}
$('#copySelected').onclick = () => chooseCopy([...S.selected]);
$('#viewerCopy').onclick = () => chooseCopy([S.viewerPhoto.id]);
I18n.attr($('#viewerCopy'), "title", T("复制图片到剪贴板 / 复制到文件夹；Ctrl+C 直接复制图片"));
for (const [id, mode] of [['shareSelected', 'share'], ['deleteSelected', 'recycle']]) $('#' + id).onclick = guard(() => openFileAction(mode, [...S.selected]));
for (const [id, mode] of [['viewerShare', 'share'], ['viewerDelete', 'recycle']]) $('#' + id).onclick = guard(() => openFileAction(mode, [S.viewerPhoto.id]));
$('#browseDestination').onclick = () => openFolderBrowser();
$('#confirmFile').onclick = async () => {
  const b = $('#confirmFile');
  b.disabled = true;
  I18n.text($('#fileError'), '');
  try {
    const job = await api('/api/files/start', {
      token: F.prepared.token,
      mode: F.mode,
      destination: $('#destinationPath').value,
      confirm_recycle: F.mode === 'recycle'
    });
    F.job = job.id;
    F.running = true;
    $('#fileDialog').close();
    $('#jobDone').disabled = true;
    I18n.text($('#jobDone'), T("处理中\u2026"));
    I18n.text($('#jobTitle'), F.mode === 'recycle' ? T("正在放入回收站") : F.mode === 'copy' ? T("正在复制照片") : T("正在生成分享包"));
    I18n.text($('#jobStatus'), T("准备处理\u2026"));
    I18n.text($('#jobOutput'), '');
    $('#jobErrors').replaceChildren();
    $('#showFileOutput').classList.add('hidden');
    $('#jobProgress').value = 0;
    $('#jobProgress').max = job.total;
    $('#jobDialog').showModal();
    await pollFileJob();
  } catch (e) {
    I18n.text($('#fileError'), I18n.errorText(e));
  } finally {
    b.disabled = false;
  }
};
async function pollFileJob() {
  try {
    const job = await api('/api/files/job');
    if (job.id !== F.job) throw I18n.error(T("另一个窗口开始了新操作，请检查目标文件夹。"));
    $('#jobProgress').value = job.processed;
    $('#jobProgress').max = job.total;
    I18n.text($('#jobStatus'), T("已处理 {0} / {1} 张", number(job.processed), number(job.total)));
    if (job.running) {
      F.timer = setTimeout(pollFileJob, 500);
      return;
    }
    F.running = false;
    I18n.text($('#jobTitle'), job.errors.length ? T("操作未全部完成") : T("处理完成"));
    I18n.text($('#jobStatus'), I18n.concat(T("成功 {0} / {1} 张", number(job.succeeded), number(job.total)), F.mode === 'recycle' ? T(" \xB7 可在 Windows 回收站还原") : ''));
    I18n.text($('#jobOutput'), job.output || '');
    $('#showFileOutput').classList.toggle('hidden', !job.output);
    $('#jobErrors').replaceChildren(...job.errors.slice(0, 20).map(r => el('li', '', I18n.concat(r.name, ': ', T(r.error)))));
    $('#jobDone').disabled = false;
    I18n.text($('#jobDone'), T("完成"));
    if (F.mode === 'recycle') {
      if ($('#viewer').open) $('#viewer').close();
      S.selected.clear();
      S.selecting = false;
      await overview();
      await load(true);
    }
  } catch (e) {
    F.running = false;
    I18n.text($('#jobTitle'), T("暂时无法读取处理进度"));
    I18n.text($('#jobStatus'), I18n.concat(I18n.errorText(e), T(" 请检查目标文件夹，避免重复操作。")));
    $('#jobDone').disabled = false;
    I18n.text($('#jobDone'), T("关闭"));
  }
}
$('#jobDialog').addEventListener('cancel', e => {
  if (F.running) e.preventDefault();
});
$('#jobDone').onclick = () => $('#jobDialog').close();
$('#showFileOutput').onclick = guard(() => api('/api/files/reveal', {}));

// Source edits stay in this dialog until Apply. Changing mode clears the draft path.
let sourceDraft = null,
  sourceApplying = false,
  sourceRefreshTimer = null,
  sourceRefreshing = false;
function paintSourceSettings() {
  const all = sourceDraft.mode === 'computer';
  $('#sourceAll').checked = all;
  $('#sourceFolderFields').classList.toggle('hidden', all);
  $('#sourceDriveFields').classList.toggle('hidden', !all);
  $('#sourceFolderPath').value = all ? '' : sourceDraft.roots[0] || '';
  paintSourceDrives();
  I18n.text($('#sourceError'), '');
}
function paintSourceDrives() {
  const all = sourceDraft.mode === 'computer';
  const box = $('#sourceDriveChoices');
  box.replaceChildren();
  const drives = [...sourceDraft.drives];
  if (all) for (const path of sourceDraft.roots) {
    if (!drives.some(d => d.path.toLowerCase() === path.toLowerCase()))
      drives.push({path, ready: false, kind: 'offline'});
  }
  for (const drive of drives) {
    const label = el('label', 'source-drive'),
      input = document.createElement('input');
    input.type = 'checkbox';
    input.value = drive.path;
    input.checked = all && sourceDraft.roots.some(p => p.toLowerCase() === drive.path.toLowerCase());
    input.disabled = sourceApplying || (drive.ready === false && !input.checked);
    input.onchange = () => {
      sourceDraft.roots = input.checked ? [...sourceDraft.roots, drive.path] : sourceDraft.roots.filter(p => p.toLowerCase() !== drive.path.toLowerCase());
      paintSourceApply();
    };
    const name = el('span', 'source-drive-name', drive.label ? drive.path + ' · ' + drive.label : drive.path);
    const types = {fixed: '本机固定磁盘', sd: 'SD / MMC 卡', usb: 'USB 外接存储', removable: '可移动磁盘 / 读卡器', offline: '设备未连接'};
    let details = T(types[drive.kind] || '可移动磁盘 / 读卡器');
    if (drive.ready === false) details = I18n.concat(details, ' · ', T('未就绪或无法读取'));
    else if (drive.total_bytes) details = I18n.concat(details, ' · ', T('可用 {0} / {1} GB',
      I18n.number(Math.round(drive.free_bytes / 1073741824)), I18n.number(Math.round(drive.total_bytes / 1073741824))));
    label.classList.toggle('source-drive-offline', drive.ready === false);
    label.append(input, name, el('small', '', details));
    box.append(label);
  }
  if (!drives.length) box.append(el('p', '', T("暂未找到磁盘，请连接 SD 卡或外接存储后刷新。")));
  paintSourceApply();
}
function paintSourceApply() {
  const disconnected = sourceDraft?.mode === 'computer' && sourceDraft.roots.some(path =>
    !sourceDraft.drives.some(d => d.path.toLowerCase() === path.toLowerCase() && d.ready !== false));
  const ready = sourceDraft && sourceDraft.roots.length > 0 && !disconnected;
  $('#applySource').disabled = sourceApplying || !ready;
  $('#sourceRecommended').disabled = sourceApplying || !sourceDraft?.drives.some(d => d.default && d.ready !== false);
  if (disconnected) {
    I18n.text($('#sourceSelection'), T('所选设备未就绪，请重新连接或取消勾选。'));
    return;
  }
  I18n.text($('#sourceSelection'), ready ? sourceDraft.mode === 'computer' ? T("已选 {0} 个磁盘", sourceDraft.roots.length) : T("已选择照片文件夹") : T("请重新选择浏览范围"));
}
async function openSourceSettings() {
  const state = await api('/api/source');
  sourceDraft = {
    mode: state.mode,
    roots: [...state.roots],
    drives: state.drives
  };
  paintSourceSettings();
  $('#sourceDialog').showModal();
  clearInterval(sourceRefreshTimer);
  sourceRefreshTimer = setInterval(() => refreshSourceDrives(false), 4000);
}
async function refreshSourceDrives(manual = true) {
  if (sourceApplying || sourceRefreshing || !$('#sourceDialog').open) return;
  sourceRefreshing = true;
  const draft = sourceDraft;
  $('#sourceRefresh').disabled = true;
  try {
    const state = await api('/api/source');
    if (!$('#sourceDialog').open || sourceDraft !== draft || sourceApplying) return;
    const signature = drives => JSON.stringify(drives.map(({free_bytes, ...identity}) => identity));
    if (manual || signature(state.drives) !== signature(sourceDraft.drives)) {
      sourceDraft.drives = state.drives;
      paintSourceDrives();
    }
    if (manual) I18n.text($('#sourceError'), '');
  } catch (err) {
    if ($('#sourceDialog').open && manual) I18n.text($('#sourceError'), I18n.errorText(err));
  } finally {
    sourceRefreshing = false;
    $('#sourceRefresh').disabled = sourceApplying;
  }
}
$('#sourceRefresh').onclick = () => refreshSourceDrives();
$('#sourceSettings').onclick = $('#sourceSettingsTop').onclick = guard(openSourceSettings);
$('#sourceAll').onchange = () => {
  sourceDraft.mode = $('#sourceAll').checked ? 'computer' : 'folder';
  sourceDraft.roots = [];
  paintSourceSettings();
};
$('#sourceFolderPath').oninput = () => {
  const value = $('#sourceFolderPath').value.trim();
  sourceDraft.roots = value ? [value] : [];
  paintSourceApply();
};
$('#sourceBrowse').onclick = () => openFolderBrowser({
  title: T("选择要浏览的照片文件夹"),
  value: $('#sourceFolderPath').value,
  onSelect: path => {
    sourceDraft.roots = [path];
    $('#sourceFolderPath').value = path;
    paintSourceApply();
  }
});
$('#sourceRecommended').onclick = () => {
  sourceDraft.roots = sourceDraft.drives.filter(d => d.default && d.ready !== false).map(d => d.path);
  paintSourceSettings();
};
$('#sourceForm').onsubmit = async e => {
  e.preventDefault();
  sourceApplying = true;
  const button = $('#applySource');
  for (const n of $('#sourceForm').elements) n.disabled = true;
  I18n.text(button, T("正在切换\u2026"));
  I18n.text($('#sourceError'), '');
  try {
    await api('/api/source/apply', {
      mode: sourceDraft.mode,
      roots: sourceDraft.roots
    });
    location.reload();
  } catch (err) {
    sourceApplying = false;
    for (const n of $('#sourceForm').elements) n.disabled = false;
    I18n.text($('#sourceError'), I18n.errorText(err));
    I18n.text(button, T("应用并浏览"));
    paintSourceDrives();
  }
};
$('#sourceDialog').addEventListener('cancel', e => {
  if (sourceApplying) e.preventDefault();
});
$('#sourceDialog').addEventListener('close', () => {
  clearInterval(sourceRefreshTimer);
  sourceRefreshTimer = null;
  I18n.text($('#applySource'), T("应用并浏览"));
});
