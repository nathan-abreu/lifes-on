# Leitura dos alertas — Semana 6

A tabela `public.alertas` já existe no Supabase configurado. Uma consulta real
somente de leitura confirmou os seis campos previstos e a ausência de
`chave_evento` (42703). IDs são bigint, data_hora é timestamp; status/tipo
aceitam texto. Não houve migração nem escrita remota nesta tarefa.

## SQL manual necessário

Execute todo o arquivo `migrations/alertas_leitura.sql` no SQL Editor do mesmo
projeto Supabase. Ele acrescenta somente chave_evento e um índice único em
(id_usuario, chave_evento). Não altera permissões, RLS, status existentes ou
autenticação. Registros legados sem chave são preservados. O schema completo
inclui a definição da tabela para instalações novas.

Após aplicar, abra Alertas e teste os botões. O backend precisa das permissões
SELECT/INSERT/UPDATE já configuradas para essa tabela; não foram presumidas nem
ampliadas. `python -m scripts.verificar_banco` confere as colunas, não a escrita.
Sem a migração/acesso, Alertas informa a pendência; Dashboard e demais módulos
continuam acessíveis. Não há estado de leitura fictício em memória.

## Persistência e identidade

Os alertas são detectados nas visitas às telas que já calculavam lembretes.
São inseridos na tabela existente com mensagem, tipo/destino, data_hora,
id_usuario da sessão e status `nao_lido`. O hash da identidade do evento é
armazenado em chave_evento:

- Treino: ID + horário agendado. Amanhã/hoje não muda a identidade; remarcar muda.
- Meta: ID + prazo + fase próxima/vencida. Não renotifica diariamente na mesma fase.
- Metas pendentes: conjunto dos IDs pendentes.
- Inatividade: data da última atividade. A mesma ausência não renotifica diariamente.
- Primeiro registro: identidade fixa por usuário.

O upsert usa ON CONFLICT DO NOTHING: nem visitas nem requisições concorrentes
sobrescrevem um status lido. O índice é a proteção de concorrência no banco.
Alertas antigos sem identidade não são associados automaticamente a eventos
atuais, pois isso exigiria adivinhar sua origem pelo texto.

Na página Alertas fica o histórico, inclusive depois de a situação terminar.
As mensagens são fotografias da geração, com data exibida: "amanhã" refere-se
àquela data. O Dashboard mantém seus lembretes dinâmicos atuais sem redesenho.
Seu sino e o das demais telas contam registros com status diferente de `lido`.
Status legado diferente de `lido` é tratado como não lido; nenhum registro é apagado.

POST /alertas/<id_alerta>/ler confere o dono e atualiza somente o registro dele.
POST /alertas/ler-todas atualiza somente linhas com id_usuario da sessão.
Ambos exigem autenticação e CSRF. Novo evento inserido depois continua não lido.

## Testes

40 testes locais com banco simulado cobrem persistência, recarga, contador,
leitura individual/em lote, novos eventos, mudança amanhã/hoje, vazio, falha
de acesso, CSRF, isolamento e regressão das funcionalidades existentes.
Chrome local cobre também os botões e o contador, além da Agenda, registro manual,
cronômetro, Progresso, Metas e Conquistas. Nenhuma gravação foi testada no Supabase
real nesta tarefa. SQL validado por parser PostgreSQL; isso não valida permissões,
constraints adicionais ou execução real. Não há dependências novas.

Nenhum recurso de XP, pontuação, níveis, ranking, Dicas ou notificação externa
foi implementado. O escopo permanece na Semana 6, dentro do projeto na Semana 7.
