# Lifes On

Aplicativo Flask + Supabase para acompanhar atividades físicas, Agenda, perfil,
metas automáticas, progresso, conquistas, alertas, dicas e XP.

A etapa atual está documentada em [EVOLUCAO_PERFIL_METAS_XP.md](EVOLUCAO_PERFIL_METAS_XP.md):
perfil e fotos privadas, distância, Caminhada, metas por atividades, XP por tempo/distância
e níveis progressivos. Inclui arquivos, regras, testes, limitações e checklist.

As três migrações anteriores foram implantadas, conforme informado. A sondagem
somente de leitura confirmou suas colunas acessíveis em 09/10/2026. As novas
colunas ainda dependem de `evolucao_perfil_metas_xp_niveis.sql`; fotos dependem também
do bucket/policy propostos em `storage_perfis_privado.sql`. Nada foi aplicado remotamente.
Não iniciar a nova versão em produção sem essa revisão e validação.

Os relatórios anteriores (auditoria de XP, estabilização e redesign) permanecem
como histórico; as regras atuais e a ordem de implantação estão no novo guia acima.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Configure .env conforme .env.example e EVOLUCAO_PERFIL_METAS_XP.md; chave apenas no servidor.
.\.venv\Scripts\python.exe -m flask --app app run
```

Banco existente com as três migrações anteriores: diagnóstico somente leitura,
`migrations/evolucao_perfil_metas_xp_niveis.sql` e, para fotos,
`migrations/storage_perfis_privado.sql`, após revisão/autorização. **Não reaplicar
as migrações antigas sobre a evolução.** Ver os pré-requisitos e `.env` no novo guia.
Banco novo: `schema.sql`, depois evolução e Storage. Não aplicar o schema de instalação
como migração sobre dados existentes.
Não há execução automática de SQL remoto.

```powershell
.\.venv\Scripts\python.exe -m unittest -q
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m tests.browser_smoke
.\.venv\Scripts\python.exe -m tests.browser_semanas_8_9
.\.venv\Scripts\python.exe -m tests.browser_finalizacao
.\.venv\Scripts\python.exe -m tests.browser_evolucao
.\.venv\Scripts\python.exe -m scripts.verificar_banco --evolucao --detalhado
```

Testes de navegador usam Chrome e banco em memória. As instruções do teste SQL local
estão na documentação técnica. Dados fictícios existem somente nos testes.

As [Semanas 6/7](SEMANAS_6_7.md) e [leitura de alertas](ALERTAS_LEITURA.md) são o registro
histórico anterior; as regras atuais estão em EVOLUCAO_PERFIL_METAS_XP.md.

Validação PostgreSQL local (não acessa o Supabase):

```powershell
npm install --prefix "$env:TEMP\lifes-on-sql-validation" @electric-sql/pglite --no-audit --no-fund
$env:PGLITE_MODULE = "$env:TEMP\lifes-on-sql-validation\node_modules\@electric-sql\pglite"
node tests/sql_semanas_8_9.cjs
node tests/sql_seguranca.cjs
node tests/sql_defaults_xp.cjs
node tests/sql_indice_conquistas.cjs
node tests/sql_evolucao.cjs
node tests/sql_evolucao.cjs --date
node tests/sql_storage_perfis.cjs
```

Imagens: oito modalidades com ilustrações em `static/img/modalidades/`. Yoga e
Ciclismo receberam PNGs transparentes; artes anteriores e fallback foram preservados.
Conversão opcional com as dependências de desenvolvimento instaladas:
`python -m scripts.otimizar_modalidades`.

Cada registro é uma sessão; frequência foi retirada do formulário, com NULL para
sessões novas e valores legados preservados. Excluir atividade premiada estorna
o saldo da sessão; conquistas, metas e sequência são marcos históricos de recompensa única.
Abrir páginas não concede XP. Veja regras completas e pendências no relatório atual.
