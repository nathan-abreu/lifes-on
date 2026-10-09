/* Sons originais sintetizados; nenhuma mídia externa, áudio opcional. */
(() => {
 'use strict';
 const chave = 'lifes-on-audio-' + document.body.dataset.usuario;
 let preferencias = {ativo:false, volume:25}, contexto, ultimoSom=0, celebrando=false, somPendente=null, fimSom=0;
 const osciladoresAtivos=new Set();
 try { const dados=JSON.parse(localStorage.getItem(chave)); if(dados && typeof dados.ativo==='boolean') preferencias={ativo:dados.ativo, volume:Math.max(0,Math.min(100,Number(dados.volume)||0))}; } catch (_) {}
 const sequencias = {clique:[180], selecao:[220], navegacao:[196], confirmar:[261.63,329.63], treino:[261.63,392], xp:[329.63,392,523.25], conquista:[261.63,329.63,392,523.25], nivel:[261.63,392,523.25,659.25], erro:[220,196]};
 function som(nome, prioridade=false) {
  if(!preferencias.ativo || !preferencias.volume || (celebrando && !prioridade)) return;
  if(!prioridade && performance.now()-ultimoSom<120) return;
  ultimoSom=performance.now();
  try {
   const Audio=window.AudioContext || window.webkitAudioContext;
   if(!Audio) return;
   contexto ||= new Audio();
   // Só desbloqueia após gesto real; reload pode manter o contexto suspenso.
   if(contexto.state!=='running') { if(prioridade) somPendente=nome; return; }
   const notas=sequencias[nome] || sequencias.clique;
   if(!prioridade && contexto.currentTime<fimSom) return;
   const base=Math.max(contexto.currentTime,fimSom);
   const curto=['clique','selecao','navegacao'].includes(nome);
   const duracao=curto?0.055:0.27, intervalo=0.12;
   fimSom=base+(notas.length-1)*intervalo+duracao;
   notas.forEach((freq,i)=> {
    const oscilador=contexto.createOscillator(), ganho=contexto.createGain();
    osciladoresAtivos.add(oscilador);oscilador.onended=()=>osciladoresAtivos.delete(oscilador);
    const inicio=base+i*intervalo;
    oscilador.type='sine'; oscilador.frequency.value=freq;
    ganho.gain.setValueAtTime(0,inicio);
    ganho.gain.linearRampToValueAtTime(preferencias.volume/100*(curto?0.018:0.055),inicio+0.018);
    ganho.gain.exponentialRampToValueAtTime(0.0001,inicio+duracao);
    oscilador.connect(ganho); ganho.connect(contexto.destination);
    oscilador.start(inicio); oscilador.stop(inicio+duracao+0.01);
   });
  } catch (_) { /* Feedback textual continua disponível. */ }
 }
 function desbloquear() {
  if(!preferencias.ativo) return;
  try { contexto ||= new (window.AudioContext || window.webkitAudioContext)(); contexto.resume().then(()=>{
    if(somPendente) {const nome=somPendente;somPendente=null;som(nome,true);}
  }).catch(()=>{}); } catch (_) {}
 }
 document.addEventListener('pointerdown',desbloquear,{passive:true});
 document.addEventListener('keydown',desbloquear);
 document.addEventListener('click',e=> {
  const alvo=e.target.closest('button,a');
  if(alvo && !alvo.disabled && !alvo.closest('#audioTestar,#audioAlternar') && alvo.type!=='submit') som(alvo.tagName==='A'?'navegacao':'clique');
 });
 document.addEventListener('change',e=>{if(e.target.matches('select,input[type=checkbox],input[type=radio]'))som('selecao');});
 document.addEventListener('invalid',()=>som('erro'),true);
 document.addEventListener('submit',e=>{
  if(e.defaultPrevented || e.target.method.toLowerCase()!=='post')return;
  const botao=e.submitter;
  if(botao) { botao.disabled=true; botao.setAttribute('aria-busy','true'); botao.dataset.rotulo=botao.textContent; botao.textContent='Salvando…'; }
  // Confirmação sonora só após resposta positiva, nunca ao enviar o formulário.
 });
 window.addEventListener('pageshow',()=>document.querySelectorAll('[aria-busy=true]').forEach(b=>{b.disabled=false;b.removeAttribute('aria-busy');b.textContent=b.dataset.rotulo;}));
 const fila=[]; let ativa=false;
 function proxima() {
  if(!fila.length) {ativa=false;celebrando=false;return;}
  ativa=true;celebrando=true;
  const item=fila.shift(), toast=document.getElementById('recompensaToast');
  if(!toast) {fila.length=0;ativa=false;celebrando=false;return;}
  toast.textContent=item.texto;toast.classList.toggle('recompensa-nivel',item.som==='nivel');toast.hidden=false;
  som(item.som,true);
  setTimeout(()=>{toast.hidden=true;setTimeout(proxima,200);},3000);
 }
 function recompensar(dados) {
  if(!dados || !Number.isInteger(dados.xp_recebido) || dados.xp_recebido===0)return;
  const indicador=document.querySelector('.xp-card');
  if(indicador) {indicador.classList.add('xp-pulso');setTimeout(()=>indicador.classList.remove('xp-pulso'),700);}
  fila.push({texto:(dados.xp_recebido>0?'✦ +':'Ajuste: ')+dados.xp_recebido+' XP · '+dados.xp+' XP acumulados',som:dados.xp_recebido>0?'xp':'clique'});
  (dados.conquistas || []).forEach(c=>fila.push({texto:'🏆 '+c.nome+' — '+c.descricao,som:'conquista'}));
  if(dados.subiu_nivel)fila.push({texto:'✦ Você chegou ao nível '+dados.nivel+'!',som:'nivel'});
  if(dados.desceu_nivel)fila.push({texto:'Sua pontuação foi recalculada. Nível atual: '+dados.nivel+'.',som:'clique'});
  if(!ativa)proxima();
 }
 const ativo=document.getElementById('audioAtivo'), volume=document.getElementById('audioVolume'), valor=document.getElementById('audioValor');
 function salvar() {try {localStorage.setItem(chave,JSON.stringify(preferencias));}catch(_){} }
 const alternar=document.getElementById('audioAlternar');
 function atualizarControle() {
  if(!alternar)return;
  alternar.setAttribute('aria-pressed',String(preferencias.ativo));
  alternar.setAttribute('aria-label',preferencias.ativo?'Desativar sons':'Ativar sons');
  alternar.querySelector('i').className='fa-solid '+(preferencias.ativo?'fa-volume-low':'fa-volume-xmark');
 }
 function silenciar() {somPendente=null;fimSom=0;osciladoresAtivos.forEach(o=>{try{o.stop();}catch(_){}});osciladoresAtivos.clear();if(contexto)contexto.suspend().catch(()=>{});}
 if(alternar) {atualizarControle();alternar.addEventListener('click',()=>{
  preferencias.ativo=!preferencias.ativo;salvar();atualizarControle();
  if(ativo)ativo.checked=preferencias.ativo;
  if(preferencias.ativo)desbloquear();else silenciar();
 });}
 if(ativo) {
  ativo.checked=preferencias.ativo; volume.value=preferencias.volume;valor.textContent=preferencias.volume+'%';
  ativo.addEventListener('change',()=>{preferencias.ativo=ativo.checked;salvar();atualizarControle();if(preferencias.ativo)desbloquear();else silenciar();});
  volume.addEventListener('input',()=>{preferencias.volume=Number(volume.value);valor.textContent=volume.value+'%';salvar();});
  document.getElementById('audioTestar').addEventListener('click',async()=>{desbloquear();if(contexto)await contexto.resume();som('xp',true);});
 }
 window.LifesUI={som,recompensar};
 const feedback=document.getElementById('feedbackRecompensa');
 if(feedback)try {recompensar(JSON.parse(feedback.textContent));}catch(_){}
})();
