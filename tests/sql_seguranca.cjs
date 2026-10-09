/* PostgreSQL WASM local; simula roles/ACL Supabase, nunca acessa rede/banco remoto. */
const {PGlite}=require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs=require('fs'),assert=require('node:assert/strict');
const ler=p=>fs.readFileSync(p,'utf8').replace(/^\uFEFF/,'');
(async()=>{
 const db=new PGlite();
 const aplicar=async sql=>{try{await db.exec(sql);}catch(e){await db.exec('rollback;');throw e;}};
 const como=async(papel,sql)=>{await db.exec(`set role ${papel};`);try{return await db.query(sql);}finally{await db.exec('reset role;');}};
 const total=async()=>Number((await db.query('select coalesce(sum(xp),0) n from recompensas_xp')).rows[0].n);
 try {
  // Diagnóstico também deve executar antes de haver qualquer tabela/role de API.
  await aplicar(ler('migrations/diagnostico_finalizacao.sql'));
  await db.exec('create role anon;create role authenticated;create role service_role bypassrls;');
  const base=ler('schema.sql').split('-- SEGURANÇA:')[0];
  await db.exec(base);
  await db.exec('grant usage,create on schema public to public; grant all on all tables in schema public to public,anon,authenticated,service_role; grant all on all sequences in schema public to public,anon,authenticated,service_role;');
  await aplicar(ler('migrations/diagnostico_finalizacao.sql'));
  // Migração XP não deve instalar triggers enquanto o papel público pode forjar eventos.
  await assert.rejects(aplicar(ler('migrations/semanas_8_9.sql')));
  assert.equal((await db.query("select to_regclass('public.recompensas_xp') as t")).rows[0].t,null);
  // RPC definer desconhecida bloqueia o plano; não é apagada silenciosamente.
  await db.exec('create function public.rpc_exposta() returns int language sql security definer as $$select 1$$;');
  await assert.rejects(aplicar(ler('migrations/seguranca_backend.sql')),/SECURITY DEFINER acessível: public.rpc_exposta\(\)|SECURITY DEFINER acessível: rpc_exposta\(\)/);
  assert.equal((await db.query("select has_table_privilege('anon','public.usuarios','SELECT') ok")).rows[0].ok,true);
  await db.exec('drop function public.rpc_exposta();');
  // Funções internas fora de public não devem ser confundidas com RPCs públicas.
  await db.exec('create schema interno_fixture; create function interno_fixture.interna() returns int language sql security definer as $$select 1$$;');
  // Views continuam exigindo revisão mesmo se invoker: podem chamar funções.
  await db.exec('create view public.v_usuarios as select nome from usuarios; grant select on public.v_usuarios to anon;');
  await assert.rejects(aplicar(ler('migrations/seguranca_backend.sql')),/View pública legível: (public\.)?v_usuarios/);
  await db.exec('alter view public.v_usuarios set (security_invoker=true);');
  await assert.rejects(aplicar(ler('migrations/seguranca_backend.sql')),/View pública legível/);
  await db.exec('drop view public.v_usuarios;');
  // REVOKE de grants diretos não remove privilégios herdados de outro papel.
  await db.exec('create role legado;grant legado to anon;grant select(nome) on usuarios to legado;');
  await assert.rejects(aplicar(ler('migrations/seguranca_backend.sql')),/Privilégio residual/);
  await db.exec('revoke legado from anon;revoke select(nome) on usuarios from legado;drop role legado;');
  await aplicar(ler('migrations/seguranca_backend.sql'));
  // O gate também exige os grants positivos: evitar migração "verde" e Flask quebrado.
  await db.exec('revoke insert on usuarios from service_role;');
  await assert.rejects(db.query('select lifes_private.exigir_backend_privado()'),/Permissão necessária ao Flask ausente/);
  await db.exec('grant insert on usuarios to service_role;');
  await db.exec('revoke usage on sequence usuarios_id_usuario_seq from service_role;');
  await assert.rejects(db.query('select lifes_private.exigir_backend_privado()'),/Permissão necessária ao Flask ausente/);
  await db.exec('grant usage on sequence usuarios_id_usuario_seq to service_role;');
  // Um índice com o nome esperado e definição errada não deve passar por IF NOT EXISTS.
  await db.exec('create index atividade_registro_uidx on atividades(id_usuario);');
  await assert.rejects(aplicar(ler('migrations/semanas_8_9.sql')),/Unicidade obrigatória/);
  assert.equal((await db.query("select to_regclass('public.recompensas_xp') as t")).rows[0].t,null);
  await db.exec('drop index atividade_registro_uidx;');
  await aplicar(ler('migrations/semanas_8_9.sql'));
  // Duplicidade legada exige decisão humana: falha sem apagar/mesclar IDs.
  await db.exec("insert into conquistas(nome,descricao,pontos) values(' PRIMEIRO PASSO ','Legado',0)");
  await assert.rejects(aplicar(ler('migrations/finalizacao_premium.sql')),e=>e.code==='23505');
  assert.equal((await db.query("select count(*)::int n from conquistas where lower(btrim(nome))='primeiro passo'")).rows[0].n,2);
  await db.exec("delete from conquistas where descricao='Legado'"); // remove só a fixture local
  await db.exec('create index conquistas_nome_normalizado_uidx on conquistas(nome);');
  await assert.rejects(aplicar(ler('migrations/finalizacao_premium.sql')),/Índice de nomes/);
  await db.exec('drop index conquistas_nome_normalizado_uidx;');
  await aplicar(ler('migrations/finalizacao_premium.sql'));
  await aplicar(ler('migrations/diagnostico_finalizacao.sql'));
  for(const papel of ['anon','authenticated']) {
   for(const sql of ['select * from usuarios','select * from recompensas_xp',
    "insert into atividades(id_usuario,tipo_exercicio,duracao) values(1,'Corrida',20)",
    'delete from atividades','truncate recompensas_xp',
    "insert into usuario_conquista(id_usuario,id_conquista) values(1,1)",
    'update metas set progresso=100']) await assert.rejects(como(papel,sql),e=>e.code==='42501');
   await assert.rejects(como(papel,"create table public.falsa(id int)"),e=>e.code==='42501');
  }
  // Fluxo compatível com Flask: service_role cria usuários, fontes e lê recompensas.
  await como('service_role',"insert into usuarios(nome,email,senha_hash) values('Teste','teste@local.test','hash'),('Outro','outro@local.test','hash')");
  await como('service_role',"insert into agenda(id_usuario,titulo,horario) values(1,'Treino',now())");
  const insert="insert into atividades(id_usuario,tipo_exercicio,duracao,chave_registro,id_agenda) values(1,'Corrida',30,'00000000-0000-4000-8000-000000000001',1) returning *";
  assert.equal((await como('service_role',insert)).rows.length,1);
  assert.equal((await como('service_role',insert)).rows.length,0);
  assert.equal(await total(),20);
  assert.equal((await como('service_role','select xp from recompensas_xp')).rows[0].xp,20);
  // Transação descartável com as mesmas operações ON CONFLICT do Flask/Dashboard.
  await db.exec('begin;');
  await como('service_role','insert into usuario_conquista(id_usuario,id_conquista) values(1,1) on conflict(id_usuario,id_conquista) do nothing returning *');
  await como('service_role','insert into usuario_conquista(id_usuario,id_conquista) values(1,1) on conflict(id_usuario,id_conquista) do nothing returning *');
  assert.equal(await total(),50);
  await como('service_role',"insert into alertas(id_usuario,chave_evento,mensagem,tipo,status) values(1,'fixture','Aviso','agenda','nao_lido') on conflict(id_usuario,chave_evento) do nothing returning *");
  await como('service_role',"update alertas set status='lido' where id_usuario=1 returning *");
  for (const tabela of ['usuarios','agenda','atividades','metas','conquistas','usuario_conquista','alertas','dicas','recompensas_xp'])
    await como('service_role',`select * from public.${tabela} limit 1`);
  await db.exec('rollback;');
  for(const sql of ["insert into recompensas_xp(id_usuario,chave_evento,motivo,xp) values(1,'forjado','Forjado',50)",
   'update recompensas_xp set xp=50','delete from recompensas_xp','truncate recompensas_xp',
   'select setval(\'recompensas_xp_id_recompensa_seq\',999)',
   'create trigger malicioso after insert on atividades for each row execute function public.lifes_premiar()'])
    await assert.rejects(como('service_role',sql),e=>e.code==='42501');
  const funcoes=(await db.query("select p.oid::regprocedure::text assinatura,pg_get_userbyid(proowner) dono,proconfig from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname like 'lifes_%'")).rows;
  for(const f of funcoes) {
   assert.equal(f.dono,'postgres');assert.deepEqual(f.proconfig,['search_path=pg_catalog']);
   for(const papel of ['anon','authenticated','service_role'])
    assert.equal((await db.query('select has_function_privilege($1,$2,\'EXECUTE\') ok',[papel,f.assinatura])).rows[0].ok,false);
  }
  // Profundidade >1 não autoriza anon nem se um grant INSERT for reintroduzido.
  // Fixture controlada: schema próprio com trigger invoker e ACL temporária no livro.
  await db.exec("create schema ataque authorization anon; grant insert on recompensas_xp to anon;");
  await como('anon',"create table ataque.fonte(id int)");
  await como('anon',"create function ataque.injetar() returns trigger language plpgsql as $$begin insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp) overriding system value values(1,'ataque','forjado',50);return new;end$$");
  await como('anon','create trigger injetar after insert on ataque.fonte for each row execute function ataque.injetar()');
  // Identity precisa USAGE para que a execução alcance o guard, não falhe antes.
  await db.exec('grant usage on sequence recompensas_xp_id_recompensa_seq to anon;');
  await assert.rejects(como('anon','insert into ataque.fonte values(1)'),/histórico de XP/);
  assert.equal(await total(),20);
  await db.exec('revoke insert on recompensas_xp from anon;revoke usage on sequence recompensas_xp_id_recompensa_seq from anon;drop schema ataque cascade;');
  // Serviço é confiável, não identifica o usuário final no banco. A sessão Flask filtra.
  assert.equal((await como('service_role','select id_usuario from usuarios')).rows.length,2);
  await como('service_role','delete from atividades where id_usuario=1');
  assert.equal(await total(),0);
  assert.equal((await como('service_role',insert)).rows.length,0);
  assert.equal(await total(),0);
  await como('service_role',"insert into metas(id_usuario,descricao,prazo) values(1,'Meta',current_date)");
  await como('service_role','update metas set progresso=100');
  await como('service_role','update metas set progresso=0');
  await como('service_role','update metas set progresso=100');
  await como('service_role','delete from metas');
  assert.equal(await total(),50); // marco histórico legítimo, não nova premiação.
  assert.equal((await db.query('select count(*)::int n from conquistas')).rows[0].n,14);
  await assert.rejects(db.exec("insert into conquistas(nome,descricao,pontos) values(' PRIMEIRO PASSO ','Duplicada',0)"),e=>e.code==='23505');
  const ids=(await db.query('select id_conquista,nome from conquistas order by id_conquista')).rows;
  await aplicar(ler('migrations/seguranca_backend.sql'));
  await aplicar(ler('migrations/semanas_8_9.sql'));
  await aplicar(ler('migrations/finalizacao_premium.sql'));
  assert.deepEqual((await db.query('select id_conquista,nome from conquistas order by id_conquista')).rows,ids);
  assert.equal(await total(),50);
  await aplicar(ler('migrations/diagnostico_finalizacao.sql'));
  console.log('Segurança SQL local OK: anon/auth bloqueados, Flask service_role funcional, ACL efetiva/colunas/herança, RPC exposta rejeitada, ataque com trigger aninhado rejeitado, histórico e 14 conquistas preservados.');
 } finally {await db.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
