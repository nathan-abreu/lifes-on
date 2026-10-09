# Lifes On

Diagnóstico real e correções de integração mais recentes:
[ESTABILIZACAO_INTEGRACAO.md](ESTABILIZACAO_INTEGRACAO.md).

Aplicativo Flask + Supabase para acompanhar atividades físicas, Agenda, metas,
progresso, conquistas, alertas, dicas e XP.

Para configurar o .env e aplicar as migrações na ordem correta, siga
[IMPLANTACAO_SEGURA.md](IMPLANTACAO_SEGURA.md).

A auditoria atual de segurança, pré-requisitos e validação está em
[AUDITORIA_XP.md](AUDITORIA_XP.md). O relatório de interface permanece em
[FINALIZACAO_PREMIUM.md](FINALIZACAO_PREMIUM.md).

**Bloqueio remoto confirmado:** faltam colunas das Semanas 8/9 e o livro de XP não
está acessível. A interface foi implementada e validada localmente, mas o salvamento
completo no Supabase depende das migrações autorizadas. Nenhum SQL remoto foi executado.
Consulte as regras, migração, resultados e limitações antes de apresentar o sistema.
O [checklist da apresentação](CHECKLIST_APRESENTACAO.md) distingue testes locais e
validação ainda pendente no Supabase real.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Configure .env conforme .env.example e AUDITORIA_XP.md; chave apenas no servidor.
.\.venv\Scripts\python.exe -m flask --app app run
```

Banco existente: primeiro `migrations/diagnostico_finalizacao.sql` (somente leitura);
depois, em manutenção e mediante autorização, `migrations/seguranca_backend.sql`,
`migrations/semanas_8_9.sql` e `migrations/finalizacao_premium.sql`, nessa ordem e
após as migrações anteriores. Configurar service_role no Flask antes de restringir
ACLs. Nenhuma dessas etapas altera RLS; revisar impacto em outros consumidores.
Banco novo: `schema.sql`. Não aplicar o schema de instalação como migração.
Não há execução automática de SQL remoto.

```powershell
.\.venv\Scripts\python.exe -m unittest -q
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m tests.browser_smoke
.\.venv\Scripts\python.exe -m tests.browser_semanas_8_9
.\.venv\Scripts\python.exe -m tests.browser_finalizacao
.\.venv\Scripts\python.exe -m scripts.verificar_banco --detalhado
```

Testes de navegador usam Chrome e banco em memória. As instruções do teste SQL local
estão na documentação técnica. Dados fictícios existem somente nos testes.

As [Semanas 6/7](SEMANAS_6_7.md) e [leitura de alertas](ALERTAS_LEITURA.md) são o registro
histórico anterior; as regras atuais de XP e vínculo da Agenda estão em FINALIZACAO_PREMIUM.md.

Validação PostgreSQL local (não acessa o Supabase):

```powershell
npm install --prefix "$env:TEMP\lifes-on-sql-validation" @electric-sql/pglite --no-audit --no-fund
$env:PGLITE_MODULE = "$env:TEMP\lifes-on-sql-validation\node_modules\@electric-sql\pglite"
node tests/sql_semanas_8_9.cjs
node tests/sql_seguranca.cjs
node tests/sql_defaults_xp.cjs
node tests/sql_indice_conquistas.cjs
```

Imagens: sete modalidades com ilustrações em `static/img/modalidades/`. Yoga e
Ciclismo receberam PNGs transparentes; artes anteriores e fallback foram preservados.
Conversão opcional com as dependências de desenvolvimento instaladas:
`python -m scripts.otimizar_modalidades`.

Cada registro é uma sessão; frequência foi retirada do formulário, com NULL para
sessões novas e valores legados preservados. Excluir atividade premiada estorna
20 XP; conquistas, metas e sequência são marcos históricos de recompensa única.
Abrir páginas não concede XP. Veja regras completas e pendências no relatório atual.
