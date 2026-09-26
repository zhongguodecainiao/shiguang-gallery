'use strict';

(() => {
  const dialog = $('#releaseDialog');
  let current = null,
    closing = false,
    opened = false;
  function sections(groups, compact = false) {
    return groups.map(group => {
      const section = el('section', compact ? 'release-section compact' : 'release-section'),
        list = el('ul');
      list.append(...group.items.map(text => el('li', '', T(text))));
      section.append(el('h3', '', T(group.title)), list);
      return section;
    });
  }
  function historyCard(item, compact = false) {
    const card = el('article', compact ? 'release-history-card' : 'release-archive-card');
    card.append(el('h3', '', item.version), el('p', '', T(item.summary)), ...sections(item.sections, compact));
    return card;
  }
  function paintHistory(release) {
    const history = release.history || [release];
    $('#releaseHistory').replaceChildren(...history.map(item => historyCard(item, true)));
    const older = history.filter(item => item.version !== release.version);
    $('#releaseArchive').replaceChildren(el('h2', '', T('过往版本')), ...older.map(item => historyCard(item)));
  }
  function show(release) {
    if (dialog.open) return;
    current = release;
    opened = true;
    I18n.text($('#releaseVersion'), release.version === '1.0.3' ? 'v 1.0.3' : release.version);
    I18n.text($('#releaseSummary'), T(release.summary));
    $('#releaseSections').replaceChildren(...sections(release.sections));
    paintHistory(release);
    dialog.scrollTop = 0;
    dialog.showModal();
  }
  async function dismiss() {
    if (closing || !current) return;
    closing = true;
    $('#releaseDone').disabled = $('#releaseClose').disabled = true;
    try {
      await api('/api/updates/seen', {
        version: current.version
      });
    } catch (e) {
      toast(T("更新说明已关闭，但未能保存已读状态，下次打开可能再次提示。"));
    } finally {
      dialog.close();
      closing = false;
      $('#releaseDone').disabled = $('#releaseClose').disabled = false;
    }
  }
  $('#releaseDone').onclick = $('#releaseClose').onclick = dismiss;
  dialog.addEventListener('cancel', e => {
    e.preventDefault();
    dismiss();
  });
  $('#showReleaseNotes').onclick = guard(async () => show(await api('/api/updates')));
  const updateDialog = $('#updateDialog'), updateStatus = $('#updateStatus'), updateDetails = $('#updateDetails'), updateDownload = $('#updateDownload'), updateDone = $('#updateDone'), updateClose = $('#updateClose');
  function showUpdate(result) {
    updateDownload.disabled = true;
    updateDownload.onclick = null;
    updateDetails.replaceChildren();
    if (!result.ok) {
      updateStatus.textContent = result.error || '暂时无法连接更新服务器。';
    } else if (!result.update_available) {
      updateStatus.textContent = '当前已经是最新版本。';
      updateDetails.append(el('p', '', `当前版本：${result.current_display_version}`));
    } else {
      const latest = result.latest;
      updateStatus.textContent = `发现新版本：${latest.display_version}`;
      updateDetails.append(el('p', '', latest.summary));
      if (latest.published_at) updateDetails.append(el('p', '', `发布日期：${latest.published_at}`));
      if (latest.download_url) {
        updateDownload.disabled = false;
        updateDownload.onclick = installUpdate;
      }
    }
  }
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  async function installUpdate() {
    if (!window.confirm('拾光图库将下载并校验更新包，然后自动退出、安装新版并重新启动。现在继续吗？')) return;
    updateDownload.disabled = true;
    updateDone.disabled = updateClose.disabled = true;
    updateStatus.textContent = '正在准备应用内更新…';
    try {
      const started = await api('/api/update-install', {});
      if (started.state === 'failed') throw new Error(started.message || '无法开始更新。');
      for (;;) {
        const state = await api('/api/update-status');
        updateStatus.textContent = state.message || '正在处理更新…';
        if (state.state === 'failed') throw new Error(state.message || '更新失败。');
        if (state.state === 'installing') return;
        await pause(700);
      }
    } catch (error) {
      updateStatus.textContent = error.message || '自动更新失败。';
      updateDownload.disabled = false;
      updateDone.disabled = updateClose.disabled = false;
    }
  }
  async function checkUpdate() {
    updateStatus.textContent = '正在连接更新服务器…';
    updateDetails.replaceChildren();
    updateDownload.disabled = true;
    updateDialog.showModal();
    showUpdate(await api('/api/update-check'));
  }
  $('#updateCheck').onclick = guard(checkUpdate);
  $('#updateClose').onclick = $('#updateDone').onclick = () => updateDialog.close();
  async function startup() {
    try {
      const release = await api('/api/updates');
      paintHistory(release);
      if (!release.unread || opened) return;
      // Do not interrupt a photo or another dialog opened before the startup request returned.
      const whenReady = () => {
        if (opened) return;
        if (document.hidden || document.querySelector('dialog[open]')) {
          setTimeout(whenReady, 500);
          return;
        }
        show(release);
      };
      whenReady();
    } catch (e) {
      console.warn(T("暂时无法读取更新说明"), e);
    }
  }
  I18n.ready.then(startup);
})();
