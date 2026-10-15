'use strict';
// Every same-origin mutation carries the session's CSRF token.
(() => {
 const nativeFetch = window.fetch.bind(window);
 window.fetch = async function(input, options = {}) {
  const url = new URL(input instanceof Request ? input.url : input, location.href);
  const method = (options.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
  if (url.origin === location.origin) {
   const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
   headers.set('X-Requested-With', 'XMLHttpRequest');
   if (!['GET','HEAD','OPTIONS'].includes(method)) headers.set('X-CSRF-Token', document.querySelector('meta[name=csrf-token]')?.content || '');
   options = {...options, headers};
  }
  const response = await nativeFetch(input, options);
  if (response.status === 401 && url.origin === location.origin && location.pathname !== '/login') location.assign('/login');
  return response;
 };
 window.postDelete = function(url) {
  const target = new URL(url, location.href);
  if(target.origin !== location.origin) return;
  const form = document.createElement('form');form.method='POST';form.action=target.pathname;
  const token=document.createElement('input');token.type='hidden';token.name='csrf_token';token.value=document.querySelector('meta[name=csrf-token]').content;
  form.append(token);document.body.append(form);form.submit();
 };
 document.addEventListener('click', event => {
  if(event.defaultPrevented)return;
  const link=event.target.closest('a[href]');
  if(link && /^\/excluir(?:_|\/)/.test(link.getAttribute('href'))){event.preventDefault();window.postDelete(link.href);}
 });
 document.addEventListener('DOMContentLoaded',()=>{if(localStorage.getItem('tema_preferido')==='escuro')document.body.classList.add('dark-mode');});
})();
