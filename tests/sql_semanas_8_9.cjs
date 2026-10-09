/* Executa SQL real em PostgreSQL WASM local; não acessa Supabase.
 * Instalar @electric-sql/pglite fora do projeto e definir PGLITE_MODULE.
 * node tests/sql_semanas_8_9.cjs
 */
const {PGlite}=require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs=require('fs'), assert=require('node:assert/strict');
(async()=>{
 const db=new PGlite();
 try {
 await db.exec('create role anon; create role authenticated; create role service_role bypassrls;');
 await db.exec(fs.readFileSync('schema.sql','utf8'));
 const sql=fs.readFileSync('migrations/semanas_8_9.sql','utf8').replace(/^\uFEFF/,'');
 await db.exec(sql); await db.exec(sql);
 const finalizacao=fs.readFileSync('migrations/finalizacao_premium.sql','utf8');
 await db.exec(finalizacao);await db.exec(finalizacao);
 assert.equal((await db.query('select count(*)::integer as n from conquistas')).rows[0].n,14);
 await db.exec("insert into usuarios(nome,email,senha_hash) values('Teste 1','1@test','hash'),('Teste 2','2@test','hash');");
 const total=async id=>(await db.query('select coalesce(sum(xp),0)::integer as total from recompensas_xp where id_usuario=$1',[id])).rows[0].total;
 const count=async tabela=>(await db.query('select count(*)::integer as n from '+tabela)).rows[0].n;
 const chave='00000000-0000-4000-8000-000000000001';
 await db.query("insert into agenda(id_usuario,titulo,horario) values(1,'Treino',now())");
 const inserir=async(k=chave,u=1,agenda=1)=>db.query('insert into atividades(id_usuario,tipo_exercicio,duracao,frequencia,chave_registro,id_agenda) values($1,\'Corrida\',30,1,$2,$3) returning *',[u,k,agenda]);
 await inserir();assert.equal(await total(1),20);
 assert.equal((await db.query('select realizado_em from agenda')).rows[0].realizado_em!==null,true);
 assert.equal((await inserir()).rows.length,0);
 assert.equal((await inserir('00000000-0000-4000-8000-000000000002')).rows.length,0);
 assert.equal(await count('atividades'),1);
 await assert.rejects(inserir('00000000-0000-4000-8000-000000000003',2));
 assert.equal(await total(2),0);
 await db.exec('update atividades set duracao=40; delete from atividades;');
 assert.equal(await total(1),0);assert.equal((await inserir()).rows.length,0);
 await db.exec("insert into metas(id_usuario,descricao,prazo) values(1,'Meta',current_date); update metas set progresso=100; update metas set progresso=0; update metas set progresso=100;");
 assert.equal(await total(1),50);
 await db.exec('insert into usuario_conquista(id_usuario,id_conquista) values(1,1) on conflict do nothing; insert into usuario_conquista(id_usuario,id_conquista) values(1,1) on conflict do nothing;');
 assert.equal(await total(1),80);
 // Alterar a data pode atingir o marco de sequência sem duplicar os 20 XP básicos.
 await db.exec("insert into usuarios(nome,email,senha_hash) values('Teste edição','3@test','hash');");
 for(const i of [0,1,2,3,4,5,7]) await db.query("insert into atividades(id_usuario,tipo_exercicio,duracao,frequencia,data_registro) values(3,'Yoga',10,null,now()-($1::integer * interval '1 day'))",[i]);
 assert.equal(await total(3),140);
 await db.exec("update atividades set data_registro=now()-interval '6 days' where id_usuario=3 and data_registro < now()-interval '6 days';");
 assert.equal(await total(3),190);
 await db.exec('update atividades set duracao=20 where id_usuario=3;');
 assert.equal(await total(3),190);
 await db.exec('delete from atividades where id_usuario=3;');
 assert.equal(await total(3),50);
 // Sete dias locais históricos, uma recompensa de sequência, independentemente da ordem.
 for(let i=0;i<8;i++) await db.query("insert into atividades(id_usuario,tipo_exercicio,duracao,frequencia,data_registro,chave_registro) values(2,'Yoga',10,1,now()-($1::integer * interval '1 day'),$2)",[i,`00000000-0000-4000-8000-${String(i+10).padStart(12,'0')}`]);
 assert.equal(await total(2),210);
 for(const query of ["insert into recompensas_xp(id_usuario,chave_evento,motivo,xp) values(1,'falso','Falso',50)", 'update recompensas_xp set xp=50', 'delete from recompensas_xp', 'truncate recompensas_xp']) await assert.rejects(db.exec(query));
 // Falha na recompensa reverte atividade e conclusão da agenda juntas.
 await db.exec("insert into agenda(id_usuario,titulo,horario) values(1,'Falha',now()); create function public.falha_teste() returns trigger language plpgsql as $$ begin raise exception 'Conexão simulada na transação'; end $$; create trigger falha before insert on recompensas_xp for each row execute function falha_teste();");
 const antes=await count('atividades');
 await assert.rejects(inserir('00000000-0000-4000-8000-000000000099',1,2));
 assert.equal(await count('atividades'),antes);
 assert.equal((await db.query('select realizado_em from agenda where id_agenda=2')).rows[0].realizado_em,null);
 await db.exec('drop trigger falha on recompensas_xp;');
 await assert.rejects(db.exec("insert into atividades(id_usuario,tipo_exercicio,duracao,frequencia) values(1,'Inválido',20,1)"));
 await db.exec("insert into atividades(id_usuario,tipo_exercicio,duracao,frequencia,chave_registro) values(1,'Artes Marciais',45,null,'00000000-0000-4000-8000-000000000199');");
 assert.equal(await total(1),100);
 await assert.rejects(db.exec("update atividades set id_usuario=2 where chave_registro='00000000-0000-4000-8000-000000000199'"));
 await db.exec("update atividades set duracao=60 where chave_registro='00000000-0000-4000-8000-000000000199';");
 assert.equal(await total(1),100);
 await db.exec("delete from atividades where chave_registro='00000000-0000-4000-8000-000000000199';");
 assert.equal(await total(1),80);
 await db.exec("delete from atividades where chave_registro='00000000-0000-4000-8000-000000000199';");
 assert.equal(await total(1),80);
 // Timestamp legado é UTC, mesmo se a sessão PostgreSQL usar outro fuso.
 await db.exec("alter table atividades alter column data_registro type timestamp without time zone using data_registro at time zone 'UTC'; set timezone='America/Los_Angeles';");
 // Reinstala funções sobre o tipo legado, como numa migração real; invalida planos
 // de trigger em cache nesta conexão que antes usavam o tipo timestamptz.
 await db.exec(finalizacao);
 await db.exec("insert into usuarios(nome,email,senha_hash) values('Legado','4@test','hash');");
 for(let i=0;i<7;i++) await db.query("insert into atividades(id_usuario,tipo_exercicio,duracao,data_registro) values(4,'Yoga',10,(now() at time zone 'UTC') - interval '1 minute' - ($1::integer * interval '1 day'))",[i]);
 assert.equal(await total(4),190);
 await assert.rejects(db.exec("insert into atividades(id_usuario,tipo_exercicio,duracao,data_registro) values(4,'Yoga',10,(now() at time zone 'UTC') + interval '1 hour')"),/Atividade inválida/);
 console.log('SQL PostgreSQL local OK: migração repetível, XP, agenda, retries, exclusão, metas, conquistas, sequência/fuso legado, isolamento do vínculo, livro protegido e rollback.');
 } finally { await db.close(); }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
