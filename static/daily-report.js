'use strict';
document.addEventListener('DOMContentLoaded', () => {
 const button = document.getElementById('reportTheme');
 try {document.body.classList.toggle('dark-mode', localStorage.getItem('tema_preferido') === 'escuro');} catch (_) {}
 button.addEventListener('click', () => {
  const dark = document.body.classList.toggle('dark-mode');
  try {localStorage.setItem('tema_preferido', dark ? 'escuro' : 'claro');} catch (_) {}
 });
});
