'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('modalCalendario');
  const list = document.getElementById('listaInteracoes');
  const dateInput = document.getElementById('calendarDate');
  const iso = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  const parse = value => new Date(`${value}T12:00:00`);
  let month = new Date(), selected = iso(new Date()), days = new Set(), reminders = [], requestId = 0;
  const reminderDate = item => { const [d,m,y] = item.data.slice(0,10).split('/'); return `${y}-${m}-${d}`; };
  function textElement(tag, text, className) { const el = document.createElement(tag);el.textContent=text;if(className)el.className=className;return el; }
  function render() {
    document.getElementById('mesAnoAtual').textContent = month.toLocaleDateString('pt-BR',{month:'long',year:'numeric'});
    const grid = document.getElementById('calendarDays');grid.replaceChildren();
    const first = new Date(month.getFullYear(),month.getMonth(),1);
    const offset = (first.getDay()+6)%7;
    const today = iso(new Date());
    for(let i=0;i<42;i++) {
      const date = new Date(month.getFullYear(),month.getMonth(),i-offset+1), key=iso(date);
      const button = document.createElement('button');button.type='button';button.className='calendar-day';
      button.classList.toggle('outside-month',date.getMonth()!==month.getMonth());button.classList.toggle('is-today',key===today);button.classList.toggle('selected',key===selected);
      button.setAttribute('aria-pressed',String(key===selected));if(key===today)button.setAttribute('aria-current','date');
      const dayReminders = reminders.filter(r=>reminderDate(r)===key && !r.lido);
      button.setAttribute('aria-label',`${date.toLocaleDateString('pt-BR',{day:'numeric',month:'long',year:'numeric'})}${days.has(key)?', com interações':''}${dayReminders.length?`, ${dayReminders.length} lembrete(s)`:''}`);
      button.append(textElement('span',date.getDate()));
      const marks=textElement('span','','day-marks');
      if(days.has(key))marks.append(textElement('i','','interaction-dot'));
      if(dayReminders.length)marks.append(textElement('i','','reminder-dot'));
      button.append(marks);button.addEventListener('click',()=>selectDay(key));grid.append(button);
    }
    dateInput.value=selected;
  }
  async function agenda() {
    const id=++requestId, key=selected;
    document.getElementById('dataSelecionadaLabel').textContent=parse(key).toLocaleDateString('pt-BR',{weekday:'long',day:'numeric',month:'long'});
    list.replaceChildren(textElement('p','Carregando atividades…','agenda-empty'));
    try {
      let companies=[];
      if(days.has(key)){const response=await fetch(`/api/interacoes_dia/${key}`);if(!response.ok)throw new Error();companies=await response.json();}
      if(id!==requestId)return;
      list.replaceChildren();
      const pending=reminders.filter(r=>reminderDate(r)===key && !r.lido);
      if(!companies.length && !pending.length){list.append(textElement('div','Sem atividades neste dia. Selecione um dia marcado para acompanhar as empresas.','agenda-empty'));return;}
      if(pending.length){list.append(textElement('h5',`Lembretes · ${pending.length}`));for(const item of pending){const card=textElement('div','','agenda-reminder');card.append(textElement('span',item.data.slice(11)+(item.vencido?' · Vencido':''),'agenda-time'),textElement('strong',item.empresa),textElement('p',item.texto));const action=textElement('button','Marcar como lido','agenda-action');action.type='button';action.addEventListener('click',async()=>{action.disabled=true;try{const response=await fetch(`/api/marcar_lembrete_lido/${item.id}`,{method:'POST'});if(!response.ok)throw new Error();item.lido=true;render();agenda();}catch{action.disabled=false;action.textContent='Tentar novamente';}});card.append(action);list.append(card);}}
      if(companies.length){list.append(textElement('h5',`Empresas com interação · ${companies.length}`));for(const company of companies){const button=textElement('button','','agenda-company');button.type='button';button.append(textElement('span',company.nome),textElement('small','Abrir histórico →'));button.addEventListener('click',()=>{window.fecharModalCalendario();window.abrirChat(company.id,company.nome);});list.append(button);}}
    }catch{if(id===requestId){list.replaceChildren(textElement('p','Não foi possível carregar as atividades.','agenda-empty'));const retry=textElement('button','Tentar novamente','subtle-button');retry.addEventListener('click',agenda);list.append(retry);}}
  }
  function selectDay(key){selected=key;month=parse(key);render();agenda();}
  window.abrirModalCalendario=async function(){modal.style.display='flex';selected=iso(new Date());month=new Date();days=new Set();reminders=[];render();list.replaceChildren(textElement('p','Carregando calendário…','agenda-empty'));try{const responses=await Promise.all([fetch('/api/dias_com_interacao'),fetch('/api/lista_lembretes')]);if(responses.some(r=>!r.ok))throw new Error();const data=await Promise.all(responses.map(r=>r.json()));days=new Set(data[0]);reminders=data[1];render();agenda();}catch{list.replaceChildren(textElement('p','Não foi possível carregar o calendário.','agenda-empty'));const retry=textElement('button','Tentar novamente','subtle-button');retry.addEventListener('click',window.abrirModalCalendario);list.append(retry);}};
  window.fecharModalCalendario=function(){modal.style.display='none';requestId++;};
  window.mudarMes=function(direction){month=new Date(month.getFullYear(),month.getMonth()+direction,1);selected=iso(month);render();agenda();};
  document.getElementById('calendarToday').addEventListener('click',()=>selectDay(iso(new Date())));
  dateInput.addEventListener('change',()=>{if(dateInput.value && !Number.isNaN(parse(dateInput.value).getTime()))selectDay(dateInput.value);});
});
