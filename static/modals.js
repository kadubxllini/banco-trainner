'use strict';
// Native dialogs live in the browser's top layer, outside page clipping and stacking.
function abrirJanelaModal(id) {
 const modal = typeof id === 'string' ? document.getElementById(id) : id;
 if (!modal || modal.open) return;
 modal.showModal();
 modal.scrollTop = 0;
 const content = modal.querySelector('.modal-content');
 if (content) content.scrollTop = 0;
 const close = modal.querySelector('.close-modal');
 if (close) close.focus({preventScroll:true});
 // Form population and vacancy sorting finish synchronously after opening.
 requestAnimationFrame(() => {
  if (!modal.open) return;
  modal.scrollTop = 0;
  if (content) content.scrollTop = 0;
 });
}
function fecharJanelaModal(id) {
 const modal = typeof id === 'string' ? document.getElementById(id) : id;
 if (modal?.open) modal.close();
}
document.addEventListener('DOMContentLoaded', () => {
 document.querySelectorAll('dialog.modal').forEach(modal => {
  const title = modal.querySelector('h3');
  if (title) {title.id ||= `${modal.id}Title`;modal.setAttribute('aria-labelledby',title.id);}
  modal.addEventListener('cancel', event => {
   event.preventDefault();
   if (modal.id === 'modalCalendario') window.fecharModalCalendario();
   else fecharJanelaModal(modal);
  });
 });
});
