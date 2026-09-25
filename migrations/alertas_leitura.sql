-- Execute integralmente no SQL Editor do Supabase.
-- A tabela public.alertas já existe no banco real. Não altera permissões/RLS.
begin;
alter table public.alertas add column if not exists chave_evento text;
-- Registros legados sem chave são preservados. NULL não conflita no índice.
create unique index if not exists alertas_usuario_evento_uidx
    on public.alertas (id_usuario, chave_evento);
notify pgrst, 'reload schema';
commit;
