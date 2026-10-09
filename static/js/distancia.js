(() => {
 const permitidas=['Corrida','Caminhada','Ciclismo','Natação'];
 window.LifesDistancia = (modalidade, campo) => {
  if(!modalidade || !campo) return;
  const atualizar=()=>{campo.disabled=!permitidas.includes(modalidade.value);campo.closest('[data-distancia]').hidden=campo.disabled;if(campo.disabled)campo.value='';};
  modalidade.addEventListener('change',atualizar);atualizar();return atualizar;
 };
 window.LifesDistancia(document.getElementById('tipo_exercicio'),document.getElementById('distancia_km'));
 const metrica=document.getElementById('metrica'), modalidade=document.getElementById('modalidadeMeta');
 if(metrica && modalidade) {
  const atualizar=()=>{
   for(const o of modalidade.options) o.disabled=metrica.value==='km' && o.value!=='' && !permitidas.includes(o.value);
   if(modalidade.selectedOptions[0]?.disabled)modalidade.value='';
   metrica.querySelector('option[value="km"]').disabled=modalidade.value!=='' && !permitidas.includes(modalidade.value);
   const alvo=document.getElementById('alvo');alvo.inputMode=metrica.value==='km'?'decimal':'numeric';
   alvo.placeholder=metrica.value==='km'?'Ex.: 10,5':metrica.value==='minutos'?'Ex.: 120':'Ex.: 12';
  };
  metrica.addEventListener('change',atualizar);modalidade.addEventListener('change',atualizar);atualizar();
 }
})();
