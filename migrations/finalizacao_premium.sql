-- Revisar e autorizar antes de executar. Requer semanas_8_9.sql.
-- Requer também seguranca_backend.sql. Preserva linhas, frequência legada e RLS.
-- ACL das funções internas é restrita; histórico permanece imutável.
begin;
select lifes_private.exigir_backend_privado();
alter table public.atividades alter column frequencia drop not null;
comment on column public.atividades.frequencia is
 'Frequência semanal declarada em registros legados. Novas sessões usam NULL; nunca multiplica sessões.';
alter table public.agenda add column if not exists modalidade text;

create or replace function public.lifes_validar_registro() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare concluido timestamptz;
begin
 if tg_relid <> 'public.atividades'::regclass or tg_when <> 'BEFORE' or tg_op not in ('INSERT','UPDATE') then
   raise exception 'Contexto de trigger inválido';
 end if;
 perform 1 from public.usuarios where id_usuario=new.id_usuario for update;
 if tg_op='UPDATE' then
   if new.id_usuario is distinct from old.id_usuario
      or new.chave_registro is distinct from old.chave_registro
      or (new.id_agenda is distinct from old.id_agenda and new.id_agenda is not null) then
     raise exception 'Identidade da sessão não pode ser alterada';
   end if;
   -- ON DELETE SET NULL da agenda deve preservar inclusive registros legados.
   if new.id_agenda is null and old.id_agenda is not null
      and new.tipo_exercicio=old.tipo_exercicio and new.duracao=old.duracao
      and new.data_registro=old.data_registro then return new; end if;
 else
   if new.chave_registro is not null and exists (
     select 1 from public.recompensas_xp where id_usuario=new.id_usuario
       and chave_evento='atividade:' || new.chave_registro::text) then return null; end if;
   if new.id_agenda is not null then
     select realizado_em into concluido from public.agenda
       where id_agenda=new.id_agenda and id_usuario=new.id_usuario for update;
     if not found then raise exception 'Treino não pertence ao usuário'; end if;
     if concluido is not null then return null; end if;
   end if;
 end if;
 if new.tipo_exercicio is null or new.tipo_exercicio not in
   ('Corrida','Musculação','Ciclismo','Natação','Yoga','Artes Marciais','Outros')
   or new.duracao is null or new.duracao not between 1 and 1440
   or (new.frequencia is not null and new.frequencia not between 1 and 7)
   or new.data_registro is null or
     (case when pg_typeof(new.data_registro)::text='timestamp without time zone'
       then new.data_registro::timestamp at time zone 'UTC'
       else new.data_registro::timestamptz end) > now() + interval '5 minutes' then
   raise exception 'Atividade inválida';
 end if;
 return new;
end $$;
create or replace trigger lifes_validar_atividade before insert or update on public.atividades
 for each row execute function public.lifes_validar_registro();

create or replace function public.lifes_premiar() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
begin
 if tg_when <> 'AFTER' or not ((tg_relid='public.atividades'::regclass and tg_op in ('INSERT','UPDATE'))
   or (tg_relid='public.metas'::regclass and tg_op='UPDATE')
   or (tg_relid='public.usuario_conquista'::regclass and tg_op='INSERT')) then
   raise exception 'Contexto de recompensa inválido';
 end if;
 perform 1 from public.usuarios where id_usuario=new.id_usuario for update;
 if tg_table_name='atividades' then
  if tg_op='INSERT' then
   insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
   values(new.id_usuario,'atividade:' || coalesce(new.chave_registro::text,new.id_atividade::text),'Atividade concluída',20)
   on conflict(id_usuario,chave_evento) do nothing;
   if new.id_agenda is not null then
     update public.agenda set realizado_em=now() where id_agenda=new.id_agenda and id_usuario=new.id_usuario;
   end if;
  elsif new.data_registro is not distinct from old.data_registro then
    return new;
  end if;
   -- A edição da data pode alcançar o marco; duração/tipo não repetem XP.
   -- Timestamp legado sem offset representa UTC, como no cálculo Python.
   if exists (
     select 1 from (
       select dia, dia - (row_number() over(order by dia))::integer as grupo
       from (select distinct (case when pg_typeof(data_registro)::text='timestamp without time zone'
               then (data_registro::timestamp at time zone 'UTC') at time zone 'America/Sao_Paulo'
               else data_registro::timestamptz at time zone 'America/Sao_Paulo' end)::date as dia
             from public.atividades where id_usuario=new.id_usuario and
               (case when pg_typeof(data_registro)::text='timestamp without time zone'
                 then data_registro::timestamp at time zone 'UTC'
                 else data_registro::timestamptz end)<=now()) d
     ) s group by grupo having count(*)>=7
   ) then
     insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
     values(new.id_usuario,'sequencia:primeiros-7','Primeira sequência de 7 dias',50)
     on conflict(id_usuario,chave_evento) do nothing;
   end if;
 elsif tg_table_name='metas' then
  if new.progresso=100 and old.progresso<100 then
   insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
   values(new.id_usuario,'meta:' || new.id_meta::text,'Meta concluída',50)
   on conflict(id_usuario,chave_evento) do nothing;
  end if;
 elsif tg_table_name='usuario_conquista' then
   insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
   values(new.id_usuario,'conquista:' || new.id_conquista::text,'Conquista desbloqueada',30)
   on conflict(id_usuario,chave_evento) do nothing;
 end if;
 return new;
