-- NOVA migração: executar como postgres, após as três migrações anteriores.
-- Revisão/autorização antes da execução. Não altera RLS, dados históricos ou Storage.
begin;
select lifes_private.exigir_backend_privado();
do $$
declare tipo_data regtype; conflito record; esperado record;
begin
 -- Triggers desconhecidos podem alterar saldo/progresso fora destas regras.
 -- Aborta para revisão; nunca remove nem desativa objetos preexistentes.
 for conflito in
   select t.tgname,c.relname from pg_trigger t join pg_class c on c.oid=t.tgrelid
   where t.tgrelid in ('public.atividades'::regclass,'public.metas'::regclass,
     'public.usuario_conquista'::regclass,'public.recompensas_xp'::regclass)
     and not t.tgisinternal and (t.tgenabled not in ('O','A') or not exists (
       select 1 from (values
        ('atividades','lifes_validar_atividade','lifes_validar_registro'),
        ('atividades','lifes_xp_atividade','lifes_premiar'),
        ('atividades','lifes_estorno_atividade','lifes_estornar_atividade'),
        ('atividades','lifes_z_recalcular_metas','lifes_recalcular_metas'),
        ('metas','lifes_calcular_meta','lifes_calcular_meta'),
        ('metas','lifes_xp_meta','lifes_premiar'),
        ('usuario_conquista','lifes_xp_conquista','lifes_premiar'),
        ('recompensas_xp','lifes_livro_imutavel','lifes_proteger_livro'),
        ('recompensas_xp','lifes_livro_sem_truncate','lifes_proteger_livro')
       ) e(tabela,gatilho,funcao)
       where e.tabela=c.relname and e.gatilho=t.tgname
         and t.tgfoid=to_regprocedure('public.'||e.funcao||'()'))) loop
   raise exception 'Trigger requer revisão: %.%; nenhuma alteração confirmada',conflito.relname,conflito.tgname;
 end loop;
 -- Estes triggers não são recriados abaixo; ausência/WHEN/colunas restritas
 -- deixariam de proteger o livro ou de premiar conquistas.
 for esperado in select * from (values
   ('recompensas_xp','lifes_livro_imutavel','lifes_proteger_livro',31),
   ('recompensas_xp','lifes_livro_sem_truncate','lifes_proteger_livro',34),
   ('usuario_conquista','lifes_xp_conquista','lifes_premiar',5)
 ) e(tabela,gatilho,funcao,tipo) loop
   if not exists(select 1 from pg_trigger t
     where t.tgrelid=to_regclass('public.'||esperado.tabela) and t.tgname=esperado.gatilho
       and t.tgfoid=to_regprocedure('public.'||esperado.funcao||'()')
       and t.tgtype=esperado.tipo and t.tgqual is null and t.tgnargs=0
       and t.tgattr=''::int2vector and t.tgenabled in ('O','A')) then
     raise exception 'Trigger obrigatório ausente/incompatível: %.%',esperado.tabela,esperado.gatilho;
   end if;
 end loop;
 for esperado in select * from (values
   ('atividades',array['id_usuario','chave_registro']),
   ('atividades',array['id_usuario','id_agenda']),
   ('recompensas_xp',array['id_usuario','chave_evento']),
   ('usuario_conquista',array['id_usuario','id_conquista'])
 ) e(tabela,colunas) loop
   if not exists(select 1 from pg_index i
     where i.indrelid=to_regclass('public.'||esperado.tabela)
       and i.indisunique and i.indisvalid and i.indisready and i.indislive and i.indimmediate
       and i.indpred is null and i.indexprs is null
       and (select array_agg(a.attname::text order by k.ord)
         from unnest(i.indkey) with ordinality k(num,ord)
         join pg_attribute a on a.attrelid=i.indrelid and a.attnum=k.num
         where k.ord<=i.indnkeyatts)=esperado.colunas) then
     raise exception 'Unicidade obrigatória incompatível: % (%)',esperado.tabela,esperado.colunas;
   end if;
 end loop;
 if to_regprocedure('public.lifes_estornar_atividade()') is null
    or not exists(select 1 from pg_attribute where attrelid='public.atividades'::regclass
      and attname='frequencia' and not attnotnull) then
   raise exception 'Aplique finalizacao_premium.sql antes desta evolução';
 end if;
 select atttypid::regtype into tipo_data from pg_attribute
 where attrelid='public.atividades'::regclass and attname='data_registro' and not attisdropped;
 if tipo_data='date'::regtype then
   alter table public.atividades alter column data_registro set default (now() at time zone 'America/Sao_Paulo')::date;
 elsif tipo_data='timestamp without time zone'::regtype then
   alter table public.atividades alter column data_registro set default (now() at time zone 'UTC');
 elsif tipo_data<>'timestamp with time zone'::regtype or tipo_data is null then
   raise exception 'Tipo de data_registro incompatível; esperado date/timestamp/timestamptz';
 end if;
 if not exists(select 1 from pg_attribute where attrelid='public.atividades'::regclass
   and attname='duracao' and atttypid in ('integer'::regtype,'smallint'::regtype)) then
   raise exception 'Duração deve ser integer/smallint; revisar o diagnóstico sem converter dados automaticamente';
 end if;
