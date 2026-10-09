"""Chrome local: novos módulos, áudio, animações, mobile e retry após resposta perdida."""
import logging
import threading
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
from tests.test_semanas_6_7 import BancoTeste, AGORA, DataHoraTeste, projeto


def executar():
    banco=BancoTeste()
    banco.dados['usuarios']=[dict(id_usuario=1,nome='Estudante',email='teste@example.test',senha_hash=generate_password_hash('teste'))]
    banco.dados['dicas']=[dict(id_dica=1,titulo='Água por perto',descricao='Tenha água disponível durante o dia.',categoria='Hidratação',fonte='https://www.cdc.gov/healthy-weight-growth/water-healthy-drinks/'),
                          dict(id_dica=2,titulo='Dormir melhor',descricao='Mantenha horários regulares.',categoria='Sono',fonte='https://www.cdc.gov/sleep/about/')]
    projeto.app.config.update(SECRET_KEY='apenas-teste',TESTING=True)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    pasta=Path('artifacts/validacao');pasta.mkdir(parents=True,exist_ok=True)
    with patch.object(projeto,'supabase',banco),patch.object(projeto,'agora_local',return_value=AGORA),patch.object(projeto,'datetime',DataHoraTeste):
        servidor=make_server('127.0.0.1',0,projeto.app)
        thread=threading.Thread(target=servidor.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                page=browser.new_page(viewport=dict(width=1366,height=900))
                erros=[];page.on('pageerror',lambda e:erros.append(str(e)))
                page.add_init_script('''window.osciladores=0; const original=AudioContext.prototype.createOscillator; AudioContext.prototype.createOscillator=function(){window.osciladores++;return original.apply(this,arguments)};''')
                base=f'http://127.0.0.1:{servidor.server_port}'
                page.goto(base+'/login');page.locator('#email').fill('teste@example.test');page.locator('#senha').fill('teste');page.get_by_role('button',name='Entrar',exact=True).click()
                page.wait_for_url(base+'/dashboard');expect(page.locator('.xp-card')).to_contain_text('0 XP')
                page.screenshot(path=str(pasta/'dashboard-vazio.png'),full_page=True)
                page.goto(base+'/dicas');page.locator('#pesquisaDicas').fill('água');page.get_by_role('button',name='Pesquisar',exact=True).click()
                expect(page.locator('.dica-card')).to_have_count(1)
                page.get_by_role('link',name='Ler dica').click();expect(page.locator('h1')).to_have_text('Água por perto')
                page.goto(base+'/dicas');page.screenshot(path=str(pasta/'dicas-desktop.png'),full_page=True)
                page.goto(base+'/configuracoes');expect(page.locator('#audioAtivo')).not_to_be_checked()
                page.locator('#audioTestar').click();assert page.evaluate('window.osciladores')==0
                page.locator('#audioAtivo').check();page.locator('#audioVolume').fill('40');page.locator('#audioTestar').click()
                page.wait_for_function('window.osciladores>0')
                page.reload();expect(page.locator('#audioAtivo')).to_be_checked();expect(page.locator('#audioVolume')).to_have_value('40')
                page.locator('#audioAtivo').uncheck();antes=page.evaluate('window.osciladores');page.locator('#audioTestar').click();assert page.evaluate('window.osciladores')==antes
                page.locator('#audioAtivo').check()
                page.goto(base+'/atividades/nova');page.locator('#tipo_exercicio').select_option('Corrida');page.locator('#duracao').fill('30');page.locator("#data_realizacao").fill("2026-09-24");page.get_by_role('button',name='Salvar atividade').click()
                expect(page.locator('#recompensaToast')).to_contain_text('+60 XP')
                page.reload();expect(page.locator('#recompensaToast')).to_be_hidden()
                page.goto(base+'/metas/nova');page.locator('#descricao').fill('Meta concluída');page.locator('#metrica').select_option('sessoes');page.locator('#alvo').fill('1');page.locator('#prazo').fill('2026-09-25');page.get_by_role('button',name='Salvar meta').click()
                expect(page.locator('#recompensaToast')).to_contain_text('+80 XP')
                page.goto(base+'/dashboard');expect(page.locator('.xp-card')).to_contain_text('Nível 2');expect(page.locator('.xp-card')).to_contain_text('140 XP')
                for titulo in ('Resposta perdida','Treino com som'):
                    page.goto(base+'/agenda/novo');page.locator('#titulo').fill(titulo);page.locator('#data').fill('2026-09-25');page.locator('#horario').fill('18:30');page.get_by_role('button',name='Salvar treino').click()
                page.goto(base+'/dashboard');page.clock.install()
                def concluir(id_treino):
                    page.locator('.timer-detalhes').evaluate('e=>e.open=true')
                    page.locator('#timerAtividade').select_option(str(id_treino));page.locator('#timerBotaoIniciar').click();page.clock.run_for(60000);page.locator('#timerBotaoConcluir').click();page.locator('#timerModalidade').select_option('Yoga')
                concluir(1)
                def perder_resposta(route):
                    route.fetch();route.abort()
                page.route('**/atividades/concluir_timer',perder_resposta,times=1)
                page.locator('#timerBotaoSalvar').click();expect(page.locator('#timerErro')).to_contain_text('Conexão interrompida')
                assert len(banco.dados['atividades'])==2
                page.locator('#timerBotaoSalvar').click();expect(page.locator('#timerMensagem')).to_contain_text('já registrado')
                page.wait_for_function("document.querySelector('.xp-card').textContent.includes('141 XP')")
                assert len(banco.dados['atividades'])==2
                page.locator('#timerBotaoNovo').click();concluir(2)
                page.locator('#timerBotaoSalvar').evaluate('b=>{b.click();b.click()}')
                expect(page.locator('#recompensaToast')).to_contain_text('+1 XP')
                page.wait_for_function("document.querySelector('.xp-card').textContent.includes('142 XP')")
                assert len(banco.dados['atividades'])==3
                assert page.evaluate('window.osciladores')>0
                page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(pasta/'dashboard-dados.png'),full_page=True)
                page.emulate_media(reduced_motion='reduce')
                page.goto(base+'/dicas')
                assert page.locator('.dica-card').first.evaluate("e=>getComputedStyle(e).transitionDuration")=='0s'
                page.set_viewport_size(dict(width=390,height=844))
                for rota in ('/dashboard','/dicas','/dicas/1','/pontuacao','/configuracoes','/atividades','/metas','/conquistas','/agenda','/alertas'):
                    page.goto(base+rota);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),rota
                page.goto(base+'/dicas');page.screenshot(path=str(pasta/'dicas-mobile.png'),full_page=True)
                page.goto(base+'/dashboard');page.screenshot(path=str(pasta/'dashboard-mobile.png'),full_page=True)
                page.set_viewport_size(dict(width=320,height=700));assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), page.evaluate("Array.from(document.querySelectorAll('main *')).filter(e=>e.getBoundingClientRect().right>innerWidth).map(e=>[e.tagName,e.className,e.getBoundingClientRect().right])")
                assert not erros,erros
                browser.close()
                print('Chrome semanas 8/9 OK: dicas, XP exato, nível, preferências de áudio, síntese, movimento reduzido, mobile, duplo clique e retry após resposta perdida.')
                print(f'Capturas: {pasta.resolve()}')
        finally:
            servidor.shutdown();thread.join(timeout=5)

if __name__=='__main__': executar()
