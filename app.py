import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/teste")
def teste_conexao():
    resposta = supabase.table("dicas").select("*").execute()
    return jsonify(resposta.data)


if __name__ == "__main__":
    app.run(debug=True)