end $$;
alter table public.usuarios add column if not exists foto_path text;
alter table public.usuarios add column if not exists perfil_versao bigint not null default 0;
alter table public.atividades add column if not exists distancia_km numeric;
-- DEFAULT 1 preserva o significado das linhas antigas; o trigger impõe 2 nas novas.
alter table public.atividades add column if not exists xp_versao integer not null default 1;
alter table public.atividades add column if not exists xp_atual integer not null default 0;
alter table public.atividades add column if not exists xp_revisao bigint not null default 0;
alter table public.atividades add column if not exists xp_transacao bigint;
alter table public.metas add column if not exists metrica text;
alter table public.metas add column if not exists modalidade text;
alter table public.metas add column if not exists alvo numeric;
alter table public.metas add column if not exists inicio date;
alter table public.metas add column if not exists acumulado numeric;
-- Agrupa recompensas de uma mesma transação sem confundir outras abas.
-- Linhas históricas continuam NULL; nenhum lançamento é atualizado.
alter table public.recompensas_xp add column if not exists transacao bigint;
alter table public.recompensas_xp alter column transacao set default pg_catalog.txid_current();
create index if not exists lifes_atividades_usuario_data_idx on public.atividades(id_usuario,data_registro);
create index if not exists lifes_metas_automaticas_usuario_idx on public.metas(id_usuario) where metrica is not null;

-- Limite absoluto por sessão: 1440 minutos + 3600 XP (720 km de corrida).
-- O limite efetivo de velocidade reduz os demais casos. Histórico nunca é refeito.
alter table public.recompensas_xp drop constraint if exists recompensas_xp_xp_check;
alter table public.recompensas_xp add constraint recompensas_xp_xp_check
 check (xp between -5040 and 5040 and xp <> 0);

create or replace function lifes_private.xp_sessao(tipo text, minutos integer, km numeric)
returns integer language plpgsql immutable set search_path=pg_catalog as $$
declare taxa integer; velocidade integer;
begin
 if tipo is null or tipo not in ('Corrida','Caminhada','Ciclismo','Natação','Musculação','Yoga','Artes Marciais','Outros')
    or minutos is null or minutos not between 1 and 1440 then raise exception 'Atividade inválida'; end if;
 taxa := case tipo when 'Corrida' then 5 when 'Caminhada' then 3 when 'Ciclismo' then 2 when 'Natação' then 10 end;
 velocidade := case tipo when 'Corrida' then 30 when 'Caminhada' then 12 when 'Ciclismo' then 80 when 'Natação' then 10 end;
 if km is not null and (taxa is null or km::text in ('NaN','Infinity','-Infinity')
    or km<=0 or km>1000 or km<>trunc(km,3) or km*60>minutos*velocidade) then
   raise exception 'Distância incompatível com modalidade, precisão ou duração';
 end if;
 return minutos + coalesce(floor(km*taxa)::integer,0);
end $$;
revoke all on function lifes_private.xp_sessao(text,integer,numeric) from public,anon,authenticated,service_role;

-- Livro é a fonte do saldo: original + revisões numeradas + estorno, nunca bônus.
-- NULL distingue uma sessão sem lançamento original de uma sessão já estornada.
create or replace function lifes_private.saldo_atividade(usuario bigint, evento text)
returns bigint language sql stable set search_path=pg_catalog as $$
 select sum(r.xp)::bigint from public.recompensas_xp r
 where r.id_usuario=usuario and (r.chave_evento=evento
   or r.chave_evento='estorno:'||evento
   or r.chave_evento ~ ('^ajuste:'||evento||':[1-9][0-9]*$'))
 having count(*) filter (where r.chave_evento=evento)=1
