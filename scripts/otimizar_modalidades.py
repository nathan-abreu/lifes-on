"""Copia PNGs disponíveis e exporta WebP via Chrome, preservando os originais.

Utilitário local opcional: requer requirements-dev e Chrome; nenhuma dependência
nova no aplicativo. Executar: python -m scripts.otimizar_modalidades.
"""
import base64
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
from modalidades import MODALIDADES


def executar():
    raiz = Path(__file__).resolve().parents[1]
    destino = raiz / 'static/img/modalidades'
    destino.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        for nome, (slug, _) in MODALIDADES.items():
            nomes = [slug + '.png']
            if nome == 'Artes Marciais':
                nomes.append('artesmarciais.png')
            origem = next((p / n for p in (raiz / 'imgs', raiz / 'static/imgs', destino)
                           for n in nomes if (p / n).is_file()), None)
            if not origem:
                print(f'{nome}: arquivo ausente, fallback mantido.')
                continue
            png = destino / (slug + '.png')
            if not png.exists():
                shutil.copy2(origem, png)
            dados = base64.b64encode(png.read_bytes()).decode('ascii')
            webp = page.evaluate('''async dados => {
                const img = new Image();img.src='data:image/png;base64,'+dados;
                await img.decode();
                const escala=Math.min(1,800/Math.max(img.width,img.height));
                const canvas=document.createElement('canvas');
                canvas.width=Math.round(img.width*escala);canvas.height=Math.round(img.height*escala);
                canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);
                return canvas.toDataURL('image/webp',0.92).split(',')[1];
            }''', dados)
            arquivo = destino / (slug + '.webp')
            arquivo.write_bytes(base64.b64decode(webp))
            print(f'{nome}: PNG {png.stat().st_size} -> WebP {arquivo.stat().st_size} bytes.')
        browser.close()


if __name__ == '__main__':
    executar()
