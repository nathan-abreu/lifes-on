import os
import secrets
from io import BytesIO
from storage3.exceptions import StorageApiError
from evolucao import validar_distancia, validar_meta, quantidade, data_para_banco
from perfil import validar_nome, preparar_foto, caminho_proprio
from uuid import uuid4
from recompensas import validar_chave, resumir_recompensas
from datetime import date, datetime, time, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    g,
    send_file,
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
from banco import criar_cliente, chave_do_servidor
from erros_banco import classificar_erro
from modalidades import TIPOS_EXERCICIO, imagem_modalidade
from werkzeug.exceptions import HTTPException
from alertas import preparar_alertas, sincronizar_alertas
from werkzeug.security import check_password_hash, generate_password_hash
from progresso import (
    FUSO, agora_local, calcular_conquistas, calcular_progresso, data_atividade,
    gerar_alertas, preparar_treinos,
)

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = chave_do_servidor()

supabase = criar_cliente(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.add_template_filter(quantidade, 'quantidade')
app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=6*1024*1024)


@app.context_processor
def contexto_formularios():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    contexto = {"csrf_token": session["csrf_token"], "chave_registro": str(uuid4()),
                "feedback_recompensa": session.pop("feedback_recompensa", None),
                "data_hoje_iso": agora_local().date().isoformat(),
                "imagem_modalidade": imagem_modalidade, "tipos_exercicio": TIPOS_EXERCICIO}
    if "id_usuario" in session:
        try:
            usuario = usuario_perfil(obrigatorio=False)
            contexto['perfil_foto_disponivel'] = bool(usuario and caminho_proprio(usuario.get('foto_path'), session['id_usuario']))
            if usuario:
                session['nome'] = usuario['nome']
                contexto['nome_perfil'] = usuario['nome']
        except (APIError, HTTPError) as erro:
            contexto['perfil_foto_disponivel'] = False
            mensagem_erro_banco(erro)
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
    mensagem = mensagem_erro_banco(erro)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"erro": mensagem}), 503
    return render_template("indisponivel.html", mensagem=mensagem), 503


def mensagem_erro_banco(erro):
    codigo, categoria, mensagem = classificar_erro(erro)
    # Endpoint não inclui IDs, query string, e-mail ou valores de formulários.
    app.logger.warning("Banco: rota=%s metodo=%s categoria=%s codigo=%s tipo=%s",
                       request.endpoint, request.method, categoria, codigo, type(erro).__name__)
    return mensagem


@app.errorhandler(HTTPException)
def erro_http(erro):
    if request.is_json or request.path.startswith("/api/"):
        return jsonify(erro=erro.description), erro.code
    return erro


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
    return listar_do_usuario("agenda", ["horario", "id_agenda"], "*")