$$;
alter function lifes_private.saldo_atividade(bigint,text) owner to postgres;
revoke all on function lifes_private.saldo_atividade(bigint,text) from public,anon,authenticated,service_role;

-- Metas antigas ficam intactas até conversão explícita pelo formulário.
create or replace function public.lifes_calcular_meta() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if tg_relid<>'public.metas'::regclass or tg_when<>'BEFORE' or tg_op not in ('INSERT','UPDATE') then
   raise exception 'Contexto de meta inválido'; end if;
 perform 1 from public.usuarios where id_usuario=new.id_usuario for update;
 if tg_op='UPDATE' and (new.id_usuario is distinct from old.id_usuario or new.id_meta is distinct from old.id_meta) then
   raise exception 'Identidade da meta imutável'; end if;
 if new.metrica is null then
   if tg_op='INSERT' then raise exception 'Novas metas devem ser automáticas'; end if;
   if old.metrica is not null or new.progresso is distinct from old.progresso then
     raise exception 'Progresso manual desativado; converta a meta legada'; end if;
   new.acumulado:=old.acumulado;
   return new;
 end if;
 if new.metrica not in ('minutos','km','sessoes') or new.alvo is null
    or new.alvo::text in ('NaN','Infinity','-Infinity') or new.alvo<=0 or new.alvo>1000000
    or new.alvo<>trunc(new.alvo,3) or (new.metrica<>'km' and new.alvo<>trunc(new.alvo))
    or new.inicio is null or new.prazo is null or new.prazo<new.inicio
    or new.descricao is null or length(btrim(new.descricao)) not between 1 and 200
    or (new.modalidade is not null and new.modalidade not in
        ('Corrida','Caminhada','Ciclismo','Natação','Musculação','Yoga','Artes Marciais','Outros'))
    or (new.metrica='km' and new.modalidade is not null and new.modalidade not in ('Corrida','Caminhada','Ciclismo','Natação')) then
   raise exception 'Objetivo automático inválido'; end if;
 select coalesce(sum(case new.metrica when 'minutos' then a.duracao
                     when 'sessoes' then 1 else coalesce(a.distancia_km,0) end),0)
 into new.acumulado from public.atividades a
 where a.id_usuario=new.id_usuario and (new.modalidade is null or a.tipo_exercicio=new.modalidade)
   and a.duracao between 1 and 1440
   and a.tipo_exercicio in ('Corrida','Caminhada','Ciclismo','Natação','Musculação','Yoga','Artes Marciais','Outros')
   and (new.metrica<>'km' or a.tipo_exercicio in ('Corrida','Caminhada','Ciclismo','Natação'))
   and (case when pg_typeof(a.data_registro)::text='date' then a.data_registro::date::timestamp at time zone 'America/Sao_Paulo'
      when pg_typeof(a.data_registro)::text='timestamp without time zone'
      then a.data_registro::timestamp at time zone 'UTC' else a.data_registro::timestamptz end)<=now()
   and (case when pg_typeof(a.data_registro)::text='date' then a.data_registro::date::timestamp at time zone 'America/Sao_Paulo'
      when pg_typeof(a.data_registro)::text='timestamp without time zone'
      then a.data_registro::timestamp at time zone 'UTC' else a.data_registro::timestamptz end
      at time zone 'America/Sao_Paulo')::date between new.inicio and new.prazo;
 new.progresso:=least(100,floor(new.acumulado*100/new.alvo))::integer;
 return new;
end $$;
create or replace trigger lifes_calcular_meta before insert or update on public.metas
 for each row execute function public.lifes_calcular_meta();

create or replace function public.lifes_recalcular_metas() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
declare
 usuario bigint; antes timestamptz; depois timestamptz;
 -- %ROWTYPE mantém a estrutura conhecida mesmo quando os campos são NULL.
 -- Somente o ramo da operação copia OLD/NEW; o SQL compartilhado usa estas cópias.
 anterior public.atividades%rowtype;
 posterior public.atividades%rowtype;
