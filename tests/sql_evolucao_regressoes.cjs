/* Fixtures exclusivamente no PGlite descartável de sql_evolucao.cjs. */
const assert=require('node:assert/strict');
exports.preparar=async exec=>{
 await exec(`insert into usuarios(id_usuario,nome,email,senha_hash) values(900,'Regressão','regressao@local','hash');
 insert into atividades(id_atividade,id_usuario,tipo_exercicio,duracao,data_registro)
 values(900,900,'Yoga',10,'2020-03-01');
 alter table atividades disable trigger lifes_xp_atividade;
 insert into atividades(id_atividade,id_usuario,tipo_exercicio,duracao,data_registro)
 values(901,900,'Yoga',10,'2020-03-01');
 alter table atividades enable trigger lifes_xp_atividade;
 insert into atividades(id_atividade,id_usuario,tipo_exercicio,duracao,data_registro)
 values(902,900,'Yoga',10,'2019-01-01');
 -- Importação histórica simulada; apenas fixture local anterior à migração.
 alter table recompensas_xp disable trigger lifes_livro_imutavel;
 update recompensas_xp set xp=50 where id_usuario=900 and chave_evento='atividade:902';
 alter table recompensas_xp enable trigger lifes_livro_imutavel;
 insert into metas(id_meta,id_usuario,descricao,prazo,progresso) values
 (900,900,'Legada premiada','2020-03-31',0),
 (901,900,'Legada 100 sem lançamento','2020-03-31',100),
 (902,900,'Legada incompleta','2020-03-31',0);
 update metas set progresso=100 where id_meta=900;`);
};
exports.verificar=async(db,exec,modoDate,ler)=>{
 const one=async sql=>(await db.query(sql)).rows[0];
 const saldo=async evento=>Number((await one(`select coalesce(lifes_private.saldo_atividade(900,'${evento}'),0) n`)).n);
 const premio=async id=>Number((await one(`select count(*) n from recompensas_xp where id_usuario=900 and chave_evento='meta:${id}'`)).n);
 await assert.rejects(exec("set role service_role;update metas set metrica='minutos',alvo=0,inicio='2020-03-01',progresso=100 where id_meta=902;"),/Objetivo automático inválido/);
 await exec('reset role;');
 assert.equal((await one('select metrica from metas where id_meta=902')).metrica,null);
 assert.equal(Number((await one('select progresso from metas where id_meta=902')).progresso),0);
 assert.equal(await premio(902),0);
 // Conversão calcula os registros, ignora progresso/acumulado enviados e preserva IDs.
 await exec(`set role service_role;
 update metas set metrica='minutos',alvo=20,inicio='2020-03-01',modalidade='Yoga',progresso=1,acumulado=999 where id_meta in (900,901);
 update metas set metrica='minutos',alvo=200,inicio='2020-03-01',modalidade='Yoga',progresso=100,acumulado=999 where id_meta=902;
 reset role;`);
 assert.equal(Number((await one('select progresso from metas where id_meta=901')).progresso),100);
 assert.equal(Number((await one('select progresso from metas where id_meta=902')).progresso),10);
 assert.equal(await premio(900),1);assert.equal(await premio(901),1);assert.equal(await premio(902),0);
 for(const sql of ['update metas set metrica=null where id_meta=901','update metas set id_usuario=1 where id_meta=901','update metas set id_meta=9999 where id_meta=901']) {
  await assert.rejects(exec(`set role service_role;${sql};`));await exec('reset role;');
 }
 await exec(`set role service_role;update metas set progresso=100,acumulado=100000 where id_meta=902;
 update atividades set duracao=5 where id_atividade=900;reset role;`);
 assert.equal(Number((await one('select progresso from metas where id_meta=901')).progresso),75);
 assert.equal(await premio(901),1); // bônus histórico não sofre estorno
 await exec('set role service_role;update atividades set duracao=10 where id_atividade=900;delete from atividades where id_atividade in (900,901);reset role;');
 assert.equal(await premio(901),1);
 assert.equal(await saldo('atividade:900'),0);
 assert.equal(Number((await one("select xp from recompensas_xp where id_usuario=900 and chave_evento='estorno:atividade:900'")).xp),-20);
 assert.equal(Number((await one("select count(*) n from recompensas_xp where id_usuario=900 and chave_evento='estorno:atividade:901'")).n),0);
 assert.equal(Number((await one('select progresso from metas where id_meta=901')).progresso),0);
 assert.equal(Number((await one("select count(*) n from recompensas_xp where id_usuario=900 and chave_evento like 'estorno:meta:%'")).n),0);
 await exec("set role service_role;update atividades set duracao=80 where id_atividade=902;delete from atividades where id_atividade=902;reset role;");
 assert.equal(Number((await one("select xp from recompensas_xp where id_usuario=900 and chave_evento='estorno:atividade:902'")).xp),-50);
 await exec("set role service_role;insert into atividades(id_atividade,id_usuario,tipo_exercicio,duracao) values(902,900,'Yoga',20);reset role;");
 assert.equal(Number((await one('select count(*) n from atividades where id_atividade=902')).n),0);
 await exec("set role service_role;insert into atividades(id_atividade,id_usuario,tipo_exercicio,duracao,data_registro) values(905,900,'Yoga',20,'2020-03-01 12:00:00');reset role;");
 assert.equal(Number((await one('select progresso from metas where id_meta=901')).progresso),100);
 assert.equal(await premio(900),1);assert.equal(await premio(901),1);
 await exec('set role service_role;delete from atividades where id_atividade=905;reset role;');
 // Várias revisões, redução/aumento, repetição sem mudança, exclusão e retry.
 const uuid='90000000-0000-4000-8000-000000000001',evento='atividade:'+uuid;
 await exec(`set role service_role;insert into atividades(id_usuario,tipo_exercicio,duracao,distancia_km,data_registro,chave_registro)
 values(900,'Corrida',30,3,'2020-03-01','${uuid}');reset role;`);
 for(const [min,km,esperado] of [[25,5,50],[60,6,90],[10,1,15],[30,3,45],[30,3,45]]) {
  await exec(`set role service_role;update atividades set duracao=${min},distancia_km=${km},xp_atual=999,xp_revisao=999 where chave_registro='${uuid}';reset role;`);
  assert.equal(await saldo(evento),esperado);
 }
 assert.equal(Number((await one(`select xp_revisao from atividades where chave_registro='${uuid}'`)).xp_revisao),4);
 // Inconsistência simulada por administrador nunca é encoberta por edição/exclusão.
 for(const comando of [`update atividades set duracao=35 where chave_registro='${uuid}'`,`delete from atividades where chave_registro='${uuid}'`]) {
  await exec(`begin;alter table recompensas_xp disable trigger lifes_livro_imutavel;
   update recompensas_xp set xp=xp+1 where id_usuario=900 and chave_evento='${evento}';`);
  await assert.rejects(exec(`set local role service_role;${comando};`),/Saldo da atividade divergente/);
  assert.equal(await saldo(evento),45); // rollback restaura inclusive fixture e trigger
 }
 await exec(`set role service_role;delete from atividades where chave_registro='${uuid}';
 delete from atividades where chave_registro='${uuid}';
 insert into atividades(id_usuario,tipo_exercicio,duracao,chave_registro) values(900,'Yoga',30,'${uuid}');reset role;`);
 assert.equal(await saldo(evento),0);
 assert.equal(Number((await one(`select count(*) n from atividades where chave_registro='${uuid}'`)).n),0);
 // Instrumenta quantas metas sofreram UPDATE, sem acrescentar regras ao aplicativo.
 await exec(`create temporary table metas_tocadas(id bigint);
 create function public.observar_meta_teste() returns trigger language plpgsql as $$begin insert into pg_temp.metas_tocadas values(new.id_meta);return new;end$$;
 create trigger observar_meta_teste after update on metas for each row execute function public.observar_meta_teste();
 insert into metas(id_meta,id_usuario,descricao,metrica,alvo,modalidade,inicio,prazo) values
 (910,900,'Minutos corrida','minutos',100,'Corrida','2020-03-01','2020-03-31'),
 (911,900,'Km corrida','km',100,'Corrida','2020-03-01','2020-03-31'),
 (912,900,'Sessões corrida','sessoes',100,'Corrida','2020-03-01','2020-03-31'),
 (913,900,'Outro período','minutos',100,'Corrida','2021-01-01','2021-01-31');
 insert into agenda(id_agenda,id_usuario,horario) values(910,900,'2020-03-01 12:00:00');
 insert into atividades(id_atividade,id_usuario,tipo_exercicio,duracao,distancia_km,data_registro,id_agenda) values(910,900,'Corrida',30,3,'2020-03-01 12:00:00',910);
 truncate metas_tocadas;`);
 const tocadas=async()=> (await db.query('select distinct id from metas_tocadas order by id')).rows.map(r=>Number(r.id));
 await exec('update atividades set duracao=40 where id_atividade=910;');assert.deepEqual(await tocadas(),[910]);
 await exec('truncate metas_tocadas;update atividades set distancia_km=4 where id_atividade=910;');assert.deepEqual(await tocadas(),[911]);
 await exec('truncate metas_tocadas;update atividades set frequencia=2,xp_atual=999 where id_atividade=910;');assert.deepEqual(await tocadas(),[]);
 await exec('delete from agenda where id_agenda=910;');assert.deepEqual(await tocadas(),[]);
 assert.equal((await one('select id_agenda from atividades where id_atividade=910')).id_agenda,null);
 await exec("update atividades set data_registro='2020-03-02 12:00:00' where id_atividade=910;");assert.deepEqual(await tocadas(),[]);
 await exec("update atividades set data_registro='2021-01-02 12:00:00' where id_atividade=910;");assert.deepEqual(await tocadas(),[910,911,912,913]);
 await exec('drop trigger observar_meta_teste on metas;drop function public.observar_meta_teste();'); // fixture local
 // Menor alvo aceito e grande acumulado não estouram integer antes do limite 100.
 await assert.rejects(db.query('select least(100,floor(22000::numeric*100/0.001)::integer)'),e=>e.code==='22003');
 await exec(`insert into atividades(id_usuario,tipo_exercicio,duracao,distancia_km,data_registro)
 select 900,'Ciclismo',1440,1000,'2020-04-01 12:00:00' from generate_series(1,22);
 insert into metas(id_usuario,descricao,metrica,alvo,inicio,prazo) values(900,'Alvo mínimo','km',0.001,'2020-04-01','2020-04-01');`);
 assert.equal(Number((await one("select progresso from metas where descricao='Alvo mínimo'")).progresso),100);
 // Gate não remove gatilhos desconhecidos nem confirma migração parcial.
 await exec(`create function public.extra_teste() returns trigger language plpgsql as $$begin return new;end$$;
 create trigger extra_teste after update on atividades for each row execute function public.extra_teste();`);
 await assert.rejects(exec(ler('migrations/evolucao_perfil_metas_xp_niveis.sql')),/Trigger requer revisão/);
 assert.equal(Number((await one("select count(*) n from pg_trigger where tgname='extra_teste'")).n),1);
 await exec('drop trigger extra_teste on atividades;drop function public.extra_teste();');
 await exec('alter table usuario_conquista disable trigger lifes_xp_conquista;');
 await assert.rejects(exec(ler('migrations/evolucao_perfil_metas_xp_niveis.sql')),/Trigger requer revisão/);
 await exec('alter table usuario_conquista enable trigger lifes_xp_conquista;');
 await exec('begin;drop trigger lifes_livro_sem_truncate on recompensas_xp;');
 // O BEGIN da migração já fica na transação de fixture, revertida no erro.
 await assert.rejects(exec(ler('migrations/evolucao_perfil_metas_xp_niveis.sql')),/Trigger obrigatório ausente/);
 assert.equal(Number((await one("select count(*) n from pg_trigger where tgname='lifes_livro_sem_truncate'")).n),1);
 await exec('begin;drop index atividade_registro_uidx;');
 await assert.rejects(exec(ler('migrations/evolucao_perfil_metas_xp_niveis.sql')),/Unicidade obrigatória incompatível/);
 assert.equal((await one("select to_regclass('public.atividade_registro_uidx') is not null ok")).ok,true);
 for(const papel of ['anon','authenticated','service_role']) {
  assert.equal((await db.query("select has_function_privilege($1,'lifes_private.saldo_atividade(bigint,text)','EXECUTE') p",[papel])).rows[0].p,false);
 }
 console.log('OK regressões: conversão, marcos históricos, múltiplos ajustes, estorno, divergências e recálculo seletivo.');
};
