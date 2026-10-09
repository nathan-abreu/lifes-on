-- EXCLUSIVAMENTE LEITURA. Executar como administrador para ver todos os metadados.
-- Funciona antes/depois das migrações, inclusive quando tabelas/roles estão ausentes.
-- Não consulta registros pessoais. Definições de funções legadas podem conter
-- segredos embutidos: revisar/redigir a saída antes de compartilhá-la.
begin transaction read only;
select current_user, session_user, version(), current_setting('TimeZone') as timezone,
 current_setting('transaction_read_only') as somente_leitura;

-- Objetos obrigatórios e proprietários (NULL = ausente).
with esperadas(nome) as (values ('usuarios'),('atividades'),('metas'),('agenda'),
 ('conquistas'),('usuario_conquista'),('alertas'),('dicas'),('recompensas_xp'))
select e.nome,c.oid::regclass as objeto,c.relkind,pg_get_userbyid(c.relowner) as dono,
 c.relrowsecurity as rls,c.relforcerowsecurity as force_rls,c.relacl
from esperadas e left join pg_class c on c.oid=to_regclass('public.'||e.nome)
order by e.nome;

-- Tipos exatos, domínios, NOT NULL, defaults e identidades.
select c.relname as tabela,a.attname as coluna,format_type(a.atttypid,a.atttypmod) as tipo,
 a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid) as valor_padrao,a.attacl
from pg_attribute a join pg_class c on c.oid=a.attrelid
join pg_namespace n on n.oid=c.relnamespace
left join pg_attrdef d on d.adrelid=a.attrelid and d.adnum=a.attnum
where n.nspname='public' and a.attnum>0 and not a.attisdropped
and c.relname in ('usuarios','atividades','metas','agenda','conquistas','usuario_conquista','alertas','dicas','recompensas_xp')
order by c.relname,a.attnum;

-- Checklist de colunas novas, com tipo esperado. Não supor que IF NOT EXISTS corrige tipos.
with esperadas(tabela,coluna,tipo) as (values
 ('atividades','chave_registro','uuid'),('atividades','id_agenda','bigint'),
 ('agenda','realizado_em','timestamp with time zone'),('agenda','modalidade','text'),
 ('dicas','categoria','text'),('dicas','fonte','text'),
 ('recompensas_xp','id_recompensa','bigint'),('recompensas_xp','id_usuario','bigint'),
 ('recompensas_xp','chave_evento','text'),('recompensas_xp','xp','integer'),
 ('recompensas_xp','motivo','text'),('recompensas_xp','criado_em','timestamp with time zone'))
select e.*,format_type(a.atttypid,a.atttypmod) as tipo_real,
 case when a.attname is null then 'PENDENTE' when format_type(a.atttypid,a.atttypmod)=e.tipo then 'OK' else 'REVISAR TIPO' end as estado
from esperadas e left join pg_attribute a on a.attrelid=to_regclass('public.'||e.tabela)
 and a.attname=e.coluna and not a.attisdropped;

select c.conrelid::regclass as tabela,c.conname,c.contype,c.convalidated,
 c.condeferrable,c.condeferred,pg_get_constraintdef(c.oid) as definicao
from pg_constraint c join pg_namespace n on n.oid=c.connamespace
where n.nspname='public' order by c.conrelid::regclass::text,c.conname;
select t.oid::regclass as tabela,i.indexrelid::regclass as indice,i.indisunique,
 i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid) as definicao
from pg_index i join pg_class t on t.oid=i.indrelid
join pg_namespace n on n.oid=t.relnamespace where n.nspname='public';
select t.tgrelid::regclass as tabela,t.tgname,t.tgenabled,t.tgfoid::regprocedure as funcao,
 pg_get_triggerdef(t.oid) as definicao from pg_trigger t
join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and not t.tgisinternal;

-- Funções/RPCs: dono, assinatura, SECURITY DEFINER, search_path, ACL e código.
-- Incluir todas as funções públicas: uma RPC antiga pode contornar ACL de tabela.
select p.oid::regprocedure as funcao,pg_get_userbyid(p.proowner) as dono,
 p.prosecdef,p.proconfig,p.proacl,pg_get_functiondef(p.oid) as definicao
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname in ('public','lifes_private') and p.prokind in ('f','p');
select tablename,policyname,permissive,roles,cmd,qual,with_check
from pg_policies where schemaname='public';

