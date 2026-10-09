/* PostgreSQL local descartável (PGlite); não usa Supabase nem credenciais. */
const {PGlite}=require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs=require('node:fs'),assert=require('node:assert/strict');
const ler=p=>fs.readFileSync(p,'utf8').replace(/^\uFEFF/,'');
(async()=>{
 for(const tipo of ['date','timestamp without time zone','timestamp with time zone']) {
  const db=new PGlite();
  try {
   await db.exec('create role anon;create role authenticated;create role service_role bypassrls;');
   await db.exec(ler('schema.sql').replace('data_registro timestamptz not null default now()',`data_registro ${tipo} not null default now()`));
   await db.exec(ler('migrations/evolucao_perfil_metas_xp_niveis.sql'));
   await db.exec(`insert into usuarios(nome,email,senha_hash) values('Teste','teste@local','hash');
    set role service_role;
    insert into metas(id_usuario,descricao,metrica,alvo,modalidade,inicio,prazo) values
    (1,'Minutos','minutos',60,'Corrida','2020-01-01','2020-01-31'),
    (1,'Km','km',10,'Corrida','2020-01-01','2020-01-31'),
    (1,'Sessões','sessoes',2,'Corrida','2020-01-01','2020-01-31');reset role;`);
   const metas=async()=> (await db.query('select metrica,acumulado,progresso from metas order by metrica')).rows
    .map(r=>[r.metrica,Number(r.acumulado),Number(r.progresso)]);
   const esperar=async(km,min,sessoes)=>assert.deepEqual(await metas(),[
    ['km',km,Math.min(100,Math.floor(km*10))],
    ['minutos',min,Math.min(100,Math.floor(min*100/60))],
    ['sessoes',sessoes,Math.min(100,sessoes*50)]]);
   const estado=async()=>({metas:await metas(),
    atividades:(await db.query('select * from atividades order by id_atividade')).rows,
    livro:(await db.query('select * from recompensas_xp order by id_recompensa')).rows});
   const inserir=`insert into atividades(id_usuario,tipo_exercicio,duracao,distancia_km,data_registro)
    values(1,'Corrida',30,3,'2020-01-10 12:00:00')`;
   await esperar(0,0,0);
   await db.exec(`set role service_role;${inserir};reset role;`);
   await esperar(3,30,1);
   await db.exec("set role service_role;update atividades set duracao=60,distancia_km=6;reset role;");
   await esperar(6,60,1);
   // Cada operação precisa atualizar as três métricas na transação e reverter tudo.
   for(const [sql,km,min,sessoes] of [
    [inserir,9,90,2],
    ['update atividades set duracao=20,distancia_km=2',2,20,1],
    ['delete from atividades',0,0,0]]) {
    const antes=await estado();
    await db.exec(`begin;set local role service_role;${sql};`);
    await esperar(km,min,sessoes);
    await db.exec('rollback;');
    assert.deepEqual(await estado(),antes);
   }
   // Erro posterior ao recálculo: a instrução também reverte metas, sessão e XP.
   await db.exec(`create function public.falhar_depois_teste() returns trigger language plpgsql as
    $$begin raise exception 'falha posterior de teste';end$$;
    create trigger zzzz_falhar_depois_teste after insert or update or delete on atividades
    for each row execute function public.falhar_depois_teste();`);
   for(const sql of [inserir,'update atividades set duracao=20,distancia_km=2','delete from atividades']) {
    const antes=await estado();
    await db.exec('set role service_role;');
    await assert.rejects(db.exec(sql),/falha posterior de teste/);
    await db.exec('reset role;');
    assert.deepEqual(await estado(),antes);
   }
   await db.exec('drop trigger zzzz_falhar_depois_teste on atividades;drop function public.falhar_depois_teste();');
   await db.exec('set role service_role;delete from atividades;reset role;');
   await esperar(0,0,0);
   await db.exec('select lifes_private.exigir_backend_privado();');
   console.log(`OK ${tipo}: INSERT/UPDATE/DELETE, acumulados das três métricas, rollback explícito e rollback por erro posterior.`);
  } finally {await db.close();}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
