/* Integração das três migrações: PostgreSQL WASM descartável, sem acesso remoto. */
const {PGlite}=require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs=require('fs'),assert=require('node:assert/strict');
const ler=p=>fs.readFileSync(p,'utf8').replace(/^\uFEFF/,'');
(async()=>{
 const db=new PGlite();
 const aplicar=async sql=>{try{await db.exec(sql);}catch(e){await db.exec('rollback');throw e;}};
 const como=async(papel,sql)=>{await db.exec(`set role ${papel}`);try{return await db.query(sql);}finally{await db.exec('reset role');}};
 const defaults=async()=>(await db.query('select defaclnamespace,defaclobjtype,defaclacl::text from pg_default_acl order by 1,2')).rows;
 try {
  await db.exec('create role anon;create role authenticated;create role service_role bypassrls;create role visitante;');
  await db.exec(ler('schema.sql').split('-- SEGURANÇA:')[0]);
  // Defaults reais de PostgreSQL, aplicáveis a objetos ainda não criados.
  await db.exec(`grant usage on schema public to public;
   alter default privileges grant all on tables to public,anon,authenticated,service_role;
   alter default privileges grant all on sequences to public,anon,authenticated,service_role;
   alter default privileges grant execute on functions to public,anon,authenticated,service_role;`);
  const originalDefaults=await defaults();
  await aplicar(ler('migrations/seguranca_backend.sql'));
  assert.equal((await db.query("select to_regclass('public.recompensas_xp') t")).rows[0].t,null);
  // PostgreSQL não tem default ACL por coluna. Esta fixture DDL simula um grant
  // por coluna feito por automação ao criar a tabela; não existe nas migrações.
  await db.exec(`create function lifes_private.fixture_acl_coluna() returns event_trigger
   language plpgsql as $$begin
    if to_regclass('public.recompensas_xp') is not null then
      grant select(xp),insert(xp),update(xp),references(xp) on public.recompensas_xp
        to public,anon,authenticated,service_role;
    end if;
   end$$;
   create event trigger fixture_acl_coluna on ddl_command_end when tag in ('CREATE TABLE')
     execute function lifes_private.fixture_acl_coluna();`);
  // Herança não é default privilege: não remover silenciosamente papéis externos.
  await db.exec(`create role herdado;grant herdado to anon;
   alter default privileges grant select on tables to herdado;`);
  await assert.rejects(aplicar(ler('migrations/semanas_8_9.sql')),/Privilégio residual/);
  assert.equal((await db.query("select to_regclass('public.recompensas_xp') t")).rows[0].t,null);
  await db.exec('alter default privileges revoke select on tables from herdado;');
  const maintain=(await db.query("select exists(select 1 from aclexplode(acldefault('r',(select oid from pg_roles where rolname=current_user))) where privilege_type='MAINTAIN') ok")).rows[0].ok;
  if(maintain) {
   await db.exec('alter default privileges grant maintain on tables to herdado;');
   await assert.rejects(aplicar(ler('migrations/semanas_8_9.sql')),/Privilégio residual anon.MAINTAIN/);
   assert.equal((await db.query("select to_regclass('public.recompensas_xp') t")).rows[0].t,null);
   await db.exec('alter default privileges revoke maintain on tables from herdado;');
  }
  await db.exec('revoke herdado from anon;drop role herdado;');
  await aplicar(ler('migrations/semanas_8_9.sql'));
  // Não pode sobrar nenhum grant explícito por coluna, nem para service_role.
  assert.equal((await db.query(`select count(*)::int n from pg_attribute a,
   lateral aclexplode(a.attacl) acl where a.attrelid='public.recompensas_xp'::regclass
    and (acl.grantee=0 or acl.grantee in(select oid from pg_roles
     where rolname in ('anon','authenticated','service_role')))`)).rows[0].n,0);
  for(const papel of ['anon','authenticated','visitante','service_role']) {
   for(const privilegio of ['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'])
    assert.equal((await db.query("select has_table_privilege($1,'public.recompensas_xp',$2) ok",[papel,privilegio])).rows[0].ok,
      papel==='service_role' && privilegio==='SELECT');
   for(const privilegio of ['USAGE','SELECT','UPDATE'])
    assert.equal((await db.query("select has_sequence_privilege($1,'public.recompensas_xp_id_recompensa_seq',$2) ok",[papel,privilegio])).rows[0].ok,false);
   if(papel!=='service_role') await assert.rejects(como(papel,'select xp from recompensas_xp'),e=>e.code==='42501');
  }
  await db.exec('drop event trigger fixture_acl_coluna;drop function lifes_private.fixture_acl_coluna();');
  // Uma RPC desconhecida entre as etapas bloqueia sem alterar seu código/ACL.
  await db.exec('create function public.rpc_legada() returns int language sql security definer as $$select 1$$;');
  const rpc=await db.query("select proacl::text,pg_get_functiondef(oid) def from pg_proc where oid='public.rpc_legada()'::regprocedure");
  await assert.rejects(aplicar(ler('migrations/finalizacao_premium.sql')),/SECURITY DEFINER acessível: (public\.)?rpc_legada/);
  assert.deepEqual((await db.query("select proacl::text,pg_get_functiondef(oid) def from pg_proc where oid='public.rpc_legada()'::regprocedure")).rows,rpc.rows);
  assert.equal((await db.query("select attnotnull from pg_attribute where attrelid='public.atividades'::regclass and attname='frequencia'")).rows[0].attnotnull,true);
  await db.exec('drop function public.rpc_legada();'); // Só remove a fixture local.
  await aplicar(ler('migrations/finalizacao_premium.sql'));
  for(const assinatura of ['public.lifes_validar_registro()','public.lifes_premiar()',
      'public.lifes_proteger_livro()','public.lifes_estornar_atividade()','lifes_private.exigir_backend_privado()'])
   for(const papel of ['anon','authenticated','service_role','visitante'])
    assert.equal((await db.query("select has_function_privilege($1,$2,'EXECUTE') ok",[papel,assinatura])).rows[0].ok,false);
  await como('service_role',"insert into usuarios(nome,email,senha_hash) values('Fixture','fixture@local.test','hash')");
  await como('service_role',"insert into atividades(id_usuario,tipo_exercicio,duracao,chave_registro) values(1,'Yoga',30,'00000000-0000-4000-8000-000000000001')");
  assert.deepEqual((await como('service_role','select xp from recompensas_xp order by id_recompensa')).rows,[{xp:20}]);
  for(const sql of ["insert into recompensas_xp(id_usuario,chave_evento,motivo,xp) values(1,'forjado','forjado',50)",
    'update recompensas_xp set xp=50','delete from recompensas_xp','truncate recompensas_xp'])
   await assert.rejects(como('service_role',sql),e=>e.code==='42501');
  await como('service_role','delete from atividades where id_usuario=1');
  const historico=(await como('service_role','select chave_evento,xp from recompensas_xp order by id_recompensa')).rows;
  assert.deepEqual(historico.map(r=>r.xp),[20,-20]);
  for(const arquivo of ['seguranca_backend.sql','semanas_8_9.sql','finalizacao_premium.sql'])
   await aplicar(ler('migrations/'+arquivo));
  assert.deepEqual((await como('service_role','select chave_evento,xp from recompensas_xp order by id_recompensa')).rows,historico);
  assert.deepEqual(await defaults(),originalDefaults);
  console.log('Defaults XP OK: criação posterior, PUBLIC/anon/auth, colunas, sequência, EXECUTE, herança com rollback, RPC desconhecida preservada, SELECT service_role, +20/-20 internos e reaplicação sem alterar defaults/histórico.');
 } finally {await db.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
