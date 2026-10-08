/* Sons originais sintetizados; nenhuma mídia externa, áudio opcional. */
(() => {
 'use strict';
 const chave = 'lifes-on-audio-' + document.body.dataset.usuario;
 let preferencias = {ativo:false, volume:25}, contexto, ultimoSom=0, celebrando=false, somPendente=null, fimSom=0;
 try { const dados=JSON.parse(localStorage.getItem(chave)); if(dados && typeof dados.ativo==='boolean') preferencias={ativo:dados.ativo, volume:Math.max(0,Math.min(100,Number(dados.volume)||0))}; } catch (_) {}
 const sequencias = {clique:[420], selecao:[480], navegacao:[390,490], confirmar:[520,660], treino:[440,550,660], xp:[560,700], conquista:[440,660,880], nivel:[520,650,780,1040], erro:[240,200]};
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
   const base=Math.max(contexto.currentTime,fimSom);
   fimSom=base+(notas.length-1)*0.085+0.19;
   notas.forEach((freq,i)=> {
    const oscilador=contexto.createOscillator(), ganho=contexto.createGain();
    const inicio=base+i*0.085;
    oscilador.type='sine'; oscilador.frequency.value=freq;
    ganho.gain.setValueAtTime(0,inicio);
    ganho.gain.linearRampToValueAtTime(preferencias.volume/100*0.09,inicio+0.012);
    ganho.gain.exponentialRampToValueAtTime(0.0001,inicio+0.13);
    oscilador.connect(ganho); ganho.connect(contexto.destination);
    oscilador.start(inicio); oscilador.stop(inicio+0.15);
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
  if(alvo && !alvo.disabled && !alvo.closest('#audioTestar')) som(alvo.tagName==='A'?'navegacao':'clique');
 });
 document.addEventListener('change',e=>{if(e.target.matches('select,input[type=checkbox],input[type=radio]'))som('selecao');});
 document.addEventListener('invalid',()=>som('erro'),true);
 document.addEventListener('submit',e=>{
  if(e.defaultPrevented || e.target.method.toLowerCase()!=='post')return;
  const botao=e.submitter;
  if(botao) { botao.disabled=true; botao.setAttribute('aria-busy','true'); botao.dataset.rotulo=botao.textContent; botao.textContent='Salvando…'; }
  som('confirmar');
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
  if(!dados || !Number.isInteger(dados.xp_recebido) || dados.xp_recebido<=0)return;
  fila.push({texto:'✦ +'+dados.xp_recebido+' XP · '+dados.xp+' XP acumulados',som:'xp'});
  (dados.conquistas || []).forEach(c=>fila.push({texto:'🏆 '+c.nome+' — '+c.descricao,som:'conquista'}));
  if(dados.subiu_nivel)fila.push({texto:'✦ Você chegou ao nível '+dados.nivel+'!',som:'nivel'});
  if(!ativa)proxima();
 }
 const ativo=document.getElementById('audioAtivo'), volume=document.getElementById('audioVolume'), valor=document.getElementById('audioValor');
 function salvar() {try {localStorage.setItem(chave,JSON.stringify(preferencias));}catch(_){} }
 if(ativo) {
  ativo.checked=preferencias.ativo; volume.value=preferencias.volume;valor.textContent=preferencias.volume+'%';
  ativo.addEventListener('change',()=>{preferencias.ativo=ativo.checked;salvar();desbloquear();});
  volume.addEventListener('input',()=>{preferencias.volume=Number(volume.value);valor.textContent=volume.value+'%';salvar();});
  document.getElementById('audioTestar').addEventListener('click',async()=>{desbloquear();if(contexto)await contexto.resume();som('xp',true);});
 }
 window.LifesUI={som,recompensar};
 const feedback=document.getElementById('feedbackRecompensa');
 if(feedback)try {recompensar(JSON.parse(feedback.textContent));}catch(_){}
})();
