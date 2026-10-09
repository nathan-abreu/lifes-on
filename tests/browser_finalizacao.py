"""Chrome + banco simulado: redesign, imagens, falhas HTTP e confirmação pendente."""
import logging
import threading
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
from tests.test_semanas_6_7 import BancoTeste, AGORA, DataHoraTeste, projeto


def executar():
    banco = BancoTeste()
    banco.dados['usuarios'] = [dict(id_usuario=1,nome='Marina',email='teste@example.test',
                                    senha_hash=generate_password_hash('teste'))]
    projeto.app.config.update(SECRET_KEY='apenas-teste',TESTING=True)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    pasta = Path('artifacts/validacao');pasta.mkdir(parents=True,exist_ok=True)
    with patch.object(projeto,'supabase',banco), patch.object(projeto,'agora_local',return_value=AGORA), patch.object(projeto,'datetime',DataHoraTeste):
        servidor = make_server('127.0.0.1',0,projeto.app)
        thread = threading.Thread(target=servidor.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='chrome',headless=True)
                page = browser.new_page(viewport=dict(width=1440,height=1000))
                page.emulate_media(reduced_motion='reduce')
                erros=[];page.on('pageerror',lambda e:erros.append(str(e)))
                base=f'http://127.0.0.1:{servidor.server_port}'
                page.goto(base+'/login');page.locator('#email').fill('teste@example.test');page.locator('#senha').fill('teste');page.get_by_role('button',name='Entrar',exact=True).click()
                page.wait_for_url(base+'/dashboard')
                assert [s.strip() for s in page.locator('.sidebar__nav a').all_text_contents()] == ['Dashboard','Agenda','Progresso','Metas','Registrar Atividade','Pontuação','Conquistas','Dicas','Alertas']
                page.locator('#audioAlternar').click();expect(page.locator('#audioAlternar')).to_have_attribute('aria-pressed','true')
                page.reload();expect(page.locator('#audioAlternar')).to_have_attribute('aria-pressed','true')
                page.locator('#audioAlternar').click()
                page.goto(base+'/atividades/nova')
                expect(page.locator('[name=frequencia]')).to_have_count(0)
                page.locator('[data-tipo="Artes Marciais"]').click()
                expect(page.locator('#tipo_exercicio')).to_have_value('Artes Marciais')
                page.locator('#duracao').fill('30');page.locator('#data_realizacao').fill('2026-09-23')
                page.screenshot(path=str(pasta/'registro-premium.png'),full_page=True)
                page.get_by_role('button',name='Salvar atividade',exact=True).click()
                expect(page.locator('.atividade-linha')).to_contain_text('23/09/2026')
                assert banco.dados['atividades'][0]['frequencia'] is None
                page.goto(base+'/agenda/novo');page.locator('#titulo').fill('Corrida ao ar livre');page.locator('#modalidade').select_option('Corrida')
                page.locator('#data').fill('2026-09-25');page.locator('#horario').fill('07:30');page.get_by_role('button',name='Salvar treino',exact=True).click()
                page.goto(base+'/metas/nova');page.locator('#descricao').fill('Completar meus primeiros 5 km');page.locator('#prazo').fill('2026-10-25');page.get_by_role('button',name='Salvar meta',exact=True).click()
                page.goto(base+'/dashboard');expect(page.locator('.arte-hero img')).to_have_attribute('src','/static/img/modalidades/corrida.webp')
                page.locator('.arte-hero img').evaluate('(img)=>img.decode()')
                page.screenshot(path=str(pasta/'dashboard-premium-desktop.png'),full_page=True)
                # Todos os módulos e formulários, cinco tamanhos de tela.
                for largura in (1440,1024,768,390,320):
                    page.set_viewport_size(dict(width=largura,height=900))
                    for rota in ('/dashboard','/agenda','/progresso','/metas','/atividades/nova','/atividades','/pontuacao','/conquistas','/dicas','/alertas','/agenda/novo'):
                        page.goto(base+rota)
                        page.wait_for_function('Array.from(document.images).every(i=>i.complete)')
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (largura,rota)
                    if largura in (1440,390):
                        page.goto(base+'/conquistas');page.screenshot(path=str(pasta/f'conquistas-{largura}.png'),full_page=True)
                        page.goto(base+'/dashboard');page.screenshot(path=str(pasta/f'dashboard-premium-{largura}.png'),full_page=True)
                # Falha da imagem carrega o fallback, sem outra modalidade no lugar.
                page.route('**/corrida.webp',lambda route:route.abort())
                page.goto(base+'/dashboard');expect(page.locator('.arte-hero .arte-fallback')).to_be_visible()
                page.unroute('**/corrida.webp')
                page.set_viewport_size(dict(width=1366,height=900));page.goto(base+'/agenda')
                page.get_by_role('link',name='Iniciar',exact=True).click()
                expect(page.locator('#timerRodando')).to_be_visible()
                page.clock.install();page.clock.run_for(60000);page.locator('#timerBotaoConcluir').click()
                expect(page.locator('#timerModalidade')).to_have_value('Corrida')
                page.route('**/atividades/concluir_timer', lambda route: route.fulfill(
                    status=503, content_type='application/json', body='{invalido'), times=1)
                page.locator('#timerBotaoSalvar').click()
                expect(page.locator('#timerErro')).to_contain_text('resposta inválida')
                expect(page.locator('#timerBotaoSalvar')).to_be_enabled()
                assert len(banco.dados['atividades']) == 1
                banco.ausentes.add('recompensas_xp')
                page.locator('#timerBotaoSalvar').click()
                expect(page.locator('#timerErro')).to_contain_text('atualização do banco')
                expect(page.locator('#recompensaToast')).to_be_hidden()
                assert len(banco.dados['atividades'])==1
                banco.ausentes.clear()
                # Recarregar preserva a confirmação e o UUID, inclusive após resposta perdida.
                chave = page.evaluate("JSON.parse(sessionStorage.getItem('lifes-on-atividade-1-pendente')).chaveRegistro")
                page.reload();expect(page.locator('#timerConfirmacao')).to_be_visible()
                assert chave == page.evaluate("JSON.parse(sessionStorage.getItem('lifes-on-atividade-1-pendente')).chaveRegistro")
                def perder(route):
                    route.fetch();route.abort()
                page.route('**/atividades/concluir_timer',perder,times=1)
                page.locator('#timerBotaoSalvar').click();expect(page.locator('#timerErro')).to_contain_text('Conexão interrompida')
                assert len(banco.dados['atividades'])==2
                page.reload();expect(page.locator('#timerConfirmacao')).to_be_visible()
                page.locator('#timerBotaoSalvar').click();expect(page.locator('#timerMensagem')).to_contain_text('já registrado')
                assert len(banco.dados['atividades'])==2
                assert not page.evaluate("sessionStorage.getItem('lifes-on-atividade-1-pendente')")
                assert not erros, erros
                browser.close()
                print('Premium Chrome OK: 55 telas responsivas, sidebar, Artes Marciais, data, áudio, WebP/fallback, Agenda -> timer, 503 e retry após reload/resposta perdida.')
        finally:
            servidor.shutdown();thread.join(timeout=5)


if __name__=='__main__':
    executar()