begin
 if tg_relid<>'public.atividades'::regclass or tg_when<>'AFTER' or tg_op not in ('INSERT','UPDATE','DELETE') then
   raise exception 'Contexto de recálculo inválido'; end if;
 if tg_op='INSERT' then
   posterior:=new;
   usuario:=new.id_usuario;
 elsif tg_op='DELETE' then
   anterior:=old;
   usuario:=old.id_usuario;
 else -- UPDATE: ambos os registros estão disponíveis.
   if row(new.tipo_exercicio,new.duracao,new.distancia_km,new.data_registro)
     is not distinct from row(old.tipo_exercicio,old.duracao,old.distancia_km,old.data_registro) then
     return null; -- Inclui alterações técnicas de XP e ON DELETE SET NULL da agenda.
   end if;
   anterior:=old;
   posterior:=new;
   usuario:=new.id_usuario;
 end if;
 if tg_op<>'INSERT' then
   antes:=case when pg_typeof(anterior.data_registro)::text='date'
     then anterior.data_registro::date::timestamp at time zone 'America/Sao_Paulo'
     when pg_typeof(anterior.data_registro)::text='timestamp without time zone'
     then anterior.data_registro::timestamp at time zone 'UTC' else anterior.data_registro::timestamptz end;
 end if;
 if tg_op<>'DELETE' then
   depois:=case when pg_typeof(posterior.data_registro)::text='date'
     then posterior.data_registro::date::timestamp at time zone 'America/Sao_Paulo'
     when pg_typeof(posterior.data_registro)::text='timestamp without time zone'
     then posterior.data_registro::timestamp at time zone 'UTC' else posterior.data_registro::timestamptz end;
 end if;
 -- Recalcula somente metas cuja contribuição desta sessão mudou. O BEFORE
 -- calcula o total real; não incrementa acumulados fornecidos pelo cliente.
 update public.metas m set acumulado=m.acumulado
 where m.id_usuario=usuario and m.metrica is not null and 0<>(
   select coalesce(sum(v.sinal * case m.metrica when 'minutos' then v.minutos
     when 'sessoes' then 1 else coalesce(v.km,0) end),0)
   from (values (anterior.tipo_exercicio,anterior.duracao,anterior.distancia_km,antes,-1),
                (posterior.tipo_exercicio,posterior.duracao,posterior.distancia_km,depois,1))
     v(tipo,minutos,km,instante,sinal)
   where v.instante<=now() and v.minutos between 1 and 1440
     and v.tipo in ('Corrida','Caminhada','Ciclismo','Natação','Musculação','Yoga','Artes Marciais','Outros')
     and (m.modalidade is null or m.modalidade=v.tipo)
     and (m.metrica<>'km' or v.tipo in ('Corrida','Caminhada','Ciclismo','Natação'))
     and (v.instante at time zone 'America/Sao_Paulo')::date between m.inicio and m.prazo);
 return null;
end $$;
create or replace trigger lifes_z_recalcular_metas after insert or update or delete on public.atividades
 for each row execute function public.lifes_recalcular_metas();

