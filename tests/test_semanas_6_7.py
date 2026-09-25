"""Testes locais: banco simulado somente nos testes, sem tocar no Supabase real."""

import copy
import json
import re
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from httpx import ConnectError
from postgrest.exceptions import APIError

with patch("supabase.create_client"):
    import app as projeto

from progresso import (
    FUSO, REGRAS_CONQUISTAS, calcular_conquistas, calcular_progresso, data_atividade,
    gerar_alertas, preparar_treinos,
)


AGORA = datetime(2026, 9, 24, 12, 0, tzinfo=FUSO)
HOJE = AGORA.date()


class DataHoraTeste(datetime):
    @classmethod
    def now(cls, tz=None):
        return AGORA.astimezone(tz) if tz else AGORA.replace(tzinfo=None)


def atividade(id_atividade=1, usuario=1, dia=HOJE, minutos=30):
    return {"id_atividade": id_atividade, "id_usuario": usuario,
            "tipo_exercicio": "Corrida", "duracao": minutos, "frequencia": 3,
            "data_registro": f"{dia.isoformat()}T15:00:00+00:00"}


class BancoTeste:
    def __init__(self):
        self.dados = {t: [] for t in ("usuarios", "atividades", "metas", "agenda", "dicas", "conquistas", "usuario_conquista", "alertas")}
        self.dados["conquistas"] = [{"id_conquista": i, "nome": nome, "descricao": descricao, "pontos": 0}
                                   for i, (nome, descricao, _, _, _) in enumerate(REGRAS_CONQUISTAS, 1)]
        self.consultas = []
        self.ausentes = set()
        self.colunas_ausentes = set()

    def table(self, tabela):
        return ConsultaTeste(self, tabela)


class ConsultaTeste:
    def __init__(self, banco, tabela):
        self.banco, self.tabela = banco, tabela
        self.filtros, self.ordens = [], []
        self.operacao, self.payload, self.fatia = "select", None, None

    def select(self, campos="*"):
        self.campos = campos
        return self

    def eq(self, campo, valor):
        self.filtros.append((campo, valor))
        return self

    def order(self, campo, desc=False):
        self.ordens.append((campo, desc))
        return self

    def range(self, inicio, fim):
        self.fatia = (inicio, fim)
        return self

    def insert(self, payload):
        self.operacao, self.payload = "insert", copy.deepcopy(payload)
        return self

    def update(self, payload):
        self.operacao, self.payload = "update", copy.deepcopy(payload)
        return self

    def upsert(self, payload, on_conflict, ignore_duplicates):
        assert on_conflict in ("id_usuario,id_conquista", "id_usuario,chave_evento") and ignore_duplicates
        self.conflito = on_conflict.split(",")
        self.operacao, self.payload = "upsert", copy.deepcopy(payload)
        return self

    def delete(self):
        self.operacao = "delete"
        return self

    def execute(self):
        self.banco.consultas.append(self)
        if self.tabela in self.banco.ausentes:
            raise APIError({"code": "PGRST205", "message": "Tabela ausente", "details": None, "hint": None})
        if self.tabela == "agenda" and "titulo" in self.banco.colunas_ausentes:
            raise APIError({"code": "42703", "message": "Coluna titulo ausente"})
        tabela = self.banco.dados[self.tabela]
        selecionadas = [r for r in tabela if all(r.get(k) == v for k, v in self.filtros)]
        if self.operacao == "insert":
            chaves = {"usuarios": "id_usuario", "atividades": "id_atividade", "metas": "id_meta", "agenda": "id_agenda"}
            chave = chaves[self.tabela]
            self.payload[chave] = max((r[chave] for r in tabela), default=0) + 1
            tabela.append(self.payload)
            selecionadas = [self.payload]
        elif self.operacao == "upsert":
            selecionadas = []
            for registro in self.payload:
                if not any(all(r[k] == registro[k] for k in self.conflito) for r in tabela):
                    if self.tabela == "alertas":
                        registro["id_alerta"] = max((r["id_alerta"] for r in tabela), default=0) + 1
                    tabela.append(registro)
                    selecionadas.append(registro)
        elif self.operacao == "update":
            for linha in selecionadas:
                linha.update(self.payload)
        elif self.operacao == "delete":
            for linha in selecionadas:
                tabela.remove(linha)
        for campo, desc in reversed(self.ordens):
            selecionadas = sorted(selecionadas, key=lambda r: r[campo], reverse=desc)
        if self.fatia:
            inicio, fim = self.fatia
            selecionadas = selecionadas[inicio:fim + 1]
        return SimpleNamespace(data=copy.deepcopy(selecionadas))


