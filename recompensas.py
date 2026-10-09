"""Níveis derivados exclusivamente do livro de recompensas confirmado pelo banco."""
from uuid import UUID
from math import isqrt


def validar_chave(valor):
    try:
        return str(UUID(valor))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Atualize o formulário para obter uma chave de registro válida.') from None


def calcular_nivel(total):
    total = max(0, int(total))
    # L>=2: limiar=100+75*(L-2)*(L-1). Raiz inteira: sem laço ou float.
    nivel = 1 if total < 100 else 2 + (isqrt(1 + 4 * ((total - 100) // 75)) - 1) // 2
    inicio = 0 if nivel == 1 else 100 + 75 * (nivel - 2) * (nivel - 1)
    necessario = 100 if nivel == 1 else 150 * (nivel - 1)
    atual = total - inicio
    return {'total': total, 'nivel': nivel, 'progresso': round(100 * atual / necessario, 2),
            'xp_no_nivel': atual, 'necessario': necessario, 'faltam': necessario - atual}


def resumir_recompensas(registros):
    return calcular_nivel(sum(int(r['xp']) for r in registros))
