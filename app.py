import os
import secrets
from datetime import date, datetime, time, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from httpx import HTTPError
from postgrest.exceptions import APIError
from banco import criar_cliente
from alertas import preparar_alertas, sincronizar_alertas
from werkzeug.security import check_password_hash, generate_password_hash
from progresso import (
    FUSO, agora_local, calcular_conquistas, calcular_progresso, data_atividade,
    gerar_alertas, preparar_treinos,
)

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

supabase = criar_cliente(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


@app.context_processor
def contexto_formularios():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    contexto = {"csrf_token": session["csrf_token"]}
    if "id_usuario" in session:
        try:
            contexto["alertas_nao_lidos"] = sum(a.get("status") != "lido" for a in listar_do_usuario("alertas", ["id_alerta"]))
        except (APIError, HTTPError):
            contexto["alertas_nao_lidos"] = None
    return contexto


@app.before_request
def proteger_formularios():
    if request.method == "POST":
        enviado = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        esperado = session.get("csrf_token", "")
        if not esperado or not secrets.compare_digest(enviado.encode("utf-8"), esperado.encode("utf-8")):
            abort(400, description="Formulário expirado. Atualize a página e tente novamente.")


@app.errorhandler(APIError)
@app.errorhandler(HTTPError)
def banco_indisponivel(erro):
    # Não registrar respostas do banco que possam conter dados pessoais.
    app.logger.warning("Falha de acesso ao banco: %s (%s)", type(erro).__name__, getattr(erro, "code", "rede"))
    mensagem = mensagem_erro_banco(erro)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"erro": mensagem}), 503
    return render_template("indisponivel.html", mensagem=mensagem), 503


def mensagem_erro_banco(erro):
    codigo = getattr(erro, "code", "")
    if codigo in ("42P01", "PGRST205", "PGRST204", "42703"):
        return "A estrutura do banco precisa ser atualizada. Solicite a aplicação da migração das semanas 6 e 7."
    if codigo in ("42501", "PGRST301", "PGRST302", "PGRST303", "401", "403"):
        return "O banco recusou o acesso. Confira a chave e as permissões configuradas no servidor."
    return "Não foi possível acessar o banco. Confira a conexão e tente novamente."


def listar_do_usuario(tabela, ordem, campos="*"):
    """Paginação evita truncar métricas no limite de linhas do Supabase."""
    linhas = []
    tamanho = 500
    while True:
        consulta = supabase.table(tabela).select(campos).eq("id_usuario", session["id_usuario"])
        for coluna in ordem:
            consulta = consulta.order(coluna)
        lote = consulta.range(len(linhas), len(linhas) + tamanho - 1).execute().data or []
        linhas.extend(lote)
        if len(lote) < tamanho:
            return linhas


def consultar_agenda():
    return listar_do_usuario("agenda", ["horario", "id_agenda"], "id_agenda,id_usuario,horario,lembrete,titulo")


def sincronizar_conquistas(resumo, novas_obtidas=None):
    """Registra obtenções uma única vez; nunca revoga uma conquista obtida."""
    regras = {c["nome"]: c for c in calcular_conquistas(resumo)}
    catalogo = supabase.table("conquistas").select("id_conquista,nome,descricao").order("id_conquista").execute().data or []
    catalogo = [c for c in catalogo if c["nome"] in regras]
    obtidas = listar_do_usuario("usuario_conquista", ["id_conquista"])
    ids_obtidos = {c["id_conquista"] for c in obtidas}
    novas = [
        {"id_usuario": session["id_usuario"], "id_conquista": c["id_conquista"],
         "data_obtencao": agora_local().date().isoformat()}
        for c in catalogo if regras[c["nome"]]["requisito_atingido"] and c["id_conquista"] not in ids_obtidos
    ]
    if novas:
        # ON CONFLICT DO NOTHING protege contra duas requisições simultâneas.
        inseridas = supabase.table("usuario_conquista").upsert(
            novas, on_conflict="id_usuario,id_conquista", ignore_duplicates=True
        ).execute().data or []
        if novas_obtidas is not None:
            ids_inseridos = {c["id_conquista"] for c in inseridas}
            novas_obtidas.extend({"nome": c["nome"], "descricao": c["descricao"]}
                                 for c in catalogo if c["id_conquista"] in ids_inseridos)
        obtidas = listar_do_usuario("usuario_conquista", ["id_conquista"])
    datas = {c["id_conquista"]: c["data_obtencao"] for c in obtidas}
    resultado = []
    for item in catalogo:
        conquista = {**regras[item["nome"]], **item}
        conquista["condicao"] = regras[item["nome"]]["descricao"]
        conquista["desbloqueada"] = item["id_conquista"] in datas
        conquista["data_obtencao"] = datas.get(item["id_conquista"])
        conquista["data_formatada"] = formatar_data_br(conquista["data_obtencao"])
        if conquista["desbloqueada"]:
            conquista.update(progresso=conquista["objetivo"], percentual=100)
        resultado.append(conquista)
    return resultado