class CalculosTest(unittest.TestCase):
    def test_sem_dados(self):
        resumo = calcular_progresso([], [], HOJE)
        self.assertEqual(resumo["total_atividades"], 0)
        self.assertEqual(resumo["media_metas"], 0)
        self.assertEqual(resumo["grafico"]["minutos"], [0] * 7)
        self.assertFalse(any(c["requisito_atingido"] for c in calcular_conquistas(resumo)))
        self.assertIn("ainda não", gerar_alertas(resumo, [], [], AGORA)[0]["mensagem"])

    def test_semana_sequencia_e_minutos(self):
        registros = [atividade(i, dia=HOJE - timedelta(days=i)) for i in range(8)]
        registros.append(atividade(20, minutos=15))
        resumo = calcular_progresso(registros, [{"progresso": 100}, {"progresso": 40}], HOJE)
        self.assertEqual(resumo["total_atividades"], 9)
        self.assertEqual(resumo["atividades_semana"], 5)
        self.assertEqual(resumo["minutos_semana"], 135)
        self.assertEqual(resumo["grafico"]["minutos"], [30, 30, 30, 45, 0, 0, 0])
        self.assertEqual(resumo["sequencia"], 8)
        self.assertEqual(resumo["melhor_sequencia"], 8)
        self.assertEqual(resumo["media_metas"], 70)

    def test_sequencia_ontem_quebra_e_recorde(self):
        registros = [atividade(i, dia=HOJE - timedelta(days=i)) for i in range(1, 8)]
        resumo = calcular_progresso(registros, [], HOJE)
        self.assertEqual(resumo["sequencia"], 7)
        resumo = calcular_progresso(registros, [], HOJE + timedelta(days=1))
        self.assertEqual(resumo["sequencia"], 0)
        self.assertEqual(resumo["melhor_sequencia"], 7)
        self.assertTrue(calcular_conquistas(resumo)[4]["requisito_atingido"])

    def test_fuso_utc_e_legado(self):
        for valor in ["2026-09-24T01:00:00Z", "2026-09-24T01:00:00", "2026-09-23T22:00:00-03:00"]:
            self.assertEqual(data_atividade(valor), date(2026, 9, 23))
        self.assertEqual(data_atividade("2026-09-24"), HOJE)
        self.assertIsNone(data_atividade(None))
        self.assertIsNone(data_atividade("inválida"))

    def test_futuros_e_virada_de_ano(self):
        hoje = date(2027, 1, 1)
        registros = [atividade(1, dia=date(2026, 12, 31)), atividade(2, dia=hoje + timedelta(days=1))]
        resumo = calcular_progresso(registros, [], hoje)
        self.assertEqual(resumo["total_atividades"], 1)
        self.assertEqual(resumo["atividades_semana"], 1)
        self.assertEqual(resumo["grafico"]["labels"][0], "28/12")

    def test_limites_conquistas(self):
        for total in (0, 1, 9, 10, 29, 30, 31):
            for percentual in (0, 99, 100):
                with self.subTest(total=total, percentual=percentual):
                    resumo = calcular_progresso([atividade(i) for i in range(total)], [{"progresso": percentual}], HOJE)
                    conquistas = calcular_conquistas(resumo)
                    self.assertEqual([c["requisito_atingido"] for c in conquistas[:4]], [total >= 1, total >= 10, percentual == 100, total >= 30])
                    self.assertEqual(conquistas[1]["progresso"], min(total, 10))

    def test_alertas_prazos_inatividade_treinos(self):
        metas = [{"descricao": f"Meta {d}", "prazo": (HOJE + timedelta(days=d)).isoformat(), "progresso": 0} for d in (-1, 0, 1, 3, 4)]
        metas.append({"descricao": "Já concluída", "prazo": HOJE.isoformat(), "progresso": 100})
        treinos = preparar_treinos([
            {"id_agenda": 1, "titulo": "Passado", "horario": f"{HOJE}T11:00:00"},
            {"id_agenda": 2, "titulo": "Hoje", "horario": f"{HOJE}T18:00:00"},
            {"id_agenda": 3, "titulo": "Amanhã", "horario": f"{HOJE + timedelta(days=1)}T08:00:00"},
        ], AGORA)
        resumo = calcular_progresso([atividade(dia=HOJE - timedelta(days=3))], metas, HOJE)
        texto = " ".join(a["mensagem"] for a in gerar_alertas(resumo, metas, treinos, AGORA))
        for esperado in ("3 dias sem", "5 meta(s)", "prazo vencido", "vence hoje", "vence amanhã", "em 3 dias", 'Treino "Hoje"', 'Treino "Amanhã"'):
            self.assertIn(esperado, texto)
        for ausente in ("Já concluída", "Meta 4", "Passado"):
            self.assertNotIn(ausente, texto)
        self.assertTrue(treinos[0]["passado"])
        self.assertTrue(treinos[1]["proximo"])

    def test_sem_alertas_quando_em_dia(self):
        resumo = calcular_progresso([atividade()], [], HOJE)
        self.assertEqual(gerar_alertas(resumo, [], [], AGORA), [])

    def test_mensal_semanas_e_modalidades(self):
        registros = [atividade(1, dia=date(2026, 9, 1), minutos=20),
                     atividade(2, dia=date(2026, 9, 7), minutos=40),
                     atividade(3, dia=date(2026, 8, 31), minutos=60),
                     atividade(4, dia=date(2026, 9, 30), minutos=999)]
        registros[1]["tipo_exercicio"] = "Yoga"
        resumo = calcular_progresso(registros, [], HOJE)
        self.assertEqual(resumo["grafico_mensal"]["atividades"], [1, 1, 0, 0, 0])
        self.assertEqual(resumo["grafico_mensal"]["minutos"], [20, 40, 0, 0, 0])
        self.assertEqual(resumo["minutos_mes"], 60)
        self.assertEqual(resumo["atividades_mes"], 2)
        self.assertEqual([(m["nome"], m["minutos"]) for m in resumo["modalidades"]], [("Corrida", 80), ("Yoga", 40)])
        self.assertEqual([m["percentual"] for m in resumo["modalidades"]], [100, 50])

    def test_mensal_seis_semanas_e_fevereiro_bissexto(self):
        for hoje, tamanho, ultimo in [(date(2026, 3, 31), 6, "31/03"), (date(2028, 2, 29), 5, "29/02")]:
            resumo = calcular_progresso([atividade(dia=hoje)], [], hoje)
            self.assertEqual(len(resumo["grafico_mensal"]["labels"]), tamanho)
            self.assertTrue(resumo["grafico_mensal"]["labels"][-1].endswith(ultimo))
            self.assertEqual(sum(resumo["grafico_mensal"]["atividades"]), 1)


