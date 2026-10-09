-- PROPOSTA LOCAL: exige revisão/autorização específica de permissões.
-- Executar como postgres, em manutenção, APÓS configurar o Flask com chave
-- exclusiva de servidor (sb_secret_... ou JWT service_role). Ambas usam o papel
-- service_role. Com anon/sb_publishable_... o Flask deixará de funcionar.
-- Não cria papéis, não altera RLS/policies, não apaga dados.
begin;
do $$
begin
 if current_user <> 'postgres' then raise exception 'Execute como postgres'; end if;
 if (select count(*) from pg_roles where rolname in ('anon','authenticated','service_role'))<>3 then
   raise exception 'Papéis API obrigatórios ausentes';
 end if;
 if not exists(select 1 from pg_roles where rolname='anon')
 or not exists(select 1 from pg_roles where rolname='authenticated')
 or not exists(select 1 from pg_roles where rolname='service_role' and rolbypassrls) then
   raise exception 'Papéis Supabase esperados ausentes/incompatíveis';
 end if;
end $$;

-- Impede criação/substituição de objetos no schema utilizado pelos triggers.
revoke create on schema public from public, anon, authenticated, service_role;
grant usage on schema public to service_role;
create schema if not exists lifes_private authorization postgres;
revoke all on schema lifes_private from public, anon, authenticated, service_role;

-- Restrição somente às tabelas deste aplicativo; revisar outros consumidores.
-- Revogar a ACL de tabela não basta quando existem privilégios por coluna.
do $$
declare tabela text; coluna record; seq text; funcao record;
begin
 foreach tabela in array array['usuarios','atividades','metas','agenda',
   'conquistas','usuario_conquista','alertas','dicas','recompensas_xp'] loop
   if to_regclass('public.'||tabela) is null then
     if tabela='recompensas_xp' then continue; end if;
     raise exception 'Tabela obrigatória ausente: %',tabela;
   end if;
   execute format('revoke all on table public.%I from public, anon, authenticated, service_role',tabela);
   for coluna in select attname from pg_attribute
      where attrelid=to_regclass('public.'||tabela) and attnum>0 and not attisdropped loop
     execute format('revoke select (%1$I), insert (%1$I), update (%1$I), references (%1$I) on public.%2$I from public, anon, authenticated, service_role',coluna.attname,tabela);
   end loop;
   execute format('grant select on public.%I to service_role',tabela);
   if tabela='usuarios' then
     grant insert on public.usuarios to service_role;
   elsif tabela='usuario_conquista' then
     grant insert on public.usuario_conquista to service_role;
   elsif tabela in ('atividades','metas','agenda','alertas') then
     execute format('grant insert, update, delete on public.%I to service_role',tabela);
   end if;
   for seq in select pg_get_serial_sequence('public.'||tabela,a.attname)
       from pg_attribute a where a.attrelid=to_regclass('public.'||tabela)
       and a.attnum>0 and not a.attisdropped loop
     if seq is not null then
       execute format('revoke all on sequence %s from public, anon, authenticated, service_role',seq);
       if tabela in ('usuarios','atividades','metas','agenda','alertas') then
         execute format('grant usage, select on sequence %s to service_role',seq);
       end if;
     end if;
   end loop;
 end loop;
 for funcao in select p.oid::regprocedure as assinatura from pg_proc p
   join pg_namespace n on n.oid=p.pronamespace
   where n.nspname='public' and p.pronargs=0 and p.prorettype='trigger'::regtype
     and p.proname in ('lifes_validar_registro','lifes_premiar',
                       'lifes_proteger_livro','lifes_estornar_atividade') loop
   execute format('revoke all on function %s from public, anon, authenticated, service_role',funcao.assinatura);
 end loop;
end $$;

