'use strict';

// Share selections with the grid, while keeping browsing and thumbnail picking separate.
let viewerPicking = false,
  returnPositionSerial = 0,
  timelineSerial = 0;
function paintViewerSelection() {
  const photo = viewerSession?.lastPhoto,
    chosen = photo && S.selected.has(photo.id);
  $('#viewerSelectCurrent').disabled = !photo;
  I18n.text($('#viewerSelectCurrent'), chosen ? T("\u2713 已选择当前照片") : T("\u25A1 选择当前照片"));
  $('#viewerSelectCurrent').setAttribute('aria-pressed', String(!!chosen));
  I18n.text($('#viewerSelectMode'), viewerPicking ? T("完成缩略图多选") : T("多选缩略图"));
  $('#viewerSelectMode').setAttribute('aria-pressed', String(viewerPicking));
  I18n.text($('#viewerSelectedCount'), T("已选 {0} 张", number(S.selected.size)));
  I18n.text($('#viewerAddSelected'), S.selected.size ? T("加入相册（{0}）", number(S.selected.size)) : T("加入相册"));
  $('#viewerAddSelected').disabled = $('#viewerClearSelection').disabled = !S.selected.size;
  I18n.text($('#seekHint'), viewerPicking ? T("点击缩略图勾选 \xB7 用左右箭头或时间轴继续看大图") : T("悬停放大 \xB7 点击或拖动松开切换 \xB7 滚轮浏览缩略图"));
  $('#filmRail').classList.toggle('picking', viewerPicking);
  if ($('#viewer').open) filmPaintSoon();
}
function paintFilmSelection(node, index) {
  const photo = film.rows.get(index) || viewerSession?.initial[index];
  const chosen = photo && S.selected.has(photo.id);
  node.classList.toggle('chosen', !!chosen);
  let badge = node.querySelector('.film-choice');
  if (!badge) {
    badge = el('span', 'film-choice');
    badge.setAttribute('aria-hidden', 'true');
    node.append(badge);
  }
  I18n.text(badge, chosen ? '✓' : '○');
  badge.classList.toggle('hidden', !viewerPicking && !chosen);
  if (viewerPicking) node.setAttribute('aria-pressed', String(!!chosen));else node.removeAttribute('aria-pressed');
  if (photo) I18n.attr(node, 'aria-label', T("第 {0} 张：{1}{2}{3}", number(index + 1), photo.name, chosen ? T("，已选择") : '', viewerPicking ? T("，点击切换选择") : ''));
}
async function activateFilmPhoto(index) {
  if (!viewerPicking) return showViewer(index);
  const session = viewerSession,
    photo = await viewerPhoto(index, session);
  if (photo && session === viewerSession && $('#viewer').open) toggleSelect(photo.id);
}
$('#viewerSelectMode').onclick = () => {
  viewerPicking = !viewerPicking;
  paintViewerSelection();
};
$('#viewerSelectCurrent').onclick = () => {
  if (viewerSession?.lastPhoto) toggleSelect(viewerSession.lastPhoto.id);
};
$('#viewerClearSelection').onclick = () => clearPhotoSelection();
$('#viewerAddSelected').onclick = () => {
  if (S.selected.size) chooseAlbum([...S.selected]);
};
$('#filmReturn').onclick = () => {
  if (!viewerSession?.lastPhoto) return;
  hideSeekPreview();
  film.wheel = 0;
  paintSeek(S.viewerIndex);
  film.slots.get(S.viewerIndex)?.focus({
    preventScroll: true
  });
};
$('#viewer').addEventListener('close', () => {
  viewerPicking = false;
  timelineSerial++;
  $('#seekTimeline').replaceChildren();
});

