'use strict';
document.addEventListener('DOMContentLoaded', () => {
 const rows = [...document.querySelectorAll('#radarRows tr')];
 const search = document.getElementById('radarSearch');
 const status = document.getElementById('radarStatus');
 let view = 'all', folder = '', ascending = true;
 const norm = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
 const folderBranches = [...document.querySelectorAll('.folder-branch')];
 const folderIds = id => {
  const branch = folderBranches.find(b => b.dataset.folderId === id);
  return new Set(branch ? [id,...branch.querySelectorAll('.folder-branch').values()].map(b => typeof b === 'string' ? b : b.dataset.folderId) : [id]);
 };
 const stageNames = row => [...row.querySelectorAll('.stage-select')].map(s => s.selectedOptions[0].textContent);
 function filter() {
  let count = 0, processes = 0;
  const visibleFolders = folderIds(folder);
  for (const row of rows) {
   const stages = stageNames(row);
   const text = row.querySelector('.company-label').textContent + ' ' + row.querySelector('.vacancy-cell').textContent + ' ' + row.querySelector('.responsible-cell').textContent;
   row.hidden = !(norm(text).includes(norm(search.value)) && (!folder || visibleFolders.has(row.dataset.folder)) && (!status.value || stages.includes(status.value)) && (view !== 'late' || row.dataset.late === '1') && (view !== 'open' || stages.includes('VAGA ABERTA')));
   if (!row.hidden) { count++; processes += row.querySelectorAll('.stage-select').length; }
  }
  document.getElementById('radarCount').textContent = `${count} empresas · ${processes} processos`;
  document.getElementById('radarEmpty').hidden = count > 0;
  document.getElementById('openCount').textContent = rows.filter(row => stageNames(row).includes('VAGA ABERTA')).length;
  document.getElementById('mobileFolder').value=folder;
 }
 [search,status].forEach(el => el.addEventListener('input', filter));
 document.querySelectorAll('.view-tab').forEach(button => button.addEventListener('click', () => { view = button.dataset.view; if(view==='all'){folder='';document.querySelectorAll('.folder-filter').forEach(b=>b.classList.remove('active'));} document.querySelectorAll('.view-tab').forEach(b => b.classList.toggle('active', b === button));filter(); }));
 function clear(){search.value='';status.value='';folder='';view='all';document.querySelectorAll('.view-tab').forEach(b=>b.classList.toggle('active',b.dataset.view==='all'));document.querySelectorAll('.folder-filter').forEach(b=>b.classList.remove('active'));filter();}
 document.getElementById('clearFilters').addEventListener('click',clear);
 document.getElementById('mobileFolder').addEventListener('change',event=>{folder=event.target.value;document.querySelectorAll('.folder-filter').forEach(b=>b.classList.toggle('active',b.dataset.folder===folder));filter();});
 function expandFolder(branch, expanded){
  const toggle=branch.querySelector(':scope > .folder-item > .folder-toggle');
  const children=branch.querySelector(':scope > .folder-children');
  if(!toggle||!children)return;
  toggle.setAttribute('aria-expanded',String(expanded));
  toggle.setAttribute('aria-label',`${expanded?'Fechar':'Abrir'} subpastas de ${branch.querySelector(':scope > .folder-item .folder-filter').title}`);
  children.hidden=!expanded;
 }
 document.querySelectorAll('.folder-toggle').forEach(button=>button.addEventListener('click',()=>expandFolder(button.closest('.folder-branch'),button.getAttribute('aria-expanded')!=='true')));
 document.querySelectorAll('.folder-filter').forEach(button=>button.addEventListener('click',()=>{folder=button.dataset.folder;expandFolder(button.closest('.folder-branch'),true);document.querySelectorAll('.folder-filter').forEach(b=>b.classList.toggle('active',b===button));filter();}));
 document.getElementById('radarSort').addEventListener('click',()=>{ascending=!ascending;rows.sort((a,b)=>a.dataset.name.localeCompare(b.dataset.name,'pt-BR')*(ascending?1:-1));document.getElementById('radarRows').append(...rows);document.querySelector('#radarSort span').textContent=ascending?'↑':'↓';rows.forEach((r,i)=>r.querySelector('.row-number').textContent=i+1);});
 const backdrop=document.getElementById('detailBackdrop');
 const originalOpen=window.abrirChat;
 let previousFocus;
 window.abrirChat=function(...args){previousFocus=document.activeElement;document.body.classList.add('radar-detail');backdrop.hidden=false;originalOpen(...args);document.getElementById('closeDetail').focus();};
 function closeDetail(){document.body.classList.remove('radar-detail');backdrop.hidden=true;previousFocus?.focus();}
 document.getElementById('closeDetail').addEventListener('click',closeDetail);backdrop.addEventListener('click',closeDetail);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){const modals=[...document.querySelectorAll('.modal')].filter(m=>getComputedStyle(m).display!=='none');if(modals.length)modals.at(-1).style.display='none';else closeDetail();}});
 document.querySelectorAll('.company-button').forEach(b=>b.addEventListener('click',()=>window.abrirChat(b.dataset.id,b.dataset.name)));
 document.querySelectorAll('.radar-edit').forEach(b=>b.addEventListener('click',()=>{prepararEdicao(b);organizeVacancies(document.getElementById('modalEditar'));const find=document.querySelector('#modalEditar .vacancy-search');find.value='';document.querySelectorAll('#modalEditar .vacancy-row').forEach(r=>r.hidden=false);}));
 document.querySelectorAll('.folder-edit').forEach(b=>b.addEventListener('click',()=>prepararEdicaoPasta(b)));
 const settingsButton=document.getElementById('settingsToggle'), settingsMenu=document.getElementById('settingsMenu');
 function closeSettings(){settingsMenu.hidden=true;settingsButton.setAttribute('aria-expanded','false');}
 settingsButton.addEventListener('click',()=>{settingsMenu.hidden=!settingsMenu.hidden;settingsButton.setAttribute('aria-expanded',String(!settingsMenu.hidden));});
 settingsMenu.querySelectorAll('button').forEach(b=>b.addEventListener('click',closeSettings));
 document.addEventListener('click',e=>{if(!e.target.closest('.settings-dropdown'))closeSettings();});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!settingsMenu.hidden){closeSettings();settingsButton.focus();}});
 const tones={'SP ENVIADO':'green','PROPOSTA ENVIADA':'purple','FATURAMENTO ENVIADO':'blue','VAGA ABERTA':'amber','VAGA FECHADA':'green','VAGA CANCELADA':'red'};
 const paint=s=>s.dataset.tone=tones[s.selectedOptions[0].textContent]||'neutral';
 let toastTimer;
 function toast(text){const el=document.getElementById('radarToast');el.textContent=text;el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,3500);}
 document.querySelectorAll('.stage-select').forEach(select=>{
  paint(select);
  select.addEventListener('change',async()=>{
   select.disabled=true;
   try{
    const response=await fetch('/api/processos/etapa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cliente_id:select.dataset.client,vaga_id:select.dataset.vaga,status_id:select.value})});
    if(!response.ok)throw new Error('save');
    select.dataset.saved=select.value;
    const edit=select.closest('tr').querySelector('.radar-edit');
    edit.dataset.vagas=edit.dataset.vagas.split(',').map(v=>{const parts=v.split(':');if(parts[0]===select.dataset.vaga)parts[1]=select.value;return parts.join(':');}).join(',');
    toast('Etapa atualizada');
   }catch{select.value=select.dataset.saved;toast('Não foi possível salvar a etapa. Tente novamente.');}
   finally{select.disabled=false;paint(select);filter();}
  });
 });
 // Labels and a consistent layout replace the old unlabeled fields.
 const labels={'edit_nome':'Nome da empresa','edit_pasta':'Pasta'};
 for(const [id,text] of Object.entries(labels)){const el=document.getElementById(id);const label=document.createElement('label');label.className='section-label';label.htmlFor=id;label.textContent=text;el.before(label);}
 document.querySelector('#modalCliente h3').textContent='Nova empresa';document.querySelector('#modalEditar h3').textContent='Editar empresa';
 const deleteCompany=document.createElement('button');deleteCompany.type='button';deleteCompany.className='danger-action';deleteCompany.innerHTML=actionIcon('trash')+'<span>Excluir empresa</span>'; deleteCompany.addEventListener('click',()=>{if(confirm('Excluir esta empresa e seu cadastro?'))postDelete(document.getElementById('formEditar').action.replace('/editar/','/excluir/'));});document.querySelector('#modalEditar .modal-buttons').prepend(deleteCompany);
 function organizeVacancies(modal){const picker=modal.querySelector('.vacancy-picker');if(!picker)return;const entries=[...picker.querySelectorAll('.vacancy-row')];entries.sort((a,b)=>Number(b.querySelector('input[type=checkbox]').checked)-Number(a.querySelector('input[type=checkbox]').checked));picker.append(...entries);}
 for(const modal of [document.getElementById('modalCliente'),document.getElementById('modalEditar')]){
  const checks=[...modal.querySelectorAll('input[name=vagas_ids]')];
  if(!checks.length)continue;
  const picker=checks[0].closest('label').parentElement.parentElement;picker.classList.add('vacancy-picker');
  checks.forEach(c=>c.closest('label').parentElement.classList.add('vacancy-row'));
  const find=document.createElement('input');find.type='search';find.placeholder='Buscar vaga para adicionar…';find.setAttribute('aria-label','Buscar vaga');find.className='vacancy-search';picker.before(find);
  find.addEventListener('input',()=>picker.querySelectorAll('.vacancy-row').forEach(row=>row.hidden=!norm(row.querySelector('label').textContent).includes(norm(find.value))));
  modal.querySelectorAll('.section-label').forEach(l=>{if(l.textContent.includes('Status'))l.textContent='Vagas e etapas';});
 }
 document.querySelectorAll('.modal .close-modal').forEach(el=>{el.setAttribute('role','button');el.setAttribute('tabindex','0');el.setAttribute('aria-label','Fechar');el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' ')el.click();});});
 document.querySelectorAll('.modal').forEach(el=>{el.setAttribute('role','dialog');el.setAttribute('aria-modal','true');});
 filter();
});