class RotasTest(unittest.TestCase):
    def setUp(self):
        self.banco = BancoTeste()
        self.patches = [patch.object(projeto, "supabase", self.banco),
                        patch.object(projeto, "agora_local", return_value=AGORA),
                        patch.object(projeto, "datetime", DataHoraTeste)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        projeto.app.config.update(TESTING=True, SECRET_KEY="chave-exclusiva-de-teste")
        self.client = projeto.app.test_client()
        self.entrar(1)

    def entrar(self, usuario):
        with self.client.session_transaction() as sessao:
            sessao.clear()
            sessao.update(id_usuario=usuario, nome=f"Pessoa {usuario}", csrf_token="token-teste")

    def post(self, caminho, dados=None, **kwargs):
        return self.client.post(caminho, data={"csrf_token": "token-teste", **(dados or {})}, **kwargs)

    def dados_treino(self):
        return {"titulo": "Treino real", "descricao": "Alongamento", "data": "2026-09-25", "horario": "18:30"}

    def test_paginas_vazias_e_templates(self):
        for caminho in ("/", "/login", "/cadastro", "/dashboard", "/progresso", "/alertas", "/conquistas", "/agenda", "/agenda/novo", "/atividades", "/atividades/nova", "/metas", "/metas/nova", "/api/teste"):
            with self.subTest(caminho=caminho):
                self.assertEqual(self.client.get(caminho).status_code, 200)
        for nome in projeto.app.jinja_env.list_templates():
            projeto.app.jinja_env.get_template(nome)

    def test_criar_editar_excluir_treino_e_alerta(self):
        resposta = self.post("/agenda/novo", {**self.dados_treino(), "id_usuario": 2})
        self.assertEqual(resposta.status_code, 302)
        treino = self.banco.dados["agenda"][0]
        self.assertEqual(treino["id_usuario"], 1)
        self.assertIn("amanhã", self.client.get("/alertas").get_data(as_text=True))
        self.assertIn("treino--proximo", self.client.get("/agenda").get_data(as_text=True))
        self.assertEqual(self.client.get("/agenda/editar/1").status_code, 200)
        self.assertEqual(self.post("/agenda/editar/1", {**self.dados_treino(), "titulo": "Atualizado"}).status_code, 302)
        self.assertEqual(treino["titulo"], "Atualizado")
        self.assertEqual(self.client.get("/agenda/excluir/1").status_code, 405)
        self.assertEqual(self.post("/agenda/excluir/1").status_code, 302)
        self.assertEqual(self.banco.dados["agenda"], [])
        self.assertNotIn("Atualizado", self.client.get("/alertas").get_data(as_text=True))

    def test_campos_invalidos(self):
        for campo, valor in [("titulo", "  "), ("titulo", "x" * 121), ("descricao", "x" * 2001), ("data", "2026-02-30"), ("data", ""), ("horario", "25:00"), ("horario", "10:00+03:00")]:
            with self.subTest(campo=campo, valor=valor):
                self.assertEqual(self.post("/agenda/novo", {**self.dados_treino(), campo: valor}).status_code, 400)
        self.assertFalse(self.banco.dados["agenda"])

    def test_isolamento_leituras_e_mutacoes(self):
        self.banco.dados["atividades"] = [atividade(1, 2)]
        self.banco.dados["atividades"][0]["tipo_exercicio"] = "ATIVIDADE-SECRETA"
        self.banco.dados["metas"] = [{"id_meta": 1, "id_usuario": 2, "descricao": "META-SECRETA", "prazo": "2026-09-25", "progresso": 100}]
        self.banco.dados["agenda"] = [{"horario": "2026-09-25T18:30:00", "lembrete": "Descrição", "titulo": "TREINO-SECRETO", "id_agenda": 1, "id_usuario": 2}]
        antes = copy.deepcopy(self.banco.dados)
        for caminho in ("/dashboard", "/progresso", "/conquistas", "/alertas", "/agenda", "/atividades", "/metas"):
            html = self.client.get(caminho).get_data(as_text=True)
            for segredo in ("ATIVIDADE-SECRETA", "META-SECRETA", "TREINO-SECRETO"):
                self.assertNotIn(segredo, html)
        self.assertEqual(self.client.get("/agenda/editar/1").status_code, 404)
        self.assertEqual(self.post("/agenda/editar/1", self.dados_treino()).status_code, 404)
        self.post("/agenda/excluir/1")
        for tipo in ("atividades", "metas"):
            self.assertEqual(self.client.get(f"/{tipo}/editar/1").status_code, 302)
            self.post(f"/{tipo}/editar/1", {"descricao": "Invadida", "progresso": 0})
            self.post(f"/{tipo}/excluir/1")
        self.assertEqual({k: v for k, v in antes.items() if k != "alertas"},
                         {k: v for k, v in self.banco.dados.items() if k != "alertas"})
        for consulta in self.banco.consultas:
            if consulta.tabela == "alertas" and consulta.operacao == "upsert":
                self.assertTrue(all(a["id_usuario"] == 1 for a in consulta.payload))
                continue
            if consulta.tabela != "conquistas":
                self.assertIn(("id_usuario", 1), consulta.filtros)
        self.entrar(2)
        self.assertIn("TREINO-SECRETO", self.client.get("/agenda").get_data(as_text=True))

    def test_grafico_dados_reais_e_navegacao(self):
        self.banco.dados["atividades"] = [atividade(1, minutos=45), atividade(2, usuario=2, minutos=999)]
        html = self.client.get("/progresso").get_data(as_text=True)
        dados = json.loads(re.search(r'<script id="dadosProgresso" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(dados["minutos"], [0, 0, 0, 45, 0, 0, 0])
        self.assertEqual(sum(dados["atividades"]), 1)
        for caminho in ("/progresso", "/agenda", "/conquistas", "/alertas"):
            self.assertIn(f'href="{caminho}"', html)

    def test_paginacao(self):
        self.banco.dados["atividades"] = [atividade(i) for i in range(1201)]
        with projeto.app.test_request_context():
            projeto.session["id_usuario"] = 1
            linhas = projeto.listar_do_usuario("atividades", ["data_registro", "id_atividade"])
        self.assertEqual(len(linhas), 1201)
        self.assertEqual(len(self.banco.consultas), 3)

    def test_alertas_leitura_persistente_contador_e_novo_evento(self):
        self.client.get("/alertas")
        primeiro = self.banco.dados["alertas"][0]
        self.assertEqual(primeiro["status"], "nao_lido")
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertRegex(html, r'class="sino"[^>]*>.*?<small>1</small>')
        self.assertEqual(self.post(f'/alertas/{primeiro["id_alerta"]}/ler').status_code, 302)
        for _ in range(2):
            html = self.client.get("/alertas").get_data(as_text=True)
            self.assertIn("✓ Lido", html)
            self.assertNotRegex(html, r'class="sino"[^>]*>.*?<small>')
        self.assertEqual(len(self.banco.dados["alertas"]), 1)
        self.post("/agenda/novo", self.dados_treino())
        self.client.get("/alertas")
        self.assertEqual(len(self.banco.dados["alertas"]), 2)
        self.assertEqual(primeiro["status"], "lido")
        self.assertEqual(self.banco.dados["alertas"][1]["status"], "nao_lido")
        self.post("/alertas/ler-todas")
        html = self.client.get("/alertas").get_data(as_text=True)
        self.assertNotIn("Marcar todas como lidas", html)
        self.assertNotRegex(html, r'class="sino"[^>]*>.*?<small>')

    def test_alertas_seguranca_post_csrf_e_dono(self):
        self.client.get("/alertas")
        id_alheio = self.banco.dados["alertas"][0]["id_alerta"]
        self.entrar(2)
        self.client.get("/alertas")
        self.assertEqual(self.client.get(f"/alertas/{id_alheio}/ler").status_code, 405)
        self.assertEqual(self.client.post("/alertas/ler-todas").status_code, 400)
        self.assertEqual(self.client.post(f"/alertas/{id_alheio}/ler").status_code, 400)
        self.assertEqual(self.post(f"/alertas/{id_alheio}/ler").status_code, 404)
        self.post("/alertas/ler-todas")
        self.assertEqual(self.banco.dados["alertas"][0]["status"], "nao_lido")
        self.assertEqual(self.banco.dados["alertas"][1]["status"], "lido")
        with self.client.session_transaction() as sessao:
            sessao.pop("id_usuario")
        self.assertEqual(self.post("/alertas/ler-todas").status_code, 302)

    def test_alertas_evento_estavel_e_vazio_e_falha(self):
        self.banco.dados["atividades"] = [atividade()]
        self.assertIn("Nenhum alerta por enquanto", self.client.get("/alertas").get_data(as_text=True))
        self.post("/agenda/novo", self.dados_treino())
        self.client.get("/alertas")
        self.post("/alertas/ler-todas")
        amanha = AGORA + timedelta(days=1)
        with patch.object(projeto, "agora_local", return_value=amanha):
            self.client.get("/alertas")
        self.assertEqual(len(self.banco.dados["alertas"]), 1)
        self.assertEqual(self.banco.dados["alertas"][0]["status"], "lido")
        self.post("/agenda/novo", {**self.dados_treino(), "titulo": "Outro treino"})
        self.client.get("/alertas")
        self.assertEqual(len(self.banco.dados["alertas"]), 2)
        self.banco.ausentes.add("alertas")
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.assertIn("alertas_leitura.sql", self.client.get("/alertas").get_data(as_text=True))

    def test_timer_agenda_disponiveis_ordenados_e_isolados(self):
        self.banco.dados["agenda"] = [
            {"id_agenda": i, "id_usuario": dono, "titulo": titulo, "horario": horario, "lembrete": ""}
            for i, dono, titulo, horario in [
                (1, 1, "AMANHA", "2026-09-25T07:00:00"),
                (2, 1, "HOJE", "2026-09-24T18:00:00"),
                (3, 1, "ANTIGO", "2026-09-23T08:00:00"),
                (4, 2, "ALHEIO", "2026-09-24T13:00:00"),
                (5, 1, "HOJE CEDO", "2026-09-24T07:00:00"),
            ]]
        html = self.client.get("/dashboard").get_data(as_text=True)
        seletor = re.search(r'<select id="timerAtividade".*?</select>', html, re.S).group()
        self.assertLess(seletor.index('value="5"'), seletor.index('value="2"'))
        self.assertLess(seletor.index('value="2"'), seletor.index('value="1"'))
        self.assertIn("Hoje às 18:00", seletor)
        self.assertIn("Amanhã às 07:00", seletor)
        self.assertNotIn("ANTIGO", seletor)
        self.assertNotIn("ALHEIO", html)
        self.assertEqual(self.banco.dados["atividades"], [])
        self.assertEqual(self.banco.dados["usuario_conquista"], [])

    def test_timer_agenda_valida_dono_e_preserva_planejamento(self):
        self.post("/agenda/novo", self.dados_treino())
        payload = {"id_agenda": 1, "tipo_exercicio": "Corrida", "segundos_decorridos": 1920}
        headers = {"X-CSRF-Token": "token-teste"}
        self.entrar(2)
        self.assertEqual(self.client.post("/atividades/concluir_timer", json=payload, headers=headers).status_code, 404)
        self.assertEqual(self.banco.dados["atividades"], [])
        self.entrar(1)
        for id_agenda in (True, "1", -1, 999):
            resposta = self.client.post("/atividades/concluir_timer", json={**payload, "id_agenda": id_agenda}, headers=headers)
            self.assertIn(resposta.status_code, (400, 404))
        resposta = self.client.post("/atividades/concluir_timer", json=payload, headers=headers)
        self.assertEqual(resposta.json["duracao"], 32)
        self.assertEqual(resposta.json["titulo_treino"], "Treino real")
        self.assertEqual(len(self.banco.dados["agenda"]), 1)
        self.assertEqual(self.banco.dados["atividades"][0]["id_usuario"], 1)
        self.assertEqual(resposta.json["novas_conquistas"][0]["nome"], "Primeiro passo")
        for caminho in ("/dashboard", "/progresso"):
            html = self.client.get(caminho).get_data(as_text=True)
            dados = json.loads(re.search(r'<script id="dadosProgresso" type="application/json">(.*?)</script>', html, re.S).group(1))
            self.assertEqual(sum(dados["minutos"]), 32)

    def test_timer_usuario_duracao_feedback_e_grafico(self):
        self.banco.dados["metas"] = [{"id_meta": 1, "id_usuario": 1, "descricao": "Correr mais",
                                      "prazo": "2026-09-25", "progresso": 25}]
        headers = {"X-CSRF-Token": "token-teste"}
        resposta = self.client.post("/atividades/concluir_timer", json={
            "tipo_exercicio": "Corrida", "segundos_decorridos": 150, "id_usuario": 2}, headers=headers)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json["duracao"], 3)
        self.assertEqual([c["nome"] for c in resposta.json["novas_conquistas"]], ["Primeiro passo"])
        self.assertEqual(self.banco.dados["atividades"][0]["id_usuario"], 1)
        self.assertEqual(self.banco.dados["metas"][0]["progresso"], 25)
        for caminho in ("/dashboard", "/progresso"):
            html = self.client.get(caminho).get_data(as_text=True)
            dados = json.loads(re.search(r'<script id="dadosProgresso" type="application/json">(.*?)</script>', html, re.S).group(1))
            self.assertEqual(sum(dados["minutos"]), 3)
        segunda = self.client.post("/atividades/concluir_timer", json={
            "tipo_exercicio": "Yoga", "segundos_decorridos": 30}, headers=headers)
        self.assertEqual(segunda.json["duracao"], 1)
        self.assertEqual(segunda.json["novas_conquistas"], [])
        self.entrar(2)
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertNotIn('Hoje · 3 min', html)

    def test_timer_rejeita_duracoes_invalidas_e_csrf(self):
        for segundos in (None, True, -1, 1.5, "60", 86401, 10**100):
            with self.subTest(segundos=segundos):
                resposta = self.client.post("/atividades/concluir_timer", json={
                    "tipo_exercicio": "Corrida", "segundos_decorridos": segundos},
                    headers={"X-CSRF-Token": "token-teste"})
                self.assertEqual(resposta.status_code, 400)
        self.assertEqual(self.client.post("/atividades/concluir_timer", json={
            "tipo_exercicio": "Corrida", "segundos_decorridos": 60}).status_code, 400)
        self.assertEqual(self.banco.dados["atividades"], [])

    def test_atividade_timer_e_meta_atualizam_conquistas(self):
        self.assertEqual(self.post("/atividades/nova", {"tipo_exercicio": "Corrida", "duracao": 30, "frequencia": 3}).status_code, 302)
        self.assertIn("Desbloqueada", self.client.get("/conquistas").get_data(as_text=True))
        self.assertEqual(self.post("/atividades/editar/1", {"tipo_exercicio": "Yoga", "duracao": 40, "frequencia": 2}).status_code, 302)
        headers = {"X-CSRF-Token": "token-teste"}
        resposta = self.client.post("/atividades/concluir_timer", json={"tipo_exercicio": "Corrida", "segundos_decorridos": 90}, headers=headers)
        self.assertTrue(resposta.json["registrado"])
        self.assertEqual(len(self.banco.dados["atividades"]), 2)
        resposta = self.client.post("/atividades/concluir_timer", json={"tipo_exercicio": "Corrida", "segundos_decorridos": 29}, headers=headers)
        self.assertFalse(resposta.json["registrado"])
        for payload in ([1], {"tipo_exercicio": "Inválido"}, {"tipo_exercicio": "Corrida", "segundos_decorridos": "abc"}):
            self.assertEqual(self.client.post("/atividades/concluir_timer", json=payload, headers=headers).status_code, 400)
        self.post("/metas/nova", {"descricao": "Objetivo", "prazo": "2026-09-25"})
        self.assertEqual(self.client.get("/metas/editar/1").status_code, 200)
        self.post("/metas/editar/1", {"descricao": "Objetivo", "prazo": "2026-09-25", "progresso": 100})
        self.assertEqual(self.banco.dados["metas"][0]["progresso"], 100)
        self.assertNotIn("pendente(s)", self.client.get("/alertas").get_data(as_text=True))
        self.post("/atividades/excluir/1")
        self.post("/metas/excluir/1")
        self.assertEqual(len(self.banco.dados["atividades"]), 1)
        self.assertFalse(self.banco.dados["metas"])

    def test_csrf_e_autenticacao(self):
        self.assertEqual(self.client.post("/agenda/novo", data=self.dados_treino()).status_code, 400)
        self.assertEqual(self.client.post("/agenda/novo", data={"csrf_token": "inválido"}).status_code, 400)
        self.assertFalse(self.banco.dados["agenda"])
        with self.client.session_transaction() as sessao:
            sessao.pop("id_usuario")
        for caminho in ("/dashboard", "/progresso", "/agenda", "/agenda/novo", "/agenda/editar/1", "/conquistas", "/alertas", "/atividades", "/metas"):
            self.assertEqual(self.client.get(caminho).location, "/login")
        for caminho in ("/agenda/novo", "/agenda/editar/1", "/agenda/excluir/1"):
            self.assertEqual(self.post(caminho, self.dados_treino()).location, "/login")

    def test_cadastro_login_logout(self):
        with self.client.session_transaction() as sessao:
            sessao.clear()
        self.client.get("/cadastro")
        with self.client.session_transaction() as sessao:
            token = sessao["csrf_token"]
        self.client.post("/cadastro", data={"csrf_token": token, "nome": "Estudante", "email": "teste@example.test", "senha": "senha-de-teste"})
        self.assertNotEqual(self.banco.dados["usuarios"][0]["senha_hash"], "senha-de-teste")
        resposta = self.client.post("/login", data={"csrf_token": token, "email": "teste@example.test", "senha": "errada"})
        self.assertEqual(resposta.location, "/login")
        resposta = self.client.post("/login", data={"csrf_token": token, "email": "teste@example.test", "senha": "senha-de-teste"})
        self.assertEqual(resposta.location, "/dashboard")
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.client.get("/logout")
        self.assertEqual(self.client.get("/dashboard").location, "/login")

    def test_xss_escapado(self):
        self.post("/agenda/novo", {**self.dados_treino(), "titulo": "<script>alert(1)</script>"})
        for caminho in ("/agenda", "/dashboard", "/alertas"):
            html = self.client.get(caminho).get_data(as_text=True)
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("&lt;script&gt;", html)

    def test_agenda_sem_migracao_e_banco_indisponivel(self):
        self.banco.ausentes.add("agenda")
        for caminho in ("/dashboard", "/progresso", "/alertas", "/conquistas"):
            self.assertEqual(self.client.get(caminho).status_code, 200)
        self.assertEqual(self.client.get("/agenda").status_code, 503)
        self.assertIn("estrutura do banco precisa", self.client.get("/agenda").get_data(as_text=True))
        with patch.object(self.banco, "table", side_effect=ConnectError("indisponível")):
            self.assertEqual(self.client.get("/dashboard").status_code, 503)
        with patch.object(self.banco, "table", side_effect=APIError({"code": "42501", "message": "Sem acesso"})):
            self.assertEqual(self.client.get("/progresso").status_code, 503)

    def test_agenda_rejeita_passado_na_criacao_e_edicao(self):
        for data, hora in [("2026-09-23", "23:59"), ("2026-09-24", "11:59")]:
            resposta = self.post("/agenda/novo", {**self.dados_treino(), "data": data, "horario": hora})
            self.assertEqual(resposta.status_code, 400)
            self.assertIn("passado", resposta.get_data(as_text=True))
        self.assertEqual(self.banco.dados["agenda"], [])
        self.post("/agenda/novo", self.dados_treino())
        original = copy.deepcopy(self.banco.dados["agenda"])
        resposta = self.post("/agenda/editar/1", {**self.dados_treino(), "data": "2026-09-23"})
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(original, self.banco.dados["agenda"])

    def test_agenda_hoje_amanha_ordenacao_e_dashboard(self):
        for titulo, data, hora in [("Amanhã", "2026-09-25", "07:00"),
                                   ("Hoje tarde", "2026-09-24", "18:00"),
                                   ("Agora", "2026-09-24", "12:00")]:
            self.assertEqual(self.post("/agenda/novo", {**self.dados_treino(), "titulo": titulo, "data": data, "horario": hora}).status_code, 302)
        self.assertEqual(self.banco.dados["agenda"][0]["horario"], "2026-09-25T07:00:00")
        self.assertEqual(self.banco.dados["agenda"][0]["lembrete"], "Alongamento")
        html = self.client.get("/agenda").get_data(as_text=True)
        self.assertLess(html.index("<strong>Agora"), html.index("<strong>Hoje tarde"))
        self.assertLess(html.index("<strong>Hoje tarde"), html.index("<strong>Amanhã"))
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn('<p class="mini__valor">Agora</p>', html)
        self.assertIn("para hoje", html)
        self.post("/agenda/editar/3", {**self.dados_treino(), "titulo": "Remarcado", "data": "2026-09-26"})
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn('<p class="mini__valor">Hoje tarde</p>', html)
        self.assertNotIn('Treino &#34;Remarcado&#34;', html)
        self.post("/agenda/excluir/2")
        self.assertIn('<p class="mini__valor">Amanhã</p>', self.client.get("/dashboard").get_data(as_text=True))

    def test_agenda_coluna_ausente_mensagem_e_formulario_preservado(self):
        self.banco.colunas_ausentes.add("titulo")
        for caminho in ("/agenda", "/agenda/novo"):
            resposta = self.client.get(caminho)
            self.assertEqual(resposta.status_code, 503)
            self.assertIn("migração", resposta.get_data(as_text=True))
        resposta = self.post("/agenda/novo", self.dados_treino())
        self.assertEqual(resposta.status_code, 503)
        self.assertIn("Treino não salvo", resposta.get_data(as_text=True))
        self.assertIn('value="Treino real"', resposta.get_data(as_text=True))
        self.assertEqual(self.banco.dados["agenda"], [])

    def test_agenda_independe_de_metas_atividades_e_conquistas(self):
        self.banco.ausentes.update(["metas", "atividades", "conquistas", "usuario_conquista"])
        self.assertEqual(self.client.get("/agenda").status_code, 200)
        self.assertEqual(self.post("/agenda/novo", self.dados_treino()).status_code, 302)

    def test_conquista_persistida_imediatamente_data_e_nao_duplicacao(self):
        self.post("/atividades/nova", {"tipo_exercicio": "Corrida", "duracao": 30, "frequencia": 1})
        obtidas = self.banco.dados["usuario_conquista"]
        self.assertEqual(len(obtidas), 1)
        self.assertEqual(obtidas[0], {"id_usuario": 1, "id_conquista": 1, "data_obtencao": "2026-09-24"})
        with patch.object(projeto, "agora_local", return_value=AGORA + timedelta(days=1)):
            for _ in range(3):
                html = self.client.get("/conquistas").get_data(as_text=True)
                self.assertIn("Obtida em: 24/09/2026", html)
        self.assertEqual(len(obtidas), 1)
        self.assertEqual(obtidas[0]["data_obtencao"], "2026-09-24")

    def test_conquista_persiste_apos_excluir_atividade_ou_reduzir_meta(self):
        self.post("/atividades/nova", {"tipo_exercicio": "Corrida", "duracao": 30, "frequencia": 1})
        self.post("/metas/nova", {"descricao": "Objetivo", "prazo": "2026-09-25"})
        self.post("/metas/editar/1", {"descricao": "Objetivo", "prazo": "2026-09-25", "progresso": 100})
        self.assertEqual(len(self.banco.dados["usuario_conquista"]), 2)
        self.post("/atividades/excluir/1")
        self.post("/metas/editar/1", {"descricao": "Objetivo", "prazo": "2026-09-25", "progresso": 0})
        self.client.get("/conquistas")
        self.assertEqual(len(self.banco.dados["usuario_conquista"]), 2)
        self.assertIn("2 de 6 desbloqueadas", self.client.get("/dashboard").get_data(as_text=True))

    def test_conquista_parcial_e_em_movimento(self):
        self.banco.dados["atividades"] = [atividade(i) for i in range(5)]
        html = self.client.get("/conquistas").get_data(as_text=True)
        self.assertIn("5/10 atividades", html)
        self.assertIn("2 de 6 desbloqueadas", html)
        self.assertEqual({r["id_conquista"] for r in self.banco.dados["usuario_conquista"]}, {1, 6})

    def test_conquistas_isoladas_por_usuario(self):
        self.banco.dados["atividades"] = [atividade()]
        self.client.get("/conquistas")
        self.entrar(2)
        self.assertIn("0 de 6 desbloqueadas", self.client.get("/conquistas").get_data(as_text=True))
        self.post("/atividades/nova", {"tipo_exercicio": "Yoga", "duracao": 15, "frequencia": 1})
        self.assertEqual({r["id_usuario"] for r in self.banco.dados["usuario_conquista"]}, {1, 2})
        self.assertEqual(len(self.banco.dados["usuario_conquista"]), 2)

    def test_conquista_concorrente_preserva_primeira_data(self):
        self.banco.dados["atividades"] = [atividade()]
        original = ConsultaTeste.upsert

        def corrida(consulta, payload, **kwargs):
            self.banco.dados["usuario_conquista"].append({**payload[0], "data_obtencao": "2026-09-23"})
            return original(consulta, payload, **kwargs)

        with patch.object(ConsultaTeste, "upsert", corrida):
            self.client.get("/conquistas")
        self.assertEqual(len(self.banco.dados["usuario_conquista"]), 1)
        self.assertEqual(self.banco.dados["usuario_conquista"][0]["data_obtencao"], "2026-09-23")

    def test_falha_conquista_nao_duplica_atividade_e_recupera(self):
        self.banco.ausentes.add("usuario_conquista")
        resposta = self.post("/atividades/nova", {"tipo_exercicio": "Corrida", "duracao": 30, "frequencia": 1}, follow_redirects=True)
        self.assertIn("Seu registro foi salvo", resposta.get_data(as_text=True))
        self.assertEqual(len(self.banco.dados["atividades"]), 1)
        self.assertIn("Conquistas indisponíveis", self.client.get("/conquistas").get_data(as_text=True))
        self.banco.ausentes.clear()
        self.client.get("/conquistas")
        self.assertEqual(len(self.banco.dados["usuario_conquista"]), 1)

    def test_dashboard_meta_real_conquista_e_sem_xp(self):
        self.banco.dados["atividades"] = [atividade()]
        self.banco.dados["metas"] = [{"id_meta": 1, "id_usuario": 1, "descricao": "Minha meta real", "prazo": "2026-09-25", "progresso": 70}]
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Minha meta real", html)
        self.assertIn("70%", html)
        self.assertIn("Mais recente: Primeiro passo", html)
        for futuro in ("XP", "Pontuação", "Nível", "> Dicas"):
            self.assertNotIn(futuro, html)

    def test_grafico_mensal_json_sem_dados_alheios(self):
        self.banco.dados["atividades"] = [atividade(), atividade(2, usuario=2, minutos=900)]
        html = self.client.get("/progresso").get_data(as_text=True)
        dados = json.loads(re.search(r'<script id="dadosMensais" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(sum(dados["minutos"]), 30)
        self.assertEqual(sum(dados["atividades"]), 1)
        self.assertIn("Tempo total treinado por tipo", html)


if __name__ == "__main__":
    unittest.main()
