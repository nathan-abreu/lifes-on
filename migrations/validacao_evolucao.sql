-- PÓS-MIGRAÇÃO, SOMENTE LEITURA. Cada contagem de divergências deve ser zero.
-- Não repara nem recalcula dados. Execute como postgres após evolucao_perfil_metas_xp_niveis.sql.
begin transaction read only;
select lifes_private.exigir_backend_privado();

-- Cada atividade v2 deve ter um original e um saldo igual ao valor atual.
-- Atividades excluídas devem ter saldo zero; bônus históricos ficam fora desta conta.
with originais as (
 select r.id_usuario,r.chave_evento,r.xp from public.recompensas_xp r
 where r.motivo='Atividade concluída (minutos e distância)'
), saldos as (
 select o.id_usuario,o.chave_evento,coalesce(a.xp_atual,0) as esperado,
 o.xp + coalesce((select sum(r.xp) from public.recompensas_xp r
  where r.id_usuario=o.id_usuario and (r.chave_evento='estorno:'||o.chave_evento
   or left(r.chave_evento,length('ajuste:'||o.chave_evento||':'))='ajuste:'||o.chave_evento||':')),0) as saldo
 from originais o left join public.atividades a on a.id_usuario=o.id_usuario
  and o.chave_evento='atividade:'||coalesce(a.chave_registro::text,a.id_atividade::text)
)
select count(*) as divergencias_saldo_atividade_v2 from saldos where saldo<>esperado;
select count(*) as atividades_v2_sem_lancamento from public.atividades a
where a.xp_versao=2 and not exists(select 1 from public.recompensas_xp r
 where r.id_usuario=a.id_usuario and r.chave_evento='atividade:'||coalesce(a.chave_registro::text,a.id_atividade::text));

-- Inclui estornos legados: a família contábil deve zerar, sem tocar em bônus.
select count(*) as divergencias_estornos_atividade from public.recompensas_xp r
where r.chave_evento like 'estorno:atividade:%'
 and lifes_private.saldo_atividade(r.id_usuario,substr(r.chave_evento,9)) is distinct from 0::bigint;

with esperado as (
 select m.*,coalesce((select sum(case m.metrica when 'minutos' then a.duracao
  when 'sessoes' then 1 else coalesce(a.distancia_km,0) end) from public.atividades a
  where a.id_usuario=m.id_usuario and (m.modalidade is null or m.modalidade=a.tipo_exercicio)
   and a.duracao between 1 and 1440
   and a.tipo_exercicio in ('Corrida','Caminhada','Ciclismo','Natação','Musculação','Yoga','Artes Marciais','Outros')
   and (m.metrica<>'km' or a.tipo_exercicio in ('Corrida','Caminhada','Ciclismo','Natação'))
   and (case when pg_typeof(a.data_registro)::text='date' then a.data_registro::date::timestamp at time zone 'America/Sao_Paulo'
    when pg_typeof(a.data_registro)::text='timestamp without time zone'
    then a.data_registro::timestamp at time zone 'UTC' else a.data_registro::timestamptz end)<=now()
   and (case when pg_typeof(a.data_registro)::text='date' then a.data_registro::date::timestamp at time zone 'America/Sao_Paulo'
    when pg_typeof(a.data_registro)::text='timestamp without time zone'
    then a.data_registro::timestamp at time zone 'UTC' else a.data_registro::timestamptz end
    at time zone 'America/Sao_Paulo')::date between m.inicio and m.prazo),0) as calculado
 from public.metas m where m.metrica is not null
)
select count(*) as divergencias_metas from esperado
where acumulado is distinct from calculado or progresso is distinct from
 (case when alvo>0 then least(100,floor(calculado*100/alvo))::integer else -1 end);

select count(*) as eventos_duplicados from (
 select id_usuario,chave_evento from public.recompensas_xp group by id_usuario,chave_evento having count(*)>1
) d;
select xp_versao,count(*) as sessoes from public.atividades group by xp_versao order by xp_versao;
commit;
