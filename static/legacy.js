function escapeHTML(value) {
 return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function attachmentURL(path) {
 return /^uploads\/[A-Za-z0-9_.-]+$/.test(path || '') ? '/anexos/' + encodeURIComponent(path.slice(8)) : '#';
}
function actionIcon(name) {
 const paths={trash:'M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7',edit:'m15 4 5 5 M4 20l2-6L17 3l4 4-11 11z',bell:'M5 17h14l-2-3V9a5 5 0 0 0-10 0v5z M10 21h4'};
 return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]}"/></svg>`;
}

        // ----------------------------------------------------
        // INICIALIZAÇÃO & ESTADOS GERAIS
        // ----------------------------------------------------
        document.addEventListener("DOMContentLoaded", function() {
            // Aplica o tema
            if (localStorage.getItem('tema_preferido') === 'escuro') {
                document.body.classList.add('dark-mode');
            }
            
            // Restaura estado das pastas
            document.querySelectorAll('.clientes-na-pasta').forEach(pasta => {
                let id = pasta.id;
                let estadoSalvo = localStorage.getItem('estado_' + id);
                const s = document.getElementById('seta-' + id);
                
                if (estadoSalvo === "fechado") {
                    pasta.style.display = "none";
                    if (s) s.innerText = "▶";
                } else {
                    pasta.style.display = "block";
                    if (s) s.innerText = "▼";
                }
            });

            // Lembretes
            verificarLembretePendente();
            setInterval(verificarLembretePendente, 300000); 
        });

        function toggleTheme() {
            document.body.classList.toggle('dark-mode');
            localStorage.setItem('tema_preferido', document.body.classList.contains('dark-mode') ? 'escuro' : 'claro');
        }

        // Fechar Modais Clicando Fora
        window.onclick = function(event) {
            if (event.target.classList.contains('modal')) {
                event.target.style.display = 'none';
                let containerInt = document.getElementById('interacoesDiaContainer');
                if(containerInt) containerInt.style.display = 'none';
            }
        }

        // ----------------------------------------------------
        // LÓGICA DA SIDEBAR (BUSCA E PASTAS)
        // ----------------------------------------------------
        function toggleSearch() {
            const c = document.getElementById('searchContainer');
            c.style.display = (c.style.display === "none" || c.style.display === "") ? "block" : "none";
            if(c.style.display === "block") document.getElementById('searchBar').focus();
        }

        function handleSearch() {
            let textVal = document.getElementById('searchBar').value;
            let isMsgSearch = document.getElementById('toggleSearchType').checked;
            let msgResultsBox = document.getElementById('msgSearchResults');
            let searchInput = document.getElementById('searchBar');

            filtrarTudo(); 

            if (isMsgSearch) {
                searchInput.placeholder = "Pesquisar mensagens";
                if (textVal.length < 2) {
                    msgResultsBox.style.display = 'none';
                    return;
                }

                fetch('/api/pesquisar_mensagens?q=' + encodeURIComponent(textVal))
                    .then(res => res.json())
                    .then(data => {
                        msgResultsBox.innerHTML = '';
                        if (data.length === 0) {
                            msgResultsBox.innerHTML = '<div style="padding: 10px; color: #8b949e; font-size: 12px; text-align: center;">Nenhuma mensagem encontrada.</div>';
                        } else {
                            data.forEach(msg => {
                                let div = document.createElement('div');
                                div.className = 'msg-result-item';
                                div.innerHTML = `
                                    <div class="msg-result-cliente">${escapeHTML(msg.cliente_nome)} <span style="color:#8b949e;font-weight:normal;font-size:10px;float:right">${escapeHTML(msg.data)}</span></div>
                                    <div class="msg-result-texto">${escapeHTML(msg.texto)}</div>
                                `;
                                div.onclick = () => {
                                    idFocoChat = msg.msg_id;
                                    abrirChat(msg.cliente_id, msg.cliente_nome);
                                    msgResultsBox.style.display = 'none';
                                    toggleSearch(); 
                                };
                                msgResultsBox.appendChild(div);
                            });
                        }
                        msgResultsBox.style.display = 'block';
                    });
            } else {
                searchInput.placeholder = "Pesquisar clientes";
                msgResultsBox.style.display = 'none';
            }
        }

        function toggleFilterMenu() {
            const f = document.getElementById('filterDropdown');
            f.style.display = f.style.display === 'none' ? 'block' : 'none';
        }

        function limparFiltros(e) {
            if(e) e.preventDefault();
            document.querySelectorAll('.filtro-check').forEach(c => c.checked = false);
            filtrarTudo();
        }

        function filtrarTudo() {
            let isMsgSearch = document.getElementById('toggleSearchType').checked;
            let textVal = isMsgSearch ? "" : document.getElementById('searchBar').value.toLowerCase();
            
            let fStatus = Array.from(document.querySelectorAll('.filtro-status:checked')).map(c => c.value);
            let fVagas = Array.from(document.querySelectorAll('.filtro-vaga:checked')).map(c => c.value);
            let fSels = Array.from(document.querySelectorAll('.filtro-sel:checked')).map(c => c.value);

            document.querySelectorAll('.clientes-lista li').forEach(li => {
                let btn = li.querySelector('.btn-edit');
                if(!btn) return;

                let nome = btn.getAttribute('data-nome').toLowerCase();
                let status = btn.getAttribute('data-status');
                let vagas = btn.getAttribute('data-vagas').split(',');
                let selecionadoras = btn.getAttribute('data-selecionadoras').split(',');

                let matchText = nome.includes(textVal);
                let matchStatus = fStatus.length === 0 || fStatus.includes(status);
                let matchVaga = fVagas.length === 0 || fVagas.some(v => vagas.includes(v));
                let matchSel = fSels.length === 0 || fSels.some(s => selecionadoras.includes(s));

                li.style.display = (matchText && matchStatus && matchVaga && matchSel) ? "flex" : "none";
            });

            document.querySelectorAll('.pasta-container').forEach(pasta => {
                let clientesNaPasta = pasta.querySelectorAll('li');
                let temClienteVisivel = Array.from(clientesNaPasta).some(cli => cli.style.display !== 'none');
                pasta.style.display = temClienteVisivel ? "block" : "none";
            });
        }

        function togglePasta(id) {
            const l = document.getElementById(id);
            const s = document.getElementById('seta-' + id);
            
            if (l.style.display === "none") {
                l.style.display = "block";
                s.innerText = "▼";
                localStorage.setItem('estado_' + id, 'aberto');
            } else {
                l.style.display = "none";
                s.innerText = "▶";
                localStorage.setItem('estado_' + id, 'fechado');
            }
        }

        // ----------------------------------------------------
        // LÓGICA DE MODAIS DE ABERTURA E FECHAMENTO
        // ----------------------------------------------------
        function abrirModalVagas() { document.getElementById('modalGerenciarVagas').style.display = 'flex'; }
        function fecharModalVagas() { document.getElementById('modalGerenciarVagas').style.display = 'none'; }
        function abrirModalStatus() { document.getElementById('modalGerenciarStatus').style.display = 'flex'; }
        function fecharModalStatus() { document.getElementById('modalGerenciarStatus').style.display = 'none'; }
        function abrirModalSelecionadoras() { document.getElementById('modalGerenciarSelecionadoras').style.display = 'flex'; }
        function fecharModalSelecionadoras() { document.getElementById('modalGerenciarSelecionadoras').style.display = 'none'; }
        function abrirModalCliente() { document.getElementById('modalCliente').style.display = 'flex'; }
        function fecharModalCliente() { document.getElementById('modalCliente').style.display = 'none'; }
        function abrirModalPasta() { document.getElementById('modalPasta').style.display = 'flex'; }
        function fecharModalPasta() { document.getElementById('modalPasta').style.display = 'none'; }
        function fecharModalEditar() { document.getElementById('modalEditar').style.display = 'none'; }
        function fecharModalEditarPasta() { document.getElementById('modalEditarPasta').style.display = 'none'; }

        // ----------------------------------------------------
        // LÓGICA DE PREPARAÇÃO DE EDIÇÃO (PREENCHER DADOS)
        // ----------------------------------------------------
        function prepararEdicao(b) {
            document.getElementById('formEditar').action = '/editar/' + b.getAttribute('data-id');
            document.getElementById('edit_nome').value = b.getAttribute('data-nome');
            document.getElementById('edit_pasta').value = b.getAttribute('data-pasta');
            
            const vData = b.getAttribute('data-vagas').split(',');
            const sIds = b.getAttribute('data-selecionadoras').split(',');
            
            // Limpeza inicial
            document.querySelectorAll('.edit-vaga-check').forEach(c => {
                c.checked = false;
                let select = document.getElementById('edit_status_' + c.value);
                let inputTaxa = document.getElementById('edit_taxa_' + c.value);
                if(select) { select.disabled = true; select.value = ""; }
                if(inputTaxa) { inputTaxa.disabled = true; inputTaxa.value = ""; }
            });
            
            // Preenche os dados
            vData.forEach(item => {
                if(!item) return;
                const parts = item.split(':');
                const vId = parts[0];
                
                const checkbox = document.getElementById('edit_check_' + vId);
                if(checkbox) {
                    checkbox.checked = true;
                    
                    const select = document.getElementById('edit_status_' + vId);
                    if(select) { select.disabled = false; select.value = parts[1] || ""; }
                    
                    const inputTaxa = document.getElementById('edit_taxa_' + vId);
                    if(inputTaxa) { inputTaxa.disabled = false; inputTaxa.value = parts[2] || ""; }
                }
            });
            
            document.querySelectorAll('.edit-sel-check').forEach(c => c.checked = sIds.includes(c.value));
            
            document.getElementById('modalEditar').style.display = 'flex';

            const contatosContainer = document.getElementById('contatos-container');
            contatosContainer.innerHTML = ''; 
            const contatosLista = JSON.parse(b.getAttribute('data-contatos') || '[]');
            contatosLista.forEach(c => adicionarContatoBloco(c.nome, c.email, c.telefone));
        }

        function prepararEdicaoVaga(id, n) { 
            document.getElementById('formEditarVaga').action = '/editar_vaga/'+id; 
            document.getElementById('edit_nome_vaga').value = n; 
            fecharModalVagas(); 
            document.getElementById('modalEditarVaga').style.display = 'flex'; 
        }
        function fecharModalEditarVaga() { document.getElementById('modalEditarVaga').style.display = 'none'; abrirModalVagas(); }

        function prepararEdicaoStatus(id, n) { 
            document.getElementById('formEditarStatus').action = '/editar_status/'+id; 
            document.getElementById('edit_nome_st').value = n; 
            fecharModalStatus(); 
            document.getElementById('modalEditarStatus').style.display = 'flex'; 
        }
        function fecharModalEditarStatus() { document.getElementById('modalEditarStatus').style.display = 'none'; abrirModalStatus(); }

        function prepararEdicaoSelecionadora(id, n) { 
            document.getElementById('formEditarSelecionadora').action = '/editar_selecionadora/'+id; 
            document.getElementById('edit_nome_sel').value = n; 
            fecharModalSelecionadoras(); 
            document.getElementById('modalEditarSelecionadora').style.display = 'flex'; 
        }
        function fecharModalEditarSelecionadora() { document.getElementById('modalEditarSelecionadora').style.display = 'none'; abrirModalSelecionadoras(); }

        function prepararEdicaoPasta(b) { 
            document.getElementById('formEditarPasta').action = '/editar_pasta/'+b.getAttribute('data-id'); 
            document.getElementById('edit_nome_pasta').value = b.getAttribute('data-nome'); 
            document.getElementById('edit_parent_pasta').value = b.getAttribute('data-parent') || ''; 
            document.getElementById('modalEditarPasta').style.display = 'flex'; 
        }

        function adicionarContatoBloco(nome = '', email = '', telefone = '') {
            const container = document.getElementById('contatos-container');
            const div = document.createElement('div');
            div.className = 'contato-bloco';
            div.innerHTML = `
                <button type="button" class="btn-remover-contato action-icon" onclick="if(confirm('Tem certeza que deseja excluir este contato?')) this.parentElement.remove()" title="Remover contato" aria-label="Remover contato">${actionIcon('trash')}</button>
                <input type="text" name="contato_nome[]" placeholder="Nome do contato" value="${escapeHTML(nome)}">
                <input type="email" name="contato_email[]" placeholder="E-mail" value="${escapeHTML(email)}">
                <input type="text" name="contato_telefone[]" placeholder="Telefone" value="${escapeHTML(telefone)}">
            `;
            container.appendChild(div);
        }

        // ----------------------------------------------------
        // LÓGICA DO CALENDÁRIO
        // ----------------------------------------------------
        let dataCalendario = new Date();
        let diasComInteracao = [];
        let idFocoChat = null;

        function abrirModalCalendario() {
            document.getElementById('modalCalendario').style.display = 'flex';
            dataCalendario = new Date(); 
            fetchDiasComInteracao().then(() => renderCalendario());
        }

        function fecharModalCalendario() {
            document.getElementById('modalCalendario').style.display = 'none';
            document.getElementById('interacoesDiaContainer').style.display = 'none';
        }

        async function fetchDiasComInteracao() {
            let res = await fetch('/api/dias_com_interacao');
            diasComInteracao = await res.json();
        }

        function mudarMes(direcao) {
            dataCalendario.setMonth(dataCalendario.getMonth() + direcao);
            renderCalendario();
            document.getElementById('interacoesDiaContainer').style.display = 'none';
        }

        function renderCalendario() {
            const container = document.getElementById('calendarDays');
            container.innerHTML = '';
            
            const ano = dataCalendario.getFullYear();
            const mes = dataCalendario.getMonth();
            const mesesNomes = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
            
            document.getElementById('mesAnoAtual').innerText = `${mesesNomes[mes]} ${ano}`;

            const primeiroDia = new Date(ano, mes, 1).getDay();
            const ultimoDia = new Date(ano, mes + 1, 0).getDate();

            for (let i = 0; i < primeiroDia; i++) {
                let div = document.createElement('div');
                div.className = 'day empty';
                container.appendChild(div);
            }

            for (let dia = 1; dia <= ultimoDia; dia++) {
                let div = document.createElement('div');
                div.className = 'day';
                div.innerText = dia;
                
                let mesStr = String(mes + 1).padStart(2, '0');
                let diaStr = String(dia).padStart(2, '0');
                let dataStr = `${ano}-${mesStr}-${diaStr}`;
                
                if (diasComInteracao.includes(dataStr)) div.classList.add('has-interaction');
                
                div.onclick = (e) => selecionarDiaCalendario(dataStr, dia, mesStr, ano, e);
                container.appendChild(div);
            }
        }

        function selecionarDiaCalendario(dataStr, dia, mes, ano, e) {
            document.querySelectorAll('.calendar-days .day').forEach(d => d.classList.remove('selected'));
            e.target.classList.add('selected');

            if (!diasComInteracao.includes(dataStr)) {
                document.getElementById('interacoesDiaContainer').style.display = 'none';
                return;
            }

            document.getElementById('dataSelecionadaLabel').innerText = `${dia}/${mes}/${ano}`;
            
            fetch('/api/interacoes_dia/' + dataStr)
                .then(res => res.json())
                .then(clientes => {
                    let lista = document.getElementById('listaInteracoes');
                    lista.innerHTML = '';
                    clientes.forEach(cli => {
                        let btn = document.createElement('button');
                        btn.className = 'btn-cliente-calendario';
                        btn.innerText = `${cli.nome}`;
                        btn.onclick = () => {
                            fecharModalCalendario();
                            abrirChat(cli.id, cli.nome);
                        };
                        lista.appendChild(btn);
                    });
                    document.getElementById('interacoesDiaContainer').style.display = 'block';
                });
        }

        // ----------------------------------------------------
        // LÓGICA DO CHAT E ABAS
        // ----------------------------------------------------
        let clienteAtual = null;

        function abrirChat(id, nome) {
            clienteAtual = id;
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('chatContainer').style.display = 'flex';
            document.getElementById('chatClienteNome').innerText = nome;
            document.getElementById('chatClienteId').value = id;
            carregarMensagens();

            fetch('/api/cliente_tags/' + id)
                .then(res => res.json())
                .then(data => {
                    let html = '';
                    const coresStatus = {
                        'SP ENVIADO': '#14D927',
                        'PROPOSTA ENVIADA': '#E0109B',
                        'FATURAMENTO ENVIADO': '#AD0505',
                        'VAGA ABERTA': '#A6A128',
                        'VAGA FECHADA': '#551199',
                        'VAGA CANCELADA': '#4A4749'
                    };

                    data.vagas.forEach(v => {
                        let corHex = coresStatus[v.status] || '#58a6ff'; 
                        let corFundo = corHex + '26'; 
                        html += `<span class="header-tag" style="background: ${corFundo}; color: ${corHex}; border: 1px solid ${corHex};">${escapeHTML(v.texto)}</span>`;
                    });
                    
                    data.selecionadoras.forEach(s => html += `<span class="header-tag tag-sel">${escapeHTML(s)}</span>`);
                    document.getElementById('chatClienteTags').innerHTML = html;
                });

            trocarAbaChat('mensagens');
        }

        function carregarMensagens() {
            if(!clienteAtual) return;
            fetch('/get_mensagens/' + clienteAtual)
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('chatMessages');
                    container.innerHTML = ''; 
                    
                    let elementoFoco = null;

                    data.forEach(msg => {
                        let divMsg = document.createElement('div');
                        divMsg.className = 'mensagem-item' + (msg.tem_lembrete ? ' msg-lembrete' : '');
                        divMsg.id = "msg-" + msg.id; 
                        
                        if (idFocoChat == msg.id) {
                            elementoFoco = divMsg;
                            divMsg.style.border = '2px solid #58a6ff'; 
                            divMsg.style.boxShadow = '0 0 15px rgba(88, 166, 255, 0.4)';
                        }

                        let textoSeguro = msg.texto ? msg.texto.replace(/'/g, "\\'") : "Arquivo anexado";

                        let conteudoHTML = `
                            <div class="msg-header" style="display: flex; justify-content: space-between; width: 100%;">
                                <div class="msg-acoes">
                                    <button type="button" class="action-icon reminder-create" title="Criar lembrete" aria-label="Criar lembrete">${actionIcon('bell')}</button>
                                    <button type="button" class="action-icon" title="Editar mensagem" aria-label="Editar mensagem" onclick="editarMensagemChat(${msg.id}, this)">${actionIcon('edit')}</button>
                                    <button type="button" class="action-icon delete" title="Excluir mensagem" aria-label="Excluir mensagem" onclick="excluirMensagemChat(${msg.id})">${actionIcon('trash')}</button>
                                </div>
                                <span class="msg-data">${escapeHTML(msg.data)}</span>
                            </div>
                        `;
                        
                        if(msg.texto) conteudoHTML += `<p class="msg-texto">${escapeHTML(msg.texto)}</p>`;
                        
                        if(msg.path) {
                            if(msg.tipo === 'imagem') {
                                conteudoHTML += `<img src="${attachmentURL(msg.path)}" class="msg-img" alt="Anexo">`;
                            } else {
                                conteudoHTML += `<a href="${attachmentURL(msg.path)}" target="_blank" rel="noopener" class="msg-arquivo"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M5 3h10l4 4v14H5z M15 3v5h4 M8 12h8 M8 16h8"/></svg> Ver Anexo</a>`;
                            }
                        }
                        
                        divMsg.innerHTML = conteudoHTML;
                        divMsg.querySelector('.reminder-create').addEventListener('click', () => criarLembrete(msg.id, msg.texto || 'Arquivo anexado'));
                        container.appendChild(divMsg);
                    });
                    
                    if (elementoFoco) {
                        setTimeout(() => {
                            elementoFoco.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            idFocoChat = null;
                        }, 200);
                    } else {
                        container.scrollTop = container.scrollHeight;
                    }
                });
        }

        function atualizarNomeArquivo(input) {
            const display = document.getElementById('nomeArquivoSelecionado');
            if(input.files.length > 1) {
                display.innerText = '' + input.files.length + ' arquivos selecionados';
            } else if (input.files.length === 1) {
                display.innerText = '' + input.files[0].name;
            } else {
                display.innerText = '';
            }
        }

        function enviarMensagemChat(e) {
            e.preventDefault(); 
            const form = document.getElementById('formChat');
            const formData = new FormData(form);
            
            if(!formData.get('texto') && (!formData.get('arquivo') || formData.get('arquivo').size === 0)) return;
            
            fetch('/enviar_mensagem', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'sucesso') {
                    form.reset(); 
                    document.getElementById('nomeArquivoSelecionado').innerText = '';
                    carregarMensagens(); 
                }
            });
        }

        function editarMensagemChat(id, btnElement) {
            let textoTag = btnElement.closest('.mensagem-item').querySelector('.msg-texto');
            let textoAtual = textoTag ? textoTag.innerText : '';
            
            let novoTexto = prompt("Edite sua mensagem:", textoAtual);
            if(novoTexto === null || novoTexto === textoAtual) return;

            let formData = new FormData();
            formData.append('texto', novoTexto);

            fetch('/editar_mensagem/' + id, { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'sucesso') carregarMensagens();
            });
        }

        function excluirMensagemChat(id) {
            if(!confirm("Apagar esta mensagem? O arquivo também será excluído.")) return;
            
            fetch('/excluir_mensagem/' + id, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'sucesso') carregarMensagens();
            });
        }

        function trocarAbaChat(aba) {
            const btnChat = document.querySelector('.tab-btn:nth-child(1)');
            const btnArquivos = document.querySelector('.tab-btn:nth-child(2)');
            const btnContatos = document.querySelector('.tab-btn:nth-child(3)');

            const divMensagens = document.getElementById('chatMessages');
            const divArquivos = document.getElementById('chatFilesList');
            const divContatos = document.getElementById('chatContatosList');
            const inputArea = document.querySelector('.chat-input-area');

            divMensagens.style.display = 'none';
            divArquivos.style.display = 'none';
            divContatos.style.display = 'none';

            [btnChat, btnArquivos, btnContatos].forEach(b => b?.classList.remove('active'));

            if (aba === 'mensagens') {
                divMensagens.style.display = 'flex';
                btnChat.classList.add('active');
                inputArea.style.display = 'flex';
                carregarMensagens();
            } else if (aba === 'arquivos') {
                divArquivos.style.display = 'block';
                btnArquivos.classList.add('active');
                inputArea.style.display = 'none';
                carregarListaArquivos();
            } else if (aba === 'contatos') {
                divContatos.style.display = 'flex';
                btnContatos.classList.add('active');
                inputArea.style.display = 'none';
                carregarListaContatos();
            }
        }

        function carregarListaArquivos() {
            if(!clienteAtual) return;
            const container = document.getElementById('chatFilesList');
            container.innerHTML = '<p style="text-align:center; padding:20px; color:#8b949e;">Carregando arquivos...</p>';
            
            fetch('/get_arquivos/' + clienteAtual)
                .then(res => res.json())
                .then(data => {
                    container.innerHTML = '';
                    if(data.length === 0) {
                        container.innerHTML = '<p style="text-align:center; padding:20px; color:#8b949e;">Nenhum arquivo enviado para este cliente.</p>';
                        return;
                    }

                    data.forEach(arq => {
                        let div = document.createElement('div');
                        div.className = 'arquivo-item-lista';
                        div.innerHTML = `
                            <div class="arq-icon">${arq.tipo === 'imagem' ? '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M5 3h10l4 4v14H5z M15 3v5h4 M8 12h8 M8 16h8"/></svg>' : '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M5 3h10l4 4v14H5z M15 3v5h4 M8 12h8 M8 16h8"/></svg>'}</div>
                            <div class="arq-info">
                                <span class="arq-nome">${escapeHTML(arq.texto || arq.path.split('/').pop())}</span>
                                <span class="arq-data">${escapeHTML(arq.data)}</span>
                            </div>
                            <a href="${attachmentURL(arq.path)}" target="_blank" rel="noopener" class="btn-baixar-arq">Abrir</a>
                        `;
                        container.appendChild(div);
                    });
                });
        }

        function carregarListaContatos() {
            if(!clienteAtual) return;
            const container = document.getElementById('chatContatosList');
            container.innerHTML = '<p style="text-align:center; padding:20px; color:#8b949e;">Carregando contatos...</p>';

            fetch('/get_contatos/' + clienteAtual)
                .then(res => res.json())
                .then(data => {
                    container.innerHTML = '';
                    if(data.length === 0) {
                        container.innerHTML = '<p style="text-align:center; padding:20px; color:#8b949e;">Nenhum contato cadastrado.</p>';
                        return;
                    }

                    data.forEach(c => {
                        let div = document.createElement('div');
                        div.className = 'contato-card';
                        div.innerHTML = `
                            <div class="c-nome">${escapeHTML(c.nome || 'Nome não informado')}</div>
                            ${c.email ? `<div class="c-info"><a href="mailto:${encodeURIComponent(c.email)}">${escapeHTML(c.email)}</a></div>` : ''}
                            ${c.telefone ? `<div class="c-info"><a href="https://wa.me/55${c.telefone.replace(/\D/g,'')}" target="_blank" rel="noopener">${escapeHTML(c.telefone)}</a></div>` : ''}
                        `;
                        container.appendChild(div);
                    });
                });
        }

        // ----------------------------------------------------
        // LÓGICA DE LEMBRETES
        // ----------------------------------------------------
        let idLembreteAtual = null;

        function abrirModalLembretes() {
            document.getElementById('modalLembretes').style.display = 'flex';
            carregarListaLembretes();
        }
        function fecharModalLembretes() { document.getElementById('modalLembretes').style.display = 'none'; }
        function fecharModalCriarLembrete() { document.getElementById('modalCriarLembrete').style.display = 'none'; }

        function criarLembrete(msgId, texto) {
            document.getElementById('lembreteMsgId').value = msgId;
            document.getElementById('lembreteTexto').value = texto;
            
            let agora = new Date();
            agora.setMinutes(agora.getMinutes() - agora.getTimezoneOffset());
            
            document.getElementById('lembreteDataHora').value = agora.toISOString().slice(0, 16);
            document.getElementById('modalCriarLembrete').style.display = 'flex';
        }

        function salvarNovoLembrete(e) {
            e.preventDefault();
            const form = document.getElementById('formCriarLembrete');
            const formData = new FormData(form);

            fetch('/api/criar_lembrete', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'sucesso') {
                    fecharModalCriarLembrete();
                    carregarListaLembretes(); 
                    alert("Lembrete agendado com sucesso!");
                } else if (data.status === 'erro') {
                    alert(data.mensagem);
                }
            });
        }

        function carregarListaLembretes() {
            fetch('/api/lista_lembretes')
            .then(res => res.json())
            .then(data => {
                const container = document.getElementById('listaLembretes');
                container.innerHTML = '';
                
                data.forEach(lembrete => {
                    let div = document.createElement('div');
                    div.className = 'contato-bloco' + (lembrete.lido ? ' lembrete-concluido' : '');
                    
                    let corBorda = lembrete.lido ? 'var(--borda)' : (lembrete.vencido ? '#f85149' : '#ffd33d');
                    div.style.borderLeft = `4px solid ${corBorda}`;
                    
                    div.innerHTML = `
                        <div style="font-size: 10px; color: #58a6ff; font-weight: bold;">${escapeHTML(lembrete.empresa)}</div>
                        <div class="reminder-text" style="font-size: 13px; color: var(--texto-principal); margin-bottom: 5px;">${escapeHTML(lembrete.texto)}</div>
                        <div style="font-size: 11px; color: var(--texto-secundario); margin-bottom: 10px;">
                            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5z M10 21h4"/></svg> ${lembrete.data} ${lembrete.lido ? '(Concluído)' : ''}
                        </div>
                        ${!lembrete.lido ? `<button onclick="marcarLembreteLido(${lembrete.id})" class="btn-yellow" style="padding: 5px 10px; font-size: 11px;">✔ Concluir</button>` : ''}
                    `;
                    container.appendChild(div);
                });
            });
        }

        function verificarLembretePendente() {
            fetch('/api/lembrete_pendente')
            .then(res => res.json())
            .then(lembrete => {
                if (lembrete) {
                    idLembreteAtual = lembrete.id;
                    document.getElementById('empresaAlertaLembrete').innerText = "🏢 " + lembrete.empresa;
                    document.getElementById('textoAlertaLembrete').innerText = lembrete.texto;
                    document.getElementById('alertaLembrete').style.display = 'block';
                }
            });
        }

        function ignorarLembrete() {
            document.getElementById('alertaLembrete').style.display = 'none';
            idLembreteAtual = null;
        }

        function marcarLembreteLido(idParam) {
            let id = idParam || idLembreteAtual;
            if (!id) return;

            fetch('/api/marcar_lembrete_lido/' + id, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'sucesso') {
                    if (idLembreteAtual === id) {
                        document.getElementById('alertaLembrete').style.display = 'none';
                        idLembreteAtual = null;
                    }
                    carregarListaLembretes(); 
                }
            });
        }
    


