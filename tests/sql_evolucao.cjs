/* PostgreSQL WASM local descartável. Nunca usa credenciais nem rede Supabase. */
const {PGlite}=require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs=require('fs'),assert=require('node:assert/strict');
const ler=p=>fs.readFileSync(p,'utf8').replace(/^\uFEFF/,'');
const regressao=require('./sql_evolucao_regressoes.cjs');
(async()=>{
 const modoDate=process.argv.includes('--date');
 const db=new PGlite();
 const exec=async s=>{try{return await db.exec(s);}catch(e){await db.exec('rollback');throw e;}};
 const um=async(s,p=[])=>{const r=(await db.query(s,p)).rows[0];if(typeof r?.progresso==='string')r.progresso=Number(r.progresso);return r;};
 const total=async()=>Number((await um('select coalesce(sum(xp),0) n from recompensas_xp where id_usuario=1')).n);
 try {
  await exec('create role anon;create role authenticated;create role service_role bypassrls;');
  await exec(modoDate ? ler('schema.sql').replace('nome text not null,','nome varchar(100) not null,').replace('data_registro timestamptz not null default now()', 'data_registro date not null default now()').replace('progresso integer not null default 0', 'progresso numeric(5,2) not null default 0') : ler('schema.sql'));
  await exec('create schema storage;create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);create table storage.objects(bucket_id text,name text);alter table storage.objects enable row level security;');
  await exec(ler('migrations/diagnostico_evolucao.sql'));
  // Fixture histórica: uma sessão premiada pela regra anterior e meta legada.
  await exec("insert into usuarios(nome,email,senha_hash) values ('Um','um@local','hash'),('Dois','dois@local','hash');insert into atividades(id_usuario,tipo_exercicio,duracao,data_registro) values(1,'Yoga',40,now()-interval '1 hour');insert into metas(id_usuario,descricao,prazo,progresso) values(1,'Legada',current_date,100);");
  await regressao.preparar(exec);
  const historico=(await db.query('select * from recompensas_xp')).rows;
  await exec("create function public.rpc_desconhecida() returns int language sql security definer as 'select 1';grant execute on function public.rpc_desconhecida() to anon;");
  await assert.rejects(exec(ler('migrations/evolucao_perfil_metas_xp_niveis.sql')),/SECURITY DEFINER acessível/);
  assert.equal((await um("select has_function_privilege('anon','public.rpc_desconhecida()','EXECUTE') p")).p,true);
  assert.equal((await um("select count(*) n from pg_attribute where attrelid='atividades'::regclass and attname='distancia_km'")).n,0);
  await exec('drop function public.rpc_desconhecida();'); // somente fixture descartável
  await exec('alter default privileges grant execute on functions to public,anon,authenticated,service_role;');
  await exec(ler('migrations/evolucao_perfil_metas_xp_niveis.sql'));
  assert.deepEqual((await db.query('select * from recompensas_xp')).rows,historico.map(r=>({...r,transacao:null})));
  assert.equal((await um('select xp_versao from atividades where id_atividade=1')).xp_versao,1);
  await exec("update atividades set duracao=60 where id_atividade=1;");
  assert.deepEqual((await db.query('select * from recompensas_xp')).rows,historico.map(r=>({...r,transacao:null})));
  // Metas: minutos, km, sessões, período, modalidade e isolamento de usuário.
  await exec("set role service_role;insert into metas(id_usuario,descricao,prazo,inicio,metrica,alvo,modalidade) values (1,'Minutos',current_date+1,current_date-1,'minutos',30,'Corrida'),(1,'Km',current_date+1,current_date-1,'km',3,'Corrida'),(1,'Sessões',current_date+1,current_date-1,'sessoes',2,null),(2,'Privada',current_date+1,current_date-1,'sessoes',1,null),(1,'Futura',current_date+20,current_date+10,'sessoes',1,null);reset role;");
  let base=await total();
  await exec("set role service_role;insert into atividades(id_usuario,tipo_exercicio,duracao,distancia_km,chave_registro,data_registro) values(1,'Corrida',30,3,'00000000-0000-4000-8000-000000000001',now()-interval '1 minute');reset role;");
  const a=await um('select * from atividades where id_atividade=2');assert.equal(a.xp_atual,45);assert.equal(a.xp_transacao,(await um("select transacao from recompensas_xp where chave_evento='atividade:00000000-0000-4000-8000-000000000001'")).transacao);
  assert.equal(await total()-base,45+150); // três metas concluídas
  assert.equal((await um("select progresso from metas where descricao='Privada'")).progresso,0);
  assert.equal((await um("select progresso from metas where descricao='Futura'")).progresso,0);
  base=await total();
  await exec("set role service_role;insert into atividades(id_usuario,tipo_exercicio,duracao,distancia_km,chave_registro) values(1,'Corrida',30,3,'00000000-0000-4000-8000-000000000001');reset role;");
  assert.equal(await total(),base);
  await exec("set role service_role;update atividades set duracao=25,distancia_km=5,xp_atual=9999,xp_revisao=500,xp_versao=1 where id_atividade=2;reset role;");
  assert.equal(await total(),base+5);assert.equal((await um('select xp_atual from atividades where id_atividade=2')).xp_atual,50);
  assert.equal((await um("select progresso from metas where descricao='Minutos'")).progresso,83);
  await exec("set role service_role;update atividades set duracao=25,distancia_km=5 where id_atividade=2;reset role;");
  assert.equal(await total(),base+5);
  await exec("set role service_role;update atividades set duracao=30,distancia_km=3 where id_atividade=2;reset role;");
  assert.equal(await total(),base); // meta não repete bônus ao recompletar
  await exec("set role service_role;delete from atividades where id_atividade=2;reset role;");
  assert.equal(await total(),base-45);
  assert.equal((await um("select progresso from metas where descricao='Km'")).progresso,0);
  assert.equal(Number((await um("select xp from recompensas_xp where chave_evento='estorno:atividade:00000000-0000-4000-8000-000000000001'")).xp),-45);
  await exec("set role service_role;delete from atividades where id_atividade=1;reset role;");
  assert.equal(await total(),base-65); // estorno legado exatamente 20
  const casos=[['Corrida',25,'5',50],['Corrida',30,'3.199',45],['Caminhada',60,'5.555',76],['Ciclismo',60,'20.5',101],['Natação',60,'1.099',70],['Yoga',40,null,40],['Artes Marciais',60,null,60],['Corrida',1440,'720',5040]];
  for(const [tipo,min,km,xp] of casos) assert.equal((await um('select lifes_private.xp_sessao($1,$2,$3) xp',[tipo,min,km])).xp,xp);
  for(const [tipo,min,km] of [['Yoga',30,'2'],['Caminhada',1,'1'],['Corrida',1,'NaN'],['Ciclismo',1,'0.0001'],['Natação',30,'-1'],['Corrida',0,null],['Corrida',1441,null]]) {
   await assert.rejects(db.query('select lifes_private.xp_sessao($1,$2,$3)',[tipo,min,km]));
  }
  await assert.rejects(exec("set role service_role;insert into recompensas_xp(id_usuario,chave_evento,motivo,xp) values(1,'fraude','fraude',200);"),e=>e.code==='42501');await exec('reset role;');
  await assert.rejects(exec("set role anon;select * from recompensas_xp;"),e=>e.code==='42501');await exec('reset role;');
  await assert.rejects(exec("set role service_role;update usuarios set email='outro' where id_usuario=1;"),e=>e.code==='42501');await exec('reset role;');
  await exec("set role service_role;update usuarios set nome='Novo nome',foto_path='1/exemplo.png',perfil_versao=1 where id_usuario=1;select * from recompensas_xp;reset role;");
  await assert.rejects(exec("set role service_role;update metas set progresso=0 where descricao='Legada';"));await exec('reset role;');
  await exec("set role service_role;update metas set progresso=100,acumulado=999 where descricao='Futura';reset role;");
  assert.equal((await um("select progresso from metas where descricao='Futura'")).progresso,0);
  // Período inclusivo em São Paulo, timestamp com offset ou legado UTC.
  await exec(("set role service_role;insert into metas(id_usuario,descricao,metrica,alvo,modalidade,inicio,prazo) values(1,'Fuso','sessoes',1,'Caminhada','2020-01-01','2020-01-01');insert into atividades(id_usuario,tipo_exercicio,duracao,data_registro,distancia_km) values(1,'Caminhada',30,'2020-01-02T02:59:00Z',2);reset role;").replace('2020-01-02T02:59:00Z', modoDate ? '2020-01-01' : '2020-01-02T02:59:00Z'));
  assert.equal((await um("select progresso from metas where descricao='Fuso'")).progresso,100);
  await exec("set role service_role;update atividades set data_registro='2020-01-02T03:00:00Z' where tipo_exercicio='Caminhada';reset role;");
  assert.equal((await um("select progresso from metas where descricao='Fuso'")).progresso,0);
  // Estorno após aumento: 45 + ajuste 5 - 50 = zero para esta sessão.
  await exec("set role service_role;insert into atividades(id_usuario,tipo_exercicio,duracao,distancia_km,chave_registro) values(1,'Corrida',30,3,'00000000-0000-4000-8000-000000000002');update atividades set duracao=25,distancia_km=5 where chave_registro='00000000-0000-4000-8000-000000000002';delete from atividades where chave_registro='00000000-0000-4000-8000-000000000002';reset role;");
  assert.equal((await um("select xp from recompensas_xp where chave_evento='estorno:atividade:00000000-0000-4000-8000-000000000002'")).xp,-50);
  // Meta fora do período não interfere; erro numa meta afetada reverte a operação.
  await exec("alter table metas disable trigger lifes_calcular_meta;update metas set alvo=-1 where descricao='Futura';alter table metas enable trigger lifes_calcular_meta;");
  await exec("set role service_role;insert into atividades(id_usuario,tipo_exercicio,duracao) values(1,'Yoga',40);reset role;");
  await exec("alter table metas disable trigger lifes_calcular_meta;update metas set alvo=-1 where descricao='Sessões';alter table metas enable trigger lifes_calcular_meta;");
  const nAntes=(await um('select count(*) n from atividades')).n,xpAntes=await total();
  await assert.rejects(exec("set role service_role;insert into atividades(id_usuario,tipo_exercicio,duracao) values(1,'Yoga',40);"),/Objetivo automático inválido/);await exec('reset role;');
  assert.equal((await um('select count(*) n from atividades')).n,nAntes);assert.equal(await total(),xpAntes);
  await exec("update metas set alvo=1 where descricao in ('Futura','Sessões');");
  for(const papel of ['anon','authenticated','service_role']) {
   for(const comando of ["insert into recompensas_xp(id_usuario,chave_evento,motivo,xp) values(1,'fraude','fraude',1)",'update recompensas_xp set xp=1','delete from recompensas_xp','truncate recompensas_xp']) {
    await assert.rejects(exec(`set role ${papel};${comando};`),e=>e.code==='42501');await exec('reset role;');
   }
   assert.equal((await um("select count(*) n from pg_proc where proname in ('lifes_calcular_meta','lifes_recalcular_metas','lifes_premiar','lifes_validar_registro','lifes_estornar_atividade') and has_function_privilege($1,oid,'EXECUTE')",[papel])).n,0);
  }
  // Também aceita o timestamp legado sem offset, interpretado como UTC.
  if(!modoDate) {
  await exec("alter table atividades alter column data_registro type timestamp without time zone using data_registro at time zone 'UTC';");
  await exec(ler('migrations/evolucao_perfil_metas_xp_niveis.sql'));
  await exec("set role service_role;insert into atividades(id_usuario,tipo_exercicio,duracao,data_registro) values(1,'Caminhada',30,'2020-01-02 02:59:00');reset role;");
  assert.equal((await um("select progresso from metas where descricao='Fuso'")).progresso,100);
  }
  await exec("insert into usuarios(nome,email,senha_hash) values('Sequência','seq@local','hash');set role service_role;insert into atividades(id_usuario,tipo_exercicio,duracao,data_registro) select 3,'Yoga',1,'2020-02-01 12:00:00'::timestamp+i*interval '1 day' from generate_series(0,6) i;reset role;");
  assert.equal(Number((await um('select sum(xp) n from recompensas_xp where id_usuario=3')).n),57);
  await exec("set role service_role;delete from atividades where id_usuario=3 and data_registro='2020-02-01 12:00:00';reset role;");
  assert.equal(Number((await um('select sum(xp) n from recompensas_xp where id_usuario=3')).n),56);
  await regressao.verificar(db,exec,modoDate,ler);
  const diagnostico=await exec(ler('migrations/validacao_evolucao.sql'));
  for(const resultado of diagnostico) for(const linha of resultado.rows || []) for(const [campo,valor] of Object.entries(linha)) {
   if(campo.startsWith('divergencias_') || campo==='atividades_v2_sem_lancamento' || campo==='eventos_duplicados') assert.equal(Number(valor),0,campo);
  }
  const antes=(await db.query('select * from recompensas_xp order by id_recompensa')).rows;
  await exec(ler('migrations/evolucao_perfil_metas_xp_niveis.sql'));
  assert.deepEqual((await db.query('select * from recompensas_xp order by id_recompensa')).rows,antes);
  await exec('select lifes_private.exigir_backend_privado();');
  await exec(ler('migrations/storage_perfis_privado.sql'));
  await exec(ler('migrations/diagnostico_evolucao.sql'));
  console.log((modoDate?'DATE/NUMERIC real: ':'TIMESTAMPTZ/TIMESTAMP: ')+'OK evolução: legado, metas, isolamento, XP, ajustes, estornos, ACL e reaplicação.');
 } finally {await db.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
