"""Contratos de retry e configuração; somente clientes simulados, sem rede."""
import base64
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from tests import test_semanas_6_7 as base
from banco import chave_do_servidor
from banco import criar_cliente
import httpx
from supabase import create_client as cliente_sdk
from progresso import REGRAS_CONQUISTAS


class AuditoriaXPTest(TestCase):
    setUp = base.RotasTest.setUp
    entrar = base.RotasTest.entrar
    post = base.RotasTest.post
    dados_treino = base.RotasTest.dados_treino

    def timer(self, payload):
        return self.client.post('/atividades/concluir_timer', json=payload,
                                headers={'X-CSRF-Token': 'token-teste'})

    def payload(self):
        return dict(chave_registro=str(uuid4()), tipo_exercicio='Corrida', segundos_decorridos=90)

    def test_retry_devolve_identidade_e_valores_originais(self):
        payload = self.payload()
        original = self.timer(payload).json
        xp = list(self.banco.dados['recompensas_xp'])
        resposta = self.timer({**payload, 'tipo_exercicio': 'Yoga', 'segundos_decorridos': 900})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json['duplicado'])
        for campo in ('id_atividade', 'tipo_exercicio', 'duracao', 'data_registro'):
            self.assertEqual(resposta.json[campo], original[campo])
        self.assertIsNone(resposta.json['recompensa'])
        self.assertEqual(self.banco.dados['recompensas_xp'], xp)

    def test_insert_suprimido_por_corrida_recupera_original(self):
        payload = self.payload()
        original = self.timer(payload).json
        recuperar = base.projeto.recuperar_registro
        chamadas = []

        def corrida(*args, **kwargs):
            chamadas.append(args)
            # Simula os dois SELECTs anteriores ao commit concorrente.
            return None if len(chamadas) <= 2 else recuperar(*args, **kwargs)

        with patch.object(base.projeto, 'recuperar_registro', side_effect=corrida):
            resposta = self.timer({**payload, 'segundos_decorridos': 900})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(chamadas), 3)
        self.assertEqual(resposta.json['id_atividade'], original['id_atividade'])
        self.assertEqual(resposta.json['duracao'], original['duracao'])
        self.assertTrue(resposta.json['duplicado'])
        self.assertEqual(len(self.banco.dados['atividades']), 1)
        self.assertEqual(sum(r['xp'] for r in self.banco.dados['recompensas_xp']), 50)

    def test_insert_vazio_sem_evidencia_nao_inventa_sucesso(self):
        executar = base.ConsultaTeste.execute

        def vazio(consulta):
            if consulta.tabela == 'atividades' and consulta.operacao == 'insert':
                return SimpleNamespace(data=[])
            return executar(consulta)

        with patch.object(base.ConsultaTeste, 'execute', vazio):
            resposta = self.timer(self.payload())
        self.assertEqual(resposta.status_code, 503)
        self.assertIn('erro', resposta.json)
        self.assertNotIn('duplicado', resposta.json)
        self.assertEqual(self.banco.dados['recompensas_xp'], [])

    def test_retry_apos_excluir_agenda_recupera_por_uuid(self):
        self.post('/agenda/novo', self.dados_treino())
        payload = {**self.payload(), 'id_agenda': 1}
        original = self.timer(payload).json
        self.banco.dados['agenda'].clear()
        self.banco.dados['atividades'][0]['id_agenda'] = None  # ON DELETE SET NULL
        resposta = self.timer(payload)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json['id_atividade'], original['id_atividade'])
        self.assertEqual(resposta.json['situacao'], 'existente')

    def test_retry_apos_excluir_atividade_informa_estado_historico(self):
        payload = self.payload()
        self.timer(payload)
        self.post('/atividades/excluir/1')
        resposta = self.timer(payload)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json['situacao'], 'excluida')
        self.assertTrue(resposta.json['duplicado'])
        self.assertIsNone(resposta.json['id_atividade'])
        self.assertIsNone(resposta.json['duracao'])
        self.assertEqual(self.banco.dados['atividades'], [])
        self.assertEqual(sum(r['xp'] for r in self.banco.dados['recompensas_xp']), 30)

    def test_mesmo_uuid_nao_recupera_dados_de_outro_usuario(self):
        payload = self.payload()
        primeiro = self.timer(payload).json
        self.entrar(2)
        segundo = self.timer({**payload, 'tipo_exercicio': 'Yoga'}).json
        self.assertFalse(segundo['duplicado'])
        self.assertNotEqual(segundo['id_atividade'], primeiro['id_atividade'])
        self.assertEqual(segundo['tipo_exercicio'], 'Yoga')

    def test_catalogo_sql_corresponde_aos_14_criterios_python(self):
        sql = Path('migrations/finalizacao_premium.sql').read_text(encoding='utf-8')
        seed = sql.split('insert into public.conquistas(nome,descricao,pontos)')[1]
        pares = re.findall(r"\('([^']+)','([^']+)'\)", seed)
        self.assertEqual(len(pares), 14)
        self.assertEqual({(n.strip().casefold(), d) for n, d in pares},
                         {(r[0].strip().casefold(), r[1]) for r in REGRAS_CONQUISTAS})


