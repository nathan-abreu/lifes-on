-- Execute no SQL Editor para conferir o banco real SEM modificá-lo.
begin transaction read only;

select table_name, column_name, data_type, is_nullable, column_default, is_identity
from information_schema.columns
where table_schema = 'public'
  and table_name in ('usuarios', 'atividades', 'metas', 'agenda', 'conquistas', 'usuario_conquista')
order by table_name, ordinal_position;

-- Privilégios de tabela NÃO substituem policies: conferir ambos os resultados.
select c.relname as tabela, c.relrowsecurity as rls, c.relforcerowsecurity as force_rls,
       has_table_privilege('anon', c.oid, 'SELECT') as anon_select,
       has_table_privilege('anon', c.oid, 'INSERT') as anon_insert,
       has_table_privilege('anon', c.oid, 'UPDATE') as anon_update,
       has_table_privilege('anon', c.oid, 'DELETE') as anon_delete
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in ('usuarios', 'atividades', 'metas', 'agenda', 'conquistas', 'usuario_conquista');

select tablename, policyname, roles, cmd, qual, with_check
from pg_policies
where schemaname = 'public'
  and tablename in ('usuarios', 'atividades', 'metas', 'agenda', 'conquistas', 'usuario_conquista');

select c.conrelid::regclass as tabela, c.conname, pg_get_constraintdef(c.oid) as definicao
from pg_constraint c
where c.conrelid in ('public.usuarios'::regclass, 'public.atividades'::regclass,
    'public.metas'::regclass, 'public.agenda'::regclass, 'public.conquistas'::regclass,
    'public.usuario_conquista'::regclass);

select tablename, indexname, indexdef from pg_indexes
where schemaname = 'public' and tablename in ('conquistas', 'usuario_conquista');

select count(*) as pares_duplicados from (
    select id_usuario, id_conquista from public.usuario_conquista
    group by id_usuario, id_conquista having count(*) > 1
) as duplicados;

-- Sequências: consulta não chama nextval e não altera seus contadores.
select tabela, sequencia,
       case when sequencia is not null then has_sequence_privilege('anon', sequencia, 'USAGE') end as anon_usage
from (
    select tabela, pg_get_serial_sequence('public.' || tabela, chave) as sequencia
    from (values ('usuarios', 'id_usuario'), ('atividades', 'id_atividade'),
        ('metas', 'id_meta'), ('agenda', 'id_agenda'), ('conquistas', 'id_conquista')) as t(tabela, chave)
) as sequencias;

commit;
