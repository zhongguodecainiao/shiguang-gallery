'use strict';

function canRenameFolder(folder) {
  return folder && folder !== '.' && !/^[a-z]:[\\/]?$/i.test(folder) && !S.overview?.roots.some(root => root.toLowerCase() === folder.toLowerCase());
}
function updateFolderRenameHeader() {
  if (S.view !== 'folder' || !canRenameFolder(S.folder)) return;
  const button = el('button', 'folder-title-button', S.folder);
  I18n.attr(button, 'title', T('点击重命名文件夹'));
  I18n.attr(button, 'aria-label', T('重命名文件夹：{0}', S.folder));
  button.dataset.folder = S.folder;
  button.onclick = () => openFolderRename(S.folder);
  $('#title').replaceChildren(button);
}
let renameFolderTarget = null, renameFolderBusy = false, folderMenuTarget = null;
function closeFolderMenu() { $('#folderContextMenu').classList.add('hidden'); }
function openFolderRename(folder) {
  closeFolderMenu();
  if (!canRenameFolder(folder)) return;
  renameFolderTarget = folder;
  $('#renameFolderName').value = folder.split(/[\\/]/).filter(Boolean).at(-1);
  I18n.text($('#renameFolderPath'), folder);
  I18n.text($('#renameFolderError'), '');
  $('#renameFolderDialog').showModal();
  $('#renameFolderName').focus();$('#renameFolderName').select();
}
document.addEventListener('contextmenu', e => {
  const card = e.target.closest('[data-folder]');
  if (!card || !canRenameFolder(card.dataset.folder)) {closeFolderMenu();return;}
  e.preventDefault();folderMenuTarget = card.dataset.folder;
  const menu = $('#folderContextMenu'), rect = card.getBoundingClientRect();
  menu.classList.remove('hidden');
  menu.style.left = Math.max(8, Math.min(e.clientX || rect.left + 20, innerWidth - menu.offsetWidth - 8)) + 'px';
  menu.style.top = Math.max(8, Math.min(e.clientY || rect.top + 20, innerHeight - menu.offsetHeight - 8)) + 'px';
  $('#folderContextRename').focus();
});
$('#folderContextRename').onclick = () => openFolderRename(folderMenuTarget);
document.addEventListener('pointerdown', e => {if (!e.target.closest('#folderContextMenu')) closeFolderMenu();});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeFolderMenu();
  if (e.key === 'F2' && !document.querySelector('dialog[open]')) {
    const folder = e.target.closest('[data-folder]')?.dataset.folder || (S.view === 'folder' ? S.folder : null);
    if (canRenameFolder(folder)) {e.preventDefault();openFolderRename(folder);}
  }
});
window.addEventListener('scroll', closeFolderMenu, true);
window.addEventListener('resize', closeFolderMenu);
$('#renameFolderDialog').addEventListener('cancel', e => {if (renameFolderBusy) e.preventDefault();});
$('#renameFolderForm').onsubmit = async e => {
  e.preventDefault();if (renameFolderBusy) return;
  renameFolderBusy = true;
  const folder = renameFolderTarget, name = $('#renameFolderName').value;
  const buttons = $$('#renameFolderForm button');buttons.forEach(b => b.disabled = true);
  I18n.text($('#renameFolderError'), '');
  try {
    const result = await api('/api/folders/rename', {folder, name});
    if (S.view === 'folder' && S.folder === folder) S.folder = result.folder;
    $('#renameFolderDialog').close();
    await overview();await load(true);
    toast(T('文件夹已重命名'));
  } catch (error) {
    if ($('#renameFolderDialog').open) I18n.text($('#renameFolderError'), I18n.errorText(error));
    else toast(I18n.errorText(error));
  }
  finally {renameFolderBusy = false;buttons.forEach(b => b.disabled = false);}
};
