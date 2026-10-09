-- SOMENTE LEITURA. Antes/depois da evolução. Nenhum registro pessoal é listado.
-- Complementa diagnostico_finalizacao.sql. Execute como postgres.
begin transaction read only;
select version(), current_user, current_setting('transaction_read_only') as somente_leitura;
with campos(tabela,coluna,tipo) as (values
 ('usuarios','foto_path','text'),('usuarios','perfil_versao','bigint'),
 ('atividades','distancia_km','numeric'),('atividades','xp_versao','integer'),
 ('atividades','xp_atual','integer'),('atividades','xp_revisao','bigint'),
 ('atividades','xp_transacao','bigint'),
 ('metas','metrica','text'),('metas','modalidade','text'),('metas','alvo','numeric'),
 ('metas','inicio','date'),('metas','acumulado','numeric'),('recompensas_xp','transacao','bigint'))
select e.*,format_type(a.atttypid,a.atttypmod) as tipo_real,a.attnotnull,a.attacl,
 pg_get_expr(d.adbin,d.adrelid) as valor_padrao
from campos e left join pg_attribute a on a.attrelid=to_regclass('public.'||e.tabela)
 and a.attname=e.coluna and not a.attisdropped
left join pg_attrdef d on d.adrelid=a.attrelid and d.adnum=a.attnum order by e.tabela,e.coluna;

select c.conrelid::regclass as tabela,c.conname,c.convalidated,pg_get_constraintdef(c.oid)
from pg_constraint c where c.conrelid in ('public.atividades'::regclass,'public.metas'::regclass,'public.recompensas_xp'::regclass);
select i.indexrelid::regclass as indice,i.indisunique,i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid)
from pg_index i where i.indrelid in ('public.atividades'::regclass,'public.metas'::regclass,'public.recompensas_xp'::regclass);
select t.tgrelid::regclass as tabela,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid)
from pg_trigger t where not t.tgisinternal and t.tgrelid in
 ('public.atividades'::regclass,'public.metas'::regclass,'public.usuario_conquista'::regclass,'public.recompensas_xp'::regclass);
select p.oid::regprocedure as funcao,pg_get_userbyid(p.proowner) as dono,p.prosecdef,p.proconfig,p.proacl,
 md5(pg_get_functiondef(p.oid)) as versao_definicao
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname='lifes_private' or (n.nspname='public' and p.proname like 'lifes\_%' escape '\');

-- Apenas nome/foto/versão podem receber UPDATE do servidor em usuarios.
select r.rolname,a.attname,has_column_privilege(r.oid,a.attrelid,a.attnum,'UPDATE') as pode_editar
from pg_roles r cross join pg_attribute a
where r.rolname in ('anon','authenticated','service_role') and a.attrelid='public.usuarios'::regclass
 and a.attnum>0 and not a.attisdropped order by r.rolname,a.attnum;
select r.rolname,c.relname,has_table_privilege(r.oid,c.oid,'SELECT') as leitura,
 has_table_privilege(r.oid,c.oid,'INSERT') as inserir,has_table_privilege(r.oid,c.oid,'UPDATE') as editar,
 has_any_column_privilege(r.oid,c.oid,'INSERT') as inserir_colunas,
 has_any_column_privilege(r.oid,c.oid,'UPDATE') as editar_colunas,
 has_table_privilege(r.oid,c.oid,'DELETE') as excluir,has_table_privilege(r.oid,c.oid,'TRUNCATE') as truncar
from pg_roles r cross join pg_class c where r.rolname in ('anon','authenticated','service_role')
 and c.oid='public.recompensas_xp'::regclass;

-- Storage: revisar policies globais, RLS e política restritiva do bucket.
select c.oid::regclass,c.relrowsecurity,c.relforcerowsecurity
from pg_class c where c.oid=to_regclass('storage.objects');
select schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check
from pg_policies where schemaname='storage' and tablename in ('objects','buckets');
-- Catálogo de buckets, sem listar arquivos. Supabase tem storage.buckets.
select id,name,public,file_size_limit,allowed_mime_types from storage.buckets where id='lifes-perfis';
select lifes_private.exigir_backend_privado();
commit;
