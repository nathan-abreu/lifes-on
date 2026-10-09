"""HTTP/validação/Storage simulado. Contabilidade real: tests/sql_evolucao.cjs."""
from io import BytesIO
from decimal import Decimal
import unittest
from uuid import uuid4
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image
from httpx import ConnectError
from postgrest.exceptions import APIError
from evolucao import validar_distancia, validar_meta, data_para_banco
from perfil import preparar_foto, caminho_proprio
from recompensas import calcular_nivel
from tests import test_semanas_6_7 as base


def foto(formato='PNG'):
    dados=BytesIO();Image.new('RGB',(32,24),'green').save(dados,format=formato);dados.seek(0);return dados


class StorageTeste:
    def __init__(self): self.arquivos={};self.public=False;self.removidos=[]
    def get_bucket(self, nome): return SimpleNamespace(public=self.public)
    def from_(self, nome): return self
    def upload(self, nome, conteudo, file_options):
        assert file_options == {'content-type':'image/png','upsert':'false'}
        self.arquivos[nome]=conteudo
    def download(self, nome): return self.arquivos[nome]
    def remove(self, nomes):
        for nome in nomes: self.arquivos.pop(nome,None);self.removidos.append(nome)


class EvolucaoCalculosTest(unittest.TestCase):
    def test_data_real_date_timestamp_e_timestamptz(self):
        instante='2026-10-09T01:00:00+00:00'
        self.assertEqual(data_para_banco(instante,'date'),'2026-10-08')
        self.assertEqual(data_para_banco(instante,'timestamp'),'2026-10-09T01:00:00')
        self.assertEqual(data_para_banco(instante,'timestamptz'),instante)
        with self.assertRaises(ValueError): data_para_banco(instante,'errado')
    def test_niveis_progressivos_limites_e_regresso(self):
        for nivel in range(1, 10000):
            inicio=0 if nivel==1 else 100+75*(nivel-2)*(nivel-1)
            requisito=100 if nivel==1 else 150*(nivel-1)
            self.assertEqual(calcular_nivel(inicio)['nivel'],nivel)
            self.assertEqual(calcular_nivel(inicio)['faltam'],requisito)
            self.assertEqual(calcular_nivel(inicio+requisito-1)['nivel'],nivel)
            self.assertEqual(calcular_nivel(inicio+requisito)['nivel'],nivel+1)
            if inicio: self.assertEqual(calcular_nivel(inicio-1)['nivel'],nivel-1)
        self.assertGreater(calcular_nivel(10**40)['nivel'],10**18)

    def test_distancia_decimal_limites(self):
        self.assertEqual(validar_distancia('Corrida',30,'3,125'),'3.125')
        for tipo,limite in [('Corrida',30),('Caminhada',12),('Ciclismo',80),('Natação',10)]:
            self.assertEqual(Decimal(validar_distancia(tipo,60,str(limite))),Decimal(limite))
            with self.assertRaises(ValueError): validar_distancia(tipo,60,str(limite+1))
        for valor in ('0','-1','NaN','Infinity','1.0001','1,2,3',True,'1e100000'):
            with self.subTest(valor=valor),self.assertRaises(ValueError): validar_distancia('Corrida',30,valor)
        for tipo in ('Yoga','Musculação','Artes Marciais','Outros'):
            self.assertIsNone(validar_distancia(tipo,30,''))
            with self.assertRaises(ValueError): validar_distancia(tipo,30,'1')

    def test_foto_conteudo_tamanho_formato_metadados(self):
        for formato in ('PNG','JPEG','WEBP'):
            resultado=preparar_foto(foto(formato))
            with Image.open(BytesIO(resultado)) as imagem:
                self.assertEqual(imagem.format,'PNG');self.assertFalse(imagem.getexif())
        for arquivo in (BytesIO(b'<svg onload=alert(1)>'),BytesIO(b'x'*(5*1024*1024+1)),foto('GIF'),BytesIO(b'')):
            with self.assertRaises(ValueError): preparar_foto(arquivo)
        self.assertFalse(caminho_proprio('2/'+uuid4().hex+'.png',1))
        self.assertFalse(caminho_proprio('1/../2/foto.png',1))

    def test_metas_validacao(self):
        dados=dict(descricao='Objetivo',metrica='km',alvo='10,5',modalidade='Corrida',inicio='2026-10-01',prazo='2026-10-31')
        self.assertEqual(validar_meta(dados)['alvo'],'10.5')
        for troca in [dict(metrica='manual'),dict(modalidade='Yoga'),dict(prazo='2026-09-30'),dict(alvo='0'),dict(metrica='sessoes',alvo='1.5')]:
            with self.assertRaises(ValueError): validar_meta({**dados,**troca})


