/* Banco WASM descartável. DROP/alterações de catálogo abaixo são apenas fixtures,
 * nunca executados no Supabase ou incluídos na migração de produção. */
const {PGlite}=require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs=require('fs'),assert=require('node:assert/strict');
const ler=p=>fs.readFileSync(p,'utf8').replace(/^\uFEFF/,'');
const migracao=ler('migrations/finalizacao_premium.sql');
const antiga=migracao.replace(/create unique index if not exists conquistas_nome_normalizado_uidx[\s\S]*?-- Seed completo/,
 ()=>`create unique index if not exists conquistas_nome_normalizado_uidx on public.conquistas(lower(btrim(nome)));
 do $$begin
 if not exists(select 1 from pg_index i where i.indexrelid=to_regclass('public.conquistas_nome_normalizado_uidx')
  and i.indrelid='public.conquistas'::regclass and i.indisunique and i.indisvalid and i.indisready
  and i.indimmediate and i.indnkeyatts=1 and i.indpred is null
  and pg_get_expr(i.indexprs,i.indrelid)='lower(btrim(nome))') then
  raise exception 'Índice de nomes normalizados incompatível; revisar sem remover dados';
 end if;end $$;
 -- Seed completo`);
(async()=>{
 for(const tipo of ['text','varchar(120)','char(120)']) {
  const db=new PGlite();
  const aplicar=async sql=>{try{await db.exec(sql);}catch(e){await db.exec('rollback');throw e;}};
  const indice=async()=>(await db.query("select to_regclass('public.conquistas_nome_normalizado_uidx')::oid oid")).rows[0].oid;
  const linhas=async()=>(await db.query('select * from conquistas order by id_conquista')).rows;
  try {
   await db.exec('create role anon;create role authenticated;create role service_role bypassrls;');
   await db.exec(ler('schema.sql').split('-- SEGURANÇA:')[0]);
   await db.exec(`alter table conquistas alter column nome type ${tipo};`);
   await aplicar(ler('migrations/seguranca_backend.sql'));
   await aplicar(ler('migrations/semanas_8_9.sql'));
   const antes=await linhas();
   if(tipo!=='text') {
    // Reproduz exatamente a falha reportada e o desaparecimento por rollback.
    await assert.rejects(aplicar(antiga),e=>e.code==='P0001' && /Índice de nomes/.test(e.message));
    assert.equal(await indice(),null);
    assert.deepEqual(await linhas(),antes);
    assert.equal((await db.query("select attnotnull from pg_attribute where attrelid='atividades'::regclass and attname='frequencia'")).rows[0].attnotnull,true);
   }
   await aplicar(migracao);
   const resultado=await linhas();
   assert.equal(resultado.length,14);
   assert.deepEqual(resultado.filter(r=>antes.some(a=>a.id_conquista===r.id_conquista)),antes);
   const oid=await indice();
   await aplicar(migracao);
   assert.equal(await indice(),oid);
   assert.deepEqual(await linhas(),resultado);
   assert.equal((await db.query("select to_regclass('pg_temp.lifes_conquistas_indice_ref') ref")).rows[0].ref,null);
   await assert.rejects(db.exec("insert into conquistas(nome,descricao,pontos) values(' PRIMEIRO PASSO ','Duplicada fixture',0)"),e=>e.code==='23505');
   if(tipo==='varchar(120)') {
    console.log('Reprodução varchar: guarda antiga falha/rollback; guarda corrigida aceita casts e preserva IDs.');
    // Índices criados explicitamente: qualificação/cast/INCLUDE não mudam unicidade.
    for(const expressao of [
     'pg_catalog.lower(pg_catalog.btrim(nome::pg_catalog.text))',
     'pg_catalog.lower(pg_catalog.btrim(nome::pg_catalog.text)) DESC'
    ]) {
     await db.exec('drop index conquistas_nome_normalizado_uidx');
     await db.exec(`create unique index conquistas_nome_normalizado_uidx on conquistas(${expressao}) include(id_conquista)`);
     const existente=await indice();
     await aplicar(migracao);
     assert.equal(await indice(),existente);
     assert.deepEqual(await linhas(),resultado);
    }
    const casos=[
     'create index conquistas_nome_normalizado_uidx on conquistas(lower(btrim(nome)))',
     'create unique index conquistas_nome_normalizado_uidx on conquistas(lower(btrim(nome))) where id_conquista>0',
     'create unique index conquistas_nome_normalizado_uidx on conquistas(lower(nome))',
     'create unique index conquistas_nome_normalizado_uidx on conquistas(lower(btrim(descricao)))',
     'create unique index conquistas_nome_normalizado_uidx on conquistas(lower(btrim(nome)),id_conquista)',
     'create unique index conquistas_nome_normalizado_uidx on conquistas(nome)',
     'create unique index conquistas_nome_normalizado_uidx on dicas(lower(btrim(titulo)))',
     'create unique index conquistas_nome_normalizado_uidx on conquistas(lower(btrim(nome)) text_pattern_ops)',
     'create unique index conquistas_nome_normalizado_uidx on conquistas(lower(btrim(nome)) collate "C")'
    ];
    for(const sql of casos) {
     await db.exec('drop index conquistas_nome_normalizado_uidx');
     await db.exec(sql);
     const existente=await indice();
     await assert.rejects(aplicar(migracao),/Índice de nomes normalizados incompatível/);
     assert.equal(await indice(),existente); // Nenhum índice preexistente removido pela migração.
     assert.deepEqual(await linhas(),resultado);
    }
    await db.exec('drop index conquistas_nome_normalizado_uidx');
    await db.exec('create unique index conquistas_nome_normalizado_uidx on conquistas(lower(btrim(nome)))');
    for(const flag of ['indisvalid','indisready','indislive','indimmediate']) {
     await db.exec(`update pg_index set ${flag}=false where indexrelid='conquistas_nome_normalizado_uidx'::regclass`);
     await assert.rejects(aplicar(migracao),/Índice de nomes normalizados incompatível/);
     await db.exec(`update pg_index set ${flag}=true where indexrelid='conquistas_nome_normalizado_uidx'::regclass`);
    }
    // Função homônima não pode se passar pela função pg_catalog.lower.
    await db.exec('drop index conquistas_nome_normalizado_uidx');
    await db.exec("create function lifes_private.lower(text) returns text language plpgsql immutable as $$begin return $1;end$$");
    await db.exec('create unique index conquistas_nome_normalizado_uidx on conquistas(lifes_private.lower(btrim(nome)))');
    await assert.rejects(aplicar(migracao),/Índice de nomes normalizados incompatível/);
   }
   console.log(`Índice ${tipo}: migração completa e repetição aprovadas, sem alteração das conquistas existentes.`);
  } finally {await db.close();}
 }
 console.log('Índice de conquistas OK: casts/qualificações, unicidade, flags, predicado, coluna, expressão, função, collation e opclass.');
})().catch(e=>{console.error(e.message);process.exitCode=1;});