def verificar_conquistas_apos_salvar(novas_obtidas=None):
    try:
        atividades = listar_do_usuario("atividades", ["id_atividade"])
        metas = listar_do_usuario("metas", ["id_meta"])
        sincronizar_conquistas(calcular_progresso(atividades, metas, agora_local().date()), novas_obtidas)
        return True
    except (APIError, HTTPError) as erro:
        # A operação principal já foi salva. Não induzir nova gravação por retry.
        app.logger.warning("Conquistas pendentes de atualização (%s)", getattr(erro, "code", "rede"))
        flash("Seu registro foi salvo, mas as conquistas não puderam ser atualizadas. " + mensagem_erro_banco(erro))
        return False


def dados_acompanhamento():
    agora = agora_local()
    atividades = listar_do_usuario("atividades", ["data_registro", "id_atividade"])
    metas = listar_do_usuario("metas", ["prazo", "id_meta"])
    erro_agenda = None
    try:
        treinos = consultar_agenda()
    except (APIError, HTTPError) as erro:
        treinos = []
        erro_agenda = mensagem_erro_banco(erro)
        app.logger.warning("Agenda indisponível (%s)", getattr(erro, "code", "rede"))
    treinos = preparar_treinos(treinos, agora)
    resumo = calcular_progresso(atividades, metas, agora.date())
    erro_conquistas = None
    try:
        conquistas = sincronizar_conquistas(resumo)
        if not conquistas:
            erro_conquistas = "O catálogo de conquistas ainda não foi configurado no banco."
    except (APIError, HTTPError) as erro:
        conquistas = []
        erro_conquistas = mensagem_erro_banco(erro)
        app.logger.warning("Conquistas indisponíveis (%s)", getattr(erro, "code", "rede"))
    for atividade in atividades:
        dia = data_atividade(atividade.get("data_registro"))
        atividade["data_formatada"] = dia.strftime("%d/%m/%Y") if dia else "Data não informada"
        atividade["data_relativa"] = ("Hoje" if dia == agora.date() else
                                      "Ontem" if dia and (agora.date() - dia).days == 1 else
                                      atividade["data_formatada"])
    for meta in metas:
        meta["progresso"] = max(0, min(100, int(meta.get("progresso") or 0)))
        meta["prazo_formatado"] = formatar_data_br(meta["prazo"])
    proximos = [t for t in treinos if not t["passado"]]
    gerados = gerar_alertas(resumo, metas, treinos, agora)
    erro_alertas = None
    historico_alertas = []
    try:
        existentes = listar_do_usuario("alertas", ["id_alerta"])
        sincronizar_alertas(supabase, session["id_usuario"], gerados, existentes, agora)
        historico_alertas = preparar_alertas(listar_do_usuario("alertas", ["id_alerta"]))
        historico_alertas.reverse()
    except (APIError, HTTPError) as erro:
        erro_alertas = "Não foi possível carregar o estado de leitura. Confira a migração alertas_leitura.sql e o acesso à tabela alertas."
        app.logger.warning("Alertas indisponíveis (%s)", getattr(erro, "code", "rede"))
    return {
        "nome": session["nome"], "resumo": resumo, "metas": metas,
        "atividades_registradas": list(reversed(atividades)),
        "treinos": treinos, "agenda_disponivel": erro_agenda is None, "erro_agenda": erro_agenda,
        "proximo_treino": proximos[0] if proximos else None,
        "conquistas": conquistas,
        "erro_conquistas": erro_conquistas,
        "meta_atual": next((m for m in metas if m["progresso"] < 100), None),
        "ultima_conquista": max((c for c in conquistas if c["desbloqueada"]),
                                key=lambda c: (c["data_obtencao"] or "", c["id_conquista"]), default=None),
        "total_conquistas": sum(c["desbloqueada"] for c in conquistas),
        "alertas": gerados, "historico_alertas": historico_alertas, "erro_alertas": erro_alertas,
    }