-- Papéis ausentes e herança efetiva. BYPASSRLS não equivale a privilégio de tabela.
with esperados(nome) as (values ('anon'),('authenticated'),('service_role'),('postgres'))
select e.nome,r.rolsuper,r.rolinherit,r.rolcreaterole,r.rolcanlogin,r.rolbypassrls
from esperados e left join pg_roles r on r.rolname=e.nome;
select pai.rolname as papel,filho.rolname as membro,m.admin_option
from pg_auth_members m join pg_roles pai on pai.oid=m.roleid join pg_roles filho on filho.oid=m.member;
select r.rolname,n.nspname,pg_get_userbyid(n.nspowner) as dono,n.nspacl,
 has_schema_privilege(r.oid,n.oid,'USAGE') as uso,
 has_schema_privilege(r.oid,n.oid,'CREATE') as criar
from pg_roles r cross join pg_namespace n
where r.rolname in ('anon','authenticated','service_role') and n.nspname in ('public','lifes_private');
select r.rolname,c.oid::regclass as objeto,c.relkind,
 has_table_privilege(r.oid,c.oid,'SELECT') as ler,
 has_any_column_privilege(r.oid,c.oid,'SELECT') as ler_alguma_coluna,
 has_table_privilege(r.oid,c.oid,'INSERT') as inserir,
 has_any_column_privilege(r.oid,c.oid,'INSERT') as inserir_alguma_coluna,
 has_table_privilege(r.oid,c.oid,'UPDATE') as atualizar,
 has_any_column_privilege(r.oid,c.oid,'UPDATE') as atualizar_alguma_coluna,
 has_table_privilege(r.oid,c.oid,'DELETE') as excluir,
 has_table_privilege(r.oid,c.oid,'TRUNCATE') as truncar,
 has_table_privilege(r.oid,c.oid,'TRIGGER') as criar_trigger,
 has_table_privilege(r.oid,c.oid,'REFERENCES') as referenciar,
 has_any_column_privilege(r.oid,c.oid,'REFERENCES') as referenciar_alguma_coluna
from pg_roles r cross join pg_class c join pg_namespace n on n.oid=c.relnamespace
where r.rolname in ('anon','authenticated','service_role') and n.nspname='public'
 and c.relkind in ('r','p','v','m','f') order by r.rolname,c.relname;

-- ACLs explícitas PUBLIC e grants por coluna são diferentes das ACLs de tabela.
select c.oid::regclass as objeto,coalesce(r.rolname,'PUBLIC') as destinatario,
 acl.privilege_type,acl.is_grantable
from pg_class c join pg_namespace n on n.oid=c.relnamespace
cross join lateral aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) acl
left join pg_roles r on r.oid=acl.grantee
where n.nspname='public' and c.relkind in ('r','p','v','m');
select c.oid::regclass as tabela,a.attname,coalesce(r.rolname,'PUBLIC') as destinatario,
 acl.privilege_type,acl.is_grantable
from pg_attribute a join pg_class c on c.oid=a.attrelid join pg_namespace n on n.oid=c.relnamespace
cross join lateral aclexplode(a.attacl) acl left join pg_roles r on r.oid=acl.grantee
where n.nspname='public' and a.attnum>0 and not a.attisdropped;
select r.rolname,c.oid::regclass as sequencia,pg_get_userbyid(c.relowner) as dono,c.relacl,
 has_sequence_privilege(r.oid,c.oid,'USAGE') as uso,
 has_sequence_privilege(r.oid,c.oid,'SELECT') as ler,
 has_sequence_privilege(r.oid,c.oid,'UPDATE') as alterar
from pg_roles r cross join pg_class c join pg_namespace n on n.oid=c.relnamespace
where r.rolname in ('anon','authenticated','service_role') and c.relkind='S' and n.nspname='public';
select r.rolname,p.oid::regprocedure as funcao,p.prosecdef,
 has_function_privilege(r.oid,p.oid,'EXECUTE') as executar
