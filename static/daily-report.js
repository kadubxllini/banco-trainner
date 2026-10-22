'use strict';
document.addEventListener('DOMContentLoaded', () => {
 const button = document.getElementById('reportTheme');
 try {document.body.classList.toggle('dark-mode', localStorage.getItem('tema_preferido') === 'escuro');} catch (_) {}
 button.addEventListener('click', () => {
  const dark = document.body.classList.toggle('dark-mode');
  try {localStorage.setItem('tema_preferido', dark ? 'escuro' : 'claro');} catch (_) {}
 });
 const form = document.querySelector('.report-filters');
 const status = document.getElementById('reportFilterStatus');
 let timer, controller, revision = 0;
 async function update(url) {
  const current = ++revision;
  controller?.abort();controller = new AbortController();
  status.textContent = 'Atualizando…';
  document.getElementById('reportResults').setAttribute('aria-busy','true');
  try {
   const response = await fetch(url, {signal:controller.signal});
   if (response.redirected && new URL(response.url).pathname === '/login') {location.assign(response.url);return;}
   if (!response.ok && response.status !== 400) throw new Error('request');
   const html = new DOMParser().parseFromString(await response.text(), 'text/html');
   const results = html.getElementById('reportResults');
   if (!results) throw new Error('content');
   if (current !== revision) return;
   document.getElementById('reportResults').replaceWith(results);
   history.replaceState(null,'',url);
   status.textContent = response.ok ? '' : 'Confira as datas selecionadas.';
  } catch (error) {
   if (current === revision && error.name !== 'AbortError') status.textContent = 'Falha ao atualizar. Exibindo o resultado anterior; altere um filtro para tentar novamente.';
  } finally {
   if (current === revision) document.getElementById('reportResults').removeAttribute('aria-busy');
  }
 }
 function apply() {
  clearTimeout(timer);
  if (!form.checkValidity()) return;
  const url = new URL(form.action);
  url.search = new URLSearchParams(new FormData(form)).toString();
  update(url);
 }
 form.addEventListener('submit',event=>{event.preventDefault();apply();});
 form.querySelectorAll('select,input[type=date]').forEach(control=>control.addEventListener('change',apply));
 form.querySelector('input[type=search]').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,350);});
 document.addEventListener('click', event=>{
  const link = event.target.closest('.report-pagination a');
  if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();clearTimeout(timer);update(new URL(link.href));
 });
});
