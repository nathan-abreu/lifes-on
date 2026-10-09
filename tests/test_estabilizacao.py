"""Falhas de integração sem conexão ao Supabase; nenhuma credencial real nos testes."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from httpx import Request, Response, HTTPStatusError
from postgrest.exceptions import APIError
from werkzeug.security import generate_password_hash
from tests import test_semanas_6_7 as base
from erros_banco import classificar_erro
from modalidades import imagem_modalidade


class EstabilizacaoTest(TestCase):
    setUp = base.RotasTest.setUp
    entrar = base.RotasTest.entrar
    post = base.RotasTest.post
    dados_treino = base.RotasTest.dados_treino

    def falhar(self, tabela, codigo, operacao=None):
        original = base.ConsultaTeste.execute
        def executar(consulta):
            if consulta.tabela == tabela and (operacao is None or consulta.operacao == operacao):
                raise APIError({'code': codigo, 'message': 'SEGREDO SQL email senha token',
                                'details': 'SEGREDO', 'hint': 'SEGREDO'})
            return original(consulta)
        return patch.object(base.ConsultaTeste, 'execute', executar)

    def test_login_falha_permissao_preserva_formulario_sem_expor_senha(self):
        with self.client.session_transaction() as s:
            s.clear();s['csrf_token'] = 'token-teste'
        with self.falhar('usuarios', '42501'), self.assertLogs(base.projeto.app.logger, 'WARNING') as logs:
            r = self.post('/login', dict(email='fixture@example.test', senha='SENHA-NAO-EXIBIR'))
        self.assertEqual(r.status_code, 503)
        html = r.get_data(as_text=True)
        self.assertIn('credencial e as permissões', html)
        self.assertIn('fixture@example.test', html)
        self.assertNotIn('SENHA-NAO-EXIBIR', html)
        self.assertNotIn('SEGREDO', html + str(logs.output))
        self.assertIn('rota=login', str(logs.output))
        self.assertIn('codigo=42501', str(logs.output))
        with self.client.session_transaction() as s:
            self.assertNotIn('id_usuario', s)

    def test_login_bem_sucedido_nao_e_confundido_com_falha_do_dashboard(self):
        self.banco.dados['usuarios'] = [dict(id_usuario=1, nome='Teste', email='fixture@example.test',
                                           senha_hash=generate_password_hash('senha-fixture'))]
        with self.falhar('atividades', '42501'):
            r = self.post('/login', dict(email='fixture@example.test', senha='senha-fixture'))
            self.assertEqual(r.status_code, 302)
            self.assertEqual(r.location, '/dashboard')
            self.assertEqual(self.client.get('/dashboard').status_code, 503)
        with self.client.session_transaction() as s:
            self.assertEqual(s['id_usuario'], 1)

    def test_erro_xp_original_e_preservado_e_exclusao_nao_comeca(self):
        self.banco.dados['atividades'] = [base.atividade()]
        with self.falhar('recompensas_xp', '42501'), self.assertLogs(base.projeto.app.logger, 'WARNING') as logs:
            r = self.post('/atividades/excluir/1')
        self.assertEqual(r.status_code, 503)
        self.assertIn('codigo=42501', str(logs.output))
        self.assertNotIn('PGRST205', str(logs.output))
        self.assertEqual(len(self.banco.dados['atividades']), 1)
        self.assertFalse(any(c.operacao == 'delete' for c in self.banco.consultas))

    def test_exclusao_inexistente_nao_anuncia_exclusao_real(self):
        r = self.post('/atividades/excluir/999', follow_redirects=True)
        self.assertIn('não foi encontrada', r.get_data(as_text=True))
        self.assertNotIn('Atividade excluída.', r.get_data(as_text=True))
        self.assertEqual(self.banco.dados['recompensas_xp'], [])

    def test_agenda_erro_coluna_preserva_campos(self):
        with self.falhar('agenda', 'PGRST204', 'insert'):
            r = self.post('/agenda/novo', {**self.dados_treino(), 'modalidade': 'Yoga'})
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 503)
        self.assertIn('atualização do banco', html)
        self.assertIn('value="Treino real"', html)
        self.assertIn('value="Yoga" selected', html)
        self.assertEqual(self.banco.dados['agenda'], [])

    def test_agenda_resposta_vazia_nao_inventa_sucesso(self):
        original = base.ConsultaTeste.execute
        def vazio(consulta):
            return SimpleNamespace(data=[]) if consulta.tabela == 'agenda' and consulta.operacao == 'insert' else original(consulta)
        with patch.object(base.ConsultaTeste, 'execute', vazio):
            r = self.post('/agenda/novo', self.dados_treino())
        self.assertEqual(r.status_code, 503)
        self.assertNotIn('Treino agendado com sucesso', r.get_data(as_text=True))

    def test_formulario_agenda_confere_colunas_que_vai_gravar(self):
        self.client.get('/agenda/novo')
        consultas = [c for c in self.banco.consultas if c.tabela == 'agenda']
        self.assertTrue(any('modalidade' in c.campos and 'realizado_em' in c.campos for c in consultas))

    def test_recuperacao_conquistas_falha_sem_falso_registro_salvo(self):
        self.banco.dados['atividades'] = [base.atividade()]
        with self.falhar('usuario_conquista', '42501', 'upsert'):
            r = self.post('/conquistas/sincronizar')
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 503)
        self.assertIn('verificação das conquistas não pôde ser concluída', html)
        self.assertNotIn('Seu registro foi salvo', html)
        self.assertNotIn('Conquistas conferidas com seu histórico', html)
        self.assertEqual(self.banco.dados['recompensas_xp'], [])

    def test_xp_indisponivel_nao_e_zero_nem_promessa_de_conexao(self):
        with self.falhar('recompensas_xp', 'PGRST205'):
            html = self.client.get('/pontuacao').get_data(as_text=True)
        self.assertIn('XP indisponível', html)
        self.assertIn('atualização do banco', html)
        self.assertNotIn('quando a conexão estiver disponível', html)
        self.assertNotIn('0 XP</strong>', html)

    def test_status_http_403_classificado_como_acesso(self):
        r = Response(403, request=Request('GET', 'https://fixture.invalid'))
        erro = HTTPStatusError('SEGREDO', request=r.request, response=r)
        self.assertEqual(classificar_erro(erro)[1], 'acesso')

    def test_yoga_e_ciclismo_possuem_imagens_servidas(self):
        for nome in ('Yoga', 'Ciclismo'):
            arquivo = imagem_modalidade(nome)['arquivo']
            self.assertIsNotNone(arquivo, nome)
            with self.client.get('/static/' + arquivo) as resposta:
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.content_type.startswith('image/'))