from pg_roles r cross join pg_proc p join pg_namespace n on n.oid=p.pronamespace
where r.rolname in ('anon','authenticated','service_role')
 and n.nspname in ('public','lifes_private') and p.prokind in ('f','p');
select pg_get_userbyid(d.defaclrole) as dono,n.nspname,d.defaclobjtype,d.defaclacl
from pg_default_acl d left join pg_namespace n on n.oid=d.defaclnamespace;
select c.oid::regclass as view,c.reloptions,pg_get_viewdef(c.oid) as definicao
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relkind in ('v','m');

-- Apenas contagens e catálogo editorial, nunca dados pessoais.
-- DO abaixo executa somente SELECT, protegido por TRANSACTION READ ONLY.
do $$
declare r record; quantidade bigint;
begin
 if exists(select 1 from pg_attribute where attrelid=to_regclass('public.conquistas') and attname='nome' and not attisdropped) then
   for r in execute 'select lower(btrim(nome)) as nome,count(*) as quantidade from public.conquistas group by lower(btrim(nome)) order by 1' loop
     raise notice 'Catálogo: % / % registro(s)',r.nome,r.quantidade;
   end loop;
 end if;
 if (select count(*) from pg_attribute where attrelid=to_regclass('public.usuario_conquista') and attname in ('id_usuario','id_conquista') and not attisdropped)=2 then
   execute 'select count(*) from (select id_usuario,id_conquista from public.usuario_conquista group by 1,2 having count(*)>1) d' into quantidade;
   raise notice 'Associações duplicadas: %',quantidade;
 end if;
 if (select count(*) from pg_attribute where attrelid=to_regclass('public.atividades') and attname in ('id_usuario','chave_registro') and not attisdropped)=2 then
   execute 'select count(*) from (select id_usuario,chave_registro from public.atividades where chave_registro is not null group by 1,2 having count(*)>1) d' into quantidade;
   raise notice 'UUIDs duplicados por usuário: %',quantidade;
 end if;
 if (select count(*) from pg_attribute where attrelid=to_regclass('public.atividades') and attname in ('id_usuario','id_agenda') and not attisdropped)=2 then
   execute 'select count(*) from (select id_usuario,id_agenda from public.atividades where id_agenda is not null group by 1,2 having count(*)>1) d' into quantidade;
   raise notice 'Agendas duplicadas por usuário: %',quantidade;
 end if;
 if (select count(*) from pg_attribute where attrelid=to_regclass('public.recompensas_xp') and attname in ('id_usuario','chave_evento') and not attisdropped)=2 then
   execute 'select count(*) from (select id_usuario,chave_evento from public.recompensas_xp group by 1,2 having count(*)>1) d' into quantidade;
   raise notice 'Eventos XP duplicados: %',quantidade;
 end if;
 if (select count(*) from pg_attribute where attrelid=to_regclass('public.recompensas_xp') and attname in ('id_usuario','chave_evento','xp') and not attisdropped)=3 then
   execute $sql$select count(*) from public.recompensas_xp e where e.xp=-20
     and (e.chave_evento not like 'estorno:atividade:%' or not exists
       (select 1 from public.recompensas_xp o where o.id_usuario=e.id_usuario
        and o.chave_evento=substr(e.chave_evento,9) and o.xp=20))$sql$ into quantidade;
   raise notice 'Estornos sem lançamento original compatível (esperado 0): %',quantidade;
   execute $sql$select count(*) from public.recompensas_xp where xp is null or not (
     (chave_evento like 'atividade:%' and xp=20) or
     (chave_evento like 'estorno:atividade:%' and xp=-20) or
     (chave_evento like 'meta:%' and xp=50) or
     (chave_evento like 'conquista:%' and xp=30) or
     (chave_evento='sequencia:primeiros-7' and xp=50))$sql$ into quantidade;
   raise notice 'Eventos XP fora das regras conhecidas (revisar, não apagar): %',quantidade;
 end if;
end $$;
commit;
