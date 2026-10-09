"""Chrome local: formulário de perfil, metas, distância, timer e responsividade."""
import logging
import threading
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
from tests.test_semanas_6_7 import BancoTeste, AGORA, DataHoraTeste, projeto
from tests.test_evolucao import StorageTeste, foto


def executar():
    banco=BancoTeste();banco.storage=StorageTeste()
    banco.dados['usuarios']=[dict(id_usuario=1,nome='Marina',email='perfil@local.test',senha_hash=generate_password_hash('teste'),foto_path=None,perfil_versao=0)]
    projeto.app.config.update(SECRET_KEY='apenas-teste',TESTING=True)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    pasta=Path('artifacts/validacao');pasta.mkdir(parents=True,exist_ok=True)
    with patch.object(projeto,'supabase',banco),patch.object(projeto,'agora_local',return_value=AGORA),patch.object(projeto,'datetime',DataHoraTeste):
        servidor=make_server('127.0.0.1',0,projeto.app)
        thread=threading.Thread(target=servidor.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                navegador=pw.chromium.launch(channel='chrome',headless=True)
                pagina=navegador.new_page(viewport=dict(width=1440,height=1000))
                erros=[];pagina.on('pageerror',lambda e:erros.append(str(e)))
                base=f'http://127.0.0.1:{servidor.server_port}'
                pagina.goto(base+'/login');pagina.locator('#email').fill('perfil@local.test');pagina.locator('#senha').fill('teste');pagina.get_by_role('button',name='Entrar',exact=True).click();pagina.wait_for_url(base+'/dashboard')
                pagina.goto(base+'/perfil');expect(pagina.locator('.perfil-retrato .avatar img')).to_have_count(0)
                pagina.locator('#nomePerfil').fill('Marina Oliveira')
                pagina.locator('#fotoPerfil').set_input_files(dict(name='minha-foto.png',mimeType='image/png',buffer=foto().getvalue()))
                expect(pagina.locator('#fotoPreview')).to_be_visible()
                pagina.get_by_role('button',name='Salvar perfil').click();expect(pagina.locator('#nomePerfil')).to_have_value('Marina Oliveira')
                pagina.wait_for_function("document.querySelector('.perfil-retrato .avatar img')?.naturalWidth>0")
                assert len(banco.storage.arquivos)==1
                pagina.goto(base+'/dashboard');expect(pagina.locator('.dashboard-saudacao')).to_contain_text('Marina Oliveira')
                pagina.goto(base+'/atividades/nova');pagina.locator('[data-tipo="Caminhada"]').click()
                expect(pagina.locator('#distancia_km')).to_be_visible()
                pagina.locator('#duracao').fill('30');pagina.locator('#distancia_km').fill('2,5')
                pagina.get_by_role('button',name='Salvar atividade').click();pagina.wait_for_url(base+'/atividades')
                expect(pagina.locator('.atividade-linha')).to_contain_text('2,5 km')
                pagina.goto(base+'/metas/nova');pagina.locator('#descricao').fill('Caminhar 5 km');pagina.locator('#metrica').select_option('km');pagina.locator('#modalidadeMeta').select_option('Caminhada')
                assert pagina.locator('#modalidadeMeta option[value="Yoga"]').is_disabled()
                pagina.locator('#alvo').fill('5');pagina.locator('#prazo').fill('2026-09-30');pagina.get_by_role('button',name='Salvar meta').click();pagina.wait_for_url(base+'/metas')
                expect(pagina.locator('.meta-cartao')).to_contain_text('50%');expect(pagina.locator('.meta-cartao')).to_contain_text('2,5 / 5 km')
                for largura in (1440,1024,768,390,320):
                    pagina.set_viewport_size(dict(width=largura,height=1000))
                    for rota in ('/perfil','/metas','/metas/editar/1','/atividades/nova','/pontuacao','/dashboard'):
                        pagina.goto(base+rota)
                        assert pagina.evaluate('document.documentElement.scrollWidth<=innerWidth'),(largura,rota)
                    if largura in (1440,390):
                        for rota in ('perfil','metas','pontuacao'):
                            pagina.goto(base+'/'+rota);pagina.screenshot(path=str(pasta/f'evolucao-{rota}-{largura}.png'),full_page=True)
                pagina.set_viewport_size(dict(width=1366,height=1000))
                pagina.goto(base+'/agenda/novo');pagina.locator('#titulo').fill('Caminhada com distância');pagina.locator('#modalidade').select_option('Caminhada');pagina.locator('#data').fill('2026-09-25');pagina.locator('#horario').fill('18:30');pagina.get_by_role('button',name='Salvar treino').click()
                pagina.goto(base+'/dashboard');pagina.clock.install();pagina.locator('[data-iniciar-treino]').click();pagina.clock.run_for(179000);pagina.locator('#timerBotaoConcluir').click()
                expect(pagina.locator('#timerResumo')).to_contain_text('2 min')
                pagina.locator('#timerDistancia').fill('999');pagina.locator('#timerBotaoSalvar').click()
                expect(pagina.locator('#timerErro')).to_contain_text('incompatível')
                chave=pagina.evaluate("JSON.parse(sessionStorage.getItem('lifes-on-atividade-1-pendente')).chaveRegistro")
                pagina.reload();expect(pagina.locator('#timerDistancia')).to_have_value('999');expect(pagina.locator('#timerConfirmacao')).to_be_visible()
                assert pagina.evaluate("JSON.parse(sessionStorage.getItem('lifes-on-atividade-1-pendente')).chaveRegistro")==chave
                pagina.locator('#timerDistancia').fill('0,3');pagina.locator('#timerBotaoSalvar').click();expect(pagina.locator('#timerMensagem')).to_contain_text('2 minutos')
                assert len(banco.dados['atividades'])==2
                assert banco.dados['atividades'][-1]['distancia_km']=='0.3'
                pagina.goto(base+'/perfil');pagina.locator('[name=remover_foto]').check();pagina.get_by_role('button',name='Salvar perfil').click();expect(pagina.locator('.perfil-retrato .avatar img')).to_have_count(0)
                assert not banco.storage.arquivos
                assert not erros,erros
                navegador.close()
                print('Chrome evolução OK: foto/nome, metas, Caminhada, decimal, 30 telas responsivas, timer sem arredondar e retry após validação/reload.')
        finally:
            servidor.shutdown();thread.join(timeout=5)


if __name__=='__main__': executar()
