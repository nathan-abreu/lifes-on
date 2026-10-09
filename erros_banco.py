"""Classificação pública de falhas sem expor SQL, URLs, credenciais ou registros."""
import re
from httpx import HTTPStatusError, TimeoutException


def classificar_erro(erro):
    bruto = str(getattr(erro, 'code', ''))
    codigo = bruto if re.fullmatch(r'[A-Z0-9]{5,10}', bruto) else 'REDE'
    status = erro.response.status_code if isinstance(erro, HTTPStatusError) else None
    if codigo in {'42703', '42P01', 'PGRST200', 'PGRST204', 'PGRST205'}:
        categoria = 'estrutura'
        mensagem = 'Não foi possível concluir: esta operação depende de uma atualização do banco ainda não disponível. Avise o responsável pelo sistema.'
    elif codigo in {'42501', 'PGRST301', 'PGRST302', 'PGRST303', '28000', '28P01'} or status in (401, 403):
        categoria = 'acesso'
        mensagem = 'O servidor não conseguiu autorização para acessar estes dados. O responsável precisa conferir a credencial e as permissões do banco.'
    elif codigo in {'23502', '23503', '23505', '23514', '22P02', '22007', 'P0001', '42P10'}:
        categoria = 'consistencia'
        mensagem = 'Não foi possível confirmar a operação devido a uma regra de consistência dos dados. Confira o registro antes de tentar novamente e avise o responsável se o erro persistir.'
    elif isinstance(erro, TimeoutException):
        categoria = 'tempo_limite'
        mensagem = 'O banco demorou a responder. Confira se a operação foi concluída antes de tentar novamente.'
    elif codigo == 'REDE':
        categoria = 'comunicacao'
        mensagem = 'Não foi possível obter uma resposta válida do banco. Confira a disponibilidade do serviço e tente novamente.'
    else:
        categoria = 'banco'
        mensagem = 'Não foi possível concluir a operação no banco. Avise o responsável pelo sistema.'
    return codigo, categoria, mensagem