-- DEFINIÇÕES DE ATIVIDADE E XP (geradas a partir da versão anterior revisada).
create or replace function public.lifes_validar_registro() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare concluido timestamptz; calculado integer;
begin
 if tg_relid <> 'public.atividades'::regclass or tg_when <> 'BEFORE' or tg_op not in ('INSERT','UPDATE','DELETE') then
   raise exception 'Contexto de trigger inválido';
 end if;
 if tg_op='DELETE' then
   perform 1 from public.usuarios where id_usuario=old.id_usuario for update;
   return old;
 end if;
 perform 1 from public.usuarios where id_usuario=new.id_usuario for update;
 if tg_op='UPDATE' then
   if old.xp_versao=2 and lifes_private.saldo_atividade(old.id_usuario,
       'atividade:'||coalesce(old.chave_registro::text,old.id_atividade::text))
       is distinct from old.xp_atual::bigint then
     raise exception 'Saldo da atividade divergente do livro; revisar sem alterar histórico';
   end if;
   if new.id_atividade is distinct from old.id_atividade or new.id_usuario is distinct from old.id_usuario
      or new.chave_registro is distinct from old.chave_registro
      or (new.id_agenda is distinct from old.id_agenda and new.id_agenda is not null) then
     raise exception 'Identidade da sessão não pode ser alterada';
   end if;
   -- ON DELETE SET NULL da agenda deve preservar inclusive registros legados.
   if new.id_agenda is null and old.id_agenda is not null
      and new.tipo_exercicio=old.tipo_exercicio and new.duracao=old.duracao
      and new.data_registro=old.data_registro then
     new.xp_versao:=old.xp_versao; new.xp_atual:=old.xp_atual; new.xp_revisao:=old.xp_revisao; new.xp_transacao:=old.xp_transacao;
     if new.distancia_km is not distinct from old.distancia_km then return new; end if;
   end if;
 else
   if exists (
     select 1 from public.recompensas_xp where id_usuario=new.id_usuario
       and chave_evento='atividade:' || coalesce(new.chave_registro::text,new.id_atividade::text)) then return null; end if;
   if new.id_agenda is not null then
     select realizado_em into concluido from public.agenda
       where id_agenda=new.id_agenda and id_usuario=new.id_usuario for update;
     if not found then raise exception 'Treino não pertence ao usuário'; end if;
     if concluido is not null then return null; end if;
   end if;
 end if;
 if new.tipo_exercicio is null or new.tipo_exercicio not in
   ('Corrida','Caminhada','Musculação','Ciclismo','Natação','Yoga','Artes Marciais','Outros')
   or new.duracao is null or new.duracao not between 1 and 1440
   or (new.frequencia is not null and new.frequencia not between 1 and 7)
   or new.data_registro is null or
     (case when pg_typeof(new.data_registro)::text='date' then new.data_registro::date::timestamp at time zone 'America/Sao_Paulo'
      when pg_typeof(new.data_registro)::text='timestamp without time zone'
       then new.data_registro::timestamp at time zone 'UTC'
       else new.data_registro::timestamptz end) > now() then
   raise exception 'Atividade inválida';
 end if;
 calculado:=lifes_private.xp_sessao(new.tipo_exercicio,new.duracao,new.distancia_km);
 new.xp_transacao:=pg_catalog.txid_current();
 if tg_op='INSERT' then
   new.xp_versao:=2; new.xp_atual:=calculado; new.xp_revisao:=0;
 else
   new.xp_versao:=old.xp_versao;
   new.xp_atual:=case when old.xp_versao=2 then calculado else old.xp_atual end;
   new.xp_revisao:=old.xp_revisao + case when new.xp_atual<>old.xp_atual then 1 else 0 end;
 end if;
 return new;
end $$;
create or replace trigger lifes_validar_atividade before insert or update or delete on public.atividades
 for each row execute function public.lifes_validar_registro();

create or replace function public.lifes_premiar() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
begin
 if tg_when <> 'AFTER' or not ((tg_relid='public.atividades'::regclass and tg_op in ('INSERT','UPDATE'))
   or (tg_relid='public.metas'::regclass and tg_op in ('INSERT','UPDATE'))
   or (tg_relid='public.usuario_conquista'::regclass and tg_op='INSERT')) then
   raise exception 'Contexto de recompensa inválido';
 end if;
 perform 1 from public.usuarios where id_usuario=new.id_usuario for update;
 if tg_table_name='atividades' then
  if tg_op='INSERT' then
   insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
   values(new.id_usuario,'atividade:' || coalesce(new.chave_registro::text,new.id_atividade::text),'Atividade concluída (minutos e distância)',new.xp_atual)
   on conflict(id_usuario,chave_evento) do nothing;
   if new.id_agenda is not null then
     update public.agenda set realizado_em=now() where id_agenda=new.id_agenda and id_usuario=new.id_usuario;
   end if;
  else
   if new.xp_versao=2 and new.xp_atual<>old.xp_atual then
     insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
     values(new.id_usuario,'ajuste:atividade:' || coalesce(new.chave_registro::text,new.id_atividade::text)
       || ':' || new.xp_revisao::text,'Ajuste de atividade editada',new.xp_atual-old.xp_atual);
   end if;
   if new.data_registro is not distinct from old.data_registro then return new; end if;
  end if;
   -- A edição da data pode alcançar o marco de sequência; ajustes já foram lançados.
   -- Timestamp legado sem offset representa UTC, como no cálculo Python.
   if exists (
     select 1 from (
       select dia, dia - (row_number() over(order by dia))::integer as grupo
       from (select distinct (case when pg_typeof(data_registro)::text='date' then data_registro::date::timestamp
      when pg_typeof(data_registro)::text='timestamp without time zone'
               then (data_registro::timestamp at time zone 'UTC') at time zone 'America/Sao_Paulo'
               else data_registro::timestamptz at time zone 'America/Sao_Paulo' end)::date as dia
             from public.atividades where id_usuario=new.id_usuario and
               (case when pg_typeof(data_registro)::text='date' then data_registro::date::timestamp at time zone 'America/Sao_Paulo'
      when pg_typeof(data_registro)::text='timestamp without time zone'
                 then data_registro::timestamp at time zone 'UTC'
                 else data_registro::timestamptz end)<=now()) d
     ) s group by grupo having count(*)>=7
   ) then
     insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
     values(new.id_usuario,'sequencia:primeiros-7','Primeira sequência de 7 dias',50)
     on conflict(id_usuario,chave_evento) do nothing;
   end if;
 elsif tg_table_name='metas' then
  -- Marco histórico: não estorna na regressão/exclusão e não paga reconclusão.
  -- Conversão verifica atividades reais, independentemente do progresso legado.
  if new.progresso=100 and (tg_op='INSERT' or old.progresso<100
       or (old.metrica is null and new.metrica is not null)) then
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

