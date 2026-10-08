-- Semanas 8/9. Revisar e autorizar antes de executar no Supabase.
-- Pré-requisitos: schema + semanas_6_7 + alertas_leitura.
-- Sem GRANT/REVOKE/RLS; não apaga nem premia retroativamente registros antigos.
begin;
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
-- Funções internas são invocadas exclusivamente por triggers. SECURITY DEFINER
-- permite gravar o livro interno sem dar escrita nele ao cliente do Flask.
-- search_path fixo e referências qualificadas; nenhuma função recebe usuário via RPC.
create or replace function public.lifes_validar_registro() returns trigger
language plpgsql security definer set search_path = pg_catalog, public as $$
declare concluido timestamptz;
begin
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
 if new.tipo_exercicio not in ('Corrida','Musculação','Ciclismo','Natação','Yoga','Outros')
    or new.duracao not between 1 and 1440 or new.frequencia not between 1 and 7
    or new.data_registro > now() + interval '5 minutes' then
   raise exception 'Atividade inválida';
 end if;
 return new;
end $$;
create or replace function public.lifes_premiar() returns trigger
language plpgsql security definer set search_path = pg_catalog, public as $$
begin
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
       from (select distinct (data_registro at time zone 'America/Sao_Paulo')::date as dia
             from public.atividades where id_usuario=new.id_usuario and data_registro<=now()) d
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

-- Protege o livro contra XP arbitrário via INSERT/UPDATE/DELETE direto,
-- independentemente dos privilégios preexistentes. Não altera RLS/permissões.
create or replace function public.lifes_proteger_livro() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
begin
 if tg_op <> 'INSERT' or pg_trigger_depth() < 2 then
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
notify pgrst,'reload schema';
commit;