-- Gate compartilhado pelas duas migrações: verifica privilégios EFETIVOS,
-- incluindo herança e grants por coluna. Não altera heranças desconhecidas.
create or replace function lifes_private.exigir_backend_privado() returns void
language plpgsql security invoker set search_path=pg_catalog as $$
declare papel record; tabela record; privilegio text; seq text; objeto record;
begin
 if current_user <> 'postgres' then raise exception 'Execute como postgres'; end if;
 if (select count(*) from pg_roles where rolname in ('anon','authenticated','service_role'))<>3 then
   raise exception 'Papéis API obrigatórios ausentes';
 end if;
 if not exists(select 1 from pg_roles where rolname='service_role' and rolbypassrls)
    or not has_schema_privilege('service_role','public','USAGE') then
   raise exception 'service_role requer BYPASSRLS e USAGE no schema public';
 end if;
 for objeto in select nome from unnest(array['usuarios','atividades','metas','agenda',
   'conquistas','usuario_conquista','alertas','dicas']) e(nome) loop
   if not exists(select 1 from pg_class where oid=to_regclass('public.'||objeto.nome)
                 and relkind in ('r','p')) then
     raise exception 'Tabela obrigatória ausente/incompatível: public.%',objeto.nome;
   end if;
 end loop;
 if (select nspowner from pg_namespace where nspname='lifes_private')
    is distinct from (select oid from pg_roles where rolname='postgres') then
   raise exception 'Schema lifes_private deve pertencer a postgres';
 end if;
 for papel in select oid,rolname,rolsuper,rolcreaterole from pg_roles
   where rolname in ('anon','authenticated','service_role') loop
   if papel.rolsuper or papel.rolcreaterole or pg_has_role(papel.oid,'postgres','MEMBER')
      or has_schema_privilege(papel.oid,'public','CREATE')
      or has_schema_privilege(papel.oid,'lifes_private','CREATE') then
     raise exception 'Papel API com acesso administrativo/CREATE: %',papel.rolname;
   end if;
   for tabela in select c.oid,c.relname,c.relowner from pg_class c join pg_namespace n on n.oid=c.relnamespace
     where n.nspname='public' and c.relname in ('usuarios','atividades','metas','agenda',
       'conquistas','usuario_conquista','alertas','dicas','recompensas_xp') loop
     -- Usa os privilégios disponíveis nesta versão, incluindo MAINTAIN quando
     -- suportado, sem passar nomes desconhecidos a versões anteriores.
     for privilegio in select privilege_type from aclexplode(acldefault('r',tabela.relowner)) loop
       if papel.rolname='service_role' and (
          privilegio='SELECT'
          or (privilegio='INSERT' and tabela.relname in ('usuarios','atividades','metas','agenda','usuario_conquista','alertas'))
          or (privilegio in ('UPDATE','DELETE') and tabela.relname in ('atividades','metas','agenda','alertas'))) then
         if not has_table_privilege(papel.oid,tabela.oid,privilegio) then
           raise exception 'Permissão necessária ao Flask ausente: %.% em public.%',papel.rolname,privilegio,tabela.relname;
         end if;
         continue;
       end if;
       if has_table_privilege(papel.oid,tabela.oid,privilegio)
          or (privilegio in ('SELECT','INSERT','UPDATE','REFERENCES')
              and has_any_column_privilege(papel.oid,tabela.oid,privilegio)) then
         raise exception 'Privilégio residual %.% em %; revisar herança/ACL',papel.rolname,privilegio,tabela.relname;
       end if;
     end loop;
     for seq in select pg_get_serial_sequence('public.'||tabela.relname,a.attname)
       from pg_attribute a where a.attrelid=tabela.oid and a.attnum>0 and not a.attisdropped loop
       if seq is null then continue; end if;
       foreach privilegio in array array['USAGE','SELECT','UPDATE'] loop
         if papel.rolname='service_role' and privilegio in ('USAGE','SELECT')
           and tabela.relname in ('usuarios','atividades','metas','agenda','alertas') then
           if not has_sequence_privilege(papel.oid,seq,privilegio) then
             raise exception 'Permissão necessária ao Flask ausente: %.% em %',papel.rolname,privilegio,seq;
           end if;
           continue;
         end if;
         if has_sequence_privilege(papel.oid,seq,privilegio) then
           raise exception 'Privilégio residual %.% em sequência %; revisar herança/ACL',papel.rolname,privilegio,seq;
         end if;
       end loop;
     end loop;
   end loop;
   -- Não examina funções internas em auth/storage/extensions como se fossem RPCs
   -- públicas. Extensão instalada em public NÃO é automaticamente confiável:
   -- SQL dinâmico impede provar ausência de acesso ao aplicativo via pg_depend.
   for objeto in select p.oid::regprocedure as assinatura,pg_get_userbyid(p.proowner) as dono,
       (select e.extname from pg_depend d join pg_extension e on e.oid=d.refobjid
        where d.classid='pg_proc'::regclass and d.objid=p.oid
          and d.refclassid='pg_extension'::regclass and d.deptype='e') as extensao
     from pg_proc p join pg_namespace n on n.oid=p.pronamespace
     where n.nspname='public' and p.prosecdef and has_function_privilege(papel.oid,p.oid,'EXECUTE')
     order by p.oid loop
     raise exception 'SECURITY DEFINER acessível: %, papel=%, dono=%, extensão=%',
       objeto.assinatura,papel.rolname,objeto.dono,coalesce(objeto.extensao,'nenhuma')
       using hint='Revisar esta assinatura e seus consumidores. Não revogar funções de extensões em massa nem liberar RPC desconhecida. Nenhuma alteração desta transação foi confirmada.';
   end loop;
   if papel.rolname <> 'service_role' then
    for objeto in select c.oid::regclass as nome,c.reloptions,pg_get_userbyid(c.relowner) as dono
     from pg_class c join pg_namespace n on n.oid=c.relnamespace
     where n.nspname='public' and c.relkind in ('v','m')
       and has_any_column_privilege(papel.oid,c.oid,'SELECT') order by c.oid loop
     raise exception 'View pública legível: %, papel=%, dono=%, opções=%',
       objeto.nome,papel.rolname,objeto.dono,objeto.reloptions
       using hint='Revisar a definição e dependências, inclusive funções e views encadeadas. security_invoker não garante segurança de funções chamadas. Não altera nem apaga a view.';
    end loop;
   end if;
 end loop;
end $$;
alter function lifes_private.exigir_backend_privado() owner to postgres;
revoke all on function lifes_private.exigir_backend_privado() from public,anon,authenticated,service_role;
select lifes_private.exigir_backend_privado();
notify pgrst,'reload schema';
commit;