def login_obrigatorio(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        if "id_usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorada


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/teste")
def teste_conexao():
    resposta = supabase.table("dicas").select("*").execute()
    return jsonify(resposta.data)


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form.get("nome")
        email = request.form.get("email")
        senha = request.form.get("senha")

        if not nome or not email or not senha:
            flash("Preencha todos os campos.")
            return redirect(url_for("cadastro"))

        existente = supabase.table("usuarios").select("id_usuario").eq("email", email).execute()
        if existente.data:
            flash("Esse e-mail já está cadastrado.")
            return redirect(url_for("cadastro"))

        senha_hash = generate_password_hash(senha)
        supabase.table("usuarios").insert({
            "nome": nome,
            "email": email,
            "senha_hash": senha_hash
        }).execute()

        flash("Cadastro feito! Faça login.")
        return redirect(url_for("login"))

    return render_template("cadastro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha", "")

        resposta = supabase.table("usuarios").select("*").eq("email", email).execute()

        if not resposta.data:
            flash("E-mail ou senha incorretos.")
            return redirect(url_for("login"))

        usuario = resposta.data[0]

        if not check_password_hash(usuario["senha_hash"], senha):
            flash("E-mail ou senha incorretos.")
            return redirect(url_for("login"))

        session.clear()
        session["id_usuario"] = usuario["id_usuario"]
        session["nome"] = usuario["nome"]
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_obrigatorio
def dashboard():
    dados = dados_acompanhamento()
    hoje = agora_local().date()
    disponiveis = [t for t in dados["treinos"] if t["instante"].date() >= hoje]
    for treino in disponiveis:
        dias = (treino["instante"].date() - hoje).days
        treino["quando"] = "Hoje" if dias == 0 else "Amanhã" if dias == 1 else treino["data_formatada"]
    return render_template("dashboard.html", treinos_disponiveis=disponiveis,
                           tipos_exercicio=TIPOS_EXERCICIO, **dados)


@app.route("/progresso")
@login_obrigatorio
def progresso():
    return render_template("progresso.html", **dados_acompanhamento())


@app.route("/alertas")
@login_obrigatorio
def alertas():
    return render_template("alertas.html", **dados_acompanhamento())


@app.route("/alertas/<int:id_alerta>/ler", methods=["POST"])
@login_obrigatorio
def alerta_ler(id_alerta):
    registro = (supabase.table("alertas").select("id_alerta")
                .eq("id_alerta", id_alerta).eq("id_usuario", session["id_usuario"]).execute().data)
    if not registro:
        abort(404)
    (supabase.table("alertas").update({"status": "lido"})
     .eq("id_alerta", id_alerta).eq("id_usuario", session["id_usuario"]).execute())
    return redirect(url_for("alertas"))


@app.route("/alertas/ler-todas", methods=["POST"])
@login_obrigatorio
def alertas_ler_todas():
    supabase.table("alertas").update({"status": "lido"}).eq("id_usuario", session["id_usuario"]).execute()
    return redirect(url_for("alertas"))


@app.route("/conquistas")
@login_obrigatorio
def conquistas():
    return render_template("conquistas.html", **dados_acompanhamento())


@app.route("/agenda")
@login_obrigatorio
def agenda():
    try:
        treinos = preparar_treinos(consultar_agenda(), agora_local())
        return render_template("agenda.html", nome=session["nome"], treinos=treinos, agenda_disponivel=True)
    except (APIError, HTTPError) as erro:
        app.logger.warning("Não foi possível listar a agenda (%s)", getattr(erro, "code", "rede"))
        return render_template("agenda.html", nome=session["nome"], treinos=[],
                               agenda_disponivel=False, erro_agenda=mensagem_erro_banco(erro)), 503


def validar_treino(formulario):
    titulo = formulario.get("titulo", "").strip()
    descricao = formulario.get("descricao", "").strip()
    if not titulo or len(titulo) > 120:
        raise ValueError("Informe um título de até 120 caracteres.")
    if len(descricao) > 2000:
        raise ValueError("A descrição deve ter até 2000 caracteres.")
    try:
        dia = date.fromisoformat(formulario.get("data", ""))
        horario = time.fromisoformat(formulario.get("horario", ""))
        if horario.tzinfo or horario.second or horario.microsecond:
            raise ValueError
    except ValueError:
        raise ValueError("Informe data e horário válidos (horário de Brasília).") from None
    instante = datetime.combine(dia, horario, FUSO)
    if instante < agora_local():
        raise ValueError("Não é possível agendar para uma data ou horário passado.")
    return {"titulo": titulo, "lembrete": descricao, "horario": instante.replace(tzinfo=None).isoformat()}


def formulario_treino(treino=None, modo="novo", erro_banco=None):
    return render_template("treino_form.html", nome=session["nome"], treino=treino,
                           modo=modo, hoje=agora_local().date().isoformat(), erro_banco=erro_banco)


@app.route("/agenda/novo", methods=["GET", "POST"])
@login_obrigatorio
def treino_novo():
    if request.method == "POST":
        try:
            dados = validar_treino(request.form)
        except ValueError as erro:
            flash(str(erro))
            return formulario_treino(request.form), 400
        dados["id_usuario"] = session["id_usuario"]
        try:
            supabase.table("agenda").insert(dados).execute()
        except (APIError, HTTPError) as erro:
            return formulario_treino(request.form, erro_banco="Treino não salvo. " + mensagem_erro_banco(erro)), 503
        flash("Treino agendado com sucesso!")
        return redirect(url_for("agenda"))
    try:
        consultar_agenda()  # Confirma também as colunas antes de liberar o formulário.
    except (APIError, HTTPError) as erro:
        return formulario_treino(erro_banco=mensagem_erro_banco(erro)), 503
    return formulario_treino()


@app.route("/agenda/editar/<int:id_treino>", methods=["GET", "POST"])
@login_obrigatorio
def treino_editar(id_treino):
    resposta = (supabase.table("agenda").select("*")
                .eq("id_agenda", id_treino).eq("id_usuario", session["id_usuario"]).execute())
    if not resposta.data:
        abort(404)
    treino = preparar_treinos(resposta.data, agora_local())[0]
    treino["horario"] = treino["hora_formulario"]
    if request.method == "POST":
        try:
            dados = validar_treino(request.form)
        except ValueError as erro:
            flash(str(erro))
            return formulario_treino(request.form, "editar"), 400
        try:
            (supabase.table("agenda").update(dados)
             .eq("id_agenda", id_treino).eq("id_usuario", session["id_usuario"]).execute())
        except (APIError, HTTPError) as erro:
            return formulario_treino(request.form, "editar", "Alteração não salva. " + mensagem_erro_banco(erro)), 503
        flash("Treino atualizado!")
        return redirect(url_for("agenda"))
    return formulario_treino(treino, "editar")


@app.route("/agenda/excluir/<int:id_treino>", methods=["POST"])
@login_obrigatorio
def treino_excluir(id_treino):
    (supabase.table("agenda").delete()
     .eq("id_agenda", id_treino).eq("id_usuario", session["id_usuario"]).execute())
    flash("Solicitação de exclusão processada.")
    return redirect(url_for("agenda"))


TIPOS_EXERCICIO = ["Corrida", "Musculação", "Ciclismo", "Natação", "Yoga", "Outros"]


@app.route("/atividades")
@login_obrigatorio
def atividades():
    resposta = (
        supabase.table("atividades")
        .select("*")
        .eq("id_usuario", session["id_usuario"])
        .order("data_registro", desc=True)
        .execute()
    )
    return render_template("atividades.html", nome=session["nome"], atividades=resposta.data)


@app.route("/atividades/nova", methods=["GET", "POST"])
@login_obrigatorio
def atividade_nova():
    if request.method == "POST":
        tipo_exercicio = request.form.get("tipo_exercicio")
        duracao = request.form.get("duracao")
        frequencia = request.form.get("frequencia")

        if not tipo_exercicio or not duracao or not frequencia:
            flash("Preencha todos os campos.")
            return redirect(url_for("atividade_nova"))

        try:
            duracao = int(duracao)
            frequencia = int(frequencia)
        except ValueError:
            flash("Duração e frequência devem ser números.")
            return redirect(url_for("atividade_nova"))

        if duracao <= 0:
            flash("A duração precisa ser maior que zero.")
            return redirect(url_for("atividade_nova"))

        if frequencia < 1 or frequencia > 7:
            flash("A frequência deve ser entre 1 e 7 vezes por semana.")
            return redirect(url_for("atividade_nova"))

        supabase.table("atividades").insert({
            "tipo_exercicio": tipo_exercicio,
            "duracao": duracao,
            "frequencia": frequencia,
            "data_registro": datetime.now(timezone.utc).isoformat(),
            "id_usuario": session["id_usuario"],
        }).execute()

        verificar_conquistas_apos_salvar()
        flash("Atividade registrada com sucesso!")
        return redirect(url_for("atividades"))

    return render_template(
        "atividade_form.html",
        nome=session["nome"],
        modo="nova",
        atividade=None,
        tipos_exercicio=TIPOS_EXERCICIO,
    )


@app.route("/atividades/editar/<int:id_atividade>", methods=["GET", "POST"])
@login_obrigatorio
def atividade_editar(id_atividade):
    resposta = (
        supabase.table("atividades")
        .select("*")
        .eq("id_atividade", id_atividade)
        .eq("id_usuario", session["id_usuario"])
        .execute()
    )
    if not resposta.data:
        flash("Atividade não encontrada.")
        return redirect(url_for("atividades"))

    atividade = resposta.data[0]

    if request.method == "POST":
        tipo_exercicio = request.form.get("tipo_exercicio")
        duracao = request.form.get("duracao")
        frequencia = request.form.get("frequencia")

        if not tipo_exercicio or not duracao or not frequencia:
            flash("Preencha todos os campos.")
            return redirect(url_for("atividade_editar", id_atividade=id_atividade))

        try:
            duracao = int(duracao)
            frequencia = int(frequencia)
        except ValueError:
            flash("Duração e frequência devem ser números.")
            return redirect(url_for("atividade_editar", id_atividade=id_atividade))

        if duracao <= 0:
            flash("A duração precisa ser maior que zero.")
            return redirect(url_for("atividade_editar", id_atividade=id_atividade))

        if frequencia < 1 or frequencia > 7:
            flash("A frequência deve ser entre 1 e 7 vezes por semana.")
            return redirect(url_for("atividade_editar", id_atividade=id_atividade))

        supabase.table("atividades").update({
            "tipo_exercicio": tipo_exercicio,
            "duracao": duracao,
            "frequencia": frequencia,
        }).eq("id_atividade", id_atividade).eq("id_usuario", session["id_usuario"]).execute()

        verificar_conquistas_apos_salvar()
        flash("Atividade atualizada com sucesso!")
        return redirect(url_for("atividades"))

    return render_template(
        "atividade_form.html",
        nome=session["nome"],
        modo="editar",
        atividade=atividade,
        tipos_exercicio=TIPOS_EXERCICIO,
    )


@app.route("/atividades/excluir/<int:id_atividade>", methods=["POST"])
@login_obrigatorio
def atividade_excluir(id_atividade):
    supabase.table("atividades").delete().eq("id_atividade", id_atividade).eq(
        "id_usuario", session["id_usuario"]
    ).execute()

    flash("Atividade excluída.")
    return redirect(url_for("atividades"))


@app.route("/atividades/concluir_timer", methods=["POST"])
@login_obrigatorio
def atividade_concluir_timer():
    dados = request.get_json(silent=True) or {}
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos."}), 400
    tipo_exercicio = dados.get("tipo_exercicio")
    segundos_decorridos = dados.get("segundos_decorridos")

    if not isinstance(tipo_exercicio, str) or tipo_exercicio not in TIPOS_EXERCICIO:
        return jsonify({"erro": "Selecione um tipo de exercício válido."}), 400

    if type(segundos_decorridos) is not int or not 0 <= segundos_decorridos <= 86400:
        return jsonify({"erro": "Duração inválida."}), 400

    if segundos_decorridos < 30:
        return jsonify({"registrado": False, "motivo": "muito_curta"})

    # O título é livre na Agenda; a modalidade é confirmada pelo usuário.
    # Nunca confiar no título/dono enviados pelo navegador.
    titulo_treino = None
    if "id_agenda" in dados:
        if type(dados["id_agenda"]) is not int or dados["id_agenda"] <= 0:
            return jsonify({"erro": "Treino inválido."}), 400
        treinos = (supabase.table("agenda").select("id_agenda,titulo")
                   .eq("id_agenda", dados["id_agenda"])
                   .eq("id_usuario", session["id_usuario"]).execute().data)
        if not treinos:
            return jsonify({"erro": "Treino não encontrado na sua agenda. Confira se ele foi excluído."}), 404
        titulo_treino = treinos[0]["titulo"]

    # Minutos inteiros, arredondando meio minuto para cima (igual à confirmação).
    duracao = max(1, (segundos_decorridos + 30) // 60)

    supabase.table("atividades").insert({
        "tipo_exercicio": tipo_exercicio,
        "duracao": duracao,
        "frequencia": 1,
        "data_registro": datetime.now(timezone.utc).isoformat(),
        "id_usuario": session["id_usuario"],
    }).execute()

    novas_conquistas = []
    conquistas_atualizadas = verificar_conquistas_apos_salvar(novas_conquistas)
    return jsonify({"registrado": True, "tipo_exercicio": tipo_exercicio, "duracao": duracao,
                    "titulo_treino": titulo_treino,
                    "conquistas_atualizadas": conquistas_atualizadas,
                    "novas_conquistas": novas_conquistas})


def formatar_data_br(data_iso):
    try:
        return datetime.strptime(data_iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return data_iso


def mensagem_incentivo(progresso):
    if progresso >= 100:
        return "Meta concluída! Parabéns"
    if progresso >= 60:
        return "Quase lá! Continue assim."
    if progresso >= 1:
        return "Você está evoluindo"
    return "Vamos começar? Registre seu progresso."


@app.route("/metas")
@login_obrigatorio
def metas():
    resposta = (
        supabase.table("metas")
        .select("*")
        .eq("id_usuario", session["id_usuario"])
        .order("prazo")
        .execute()
    )
    lista_metas = resposta.data
    for meta in lista_metas:
        meta["progresso"] = int(meta["progresso"])
        meta["prazo_formatado"] = formatar_data_br(meta["prazo"])
        meta["mensagem_incentivo"] = mensagem_incentivo(meta["progresso"])

    return render_template("metas.html", nome=session["nome"], metas=lista_metas)


@app.route("/metas/nova", methods=["GET", "POST"])
@login_obrigatorio
def meta_nova():
    if request.method == "POST":
        descricao = request.form.get("descricao", "").strip()
        prazo = request.form.get("prazo")

        if not descricao:
            flash("A meta precisa de um objetivo definido.")
            return redirect(url_for("meta_nova"))

        try:
            datetime.strptime(prazo, "%Y-%m-%d")
        except (TypeError, ValueError):
            flash("Informe um prazo válido.")
            return redirect(url_for("meta_nova"))

        supabase.table("metas").insert({
            "descricao": descricao,
            "prazo": prazo,
            "progresso": 0,
            "id_usuario": session["id_usuario"],
        }).execute()

        flash("Meta criada com sucesso!")
        return redirect(url_for("metas"))

    return render_template("meta_form.html", nome=session["nome"], modo="nova", meta=None)


@app.route("/metas/editar/<int:id_meta>", methods=["GET", "POST"])
@login_obrigatorio
def meta_editar(id_meta):
    resposta = (
        supabase.table("metas")
        .select("*")
        .eq("id_meta", id_meta)
        .eq("id_usuario", session["id_usuario"])
        .execute()
    )
    if not resposta.data:
        flash("Meta não encontrada.")
        return redirect(url_for("metas"))

    meta = resposta.data[0]
    meta["progresso"] = int(meta["progresso"])

    if request.method == "POST":
        descricao = request.form.get("descricao", "").strip()
        prazo = request.form.get("prazo")
        progresso = request.form.get("progresso")

        if not descricao:
            flash("A meta precisa de um objetivo definido.")
            return redirect(url_for("meta_editar", id_meta=id_meta))

        try:
            datetime.strptime(prazo, "%Y-%m-%d")
        except (TypeError, ValueError):
            flash("Informe um prazo válido.")
            return redirect(url_for("meta_editar", id_meta=id_meta))

        try:
            progresso = int(progresso)
        except (TypeError, ValueError):
            flash("O progresso deve ser um número.")
            return redirect(url_for("meta_editar", id_meta=id_meta))

        progresso = max(0, min(100, progresso))

        supabase.table("metas").update({
            "descricao": descricao,
            "prazo": prazo,
            "progresso": progresso,
        }).eq("id_meta", id_meta).eq("id_usuario", session["id_usuario"]).execute()

        verificar_conquistas_apos_salvar()
        flash("Meta atualizada com sucesso!")
        return redirect(url_for("metas"))

    return render_template("meta_form.html", nome=session["nome"], modo="editar", meta=meta)


@app.route("/metas/excluir/<int:id_meta>", methods=["POST"])
@login_obrigatorio
def meta_excluir(id_meta):
    supabase.table("metas").delete().eq("id_meta", id_meta).eq(
        "id_usuario", session["id_usuario"]
    ).execute()

    flash("Meta excluída.")
    return redirect(url_for("metas"))


if __name__ == "__main__":
    app.run(debug=True)
