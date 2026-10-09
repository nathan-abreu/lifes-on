-- OPCIONAL PARA FOTOS. Revisar/autorizar separadamente, executar como postgres.
-- Bucket exclusivo Lifes On. Não altera buckets/policies de outros aplicativos.
-- Não altera RLS: aborta se storage.objects não estiver protegido por RLS.
begin;
do $$begin
 if current_user<>'postgres' then raise exception 'Execute como postgres'; end if;
 if not exists(select 1 from pg_class where oid=to_regclass('storage.objects') and relrowsecurity) then
   raise exception 'Storage ausente ou sem RLS; revisar antes de habilitar fotos'; end if;
end $$;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('lifes-perfis','lifes-perfis',false,5242880,array['image/png'])
on conflict(id) do nothing;
do $$
declare caminho_anterior text := current_setting('search_path');
begin
 if not exists(select 1 from storage.buckets where id='lifes-perfis' and not public
   and file_size_limit=5242880 and allowed_mime_types=array['image/png']) then
   raise exception 'Bucket lifes-perfis existente incompatível; revisar sem alterar arquivos'; end if;
 -- Política RESTRITIVA impede acesso também sob policies permissivas globais.
 -- Não substitui política homônima desconhecida.
 if not exists(select 1 from pg_policy where polrelid='storage.objects'::regclass and polname='lifes_perfis_somente_backend') then
   create policy lifes_perfis_somente_backend on storage.objects as restrictive
     for all to anon,authenticated
     using (bucket_id <> 'lifes-perfis') with check (bucket_id <> 'lifes-perfis');
 end if;
 perform set_config('search_path','pg_catalog,pg_temp',true);
 create temporary table lifes_storage_policy_ref (like storage.objects) on commit drop;
 create policy lifes_perfis_referencia on lifes_storage_policy_ref as restrictive
   for all to anon,authenticated
   using (bucket_id <> 'lifes-perfis') with check (bucket_id <> 'lifes-perfis');
 if not exists(select 1 from pg_policy p cross join pg_policy r
   where p.polrelid='storage.objects'::regclass and p.polname='lifes_perfis_somente_backend'
   and r.polrelid='pg_temp.lifes_storage_policy_ref'::regclass and r.polname='lifes_perfis_referencia'
   and not p.polpermissive and p.polcmd='*' and p.polroles @> r.polroles and p.polroles <@ r.polroles
   and pg_get_expr(p.polqual,p.polrelid,false)=pg_get_expr(r.polqual,r.polrelid,false)
   and pg_get_expr(p.polwithcheck,p.polrelid,false)=pg_get_expr(r.polwithcheck,r.polrelid,false)) then
   raise exception 'Política de fotos existente incompatível; revisar sem remover policies'; end if;
 perform set_config('search_path',caminho_anterior,true);
end $$;
commit;