create or replace trigger lifes_xp_meta after insert or update on public.metas
 for each row execute function public.lifes_premiar();
create or replace function public.lifes_estornar_atividade() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare evento text; valor bigint;
begin
 if tg_relid <> 'public.atividades'::regclass or tg_op <> 'DELETE' or tg_when <> 'AFTER' then
   raise exception 'Contexto de estorno inválido';
 end if;
 perform 1 from public.usuarios where id_usuario=old.id_usuario for update;
 evento := 'atividade:' || coalesce(old.chave_registro::text,old.id_atividade::text);
 valor:=lifes_private.saldo_atividade(old.id_usuario,evento);
 if old.xp_versao=2 and valor is distinct from old.xp_atual::bigint then
   raise exception 'Saldo da atividade divergente do livro; revisar sem alterar histórico';
 end if;
 if valor is not null and valor<>0 then
   if valor not between 1 and 5040 or exists(select 1 from public.recompensas_xp
       where id_usuario=old.id_usuario and chave_evento='estorno:'||evento) then
     raise exception 'Saldo histórico incompatível com estorno único; revisar livro';
   end if;
   insert into public.recompensas_xp(id_usuario,chave_evento,motivo,xp)
   values(old.id_usuario,'estorno:' || evento,'Estorno de atividade excluída',-valor)
   on conflict(id_usuario,chave_evento) do nothing;
 end if;
 return old;
end $$;
create or replace trigger lifes_estorno_atividade after delete on public.atividades
 for each row execute function public.lifes_estornar_atividade();


-- EXECUTE interno fechado inclusive sob default privileges permissivos.
alter function public.lifes_validar_registro() owner to postgres;
revoke all on function public.lifes_validar_registro() from public,anon,authenticated,service_role;
alter function public.lifes_premiar() owner to postgres;
revoke all on function public.lifes_premiar() from public,anon,authenticated,service_role;
alter function public.lifes_estornar_atividade() owner to postgres;
revoke all on function public.lifes_estornar_atividade() from public,anon,authenticated,service_role;
alter function public.lifes_calcular_meta() owner to postgres;
revoke all on function public.lifes_calcular_meta() from public,anon,authenticated,service_role;
alter function public.lifes_recalcular_metas() owner to postgres;
revoke all on function public.lifes_recalcular_metas() from public,anon,authenticated,service_role;
grant update(nome,foto_path,perfil_versao) on public.usuarios to service_role;
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
       if papel.rolname='service_role' and tabela.relname='usuarios' and privilegio='UPDATE' then
         if has_table_privilege(papel.oid,tabela.oid,'UPDATE') or exists(
           select 1 from pg_attribute a where a.attrelid=tabela.oid and a.attnum>0 and not a.attisdropped
             and has_column_privilege(papel.oid,tabela.oid,a.attnum,'UPDATE')
                 is distinct from (a.attname in ('nome','foto_path','perfil_versao'))) then
           raise exception 'Perfil requer UPDATE apenas de nome, foto_path e perfil_versao';
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
