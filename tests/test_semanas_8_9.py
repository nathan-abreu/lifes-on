"""Semanas 8/9: contratos HTTP, isolamento, feedback real e recuperação local."""
import json
import re
import unittest
from uuid import uuid4
from unittest.mock import patch
from httpx import ConnectError
from recompensas import calcular_nivel, validar_chave
from tests import test_semanas_6_7 as base
projeto, AGORA = base.projeto, base.AGORA

# Reutiliza setup/helper sem duplicar a execução da classe de regressão.
class IntegracaoTest(unittest.TestCase):
    setUp = base.RotasTest.setUp
    entrar = base.RotasTest.entrar
    post = base.RotasTest.post
    dados_treino = base.RotasTest.dados_treino

    def registrar(self, chave=None):
        return self.post('/atividades/nova',dict(tipo_exercicio='Corrida',duracao=30,frequencia=1,
                                                chave_registro=chave or str(uuid4())))

    def test_niveis_limites(self):
        for xp,nivel,progresso in [(0,1,0),(99,1,99),(100,2,0),(250,3,0)]:
            self.assertEqual(calcular_nivel(xp)['nivel'],nivel)
            self.assertEqual(calcular_nivel(xp)['progresso'],progresso)
        for valor in (None,'abc',2):
            with self.assertRaises(ValueError): validar_chave(valor)

    def test_manual_retry_edicao_exclusao_nao_duplicam(self):
        chave=str(uuid4())
        self.registrar(chave);self.registrar(chave)
        self.assertEqual(len(self.banco.dados['atividades']),1)
        self.assertEqual(sum(r['xp'] for r in self.banco.dados['recompensas_xp']),60)
        self.post('/atividades/editar/1',dict(tipo_exercicio='Yoga',duracao=40,frequencia=2))
        self.post('/atividades/excluir/1')
        self.registrar(chave)
        self.assertEqual(len(self.banco.dados['atividades']),0)
        self.assertEqual(sum(r['xp'] for r in self.banco.dados['recompensas_xp']),30)

    def test_feedback_exato_uma_vez(self):
        self.registrar()
        html=self.client.get('/atividades').get_data(as_text=True)
        dados=json.loads(re.search(r'<script id="feedbackRecompensa" type="application/json">(.*?)</script>',html,re.S).group(1))
        self.assertEqual(dados['xp_recebido'],60)
        self.assertEqual(dados['conquistas'][0]['nome'],'Primeiro passo')
        html=self.client.get('/atividades').get_data(as_text=True)
        self.assertIn('type="application/json">null</script>',html)

    def test_xp_frontend_ignorado_e_usuario_isolado(self):
        self.post('/atividades/nova',dict(tipo_exercicio='Yoga',duracao=10,frequencia=1,xp=999,id_usuario=2))
        self.entrar(2)
        html=self.client.get('/pontuacao').get_data(as_text=True)
        self.assertIn('0 XP',html)
        self.assertNotIn('Atividade concluída',html)
        self.assertEqual(self.client.get('/atividades/editar/1').status_code,302)

    def test_agenda_concluida_e_retry_com_chave_distinta(self):
        self.post('/agenda/novo',self.dados_treino())
        payload=dict(chave_registro=str(uuid4()),id_agenda=1,tipo_exercicio='Yoga',segundos_decorridos=90)
        headers={'X-CSRF-Token':'token-teste'}
        resposta=self.client.post('/atividades/concluir_timer',json=payload,headers=headers)
        self.assertEqual(resposta.json['recompensa']['xp_recebido'],31)
        payload['chave_registro']=str(uuid4())
        resposta=self.client.post('/atividades/concluir_timer',json=payload,headers=headers)
        self.assertTrue(resposta.json['duplicado'])
        self.assertEqual(len(self.banco.dados['atividades']),1)
        self.assertIn('Realizado',self.client.get('/agenda').get_data(as_text=True))
        self.assertNotIn('value="1" data-titulo',self.client.get('/dashboard').get_data(as_text=True))

    def test_meta_transicao_repetida_e_nivel(self):
        self.registrar()
        self.post('/metas/nova',dict(metrica='sessoes',alvo='1',inicio='2026-09-01',descricao='Minha meta',prazo='2026-09-25'))
        for percentual in (100,0,100):
            self.post('/metas/editar/1',dict(metrica='sessoes',alvo='1',inicio='2026-09-01',descricao='Minha meta',prazo='2026-09-25',progresso=percentual))
        self.assertEqual(sum(r['xp'] for r in self.banco.dados['recompensas_xp']),140)
        self.assertIn('Nível 2',self.client.get('/dashboard').get_data(as_text=True))

    def test_migracao_ausente_nao_perde_registro_sem_xp(self):
        self.banco.ausentes.add('recompensas_xp')
        self.assertEqual(self.registrar().status_code,503)
        self.assertEqual(self.banco.dados['atividades'],[])
        self.assertIn('XP indisponível',self.client.get('/dashboard').get_data(as_text=True))

    def test_chave_invalida_e_validacao(self):
        self.registrar('invalida')
        for tipo,duracao in [('Invalido',30),('Corrida',1441),('Corrida',0)]:
            self.post('/atividades/nova',dict(tipo_exercicio=tipo,duracao=duracao,frequencia=1))
        self.assertEqual(self.banco.dados['atividades'],[])

    def test_dicas_pesquisa_filtro_detalhe_e_xss(self):
        self.banco.dados['dicas']=[dict(id_dica=1,titulo='Água por perto',descricao='Beba água.',categoria='Hidratação',fonte='https://www.cdc.gov/healthy-weight-growth/water-healthy-drinks/'),
                                 dict(id_dica=2,titulo='<script>alert(1)</script>',descricao='Descanso',categoria='Sono',fonte='javascript:alert(1)')]
        html=self.client.get('/dicas?q=ÁGUA&categoria=Hidratação').get_data(as_text=True)
        self.assertIn('Água por perto',html);self.assertNotIn('Descanso',html)
        self.assertIn('Consultar fonte',self.client.get('/dicas/1').get_data(as_text=True))
        html=self.client.get('/dicas/2').get_data(as_text=True)
        self.assertIn('&lt;script&gt;',html);self.assertNotIn('javascript:alert',html)
        self.assertEqual(self.client.get('/dicas/999').status_code,404)
        self.assertIn('Nenhuma dica encontrada',self.client.get('/dicas?q=zzz').get_data(as_text=True))

    def test_dicas_falha_conexao(self):
        with patch.object(self.banco,'table',side_effect=ConnectError('teste')):
            self.assertEqual(self.client.get('/dicas').status_code,503)

    def test_novas_paginas_login_e_csrf(self):
        for rota in ('/dicas','/pontuacao','/configuracoes'):
            self.assertEqual(self.client.get(rota).status_code,200)
        with self.client.session_transaction() as sessao: sessao.clear()
        for rota in ('/dicas','/pontuacao','/configuracoes'):
            self.assertEqual(self.client.get(rota).status_code,302)
        self.entrar(1)
        self.assertEqual(self.client.post('/atividades/nova',data={}).status_code,400)

    def test_feedback_nao_inclui_recompensa_de_outra_aba(self):
        with projeto.app.test_request_context('/'):
            projeto.session['id_usuario']=1
            antes=projeto.consultar_xp()
            self.banco.premiar(1,'meta:99','Outra aba',50)
            self.banco.premiar(1,'atividade:atual','Minha ação',20)
            feedback=projeto.preparar_recompensa(antes,evento='atividade:atual')
            self.assertEqual(feedback['xp_recebido'],20)
            self.assertEqual(feedback['xp'],70)

    def test_falha_conquistas_preserva_xp_basico_e_informa_estado(self):
        self.banco.ausentes.add('usuario_conquista')
        resposta=self.client.post('/atividades/concluir_timer',json=dict(chave_registro=str(uuid4()),
                                 tipo_exercicio='Corrida',segundos_decorridos=60),
                                 headers={'X-CSRF-Token':'token-teste'})
        self.assertTrue(resposta.json['registrado'])
        self.assertFalse(resposta.json['conquistas_atualizadas'])
        self.assertEqual(resposta.json['recompensa']['xp_recebido'],1)
        self.banco.ausentes.clear()
        self.post('/conquistas/sincronizar')
        self.assertEqual(sum(r['xp'] for r in self.banco.dados['recompensas_xp']),31)

    def test_formulario_falha_preserva_uuid_e_valores(self):
        self.banco.ausentes.add('recompensas_xp')
        chave=str(uuid4())
        resposta=self.registrar(chave)
        html=resposta.get_data(as_text=True)
        self.assertEqual(resposta.status_code,503)
        self.assertIn(chave,html)
        self.assertIn('value="30"',html)
        self.banco.ausentes.clear()
        self.registrar(chave)
        self.assertEqual(len(self.banco.dados['atividades']),1)
