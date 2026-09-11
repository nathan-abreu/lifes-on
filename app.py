import os
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from supabase import create_client
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")


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
        senha = request.form.get("senha")

        resposta = supabase.table("usuarios").select("*").eq("email", email).execute()

        if not resposta.data:
            flash("E-mail ou senha incorretos.")
            return redirect(url_for("login"))

        usuario = resposta.data[0]

        if not check_password_hash(usuario["senha_hash"], senha):
            flash("E-mail ou senha incorretos.")
            return redirect(url_for("login"))

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
    resposta = (
        supabase.table("atividades")
        .select("id_atividade,tipo_exercicio,duracao")
        .eq("id_usuario", session["id_usuario"])
        .order("data_registro", desc=True)
        .execute()
    )
    return render_template("dashboard.html", nome=session["nome"], atividades_registradas=resposta.data)


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
            "data_registro": datetime.utcnow().isoformat(),
            "id_usuario": session["id_usuario"],
        }).execute()

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
    tipo_exercicio = dados.get("tipo_exercicio")
    segundos_decorridos = dados.get("segundos_decorridos")

    if not tipo_exercicio or tipo_exercicio not in TIPOS_EXERCICIO:
        return jsonify({"erro": "Selecione um tipo de exercício válido."}), 400

    try:
        segundos_decorridos = int(segundos_decorridos)
    except (TypeError, ValueError):
        return jsonify({"erro": "Duração inválida."}), 400

    if segundos_decorridos < 30:
        return jsonify({"registrado": False, "motivo": "muito_curta"})

    duracao = round(segundos_decorridos / 60)
    if duracao < 1:
        duracao = 1

    supabase.table("atividades").insert({
        "tipo_exercicio": tipo_exercicio,
        "duracao": duracao,
        "frequencia": 1,
        "data_registro": datetime.utcnow().isoformat(),
        "id_usuario": session["id_usuario"],
    }).execute()

    return jsonify({"registrado": True, "tipo_exercicio": tipo_exercicio, "duracao": duracao})


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
