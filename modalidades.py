"""Catálogo único; imagens ausentes nunca representam outra modalidade."""
from pathlib import Path

MODALIDADES = {
    'Corrida': ('corrida', 'person-running'),
    'Musculação': ('musculacao', 'dumbbell'),
    'Ciclismo': ('ciclismo', 'bicycle'),
    'Natação': ('natacao', 'person-swimming'),
    'Yoga': ('yoga', 'leaf'),
    'Artes Marciais': ('artemarcial', 'hand-fist'),
    'Outros': ('outros', 'shapes'),
}
TIPOS_EXERCICIO = list(MODALIDADES)


def imagem_modalidade(nome):
    slug, icone = MODALIDADES.get(nome, ('', 'calendar-days'))
    raiz = Path(__file__).parent / 'static'
    candidatos = [f'img/modalidades/{slug}.{ext}' for ext in ('webp', 'png')]
    if nome == 'Artes Marciais':
        candidatos += ['img/modalidades/artesmarciais.png']
    return {'arquivo': next((p for p in candidatos if slug and (raiz / p).is_file()), None),
            'icone': icone, 'nome': nome or 'Treino livre'}
