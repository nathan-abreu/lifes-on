"""Níveis derivados exclusivamente do livro de recompensas confirmado pelo banco."""
from uuid import UUID


def validar_chave(valor):
    try:
        return str(UUID(valor))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Atualize o formulário para obter uma chave de registro válida.') from None


def calcular_nivel(total):
    total = max(0, int(total))
    # Cada nível exige 100 XP: nível 1 começa em zero.
    return {'total': total, 'nivel': 1 + total // 100, 'progresso': total % 100,
            'faltam': 100 - total % 100}


def resumir_recompensas(registros):
    return calcular_nivel(sum(int(r['xp']) for r in registros))