def sincronizar_conquistas(resumo, novas_obtidas=None, salvar=True):
    """Registra obtenções uma única vez; nunca revoga uma conquista obtida."""
    regras = {c["nome"]: c for c in calcular_conquistas(resumo)}
    catalogo = supabase.table("conquistas").select("id_conquista,nome,descricao").order("id_conquista").execute().data or []
    nomes_canonicos = {nome.casefold(): nome for nome in regras}
    for item in catalogo:
        item["nome"] = nomes_canonicos.get(item["nome"].strip().casefold(), item["nome"])
    nomes = set()
    catalogo_unico = []
    obtidas = listar_do_usuario("usuario_conquista", ["id_conquista"])
    ids_obtidos = {c["id_conquista"] for c in obtidas}
    # Duplicações históricas do catálogo não concedem o mesmo marco outra vez.
    for c in sorted(catalogo, key=lambda c: (c["id_conquista"] not in ids_obtidos, c["id_conquista"])):
        if c["nome"] in regras and c["nome"] not in nomes:
            catalogo_unico.append(c)
            nomes.add(c["nome"])
    catalogo = catalogo_unico
    novas = [
        {"id_usuario": session["id_usuario"], "id_conquista": c["id_conquista"],
         "data_obtencao": agora_local().date().isoformat()}
        for c in catalogo if regras[c["nome"]]["requisito_atingido"] and c["id_conquista"] not in ids_obtidos
    ]
    if novas and salvar:
        # ON CONFLICT DO NOTHING protege contra duas requisições simultâneas.
        inseridas = supabase.table("usuario_conquista").upsert(
            novas, on_conflict="id_usuario,id_conquista", ignore_duplicates=True
        ).execute().data or []
        if novas_obtidas is not None:
            ids_inseridos = {c["id_conquista"] for c in inseridas}
            novas_obtidas.extend({"id_conquista": c["id_conquista"], "nome": c["nome"], "descricao": c["descricao"]}
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


def verificar_conquistas_apos_salvar(novas_obtidas=None, registro_salvo=True):
    try:
        atividades = listar_do_usuario("atividades", ["id_atividade"])
        metas = listar_do_usuario("metas", ["id_meta"])
        sincronizar_conquistas(calcular_progresso(atividades, metas, agora_local().date()), novas_obtidas)
        return True
    except (APIError, HTTPError) as erro:
        # A operação principal já foi salva. Não induzir nova gravação por retry.
        app.logger.warning("Conquistas pendentes de atualização (%s)", getattr(erro, "code", "rede"))
        prefixo = ("Seu registro foi salvo, mas as conquistas não puderam ser atualizadas. "
                   if registro_salvo else "A verificação das conquistas não pôde ser concluída. ")
        flash(prefixo + mensagem_erro_banco(erro))
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
        conquistas = sincronizar_conquistas(resumo, salvar=False)
        if not conquistas:
            erro_conquistas = "As conquistas estão temporariamente indisponíveis."
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
    proximos = [t for t in treinos if not t["passado"] and not t.get("realizado_em")]
    gerados = gerar_alertas(resumo, metas, treinos, agora)
    erro_alertas = None
    historico_alertas = []
    try:
        existentes = listar_do_usuario("alertas", ["id_alerta"])
        sincronizar_alertas(supabase, session["id_usuario"], gerados, existentes, agora)
        historico_alertas = preparar_alertas(listar_do_usuario("alertas", ["id_alerta"]))
        historico_alertas.reverse()
    except (APIError, HTTPError) as erro:
        erro_alertas = "Não foi possível carregar seus alertas. Tente novamente em instantes."
        app.logger.warning("Alertas indisponíveis (%s)", getattr(erro, "code", "rede"))
    return {
        "nome": session["nome"], "xp": consultar_xp(), "resumo": resumo, "metas": metas,
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


def consultar_xp(estrito=False):
    try:
        registros = listar_do_usuario("recompensas_xp", ["id_recompensa"])
        return {**resumir_recompensas(registros), "historico": list(reversed(registros)), "disponivel": True}
    except (APIError, HTTPError) as erro:
        if estrito:
            raise  # Preserva 42501, 42703, rede etc.; nunca inventa PGRST205.
        return {"disponivel": False, "erro": mensagem_erro_banco(erro)}


def exigir_xp():
    return consultar_xp(estrito=True)


def preparar_recompensa(antes, novas=None, evento=None, transacao=None):
    depois = consultar_xp()
    if not antes.get("disponivel") or not depois.get("disponivel"):
        return None
    ids = {r["id_recompensa"] for r in antes["historico"]}
    novas_linhas = [r for r in depois["historico"] if r["id_recompensa"] not in ids]
    principal = next((r for r in novas_linhas if r["chave_evento"] == evento), None)
    if transacao is None and principal:
        transacao = principal.get('transacao')
    chaves_conquistas = {"conquista:" + str(c["id_conquista"]) for c in (novas or [])}
    recebidas = [r for r in novas_linhas if r["chave_evento"] == evento
                 or r["chave_evento"] in chaves_conquistas
                 or (transacao is not None and r.get('transacao') == transacao
                     and (r['chave_evento'].startswith('meta:') or r['chave_evento']=='sequencia:primeiros-7'))
                 or (principal and r["chave_evento"] == "sequencia:primeiros-7"
                     and r["criado_em"] == principal["criado_em"])]
    if not recebidas:
        return None
    return {"xp_recebido": sum(r["xp"] for r in recebidas), "xp": depois["total"],
            "nivel": depois["nivel"], "subiu_nivel": depois["nivel"] > antes["nivel"],
            "desceu_nivel": depois["nivel"] < antes["nivel"],
            "conquistas": novas or []}


def recuperar_registro(chave, id_agenda=None, historico=None):
    """Lê a identidade persistida; nunca reconstrói o resultado usando o retry."""
    consulta = supabase.table("atividades").select("*").eq("id_usuario", session["id_usuario"])
    registros = consulta.eq("chave_registro", chave).execute().data or []
    if not registros and id_agenda is not None:
        registros = (supabase.table("atividades").select("*")
                     .eq("id_usuario", session["id_usuario"]).eq("id_agenda", id_agenda).execute().data or [])
    if registros:
        return {"atividade": registros[0], "situacao": "existente"}
    if historico is None:
        historico = exigir_xp()["historico"]
    if any(r["chave_evento"] == "atividade:" + chave for r in historico):
        return {"atividade": None, "situacao": "excluida"}
    if id_agenda is not None:
        treinos = (supabase.table("agenda").select("*").eq("id_usuario", session["id_usuario"])
                   .eq("id_agenda", id_agenda).execute().data or [])
        if treinos and treinos[0].get("realizado_em"):
            return {"atividade": None, "situacao": "agenda_ja_concluida"}
    return None


def resultado_repetido(anterior):
    return {**anterior, "novo": False, "recompensa": None,
            "novas_conquistas": [], "conquistas_atualizadas": None}


def registrar_atividade(tipo, duracao, frequencia, chave, id_agenda=None, realizada_em=None, distancia=None):
    if tipo not in TIPOS_EXERCICIO or not 1 <= duracao <= 1440 or frequencia not in (None, 1):
        raise ValueError("Informe modalidade e duração de 1 a 1440 minutos.")
    chave = validar_chave(chave)
    antes = exigir_xp()
    anterior = recuperar_registro(chave, id_agenda, antes["historico"])
    if anterior:
        return resultado_repetido(anterior)
    distancia = validar_distancia(tipo, duracao, distancia)
    payload = {"distancia_km": distancia, "tipo_exercicio": tipo, "duracao": duracao, "frequencia": frequencia,
               "data_registro": data_para_banco(realizada_em or datetime.now(timezone.utc).isoformat(),
                                                os.getenv('LIFES_DATA_REGISTRO_TIPO', 'date')),
               "id_usuario": session["id_usuario"], "chave_registro": chave}
    if id_agenda is not None:
        payload["id_agenda"] = id_agenda
    inseridas = supabase.table("atividades").insert(payload).execute().data or []
    if not inseridas:
        # Outra transação pode ter vencido entre o SELECT e o INSERT. RETURN NULL
        # só significa duplicidade depois de conferir a operação persistida.
        anterior = recuperar_registro(chave, id_agenda)
        if anterior:
            return resultado_repetido(anterior)
        raise APIError({"code": "P0001", "message": "INSERT vazio sem operação persistida reconhecida"})
    novas = []
    sincronizadas = verificar_conquistas_apos_salvar(novas)
    return {"novo": True, "atividade": inseridas[0], "situacao": "criada",
            "recompensa": preparar_recompensa(antes, novas, "atividade:" + chave),
            "novas_conquistas": novas, "conquistas_atualizadas": sincronizadas}


def login_obrigatorio(f):
    @wraps(f)
    def decorada(*args, **kwargs):
        if "id_usuario" not in session:
            if request.is_json:
                return jsonify(erro="Sua sessão expirou. Entre novamente para confirmar o treino."), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorada


@app.route("/pontuacao")
@login_obrigatorio
def pontuacao():
    return render_template("pontuacao.html", nome=session["nome"], xp=consultar_xp())


def usuario_perfil(obrigatorio=True):
    if hasattr(g, 'usuario_perfil'):
        return g.usuario_perfil
    registros = (supabase.table('usuarios').select('id_usuario,nome,foto_path,perfil_versao')
                 .eq('id_usuario', session['id_usuario']).execute().data or [])
    if not registros:
        if obrigatorio: abort(404, description='Perfil não encontrado.')
        return None
    g.usuario_perfil = registros[0]
    return g.usuario_perfil


def bucket_perfil():
    bucket = os.getenv('SUPABASE_AVATAR_BUCKET', 'lifes-perfis')
    configuracao = supabase.storage.get_bucket(bucket)
    publico = configuracao.get('public') if isinstance(configuracao, dict) else configuracao.public
    if publico is not False:
        raise ValueError('O bucket de fotos precisa ser privado. Contate o administrador.')
    return supabase.storage.from_(bucket)


@app.route('/perfil', methods=['GET', 'POST'])
@login_obrigatorio
def perfil():
    usuario = usuario_perfil()
    status = 200
    if request.method == 'POST':
        try:
            nome = validar_nome(request.form.get('nome', ''))
            versao = int(request.form.get('perfil_versao', '-1'))
            if versao != usuario.get('perfil_versao', 0):
                abort(409, description='O perfil mudou em outra aba. Recarregue antes de salvar.')
            anterior = usuario.get('foto_path')
            caminho = anterior
            arquivo = request.files.get('foto')
            remover = request.form.get('remover_foto') == '1'
            if remover and arquivo and arquivo.filename:
                raise ValueError('Escolha entre substituir a foto e removê-la.')
            storage = None
            if arquivo and arquivo.filename:
                conteudo = preparar_foto(arquivo)
                storage = bucket_perfil()
                caminho = f"{session['id_usuario']}/{uuid4().hex}.png"
                storage.upload(caminho, conteudo, file_options={'content-type': 'image/png', 'upsert': 'false'})
            elif remover:
                storage = bucket_perfil() if anterior else None
                caminho = None
            resposta = (supabase.table('usuarios').update(dict(nome=nome, foto_path=caminho, perfil_versao=versao+1))
                        .eq('id_usuario', session['id_usuario']).eq('perfil_versao', versao).execute())
            if not resposta.data:
                # Só removemos a nova imagem quando sabemos que o UPDATE não gravou.
                if storage and caminho and caminho != anterior:
                    storage.remove([caminho])
                abort(409, description='O perfil mudou em outra aba. Recarregue antes de salvar.')
            session['nome'] = nome
            flash('Perfil atualizado.')
            if anterior != caminho and caminho_proprio(anterior, session['id_usuario']):
                try:
                    (storage or bucket_perfil()).remove([anterior])
                except (StorageApiError, HTTPError, ValueError):
                    app.logger.warning('Perfil: limpeza de foto anterior pendente')
                    flash('A foto atual foi salva, mas a limpeza do arquivo anterior ficou pendente.')
            return redirect(url_for('perfil'))
        except ValueError as erro:
            flash(str(erro) if 'invalid literal' not in str(erro) else 'Recarregue o perfil antes de salvar.')
            status = 400
        except (APIError, HTTPError, StorageApiError):
            # Falha de rede após UPDATE pode significar commit. Não apagar o upload
            # sem reconciliação: ele pode ser a foto persistida. Nunca logar URL/chave.
            app.logger.warning('Perfil: gravação não confirmada; conferir perfil antes de repetir')
            flash('Não foi possível confirmar o perfil. Recarregue para conferir antes de tentar novamente.')
            status = 503
    registros = listar_do_usuario('atividades', ['id_atividade'])
    metas = listar_do_usuario('metas', ['id_meta'])
    obtidas = listar_do_usuario('usuario_conquista', ['id_conquista'])
    return render_template('perfil.html', nome=session['nome'], usuario=usuario,
                           xp=consultar_xp(), resumo=calcular_progresso(registros, metas, agora_local().date()),
                           total_conquistas=len(obtidas)), status


@app.route('/perfil/foto')
@login_obrigatorio
def perfil_foto():
    usuario = usuario_perfil()
    caminho = usuario.get('foto_path')
    if not caminho_proprio(caminho, session['id_usuario']): abort(404)
    try:
        conteudo = bucket_perfil().download(caminho)
    except (StorageApiError, HTTPError, ValueError):
        abort(503, description='Foto temporariamente indisponível.')
    resposta = send_file(BytesIO(conteudo), mimetype='image/png', max_age=0)
    resposta.headers['Cache-Control'] = 'private, no-store'
    resposta.headers['X-Content-Type-Options'] = 'nosniff'
    return resposta


@app.route("/configuracoes")
@login_obrigatorio
def configuracoes():
    return render_template("configuracoes.html", nome=session["nome"])


@app.route("/dicas")
@login_obrigatorio
def dicas():
    termo = request.args.get("q", "").strip()[:120]
    categoria = request.args.get("categoria", "")
    registros = []
    while True:
        lote = supabase.table("dicas").select("*").order("id_dica").range(len(registros), len(registros)+499).execute().data or []
        registros.extend(lote)
        if len(lote)<500: break
    categorias = sorted({d.get("categoria") or "Hábitos saudáveis" for d in registros})
    filtradas = [d for d in registros if (not categoria or d.get("categoria", "Hábitos saudáveis")==categoria)
                 and termo.casefold() in (d["titulo"]+" "+(d.get("descricao") or "")).casefold()]
    return render_template("dicas.html", nome=session["nome"], dicas=filtradas,
                           categorias=categorias, termo=termo, categoria=categoria)


@app.route("/dicas/<int:id_dica>")
@login_obrigatorio
def dica_detalhe(id_dica):
    registros = supabase.table("dicas").select("*").eq("id_dica",id_dica).execute().data
    if not registros: abort(404)
    dica = registros[0]
    # Links editoriais são aceitos apenas dos domínios das fontes verificadas.
    from urllib.parse import urlparse
    fonte = dica.get("fonte") or ""
    url = urlparse(fonte)
    dica["fonte_segura"] = fonte if url.scheme=="https" and url.hostname in ("www.who.int", "www.cdc.gov") else None
    return render_template("dica_detalhe.html", nome=session["nome"], dica=dica)


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

        try:
            resposta = supabase.table("usuarios").select("id_usuario,nome,senha_hash").eq("email", email).execute()
        except (APIError, HTTPError) as erro:
            return render_template("login.html", erro_login=mensagem_erro_banco(erro), email=email), 503

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
    disponiveis = [t for t in dados["treinos"] if t["instante"].date() >= hoje and not t.get("realizado_em")]
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


@app.route("/conquistas/sincronizar", methods=["POST"])
@login_obrigatorio
def conquistas_sincronizar():
    antes = exigir_xp()
    novas = []
    if verificar_conquistas_apos_salvar(novas, registro_salvo=False):
        feedback = preparar_recompensa(antes, novas)
        if feedback:
            session["feedback_recompensa"] = feedback
        flash("Conquistas conferidas com seu histórico de atividades e metas.")
    else:
        return render_template("conquistas.html", **dados_acompanhamento()), 503
    return redirect(url_for("conquistas"))


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
    modalidade = formulario.get("modalidade") or None
    if modalidade is not None and modalidade not in TIPOS_EXERCICIO:
        raise ValueError("Selecione uma modalidade válida.")
    return {"titulo": titulo, "lembrete": descricao, "horario": instante.replace(tzinfo=None).isoformat(),
            "modalidade": modalidade}


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
            resposta = supabase.table("agenda").insert(dados).execute()
            if not resposta.data:
                raise APIError({"code": "P0001", "message": "Agenda sem confirmação de inserção"})
        except (APIError, HTTPError) as erro:
            return formulario_treino(request.form, erro_banco="Não foi possível confirmar o salvamento do treino. " + mensagem_erro_banco(erro)), 503
        flash("Treino agendado com sucesso!")
        return redirect(url_for("agenda"))
    try:
        listar_do_usuario("agenda", ["id_agenda"],
                          "id_agenda,titulo,horario,lembrete,modalidade,realizado_em")
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


def validar_data_realizada(valor):
    try:
        dia = date.fromisoformat(valor)
        if dia > agora_local().date():
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Informe uma data de realização válida, até hoje.") from None
    return datetime.combine(dia, time.min, FUSO).astimezone(timezone.utc).isoformat()



@app.route("/atividades")
@login_obrigatorio
def atividades():
    registros = listar_do_usuario("atividades", ["data_registro", "id_atividade"])
    for registro in registros:
        dia = data_atividade(registro.get("data_registro"))
        registro["data_formatada"] = dia.strftime("%d/%m/%Y") if dia else "Data não informada"
    return render_template("atividades.html", nome=session["nome"], atividades=list(reversed(registros)))


@app.route("/atividades/nova", methods=["GET", "POST"])
@login_obrigatorio
def atividade_nova():
    if request.method == "POST":
        try:
            realizada_em = validar_data_realizada(request.form.get("data_realizacao", agora_local().date().isoformat()))
            resultado = registrar_atividade(
                request.form.get("tipo_exercicio"), int(request.form.get("duracao", "")), None,
                request.form.get("chave_registro"), realizada_em=realizada_em, distancia=request.form.get("distancia_km"))
        except ValueError as erro:
            flash(str(erro) if "invalid literal" not in str(erro) else "Informe uma duração válida.")
            return render_template("atividade_form.html", nome=session["nome"], modo="nova",
                                   atividade=request.form, chave_registro=request.form.get("chave_registro")), 400
        except (APIError, HTTPError) as erro:
            flash("Não foi possível confirmar o registro. " + mensagem_erro_banco(erro) +
                  " Tente salvar novamente neste formulário; a mesma chave evita duplicação.")
            return render_template("atividade_form.html", nome=session["nome"], modo="nova",
                                   atividade=request.form, tipos_exercicio=TIPOS_EXERCICIO,
                                   chave_registro=request.form.get("chave_registro")), 503
        if resultado["recompensa"]:
            session["feedback_recompensa"] = resultado["recompensa"]
        if not resultado["novo"]:
            flash("Este registro já foi processado. Nenhuma atividade ou XP adicional foi criado.")
            return redirect(url_for("atividades"))
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
    atividade["data_realizacao"] = data_atividade(atividade["data_registro"]).isoformat()

    if request.method == "POST":
        try:
            tipo = request.form.get("tipo_exercicio")
            duracao = int(request.form.get("duracao", ""))
            if tipo not in TIPOS_EXERCICIO or not 1 <= duracao <= 1440:
                raise ValueError("Informe modalidade válida e duração de 1 a 1440 minutos.")
            distancia = validar_distancia(tipo, duracao, request.form.get("distancia_km"))
            realizada_em = validar_data_realizada(request.form.get("data_realizacao", data_atividade(atividade["data_registro"]).isoformat()))
            realizada_em = data_para_banco(realizada_em, os.getenv('LIFES_DATA_REGISTRO_TIPO', 'date'))
        except ValueError as erro:
            flash(str(erro))
            return render_template("atividade_form.html", nome=session["nome"], modo="editar",
                                   atividade={**atividade, **request.form}), 400
        try:
            antes = exigir_xp()
            atualizadas = supabase.table("atividades").update({
                "tipo_exercicio": tipo, "duracao": duracao,
                "data_registro": realizada_em,
                "distancia_km": distancia,
            }).eq("id_atividade", id_atividade).eq("id_usuario", session["id_usuario"]).execute()
        except (APIError, HTTPError) as erro:
            flash("Edição não confirmada. " + mensagem_erro_banco(erro))
            return render_template("atividade_form.html", nome=session["nome"], modo="editar",
                                   atividade={**atividade, **request.form}), 503

        if not atualizadas.data:
            abort(409, description="A atividade foi alterada ou excluída. Atualize a página.")
        novas = []
        verificar_conquistas_apos_salvar(novas)
        ajustada = atualizadas.data[0]
        evento = 'ajuste:atividade:' + str(ajustada.get('chave_registro') or id_atividade) + ':' + str(ajustada.get('xp_revisao', 0))
        feedback = preparar_recompensa(antes, novas, evento, ajustada.get('xp_transacao'))
        if feedback:
            session["feedback_recompensa"] = feedback
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
    antes = exigir_xp()
    resposta = supabase.table("atividades").delete().eq("id_atividade", id_atividade).eq(
        "id_usuario", session["id_usuario"]
    ).execute()

    if resposta.data:
        removida = resposta.data[0]
        evento = 'estorno:atividade:' + str(removida.get('chave_registro') or id_atividade)
        feedback = preparar_recompensa(antes, evento=evento)
        if feedback: session['feedback_recompensa'] = feedback
    flash("Atividade excluída." if resposta.data else "A atividade não foi encontrada na sua conta ou já foi excluída.")
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

    if segundos_decorridos < 60:
        return jsonify({"registrado": False, "motivo": "muito_curta"})

    # O título é livre na Agenda; a modalidade é confirmada pelo usuário.
    # Nunca confiar no título/dono enviados pelo navegador.
    try:
        validar_chave(dados.get("chave_registro"))
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
    titulo_treino = None
    id_agenda = dados.get("id_agenda")
    if "id_agenda" in dados and (type(id_agenda) is not int or id_agenda <= 0):
        return jsonify(erro="Treino inválido."), 400
    # Recupera por UUID antes de consultar a Agenda: ela pode ter sido excluída
    # após o commit de uma resposta perdida. Todo SELECT filtra o usuário da sessão.
    anterior = recuperar_registro(validar_chave(dados.get("chave_registro")), id_agenda)
    if anterior:
        resultado = resultado_repetido(anterior)
    else:
        if id_agenda is not None:
            treinos = (supabase.table("agenda").select("*").eq("id_agenda", id_agenda)
                       .eq("id_usuario", session["id_usuario"]).execute().data or [])
            if not treinos:
                return jsonify(erro="Treino não encontrado na sua agenda. Confira se ele foi excluído."), 404
            titulo_treino = treinos[0]["titulo"]
        duracao = segundos_decorridos // 60
        try:
            resultado = registrar_atividade(tipo_exercicio, duracao, None,
                                             dados.get("chave_registro"), id_agenda, distancia=dados.get("distancia_km"))
        except ValueError as erro:
            return jsonify(erro=str(erro)), 400
    original = resultado["atividade"] or {}
    return jsonify({"registrado": True, "duplicado": not resultado["novo"],
                    "situacao": resultado["situacao"], "id_atividade": original.get("id_atividade"),
                    "tipo_exercicio": original.get("tipo_exercicio"), "duracao": original.get("duracao"),
                    "data_registro": original.get("data_registro"), "distancia_km": original.get("distancia_km"),
                    "titulo_treino": titulo_treino, "recompensa": resultado["recompensa"],
                    "conquistas_atualizadas": resultado["conquistas_atualizadas"],
                    "novas_conquistas": resultado["novas_conquistas"]})




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
    lista_metas = listar_do_usuario('metas', ['prazo', 'id_meta'])
    for meta in lista_metas:
        meta["progresso"] = int(meta["progresso"])
        meta["prazo_formatado"] = formatar_data_br(meta["prazo"])
        meta["mensagem_incentivo"] = mensagem_incentivo(meta["progresso"])

    return render_template("metas.html", nome=session["nome"], metas=lista_metas)


def salvar_meta(meta=None):
    modo = "editar" if meta else "nova"
    if request.method == "POST":
        try:
            payload = validar_meta(request.form)
            antes = exigir_xp()
            if meta:
                resposta = (supabase.table("metas").update(payload).eq("id_usuario", session["id_usuario"])
                            .eq("id_meta", meta["id_meta"]).execute())
            else:
                resposta = supabase.table("metas").insert({**payload, "id_usuario": session["id_usuario"]}).execute()
            if not resposta.data:
                abort(409, description="A meta não foi confirmada. Atualize a página antes de tentar novamente.")
            novas = []
            verificar_conquistas_apos_salvar(novas)
            feedback = preparar_recompensa(antes, novas, "meta:" + str(resposta.data[0]["id_meta"]))
            if feedback: session["feedback_recompensa"] = feedback
            flash("Meta salva. O progresso é calculado pelas atividades do período.")
            return redirect(url_for("metas"))
        except ValueError as erro:
            flash(str(erro)); status = 400
        except (APIError, HTTPError) as erro:
            flash("Não foi possível confirmar a meta. " + mensagem_erro_banco(erro)); status = 503
        return render_template("meta_form.html", nome=session["nome"], modo=modo,
                               meta={**(meta or {}), **request.form}), status
    return render_template("meta_form.html", nome=session["nome"], modo=modo, meta=meta)


@app.route("/metas/nova", methods=["GET", "POST"])
@login_obrigatorio
def meta_nova():
    return salvar_meta()


@app.route("/metas/editar/<int:id_meta>", methods=["GET", "POST"])
@login_obrigatorio
def meta_editar(id_meta):
    registros = (supabase.table("metas").select("*").eq("id_meta", id_meta)
                 .eq("id_usuario", session["id_usuario"]).execute().data or [])
    if not registros: abort(404, description="Meta não encontrada na sua conta.")
    return salvar_meta(registros[0])


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
