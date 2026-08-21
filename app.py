import os
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
    return f"Bem-vindo, {session['nome']}!"


if __name__ == "__main__":
    app.run(debug=True)