class EvolucaoRotasTest(unittest.TestCase):
    entrar=base.RotasTest.entrar
    post=base.RotasTest.post
    def setUp(self):
        base.RotasTest.setUp(self)
        self.banco.storage=StorageTeste()
        self.banco.dados['usuarios']=[dict(id_usuario=i,nome=f'Pessoa {i}',email=f'{i}@local',senha_hash='hash',foto_path=None,perfil_versao=0) for i in (1,2)]

    def test_nome_nao_altera_login_e_isolamento(self):
        r=self.post('/perfil',dict(nome='  Maria Silva ',perfil_versao=0,id_usuario=2,email='fraude'))
        self.assertEqual(r.status_code,302)
        self.assertEqual(self.banco.dados['usuarios'][0]['nome'],'Maria Silva')
        self.assertEqual(self.banco.dados['usuarios'][0]['email'],'1@local')
        self.assertEqual(self.banco.dados['usuarios'][1]['nome'],'Pessoa 2')
        self.assertEqual(self.post('/perfil',dict(nome='Desatualizado',perfil_versao=0)).status_code,409)
        self.assertIn('Maria Silva',self.client.get('/dashboard').get_data(as_text=True))
        for consulta in self.banco.consultas:
            if consulta.tabela=='usuarios': self.assertIn(('id_usuario',1),consulta.filtros)

    def test_foto_upload_substituir_remover_privacidade(self):
        self.assertEqual(self.client.get('/perfil/foto').status_code,404)
        for versao in (0,1):
            self.assertEqual(self.post('/perfil',dict(nome='Pessoa',perfil_versao=versao,foto=(foto(),'foto.png'))).status_code,302)
            self.assertEqual(len(self.banco.storage.arquivos),1)
            r=self.client.get('/perfil/foto');self.assertEqual(r.status_code,200)
            self.assertEqual(r.headers['Cache-Control'],'private, no-store')
        self.assertEqual(len(self.banco.storage.removidos),1)
        self.entrar(2);self.assertEqual(self.client.get('/perfil/foto').status_code,404)
        self.assertEqual(self.client.get('/perfil/foto?id_usuario=1').status_code,404)
        self.entrar(1)
        self.assertEqual(self.post('/perfil',dict(nome='Pessoa',perfil_versao=2,remover_foto='1')).status_code,302)
        self.assertFalse(self.banco.storage.arquivos)
        self.assertIsNone(self.banco.dados['usuarios'][0]['foto_path'])

    def test_foto_invalida_publica_falha_storage_e_banco(self):
        self.assertEqual(self.post('/perfil',dict(nome='Pessoa',perfil_versao=0,foto=(BytesIO(b'html'),'foto.png'))).status_code,400)
        self.banco.storage.public=True
        self.assertEqual(self.post('/perfil',dict(nome='Pessoa',perfil_versao=0,foto=(foto(),'foto.png'))).status_code,400)
        self.banco.storage.public=False
        with patch.object(self.banco.storage,'upload',side_effect=ConnectError('segredo-nunca-logar')):
            with self.assertLogs(base.projeto.app.logger,level='WARNING') as logs:
                r=self.post('/perfil',dict(nome='Pessoa',perfil_versao=0,foto=(foto(),'foto.png')))
            self.assertNotIn('segredo-nunca-logar',' '.join(logs.output));self.assertEqual(r.status_code,503)
        self.assertIsNone(self.banco.dados['usuarios'][0]['foto_path'])
        original=base.ConsultaTeste.execute
        def falhar(consulta):
            if consulta.tabela=='usuarios' and consulta.operacao=='update': raise ConnectError('erro')
            return original(consulta)
        with patch.object(base.ConsultaTeste,'execute',falhar):
            self.assertEqual(self.post('/perfil',dict(nome='Pessoa',perfil_versao=0,foto=(foto(),'foto.png'))).status_code,503)
        # Upload não é apagado às cegas depois de um resultado ambíguo do UPDATE.
        self.assertEqual(len(self.banco.storage.arquivos),1)

    def test_perfil_csrf_login_e_html(self):
        html=self.client.get('/perfil').get_data(as_text=True)
        self.assertIn('Minha jornada',html);self.assertNotIn('senha_hash',html)
        self.assertEqual(self.client.post('/perfil',data={'nome':'Sem CSRF'}).status_code,400)
        with self.client.session_transaction() as sessao: sessao.clear()
        self.assertEqual(self.client.get('/perfil').status_code,302)
        self.assertEqual(self.client.get('/perfil/foto').status_code,302)

    def test_perfil_concorrencia_e_limpeza_parcial(self):
        self.post('/perfil',dict(nome='Pessoa',perfil_versao=0,foto=(foto(),'primeira.png')))
        anterior=self.banco.dados['usuarios'][0]['foto_path']
        original=base.ConsultaTeste.execute
        def concorrer(consulta):
            if consulta.tabela=='usuarios' and consulta.operacao=='update':
                self.banco.dados['usuarios'][0]['perfil_versao']=2
            return original(consulta)
        with patch.object(base.ConsultaTeste,'execute',concorrer):
            r=self.post('/perfil',dict(nome='Conflito',perfil_versao=1,foto=(foto(),'segunda.png')))
        self.assertEqual(r.status_code,409)
        self.assertEqual(list(self.banco.storage.arquivos),[anterior])
        with patch.object(self.banco.storage,'remove',side_effect=ConnectError('teste')):
            r=self.post('/perfil',dict(nome='Pessoa',perfil_versao=2,foto=(foto(),'terceira.png')),follow_redirects=True)
        self.assertEqual(r.status_code,200)
        self.assertIn('limpeza do arquivo anterior ficou pendente',r.get_data(as_text=True))
        self.assertNotEqual(self.banco.dados['usuarios'][0]['foto_path'],anterior)

    def test_manual_distancia_edicao_validacao_e_user(self):
        dados=dict(tipo_exercicio='Caminhada',duracao=30,distancia_km='2,5',id_usuario=2,xp=999,chave_registro=str(uuid4()))
        self.assertEqual(self.post('/atividades/nova',dados).status_code,302)
        a=self.banco.dados['atividades'][0]
        self.assertEqual(a['id_usuario'],1);self.assertEqual(a['distancia_km'],'2.5');self.assertNotIn('xp',a)
        self.assertEqual(self.post('/atividades/editar/1',dict(tipo_exercicio='Caminhada',duracao=30,distancia_km='999')).status_code,400)
        self.assertEqual(a['distancia_km'],'2.5')
        self.assertEqual(self.post('/atividades/editar/1',dict(tipo_exercicio='Caminhada',duracao=30,distancia_km='3,1')).status_code,302)
        self.assertIn('3,1 km',self.client.get('/atividades').get_data(as_text=True))
        self.entrar(2);self.post('/atividades/excluir/1');self.assertEqual(len(self.banco.dados['atividades']),1)

    def test_timer_minutos_completos_erro_retry_e_decimal(self):
        payload=dict(tipo_exercicio='Corrida',segundos_decorridos=179,chave_registro=str(uuid4()),distancia_km='100')
        headers={'X-CSRF-Token':'token-teste'}
        self.assertEqual(self.client.post('/atividades/concluir_timer',json=payload,headers=headers).status_code,400)
        self.assertFalse(self.banco.dados['atividades'])
        payload['distancia_km']='0,5'
        r=self.client.post('/atividades/concluir_timer',json=payload,headers=headers)
        self.assertEqual(r.json['duracao'],2);self.assertEqual(r.json['distancia_km'],'0.5')
        payload.update(distancia_km='999',segundos_decorridos=500)
        self.assertTrue(self.client.post('/atividades/concluir_timer',json=payload,headers=headers).json['duplicado'])
        self.assertEqual(len(self.banco.dados['atividades']),1)

    def test_payload_date_real_nao_muda_dia(self):
        with patch.dict('os.environ',{'LIFES_DATA_REGISTRO_TIPO':'date'}):
            r=self.post('/atividades/nova',dict(tipo_exercicio='Yoga',duracao=30,data_realizacao='2026-09-23'))
            self.assertEqual(r.status_code,302)
            self.assertEqual(self.banco.dados['atividades'][0]['data_registro'],'2026-09-23')
            self.post('/atividades/editar/1',dict(tipo_exercicio='Yoga',duracao=40,data_realizacao='2026-09-24'))
            self.assertEqual(self.banco.dados['atividades'][0]['data_registro'],'2026-09-24')

    def test_metas_automaticas_rotas_tres_metricas_sem_progresso_cliente(self):
        self.post('/atividades/nova',dict(tipo_exercicio='Corrida',duracao=30,distancia_km='3'))
        for metrica,alvo in [('minutos','30'),('km','3'),('sessoes','1')]:
            r=self.post('/metas/nova',dict(descricao=metrica,metrica=metrica,alvo=alvo,modalidade='Corrida',inicio='2026-09-01',prazo='2026-09-30',progresso=0,id_usuario=2))
            self.assertEqual(r.status_code,302)
        self.assertEqual([m['progresso'] for m in self.banco.dados['metas']],[100]*3)
        self.assertTrue(all(m['id_usuario']==1 for m in self.banco.dados['metas']))
        self.post('/atividades/excluir/1')
        self.assertEqual([m['progresso'] for m in self.banco.dados['metas']],[0]*3)
        self.assertEqual(len([r for r in self.banco.dados['recompensas_xp'] if r['chave_evento'].startswith('meta:')]),3)
        self.assertNotIn('type="range"',self.client.get('/metas/editar/1').get_data(as_text=True))

    def test_feedback_metas_correlacionadas_por_transacao(self):
        with base.projeto.app.test_request_context('/'):
            base.projeto.session['id_usuario']=1
            antes=base.projeto.consultar_xp()
            for evento,xp,tx in [('atividade:nova',45,100),('meta:1',50,100),('meta:outra-aba',50,101)]:
                self.banco.premiar(1,evento,'Teste',xp);self.banco.dados['recompensas_xp'][-1]['transacao']=tx
            feedback=base.projeto.preparar_recompensa(antes,evento='atividade:nova')
            self.assertEqual(feedback['xp_recebido'],95);self.assertEqual(feedback['xp'],145)
            # Edição apenas de data: sem ajuste de XP da sessão, mas com marco na transação.
            antes=base.projeto.consultar_xp()
            self.banco.premiar(1,'meta:data','Concluída ao corrigir a data',50)
            self.banco.dados['recompensas_xp'][-1]['transacao']=102
            feedback=base.projeto.preparar_recompensa(antes,transacao=102)
            self.assertEqual(feedback['xp_recebido'],50)
