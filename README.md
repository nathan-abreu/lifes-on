# Lifes On

Aplicativo Flask + Supabase para acompanhar atividades físicas, Agenda, metas,
progresso, conquistas, alertas, dicas e XP.

A documentação atual da primeira versão está em [SEMANAS_8_9.md](SEMANAS_8_9.md).
Consulte as regras, migração, resultados e limitações antes de apresentar o sistema.
O [checklist da apresentação](CHECKLIST_APRESENTACAO.md) distingue testes locais e
validação ainda pendente no Supabase real.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Configure .env local com SUPABASE_URL, SUPABASE_KEY e FLASK_SECRET_KEY.
.\.venv\Scripts\python.exe -m flask --app app run
```

Banco existente: `migrations/semanas_8_9.sql`, após revisão/autorização e as migrações
anteriores. Banco novo: `schema.sql`. Não aplicar o schema de instalação como migração.
Não há execução automática de SQL remoto.

```powershell
.\.venv\Scripts\python.exe -m unittest -q
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m tests.browser_smoke
.\.venv\Scripts\python.exe -m tests.browser_semanas_8_9
```

Testes de navegador usam Chrome e banco em memória. As instruções do teste SQL local
estão na documentação técnica. Dados fictícios existem somente nos testes.

As [Semanas 6/7](SEMANAS_6_7.md) e [leitura de alertas](ALERTAS_LEITURA.md) são o registro
histórico anterior; as regras atuais de XP e vínculo da Agenda estão nas Semanas 8/9.