end $$;
create or replace trigger lifes_xp_atividade after insert or update on public.atividades
 for each row execute function public.lifes_premiar();

-- O lançamento original é mantido; a exclusão acrescenta um estorno único.
alter table public.recompensas_xp drop constraint if exists recompensas_xp_xp_check;
alter table public.recompensas_xp add constraint recompensas_xp_xp_check
 check (xp in (-20,20,30,50));
create or replace function public.lifes_estornar_atividade() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare evento text;
begin
 if tg_relid <> 'public.atividades'::regclass or tg_op <> 'DELETE' or tg_when <> 'AFTER' then
   raise exception 'Contexto de estorno inválido';
 end if;
 perform 1 from public.usuarios where id_usuario=old.id_usuario for update;
 evento := 'atividade:' || coalesce(old.chave_registro::text,old.id_atividade::text);
 if exists(select 1 from public.recompensas_xp where id_usuario=old.id_usuario
    and chave_evento=evento and xp=20) then
   insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
   values(old.id_usuario,'estorno:' || evento,'Estorno de atividade excluída',-20)
   on conflict(id_usuario,chave_evento) do nothing;
 end if;
 return old;
end $$;
create or replace trigger lifes_estorno_atividade after delete on public.atividades
 for each row execute function public.lifes_estornar_atividade();

-- Duplicações anteriores abortam a migração para revisão; nunca apagar/mesclar IDs.
lock table public.conquistas in share row exclusive mode;
create unique index if not exists conquistas_nome_normalizado_uidx
 on public.conquistas(pg_catalog.lower(pg_catalog.btrim(nome)));
do $$
declare caminho_anterior text := current_setting('search_path');
begin
 -- Referência vazia com os MESMOS tipos/collations das colunas reais. O parser
 -- insere os casts corretos (ex.: varchar -> text), sem ler/copiar conquistas.
 -- Não compara com SQL literal nem remove casts/qualificações por regex.
 perform set_config('search_path','pg_catalog,pg_temp',true);
 create temporary table lifes_conquistas_indice_ref
   (like public.conquistas) on commit drop;
 create unique index lifes_conquistas_indice_ref_uidx
   on lifes_conquistas_indice_ref(pg_catalog.lower(pg_catalog.btrim(nome)));
 if not exists(select 1 from pg_index i
   join pg_class atual on atual.oid=i.indexrelid
   cross join pg_index esperado
   join pg_class referencia on referencia.oid=esperado.indexrelid
   where i.indexrelid=to_regclass('public.conquistas_nome_normalizado_uidx')
     and esperado.indexrelid=to_regclass('pg_temp.lifes_conquistas_indice_ref_uidx')
     and i.indrelid='public.conquistas'::regclass
     and i.indisunique and i.indisvalid and i.indisready and i.indislive
     and i.indimmediate and not i.indisexclusion
     and i.indnkeyatts=1 and i.indkey[0]=0 and i.indpred is null
     and atual.relam=referencia.relam
     and i.indclass=esperado.indclass and i.indcollation=esperado.indcollation
     -- Ambos reconstruídos pelo mesmo servidor/search_path a partir das árvores
     -- analisadas: aceita casts de tipo e nomes qualificados equivalentes.
     and pg_get_expr(i.indexprs,i.indrelid,false)
         =pg_get_expr(esperado.indexprs,esperado.indrelid,false)) then
   raise exception 'Índice de nomes normalizados incompatível; revisar sem remover dados';
 end if;
 perform set_config('search_path',caminho_anterior,true);
end $$;
-- Seed completo dos 14 critérios, preservando nomes/IDs/pontos existentes.
insert into public.conquistas(nome,descricao,pontos)
select s.nome,s.descricao,0 from (values
 ('Primeiro passo','Realize sua primeira atividade.'),
 ('Em Movimento','Realize 5 atividades.'),
 ('Foco Total','Realize 10 atividades.'),
 ('Veterano','Realize 30 atividades.'),
 ('Semana cheia','Registre atividades em 7 dias consecutivos.'),
 ('Meta batida','Conclua uma meta (100% de progresso).'),
 ('Lenda do Treino','Realize 100 atividades.'),
 ('Constância de Aço','Registre atividades em 14 dias consecutivos.'),
 ('Imparável','Registre atividades em 30 dias consecutivos.'),
 ('Caçador de Metas','Conclua 5 metas.'),
 ('Mestre dos Objetivos','Conclua 10 metas.'),
 ('Uma Hora de Superação','Acumule 60 minutos de atividades.'),
 ('Dez Horas de Evolução','Acumule 600 minutos de atividades.'),
 ('Centurião','Acumule 6.000 minutos de atividades.')
) s(nome,descricao)
where not exists(select 1 from public.conquistas c where lower(trim(c.nome))=lower(s.nome));
alter function public.lifes_validar_registro() owner to postgres;
revoke all on function public.lifes_validar_registro() from public,anon,authenticated,service_role;
alter function public.lifes_premiar() owner to postgres;
revoke all on function public.lifes_premiar() from public,anon,authenticated,service_role;
alter function public.lifes_estornar_atividade() owner to postgres;
revoke all on function public.lifes_estornar_atividade() from public,anon,authenticated,service_role;
select lifes_private.exigir_backend_privado();

notify pgrst,'reload schema';
commit;
