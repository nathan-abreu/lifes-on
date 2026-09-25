"""Verificação opcional no Chrome: python -m tests.browser_smoke.

Requer `pip install playwright` e Google Chrome instalado. Usa somente banco
em memória e um servidor local temporário; não acessa o Supabase real.
"""

import logging
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from tests.test_semanas_6_7 import AGORA, BancoTeste, DataHoraTeste, projeto


def executar():
    banco = BancoTeste()
    banco.dados["usuarios"] = [
        {"id_usuario": i, "nome": f"Estudante {i}", "email": f"pessoa{i}@example.test",
         "senha_hash": generate_password_hash("senha-teste")}
        for i in (1, 2)
    ]
    projeto.app.config.update(SECRET_KEY="somente-teste-local", TESTING=True)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    pasta = Path(tempfile.mkdtemp(prefix="lifes-on-browser-"))
    with (patch.object(projeto, "supabase", banco),
          patch.object(projeto, "agora_local", return_value=AGORA),
          patch.object(projeto, "datetime", DataHoraTeste)):
        servidor = make_server("127.0.0.1", 0, projeto.app)
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{servidor.server_port}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                erros = []
                page.on("pageerror", lambda erro: erros.append(str(erro)))

                def login(usuario):
                    page.goto(base + "/login")
                    page.locator("#email").fill(f"pessoa{usuario}@example.test")
                    page.locator("#senha").fill("senha-teste")
                    page.get_by_role("button", name="Entrar", exact=True).click()
                    page.wait_for_url(base + "/dashboard")

                login(1)
                page.wait_for_function("typeof Chart !== 'undefined' && !!Chart.getChart('graficoProgresso')")
                assert page.evaluate("Chart.getChart('graficoProgresso').data.datasets[0].data") == [0] * 7
                expect(page.locator("#timerRodando")).to_be_hidden()

                page.goto(base + "/atividades/nova")
                page.locator("#tipo_exercicio").select_option("Corrida")
                page.locator("#duracao").fill("30")
                page.locator('[data-valor="3"]').click()
                page.get_by_role("button", name="Salvar atividade").click()
                page.wait_for_url(base + "/atividades")
                assert len(banco.dados["usuario_conquista"]) == 1

                page.goto(base + "/metas/nova")
                page.locator("#descricao").fill("Meta do navegador")
                page.locator("#prazo").fill("2026-09-25")
                page.get_by_role("button", name="Salvar meta").click()
                page.wait_for_url(base + "/metas")

                page.goto(base + "/agenda/novo")
                page.locator("#titulo").fill("Treino do navegador")
                assert page.locator("#data").get_attribute("min") == "2026-09-24"
                page.locator("#data").fill("2026-09-25")
                page.locator("#horario").fill("18:30")
                page.locator("#descricao").fill("Descrição de teste")
                page.get_by_role("button", name="Salvar treino").click()
                page.wait_for_url(base + "/agenda")
                expect(page.locator(".treino--proximo")).to_contain_text("Treino do navegador")
                assert banco.dados["agenda"][0]["horario"] == "2026-09-25T18:30:00"
                page.get_by_role("link", name="Editar Treino do navegador").click()
                page.locator("#titulo").fill("Treino editado")
                page.get_by_role("button", name="Salvar treino").click()
                page.wait_for_url(base + "/agenda")

                page.goto(base + "/alertas")
                expect(page.locator("#alertas")).to_contain_text("Treino editado")
                expect(page.locator("#alertas")).to_contain_text("vence amanhã")
                nao_lidos = page.locator(".notificacao--nova").count()
                assert nao_lidos > 0
                page.get_by_role("button", name="Marcar como lido", exact=True).first.click()
                expect(page.locator(".notificacao--nova")).to_have_count(nao_lidos - 1)
                expect(page.locator(".sino small")).to_have_text(str(nao_lidos - 1))
                page.reload()
                expect(page.locator(".notificacao--nova")).to_have_count(nao_lidos - 1)
                page.get_by_role("button", name="Marcar todas como lidas").click()
                expect(page.locator(".sino small")).to_have_count(0)
                expect(page.locator(".notificacao--nova")).to_have_count(0)
                page.reload()
                expect(page.locator(".sino small")).to_have_count(0)
                page.goto(base + "/conquistas")
                expect(page.locator(".conquista--desbloqueada")).to_have_count(1)
                expect(page.locator(".conquista--desbloqueada")).to_contain_text("Obtida em: 24/09/2026")
                page.goto(base + "/progresso")
                page.wait_for_function("typeof Chart !== 'undefined' && !!Chart.getChart('graficoProgresso')")
                assert sum(page.evaluate("Chart.getChart('graficoProgresso').data.datasets[0].data")) == 30
                assert page.evaluate("Chart.getChart('graficoMensal').config.type") == "bar"
                assert sum(page.evaluate("Chart.getChart('graficoMensal').data.datasets[0].data")) == 1
                page.evaluate("Chart.getChart('graficoProgresso').update('none'); Chart.getChart('graficoMensal').update('none');")
                page.screenshot(path=str(pasta / "progresso-desktop.png"), full_page=True)

                page.goto(base + "/dashboard")
                expect(page.locator(".mini-cards")).to_contain_text("Meta do navegador")
                expect(page.locator(".mini-cards")).to_contain_text("Treino editado")
                assert " XP" not in page.locator("body").inner_text()
                page.clock.install()
                page.locator("#timerAtividade").select_option("1")
                page.locator("#timerBotaoIniciar").click()
                expect(page.locator("#timerRodando")).to_be_visible()
                page.locator("#timerBotaoConcluir").click()
                expect(page.locator("#timerErro")).to_contain_text("mínimo 30 segundos")
                assert len(banco.dados["atividades"]) == 1
                page.locator("#timerBotaoPausar").click()  # continuar após sessão curta
                page.clock.run_for(31000)
                page.locator("#timerBotaoPausar").click()
                expect(page.locator("#timerRelogio")).to_have_text("00:00:31")
                page.clock.run_for(120000)
                expect(page.locator("#timerRelogio")).to_have_text("00:00:31")
                page.locator("#timerBotaoPausar").click()
                page.clock.run_for(30000)
                page.locator("#timerBotaoConcluir").click()
                expect(page.locator("#timerResumo")).to_contain_text("00:01:01")
                assert len(banco.dados["atividades"]) == 1  # finalizar ainda não salva
                page.locator("#timerModalidade").select_option("Corrida")
                page.locator("#timerBotaoSalvar").evaluate("b => { b.click(); b.click(); }")
                expect(page.locator("#timerMensagem")).to_contain_text("Atividade concluída! Treino editado • 1 minuto")
                assert len(banco.dados["atividades"]) == 2
                assert banco.dados["atividades"][-1]["id_usuario"] == 1
                expect(page.locator("#timerConquistas")).to_be_empty()
                page.wait_for_function("typeof Chart !== 'undefined' && !!Chart.getChart('graficoProgresso')")
                assert sum(page.evaluate("Chart.getChart('graficoProgresso').data.datasets[0].data")) == 31
                page.locator("#timerBotaoNovo").click()
                page.locator("#timerAtividade").select_option("1")
                page.locator("#timerBotaoIniciar").click()
                page.clock.run_for(35000)
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator('#timerRodando [data-cancelar]').click()
                expect(page.locator("#timerFormulario")).to_be_visible()
                assert len(banco.dados["atividades"]) == 2
                page.evaluate("window.scrollTo(0, 0)")
                page.screenshot(path=str(pasta / "dashboard-desktop.png"), full_page=True)

                page.set_viewport_size({"width": 390, "height": 844})
                for caminho in ("/dashboard", "/progresso", "/agenda", "/conquistas", "/alertas"):
                    page.goto(base + caminho)
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), caminho
                page.goto(base + "/agenda")
                page.screenshot(path=str(pasta / "agenda-mobile.png"), full_page=True)
                page.locator("#menuBotao").click()
                expect(page.locator("#app")).to_have_class("app menu-aberto")
                page.locator("#sombraMenu").click(position={"x": 380, "y": 400})
                page.on("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Excluir Treino editado").click()
                expect(page.locator(".treino--proximo")).to_have_count(0)
                assert not banco.dados["agenda"]

                page.goto(base + "/logout")
                login(2)
                expect(page.locator("#timerAtividade")).to_have_count(0)
                expect(page.locator("#timerFormulario")).to_contain_text("Nenhum treino agendado")
                page.goto(base + "/agenda/novo")
                page.locator("#titulo").fill("Yoga da manhã")
                page.locator("#data").fill("2026-09-25")
                page.locator("#horario").fill("07:00")
                page.get_by_role("button", name="Salvar treino").click()
                page.goto(base + "/dashboard")
                page.locator('[data-iniciar-treino]').click()
                page.clock.run_for(60000)
                page.locator("#timerBotaoConcluir").click()
                page.locator("#timerBotaoVoltar").click()
                page.clock.run_for(30000)
                page.locator("#timerBotaoConcluir").click()
                page.locator("#timerModalidade").select_option("Corrida")
                page.locator("#timerBotaoSalvar").click()
                expect(page.locator("#timerConquistas")).to_contain_text("Primeiro passo")
                assert banco.dados["atividades"][-1]["id_usuario"] == 2
                assert banco.dados["atividades"][-1]["duracao"] == 2
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.clock.run_for(500)
                page.evaluate("window.scrollTo(0, 0)")
                page.screenshot(path=str(pasta / "dashboard-mobile.png"), full_page=True)
                page.set_viewport_size({"width": 320, "height": 700})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), page.evaluate("Array.from(document.querySelectorAll('main *')).filter(e => e.getBoundingClientRect().right > innerWidth).map(e => [e.tagName, e.className, e.getBoundingClientRect().right])")
                # Uma falha da CDN não esconde os números nem quebra o timer.
                page.route("**/chart.js@*/**", lambda route: route.abort())
                page.goto(base + "/progresso")
                expect(page.locator("#graficoErro")).to_be_visible()
                page.locator(".grafico-tabela summary").first.click()
                expect(page.locator(".grafico-tabela table").first).to_be_visible()
                assert not erros, erros
                browser.close()
                print("Navegador OK: login, formulários, gráfico, timer, agenda, alertas, conquistas e mobile.")
                print(f"Capturas: {pasta}")
        finally:
            servidor.shutdown()
            thread.join(timeout=5)


if __name__ == "__main__":
    executar()
