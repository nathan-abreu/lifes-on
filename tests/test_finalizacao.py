"""Regressão da finalização, exclusivamente com banco simulado."""
from datetime import timedelta
from uuid import uuid4
from unittest import TestCase
from unittest.mock import patch
from tests import test_semanas_6_7 as base
from tests.test_semanas_6_7 import atividade, AGORA, projeto
from modalidades import imagem_modalidade
from progresso import REGRAS_CONQUISTAS, calcular_conquistas, calcular_progresso


class FinalizacaoTest(TestCase):
    setUp = base.RotasTest.setUp
    entrar = base.RotasTest.entrar
    post = base.RotasTest.post
    dados_treino = base.RotasTest.dados_treino

    def test_manual_sem_frequencia_data_passada_e_artes_marciais(self):
        resposta = self.post('/atividades/nova', dict(tipo_exercicio='Artes Marciais', duracao=45,
                             data_realizacao='2026-09-22', frequencia=7))
        self.assertEqual(resposta.status_code, 302)
        registro = self.banco.dados['atividades'][0]
        self.assertIsNone(registro['frequencia'])
        self.assertEqual(registro['data_registro'], '2026-09-22T03:00:00+00:00')
        html = self.client.get('/atividades').get_data(as_text=True)
        self.assertIn('22/09/2026', html)
        self.assertIn('Artes Marciais', html)
        self.assertIn('45', self.client.get('/progresso').get_data(as_text=True))
        self.assertNotIn('name="frequencia"', self.client.get('/atividades/nova').get_data(as_text=True))

    def test_datas_invalidas_preservam_uuid_e_nao_salvam(self):
        for data in ('', '2026-02-30', '2026-09-25'):
            chave = str(uuid4())
            resposta = self.post('/atividades/nova', dict(tipo_exercicio='Yoga', duracao=20,
                                 data_realizacao=data, chave_registro=chave))
            self.assertEqual(resposta.status_code, 400)
            self.assertIn(chave, resposta.get_data(as_text=True))
        self.assertEqual(self.banco.dados['atividades'], [])

    def test_edicao_preserva_frequencia_legada_e_corrige_data(self):
        self.banco.dados['atividades'] = [atividade()]
        self.post('/atividades/editar/1', dict(tipo_exercicio='Artes Marciais', duracao=40,
                                            data_realizacao='2026-09-20', frequencia=7))
        registro = self.banco.dados['atividades'][0]
        self.assertEqual(registro['frequencia'], 3)
        self.assertEqual(registro['data_registro'], '2026-09-20T03:00:00+00:00')

    def test_visitas_nao_premiam_e_recuperacao_explicita_e_unica(self):
        self.banco.dados['atividades'] = [atividade(minutos=60)]
        for rota in ('/dashboard', '/progresso', '/conquistas', '/pontuacao'):
            self.assertEqual(self.client.get(rota).status_code, 200)
        self.assertEqual(self.banco.dados['recompensas_xp'], [])
        self.post('/conquistas/sincronizar')
        self.post('/conquistas/sincronizar')
        self.assertEqual(len(self.banco.dados['usuario_conquista']), 2)
        self.assertEqual(sum(r['xp'] for r in self.banco.dados['recompensas_xp']), 60)

    def test_erros_timer_sao_json_sem_detalhes_sql(self):
        payload = dict(tipo_exercicio='Artes Marciais', segundos_decorridos=60, chave_registro=str(uuid4()))
        self.assertEqual(self.client.post('/atividades/concluir_timer', json=payload).status_code, 400)
        self.assertIsNotNone(self.client.post('/atividades/concluir_timer', json=payload).json)
        self.banco.ausentes.add('recompensas_xp')
        resposta = self.client.post('/atividades/concluir_timer', json=payload, headers={'X-CSRF-Token':'token-teste'})
        self.assertEqual(resposta.status_code, 503)
        self.assertIn('Não foi possível', resposta.json['erro'])
        self.assertNotIn('sql', resposta.json['erro'])
        self.assertEqual(self.banco.dados['atividades'], [])
        with self.client.session_transaction() as sessao:
            sessao.pop('id_usuario')
        self.assertEqual(self.client.post('/atividades/concluir_timer', json=payload,
                         headers={'X-CSRF-Token':'token-teste'}).status_code, 401)

    def test_modalidade_agenda_timer_e_imagem(self):
        self.post('/agenda/novo', {**self.dados_treino(), 'modalidade':'Artes Marciais'})
        self.assertEqual(self.banco.dados['agenda'][0]['modalidade'], 'Artes Marciais')
        html = self.client.get('/dashboard').get_data(as_text=True)
        self.assertIn('data-modalidade="Artes Marciais"', html)
        self.assertIsNotNone(imagem_modalidade('Artes Marciais')['arquivo'])
        self.assertEqual(imagem_modalidade('Ciclismo')['icone'], 'bicycle')
        with patch('modalidades.Path.is_file', return_value=False):
            self.assertIsNone(imagem_modalidade('Corrida')['arquivo'])

    def test_catalogo_limites_minutos_metas_sequencias(self):
        self.assertEqual(len(REGRAS_CONQUISTAS), 14)
        resumo = calcular_progresso([], [], AGORA.date())
        for _, _, _, objetivo, campo in REGRAS_CONQUISTAS:
            for total in (objetivo-1, objetivo):
                casos = calcular_conquistas({**resumo, campo:total})
                for c, regra in zip(casos, REGRAS_CONQUISTAS):
                    if regra[4] == campo and regra[3] == objetivo:
                        self.assertEqual(c['requisito_atingido'], total == objetivo)

    def test_estorno_exclusao_idempotencia_e_isolamento(self):
        chave = str(uuid4())
        dados = dict(tipo_exercicio='Corrida', duracao=30, chave_registro=chave)
        self.post('/atividades/nova', dados)
        self.entrar(2)
        self.post('/atividades/excluir/1')
        self.assertEqual(len(self.banco.dados['atividades']), 1)
        self.entrar(1)
        self.post('/atividades/excluir/1')
        self.post('/atividades/excluir/1')
        self.post('/atividades/nova', dados)
        self.assertEqual(self.banco.dados['atividades'], [])
        self.assertEqual([r['xp'] for r in self.banco.dados['recompensas_xp']], [20,30,-20])

    def test_catalogo_duplicado_nao_repete_conquista_obtida(self):
        self.banco.dados['atividades'] = [atividade()]
        self.banco.dados['conquistas'].append(dict(id_conquista=99,nome='Primeiro Passo ',descricao='Legado'))
        self.banco.dados['usuario_conquista'].append(dict(id_usuario=1,id_conquista=99,data_obtencao='2026-09-23'))
        self.post('/conquistas/sincronizar')
        self.assertEqual(len(self.banco.dados['usuario_conquista']), 1)
        self.assertEqual(self.banco.dados['recompensas_xp'], [])
        self.assertIn('23/09/2026', self.client.get('/conquistas').get_data(as_text=True))

    def test_xp_indisponivel_impede_edicao_exclusao_e_recompensas_parciais(self):
        self.banco.dados['atividades'] = [atividade()]
        self.banco.dados['metas'] = [dict(id_usuario=1,id_meta=1,descricao='Meta',prazo='2026-10-01',progresso=0)]
        self.banco.ausentes.add('recompensas_xp')
        self.assertEqual(self.post('/atividades/excluir/1').status_code, 503)
        self.assertEqual(self.post('/atividades/editar/1',dict(tipo_exercicio='Yoga',duracao=50)).status_code,503)
        self.assertEqual(self.post('/metas/editar/1',dict(descricao='Meta',prazo='2026-10-01',progresso=100)).status_code,503)
        self.assertEqual(self.post('/conquistas/sincronizar').status_code,503)
        self.assertEqual(self.banco.dados['atividades'][0]['duracao'], 30)
        self.assertEqual(self.banco.dados['metas'][0]['progresso'], 0)
        self.assertEqual(self.banco.dados['usuario_conquista'], [])
