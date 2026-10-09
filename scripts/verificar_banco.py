"""Diagnóstico somente de leitura: python -m scripts.verificar_banco.

Não lê registros, não grava dados e não imprime chaves. Confere as colunas
esperadas pelo Flask usando SELECT com limit=0 no Supabase configurado.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from httpx import HTTPError
from postgrest.exceptions import APIError
from banco import criar_cliente, chave_do_servidor


def verificar():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    url = os.getenv("SUPABASE_URL")
    try:
        chave = chave_do_servidor()
    except RuntimeError as erro:
        print(str(erro))
        return 1
    if not url or not chave:
        print("Configure SUPABASE_URL e a chave do banco no .env.")
        return 1
    cliente = criar_cliente(url, chave)
    consultas = {
        "usuarios": "id_usuario,nome,email,senha_hash",
        "alertas": "id_alerta,mensagem,tipo,data_hora,status,id_usuario,chave_evento",
        "atividades": "id_atividade,id_usuario,tipo_exercicio,duracao,frequencia,data_registro,chave_registro,id_agenda",
        "metas": "id_meta,id_usuario,descricao,prazo,progresso",
        "agenda": "id_agenda,id_usuario,horario,lembrete,titulo,realizado_em,modalidade",
        "conquistas": "id_conquista,nome,descricao,pontos",
        "usuario_conquista": "id_usuario,id_conquista,data_obtencao",
        "dicas": "id_dica,titulo,descricao,categoria,fonte",
        "recompensas_xp": "id_recompensa,id_usuario,chave_evento,motivo,xp,criado_em",
    }
    falhou = False
    if '--evolucao' in sys.argv:
        consultas['usuarios'] += ',foto_path,perfil_versao'
        consultas['atividades'] += ',distancia_km,xp_versao,xp_atual,xp_revisao,xp_transacao'
        consultas['metas'] += ',metrica,modalidade,alvo,inicio,acumulado'
        consultas['recompensas_xp'] += ',transacao'
    for tabela, campos in consultas.items():
        try:
            cliente.table(tabela).select(campos).limit(0).execute()
            print(f"{tabela}: colunas acessíveis (nenhum registro consultado).")
        except APIError as erro:
            falhou = True
            if erro.code in ("42703", "PGRST204", "42P01", "PGRST205"):
                etapa = 'evolucao_perfil_metas_xp_niveis.sql' if '--evolucao' in sys.argv else 'schema.sql e as migrações anteriores'
                print(f"{tabela}: estrutura incompleta ({erro.code}); confira {etapa} antes de aplicar SQL.")
                if '--detalhado' in sys.argv and erro.code in ('42703', 'PGRST204'):
                    for campo in campos.split(','):
                        try:
                            cliente.table(tabela).select(campo).limit(0).execute()
                        except APIError as falha:
                            print(f"  {tabela}.{campo}: indisponível ({falha.code}).")
                        except HTTPError:
                            print(f"  {tabela}.{campo}: falha de conexão.")
            else:
                print(f"{tabela}: acesso recusado ou falha de banco ({erro.code}); confira chave e permissões.")
        except HTTPError:
            falhou = True
            print(f"{tabela}: falha de conexão; confira URL, DNS e disponibilidade do projeto.")
    if '--evolucao' in sys.argv:
        try:
            resposta = cliente.postgrest.session.get(url.rstrip('/') + '/rest/v1/', headers={
                'apikey': chave, 'Authorization': 'Bearer ' + chave, 'Accept': 'application/openapi+json'})
            resposta.raise_for_status()
            formato = resposta.json().get('definitions', {}).get('atividades', {}).get('properties', {}).get('data_registro', {}).get('format')
            esperado = {'date':'date', 'timestamp without time zone':'timestamp',
                        'timestamp with time zone':'timestamptz'}.get(formato)
            configurado = os.getenv('LIFES_DATA_REGISTRO_TIPO', 'date')
            if esperado is None:
                falhou = True
                print('Tipo da data não confirmado pelo OpenAPI; conferir diagnóstico SQL.')
            elif configurado != esperado:
                falhou = True
                print(f'Configuração necessária: LIFES_DATA_REGISTRO_TIPO={esperado}. Nenhuma configuração foi alterada.')
            else:
                print(f'Tipo de data confirmado: {esperado}; configuração compatível.')
        except (HTTPError, ValueError):
            falhou = True
            print('Não foi possível conferir metadados de data; usar diagnóstico SQL. Nenhum registro foi consultado.')
    print("Este diagnóstico não valida INSERT, UPDATE, DELETE, policies ou persistência.")
    return int(falhou)


if __name__ == "__main__":
    sys.exit(verificar())
