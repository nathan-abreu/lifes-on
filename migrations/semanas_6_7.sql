-- Execute integralmente no SQL Editor do Supabase.
-- Atualização mínima do banco existente, conferido na auditoria final.
-- Preserve SUPABASE_KEY e as permissões/RLS atuais. Não exige service_role.
-- Pré-requisito: tabelas existentes do projeto (ver schema.sql para banco novo).
-- Para conferir permissões e constraints sem alterações, use
-- migrations/auditoria_somente_leitura.sql antes desta migração.
begin;

-- Não modifica horario, lembrete, IDs ou registros existentes.
alter table public.agenda add column if not exists titulo varchar(120)
    not null default 'Treino agendado';

-- Se houver duplicações preexistentes, falha e reverte a transação; não apaga dados.
create unique index if not exists usuario_conquista_usuario_conquista_uidx
    on public.usuario_conquista (id_usuario, id_conquista);

-- Mantém os três nomes já cadastrados. Não altera pontos existentes.
-- Pontos das novas conquistas = 0; nenhuma lógica de XP é implementada.
insert into public.conquistas (nome, descricao, pontos)
select s.nome, s.descricao, 0 from (values
    ('Primeiro passo', 'Registrou a primeira atividade física.'),
    ('Semana cheia', 'Treinou sete dias seguidos.'),
    ('Meta batida', 'Concluiu a primeira meta.'),
    ('Em Movimento', 'Realizou cinco atividades.'),
    ('Foco Total', 'Realizou dez atividades.'),
    ('Veterano', 'Realizou trinta atividades.')
) as s(nome, descricao)
where not exists (select 1 from public.conquistas c where c.nome = s.nome);

create index if not exists atividades_usuario_data_idx on public.atividades (id_usuario, data_registro);
create index if not exists metas_usuario_prazo_idx on public.metas (id_usuario, prazo);
create index if not exists agenda_usuario_horario_idx on public.agenda (id_usuario, horario);

-- Não executa GRANT, REVOKE, mudanças de RLS/policies ou de sequências.

notify pgrst, 'reload schema';

commit;
