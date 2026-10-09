(() => {
 const arquivo=document.getElementById('fotoPerfil'), previa=document.getElementById('fotoPreview'), aviso=document.getElementById('fotoAviso');
 let url;
 arquivo.addEventListener('change', () => {
  if(url) URL.revokeObjectURL(url);
  previa.hidden=true; aviso.textContent='';
  const foto=arquivo.files[0]; if(!foto) return;
  if(!['image/jpeg','image/png','image/webp'].includes(foto.type) || foto.size>5*1024*1024) {
   aviso.textContent='Selecione JPEG, PNG ou WebP de até 5 MB.';arquivo.value='';return;
  }
  const remover=document.querySelector('[name="remover_foto"]');if(remover) remover.checked=false;
  url=URL.createObjectURL(foto);previa.src=url;previa.hidden=false;
 });
 previa.addEventListener('error',()=>{previa.hidden=true;arquivo.value='';aviso.textContent='Não foi possível ler essa imagem.';});
})();
