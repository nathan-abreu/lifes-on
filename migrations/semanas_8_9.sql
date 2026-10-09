-- Semanas 8/9. Revisar e autorizar antes de executar no Supabase.
-- Pré-requisitos: schema + semanas_6_7 + alertas_leitura.
-- Requer seguranca_backend.sql autorizada e chave exclusiva do servidor no Flask.
-- Restringe ACL do livro/funções; não modifica RLS nem apaga registros.
begin;
select lifes_private.exigir_backend_privado();
alter table public.dicas add column if not exists categoria text not null default 'Hábitos saudáveis';
alter table public.dicas add column if not exists fonte text;
alter table public.agenda add column if not exists realizado_em timestamptz;
alter table public.atividades add column if not exists chave_registro uuid;
alter table public.atividades add column if not exists id_agenda bigint references public.agenda(id_agenda) on delete set null;
create unique index if not exists atividade_registro_uidx on public.atividades(id_usuario,chave_registro);
create unique index if not exists atividade_agenda_uidx on public.atividades(id_usuario,id_agenda);

create table if not exists public.recompensas_xp (
 id_recompensa bigint generated always as identity primary key,
 id_usuario bigint not null references public.usuarios(id_usuario),
 chave_evento text not null,
 motivo text not null,
 xp integer not null check (xp in (20,30,50)),
 criado_em timestamptz not null default now(),
 unique(id_usuario,chave_evento)
);
-- A tabela pode não existir durante seguranca_backend.sql. Neutraliza seus
-- default grants nesta mesma transação, antes de instalar os triggers.
-- REVOKE na tabela não remove ACL por coluna. Não altera defaults do projeto.
revoke all on public.recompensas_xp from public,anon,authenticated,service_role;
do $$
declare coluna record; seq text;
begin
 for coluna in select attname from pg_attribute
   where attrelid='public.recompensas_xp'::regclass and attnum>0 and not attisdropped loop
   execute format('revoke select (%1$I), insert (%1$I), update (%1$I), references (%1$I) on public.recompensas_xp from public,anon,authenticated,service_role',coluna.attname);
   seq:=pg_get_serial_sequence('public.recompensas_xp',coluna.attname);
   if seq is not null then
     execute format('revoke all on sequence %s from public,anon,authenticated,service_role',seq);
   end if;
 end loop;
end $$;
grant select on public.recompensas_xp to service_role;
-- IF NOT EXISTS não prova a definição de um índice já existente.
-- Recusa índices parciais, inválidos, por expressão ou com colunas diferentes.
do $$
declare esperado record;
begin
 for esperado in select * from (values
   ('atividades',array['id_usuario','chave_registro']),
   ('atividades',array['id_usuario','id_agenda']),
   ('recompensas_xp',array['id_usuario','chave_evento']),
   ('usuario_conquista',array['id_usuario','id_conquista'])
 ) e(tabela,colunas) loop
   if not exists(select 1 from pg_index i
     where i.indrelid=to_regclass('public.'||esperado.tabela)
       and i.indisunique and i.indisvalid and i.indisready and i.indimmediate
       and i.indpred is null and i.indexprs is null
       and (select array_agg(a.attname::text order by k.ord)
            from unnest(i.indkey) with ordinality k(num,ord)
            join pg_attribute a on a.attrelid=i.indrelid and a.attnum=k.num
            where k.ord<=i.indnkeyatts)=esperado.colunas) then
     raise exception 'Unicidade obrigatória incompatível: % (%)',esperado.tabela,esperado.colunas;
   end if;
 end loop;
end $$;
-- Funções internas são invocadas exclusivamente por triggers. SECURITY DEFINER
-- permite gravar o livro interno sem dar escrita nele ao cliente do Flask.
-- search_path fixo e referências qualificadas; nenhuma função recebe usuário via RPC.
create or replace function public.lifes_validar_registro() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare concluido timestamptz;
begin
 if tg_relid <> 'public.atividades'::regclass or tg_when <> 'BEFORE' or tg_op not in ('INSERT','UPDATE') then
   raise exception 'Contexto de trigger inválido';
 end if;
 -- Serializa por usuário também as recompensas de sequência e retries concorrentes.
 perform 1 from public.usuarios where id_usuario=new.id_usuario for update;
 if new.chave_registro is not null and exists (
   select 1 from public.recompensas_xp where id_usuario=new.id_usuario
   and chave_evento='atividade:' || new.chave_registro::text) then return null; end if;
 if new.id_agenda is not null then
   select realizado_em into concluido from public.agenda
   where id_agenda=new.id_agenda and id_usuario=new.id_usuario for update;
   if not found then raise exception 'Treino não pertence ao usuário'; end if;
   if concluido is not null then return null; end if;
 end if;
 if new.tipo_exercicio is null or new.tipo_exercicio not in ('Corrida','Musculação','Ciclismo','Natação','Yoga','Outros')
    or new.duracao is null or new.duracao not between 1 and 1440
    or new.frequencia is null or new.frequencia not between 1 and 7
    or new.data_registro is null or
      (case when pg_typeof(new.data_registro)::text='timestamp without time zone'
        then new.data_registro::timestamp at time zone 'UTC'
        else new.data_registro::timestamptz end) > now() + interval '5 minutes' then
   raise exception 'Atividade inválida';
 end if;
 return new;
