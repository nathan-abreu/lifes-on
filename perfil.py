"""Imagens privadas: somente o Flask acessa Storage; nomes de objeto não vêm do cliente."""
from io import BytesIO
import re
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_FOTO = 5 * 1024 * 1024


def validar_nome(valor):
    nome = ' '.join(valor.split())
    if not 1 <= len(nome) <= 80 or any(ord(c) < 32 for c in nome):
        raise ValueError('Informe um nome de exibição com 1 a 80 caracteres.')
    return nome


def preparar_foto(arquivo):
    dados = arquivo.read(MAX_FOTO + 1)
    if not dados or len(dados) > MAX_FOTO:
        raise ValueError('A foto deve ter até 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(dados)) as img:
                if img.format not in ('JPEG', 'PNG', 'WEBP') or getattr(img, 'n_frames', 1) != 1:
                    raise ValueError('Use uma imagem estática JPEG, PNG ou WebP.')
                if img.width * img.height > 16000000:
                    raise ValueError('A foto deve ter no máximo 16 milhões de pixels.')
                img.verify()
            with Image.open(BytesIO(dados)) as img:
                img.load()
                foto = ImageOps.exif_transpose(img).convert('RGBA')
                foto.thumbnail((512, 512))
                # Nova imagem remove EXIF/metadados e conteúdo extra do arquivo.
                limpa = Image.new('RGBA', foto.size)
                limpa.paste(foto)
                saida = BytesIO()
                limpa.save(saida, format='PNG')
                return saida.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Arquivo inválido. Envie uma foto JPEG, PNG ou WebP íntegra.') from None


def caminho_proprio(caminho, usuario):
    return isinstance(caminho, str) and bool(re.fullmatch(str(usuario) + r'/[0-9a-f]{32}\.png', caminho))