class ChaveServidorTest(TestCase):
    def jwt(self, role):
        payload = base64.urlsafe_b64encode(json.dumps({'role': role}).encode()).decode().rstrip('=')
        return 'fixture.' + payload + '.sem-assinatura'

    def test_modo_estrito_rejeita_anon_ausencia_e_malformada(self):
        for chave in ('', 'invalida', 'x.%%.x', 'sb_secret_', 'sb_publishable_publica',
                      'sb_secret_com espaco', self.jwt('anon'), self.jwt('authenticated')):
            with self.subTest(chave=chave), patch.dict('os.environ',
                    {'SUPABASE_KEY': chave, 'LIFES_REQUIRE_SERVER_KEY': '1'}, clear=True):
                with self.assertRaises(RuntimeError):
                    chave_do_servidor()

    def test_service_role_tem_precedencia_e_legado_compativel(self):
        servidor = self.jwt('service_role')
        with patch.dict('os.environ', {'SUPABASE_SERVICE_ROLE_KEY': servidor,
                         'SUPABASE_KEY': self.jwt('anon'), 'LIFES_REQUIRE_SERVER_KEY': '1'}, clear=True):
            self.assertEqual(chave_do_servidor(), servidor)
        with patch.dict('os.environ', {'SUPABASE_KEY': servidor, 'LIFES_REQUIRE_SERVER_KEY': '1'}, clear=True):
            self.assertEqual(chave_do_servidor(), servidor)

    def test_secret_atual_tem_precedencia_sem_fallback_para_chave_invalida(self):
        with patch.dict('os.environ', {'SUPABASE_SECRET_KEY': 'sb_secret_fixture-local',
                'SUPABASE_SERVICE_ROLE_KEY': self.jwt('service_role'),
                'SUPABASE_KEY': self.jwt('anon'), 'LIFES_REQUIRE_SERVER_KEY': '1'}, clear=True):
            self.assertEqual(chave_do_servidor(), 'sb_secret_fixture-local')
        with patch.dict('os.environ', {'SUPABASE_SECRET_KEY': 'sb_publishable_errada',
                'SUPABASE_SERVICE_ROLE_KEY': self.jwt('service_role'),
                'LIFES_REQUIRE_SERVER_KEY': '1'}, clear=True):
            with self.assertRaises(RuntimeError):
                chave_do_servidor()

    def test_sdk_instalado_envia_secret_na_api_rest_sem_rede(self):
        requests = []
        def responder(request):
            requests.append(request)
            return httpx.Response(200, json=[])
        cliente_http = httpx.Client(transport=httpx.MockTransport(responder))
        with patch('banco.httpx.Client', return_value=cliente_http), patch('banco.create_client', cliente_sdk):
            cliente = criar_cliente('https://fixture.supabase.co', 'sb_secret_fixture-local')
            cliente.table('atividades').select('id_atividade').execute()
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].headers['apikey'], 'sb_secret_fixture-local')
        self.assertEqual(requests[0].headers['authorization'], 'Bearer sb_secret_fixture-local')
        cliente_http.close()