end $$;
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
   insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
   values(new.id_usuario,'atividade:' || coalesce(new.chave_registro::text,new.id_atividade::text),'Atividade concluída',20)
   on conflict(id_usuario,chave_evento) do nothing;
   if new.id_agenda is not null then
     update public.agenda set realizado_em=now() where id_agenda=new.id_agenda and id_usuario=new.id_usuario;
   end if;
   -- Primeira sequência de sete dias, uma vez na vida. Datas locais reais.
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
create or replace trigger lifes_validar_atividade before insert on public.atividades
 for each row execute function public.lifes_validar_registro();
create or replace trigger lifes_xp_atividade after insert on public.atividades
 for each row execute function public.lifes_premiar();
create or replace trigger lifes_xp_meta after update on public.metas
 for each row execute function public.lifes_premiar();
create or replace trigger lifes_xp_conquista after insert on public.usuario_conquista
 for each row execute function public.lifes_premiar();

-- A autorização vem das ACLs e do papel efetivo postgres dos triggers internos.
-- Profundidade é apenas uma verificação adicional de contexto, não autorização.
create or replace function public.lifes_proteger_livro() returns trigger
language plpgsql security invoker set search_path = pg_catalog as $$
begin
 if current_user <> 'postgres' or tg_relid <> 'public.recompensas_xp'::regclass
    or tg_op <> 'INSERT' or pg_trigger_depth() < 2 then
   raise exception 'O histórico de XP só aceita recompensas dos eventos internos';
 end if;
 return new;
end $$;
create or replace trigger lifes_livro_imutavel before insert or update or delete
 on public.recompensas_xp for each row execute function public.lifes_proteger_livro();
create or replace trigger lifes_livro_sem_truncate before truncate
 on public.recompensas_xp for each statement execute function public.lifes_proteger_livro();

insert into public.dicas(titulo,descricao,categoria,fonte)
select s.* from (values
 ('Movimento que cabe no seu dia','Comece com uma atividade que você gosta e aumente o tempo gradualmente. Caminhar e usar escadas também contam. Adapte a intensidade às suas possibilidades.','Atividade física','https://www.who.int/news-room/fact-sheets/detail/physical-activity'),
 ('Recuperação faz parte do treino','Alterne dias intensos e leves e observe como se sente. Descanso é parte da rotina. Dor persistente ou mal-estar merecem avaliação profissional.','Recuperação','https://www.cdc.gov/physical-activity-basics/'),
 ('Uma rotina para dormir melhor','Procure manter horários regulares e um ambiente tranquilo para dormir. Reduza telas perto da hora de deitar. Necessidades de sono variam; dificuldades persistentes merecem orientação.','Sono','https://www.cdc.gov/sleep/about/'),
 ('Água por perto','Tenha água disponível durante o dia e ao se exercitar. Calor e esforço mudam as necessidades. Não há um volume único adequado a todas as pessoas; siga orientações profissionais se tiver restrições.','Hidratação','https://www.cdc.gov/healthy-weight-growth/water-healthy-drinks/'),
 ('Pequenos hábitos, constância possível','Escolha uma mudança pequena e observe como ela se encaixa na sua rotina. Registre o que conseguiu fazer e ajuste o plano sem culpa. Não é preciso treinar todos os dias para cuidar de si.','Hábitos saudáveis','https://www.who.int/news-room/fact-sheets/detail/physical-activity')
) s(titulo,descricao,categoria,fonte)
where not exists(select 1 from public.dicas d where d.titulo=s.titulo);
-- Corrige afirmação absoluta do seed antigo sem apagar a dica.
update public.dicas set descricao='Prepare-se com movimentos leves e aumente o esforço gradualmente. O aquecimento deve considerar a atividade e suas possibilidades.', categoria='Atividade física'
where titulo='Aquecimento' and descricao='Cinco minutos de aquecimento reduzem bastante o risco de lesão.';

-- Privilégios de escrita não são necessários para o cliente Flask: apenas SELECT.
-- BYPASSRLS de service_role não concede INSERT quando a ACL o nega.
revoke all on public.recompensas_xp from public,anon,authenticated,service_role;
grant select on public.recompensas_xp to service_role;
do $$
declare seq text;
begin
 if (select relowner from pg_class where oid='public.recompensas_xp'::regclass)
    <> (select oid from pg_roles where rolname='postgres') then
   raise exception 'Proprietário do livro deve ser postgres; revisar antes de migrar';
 end if;
 seq:=pg_get_serial_sequence('public.recompensas_xp','id_recompensa');
 if seq is not null then execute format('revoke all on sequence %s from public,anon,authenticated,service_role',seq); end if;
end $$;
alter function public.lifes_validar_registro() owner to postgres;
revoke all on function public.lifes_validar_registro() from public,anon,authenticated,service_role;
alter function public.lifes_premiar() owner to postgres;
revoke all on function public.lifes_premiar() from public,anon,authenticated,service_role;
alter function public.lifes_proteger_livro() owner to postgres;
revoke all on function public.lifes_proteger_livro() from public,anon,authenticated,service_role;
select lifes_private.exigir_backend_privado();

notify pgrst,'reload schema';
commit;