// Fetch missing metadata in bounded batches and render the grid once, even after a
// jump thousands of photos ahead. Lazy image loading keeps original files untouched.
async function restoreViewerPosition(session) {
  const serial = ++returnPositionSerial,
    photo = session?.lastPhoto;
  if (!photo || session.query !== photoQuery().toString() || session.view !== S.view) return;
  const version = S.version,
    valid = () => serial === returnPositionSerial && version === S.version && !$('#viewer').open && session.query === photoQuery().toString() && session.view === S.view;
  S.restoring = serial;
  try {
    // An automatic page request may already be in flight when the dialog closes.
    while (S.loading && valid()) await new Promise(resolve => setTimeout(resolve, 25));
    if (!valid()) return;
    let target = S.items.findIndex(p => p.id === photo.id);
    if (target < 0) {
      toast(T("正在定位刚刚浏览的照片\u2026"));
      const rows = S.items.slice(),
        end = Math.min(session.total, session.lastIndex + 121);
      for (let start = rows.length; start < end; start += 960) {
        const requests = [];
        for (let offset = start; offset < Math.min(start + 960, end); offset += 240) {
          const q = new URLSearchParams(session.query);
          q.set('offset', offset);
          q.set('limit', Math.min(240, end - offset));
          requests.push(api('/api/photos?' + q));
        }
        const pages = await Promise.all(requests);
        if (!valid()) return;
        for (const page of pages) rows.push(...page.items);
      }
      S.items = rows;
      target = rows.findIndex(p => p.id === photo.id);
    }
    if (target < 0) {
      toast(T("照片列表已变化，未找到刚刚浏览的照片"));
      return;
    }
    collapsedDates.delete(photo.taken.slice(0, 10));
    renderPhotos();
    updateHeader();
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (!valid()) return;
    const card = $(`.photo-card[data-id="${photo.id}"]`);
    if (card) {
      card.scrollIntoView({
        block: 'center',
        behavior: 'instant'
      });
      card.focus({
        preventScroll: true
      });
      card.classList.add('returned-photo');
      setTimeout(() => card.classList.remove('returned-photo'), 3200);
    }
  } finally {
    if (S.restoring === serial) S.restoring = 0;
  }
}

// Labels are actual photo timestamps at evenly spaced photo indices, not invented
// evenly spaced calendar dates. Their positions match the range input's thumb.
async function renderSeekTimeline(session = viewerSession) {
  if (!session || !$('#viewer').open) return;
  const axis = $('#seekTimeline'),
    width = axis.clientWidth;
  const count = Math.min(session.total, Math.max(2, Math.min(7, Math.floor(width / 180) + 1)));
  if (session.timelineCount === count) return;
  session.timelineCount = count;
  const serial = ++timelineSerial;
  I18n.text($('#seekScope'), session.view === 'all' ? T("全图库定位") : T("当前范围定位"));
  axis.setAttribute('aria-busy', 'true');
  axis.replaceChildren();
  try {
    const indices = [...new Set(Array.from({
      length: count
    }, (_, i) => count === 1 ? 0 : Math.round(i * (session.total - 1) / (count - 1))))];
    const photos = await Promise.all(indices.map(i => viewerPhoto(i, session)));
    if (session !== viewerSession || serial !== timelineSerial || !$('#viewer').open) return;
    const first = photos[0]?.taken,
      last = photos.at(-1)?.taken;
    const span = Math.abs(Date.parse(first) - Date.parse(last));
    const detailed = session.view !== 'all' && Number.isFinite(span) && span <= 31 * 86400000;
    const acrossYears = first?.slice(0, 4) !== last?.slice(0, 4);
    axis.dataset.precision = detailed ? 'minute' : 'date';
    photos.forEach((photo, i) => {
      if (!photo) return;
      const stamp = photo.taken.replace('T', ' '),
        label = I18n.date(photo.taken, detailed ? acrossYears ? 'datetime' : 'shorttime' : 'numeric');
      const tick = el('button', 'seek-tick', label);
      tick.type = 'button';
      tick.dataset.index = indices[i];
      tick.style.left = (session.total > 1 ? indices[i] / (session.total - 1) * 100 : 0) + '%';
      if (i === 0) tick.classList.add('first');
      if (i === photos.length - 1 && i !== 0) tick.classList.add('last');
      I18n.attr(tick, "title", T("{0} \xB7 第 {1} 张 \xB7 {2}", stamp, number(indices[i] + 1), photo.name));
      I18n.attr(tick, 'aria-label', T("跳到 {0}，第 {1} 张", label, number(indices[i] + 1)));
      tick.onclick = guard(() => session === viewerSession ? showViewer(indices[i]) : undefined);
      axis.append(tick);
    });
  } catch (e) {
    if (session === viewerSession && serial === timelineSerial) {
      session.timelineCount = null;
      I18n.text(axis, T("日期暂时不可用"));
      throw e;
    }
  } finally {
    if (serial === timelineSerial) axis.removeAttribute('aria-busy');
  }
}
new ResizeObserver(() => {
  if ($('#viewer').open) guard(() => renderSeekTimeline())();
}).observe($('#seekTimeline'));
