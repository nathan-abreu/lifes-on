"""Validação de entradas. O PostgreSQL confirma metas e XP atomicamente."""
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from modalidades import TIPOS_EXERCICIO

DISTANCIAS = {'Corrida': (5, 30), 'Caminhada': (3, 12), 'Ciclismo': (2, 80), 'Natação': (10, 10)}


def quantidade(valor):
    if valor is None:
        return '—'
    return format(Decimal(str(valor)).normalize(), 'f').replace('.', ',')


def data_para_banco(valor, tipo):
    """DATE usa o dia em Brasília; timestamp legado sem offset representa UTC."""
    instante = datetime.fromisoformat(valor.replace('Z', '+00:00'))
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    if tipo == 'date':
        return instante.astimezone(ZoneInfo('America/Sao_Paulo')).date().isoformat()
    if tipo == 'timestamp':
        return instante.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
    if tipo == 'timestamptz':
        return instante.astimezone(timezone.utc).isoformat()
    raise ValueError('Configuração de data inválida. Confira LIFES_DATA_REGISTRO_TIPO no servidor.')


def decimal_positivo(valor, maximo):
    try:
        texto = str(valor).strip().replace(',', '.')
        numero = Decimal(texto)
        if not numero.is_finite() or not 0 < numero <= maximo or numero != numero.quantize(Decimal('.001')):
            raise ValueError
        return numero
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'Informe um valor positivo até {maximo}, com no máximo 3 casas decimais.') from None


def validar_distancia(tipo, duracao, valor):
    if valor is None or str(valor).strip() == '':
        return None
    if tipo not in DISTANCIAS:
        raise ValueError('Esta modalidade aceita minutos e sessões, sem distância.')
    distancia = decimal_positivo(valor, 1000)
    if distancia * 60 > Decimal(duracao) * DISTANCIAS[tipo][1]:
        raise ValueError(f'Distância incompatível com a duração: limite de {DISTANCIAS[tipo][1]} km/h para {tipo}.')
    return str(distancia)


def validar_meta(form):
    descricao = form.get('descricao', '').strip()
    metrica = form.get('metrica')
    modalidade = form.get('modalidade') or None
    if not 1 <= len(descricao) <= 200:
        raise ValueError('Informe um objetivo com até 200 caracteres.')
    if metrica not in ('minutos', 'km', 'sessoes') or (modalidade and modalidade not in TIPOS_EXERCICIO):
        raise ValueError('Selecione a métrica e a modalidade da meta.')
    if metrica == 'km' and modalidade and modalidade not in DISTANCIAS:
        raise ValueError('Esta modalidade não aceita metas de distância.')
    alvo = decimal_positivo(form.get('alvo'), 1000000)
    if metrica in ('minutos', 'sessoes') and alvo != int(alvo):
        raise ValueError('Minutos e sessões exigem um objetivo inteiro.')
    try:
        inicio, fim = date.fromisoformat(form.get('inicio', '')), date.fromisoformat(form.get('prazo', ''))
        if fim < inicio:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('Informe datas válidas; o prazo deve ser igual ou posterior ao início.') from None
    return dict(descricao=descricao, metrica=metrica, modalidade=modalidade,
                alvo=str(alvo), inicio=inicio.isoformat(), prazo=fim.isoformat())
