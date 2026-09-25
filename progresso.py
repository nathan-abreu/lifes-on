"""Cálculos das semanas 6 e 7, sem consultas ao banco ou dados de exemplo."""

from datetime import date, datetime, timedelta, timezone
from calendar import monthrange
from zoneinfo import ZoneInfo


FUSO = ZoneInfo("America/Sao_Paulo")


def agora_local():
    return datetime.now(FUSO)


def data_atividade(valor):
    """O código antigo gravava UTC sem offset; datas puras mantêm seu dia."""
    if not valor:
        return None
    try:
        if len(valor) == 10:
            return date.fromisoformat(valor)
        instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if instante.tzinfo is None:
            instante = instante.replace(tzinfo=timezone.utc)
        return instante.astimezone(FUSO).date()
    except (TypeError, ValueError):
        return None


def calcular_progresso(atividades, metas, hoje):
    inicio = hoje - timedelta(days=hoje.weekday())
    dias = [inicio + timedelta(days=i) for i in range(7)]
    registros = [(a, data_atividade(a.get("data_registro"))) for a in atividades]
    # Registros futuros não representam atividades já realizadas.
    registros = [(a, dia) for a, dia in registros if dia and dia <= hoje]
    dias_ativos = {dia for _, dia in registros}
    minutos = [sum(int(a["duracao"]) for a, dia in registros if dia == d) for d in dias]
    quantidades = [sum(dia == d for _, dia in registros) for d in dias]

    sequencia = 0
    cursor = hoje if hoje in dias_ativos else hoje - timedelta(days=1)
    while cursor in dias_ativos:
        sequencia += 1
        cursor -= timedelta(days=1)

    melhor_sequencia = atual = 0
    anterior = None
    for dia in sorted(dias_ativos):
        atual = atual + 1 if anterior and dia == anterior + timedelta(days=1) else 1
        melhor_sequencia = max(melhor_sequencia, atual)
        anterior = dia

    percentuais = [max(0, min(100, int(m.get("progresso") or 0))) for m in metas]
    minutos_total = sum(int(a["duracao"]) for a, _ in registros)
    # Semanas do calendário, recortadas pelos limites do mês atual.
    primeiro = hoje.replace(day=1)
    ultimo = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
    inicio_mes = primeiro - timedelta(days=primeiro.weekday())
    mensal = {"labels": [], "atividades": [], "minutos": []}
    while inicio_mes <= ultimo:
        de = max(primeiro, inicio_mes)
        ate = min(ultimo, inicio_mes + timedelta(days=6))
        mensal["labels"].append(f"{de:%d/%m}–{ate:%d/%m}")
        mensal["atividades"].append(sum(de <= dia <= ate for _, dia in registros))
        mensal["minutos"].append(sum(int(a["duracao"]) for a, dia in registros if de <= dia <= ate))
        inicio_mes += timedelta(days=7)
    por_tipo = {}
    for atividade, _ in registros:
        tipo = atividade["tipo_exercicio"]
        por_tipo[tipo] = por_tipo.get(tipo, 0) + int(atividade["duracao"])
    modalidades = [
        {"nome": tipo, "minutos": total, "percentual": round(total * 100 / max(por_tipo.values()))}
        for tipo, total in sorted(por_tipo.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "total_atividades": len(registros),
        "atividades_semana": sum(quantidades),
        "minutos_semana": sum(minutos),
        "minutos_total": minutos_total,
        "media_duracao": round(minutos_total / len(registros), 1) if registros else 0,
        "dias_ativos_semana": sum(q > 0 for q in quantidades),
        "sequencia": sequencia,
        "melhor_sequencia": melhor_sequencia,
        "ultima_atividade": max(dias_ativos) if dias_ativos else None,
        "total_metas": len(metas),
        "metas_concluidas": sum(p == 100 for p in percentuais),
        "media_metas": round(sum(percentuais) / len(percentuais)) if percentuais else 0,
        "minutos_mes": sum(mensal["minutos"]),
        "atividades_mes": sum(mensal["atividades"]),
        "grafico_mensal": mensal,
        "mes_referencia": hoje.strftime("%m/%Y"),
        "modalidades": modalidades,
        "grafico": {
            "labels": [d.strftime("%d/%m") for d in dias],
            "minutos": minutos,
            "atividades": quantidades,
        },
    }


# Nomes já existentes no Supabase são mantidos. Não usa pontos do catálogo.
REGRAS_CONQUISTAS = [
    ("Primeiro passo", "Realize sua primeira atividade.", "atividades", 1, "total_atividades"),
    ("Foco Total", "Realize 10 atividades.", "atividades", 10, "total_atividades"),
    ("Meta batida", "Conclua uma meta (100% de progresso).", "metas", 1, "metas_concluidas"),
    ("Veterano", "Realize 30 atividades.", "atividades", 30, "total_atividades"),
    ("Semana cheia", "Registre atividades em 7 dias consecutivos.", "dias seguidos", 7, "melhor_sequencia"),
    ("Em Movimento", "Realize 5 atividades.", "atividades", 5, "total_atividades"),
]


def calcular_conquistas(resumo):
    return [
        {"nome": nome, "descricao": descricao, "unidade": unidade, "objetivo": objetivo,
         "progresso": min(resumo[campo], objetivo), "percentual": min(100, round(resumo[campo] * 100 / objetivo)),
         "requisito_atingido": resumo[campo] >= objetivo}
        for nome, descricao, unidade, objetivo, campo in REGRAS_CONQUISTAS
    ]


def preparar_treinos(treinos, agora):
    resultado = []
    for treino in treinos:
        item = dict(treino)
        instante = datetime.fromisoformat(item["horario"].replace("Z", "+00:00"))
        # A agenda real usa timestamp sem fuso, com horário local de Brasília.
        instante = instante.replace(tzinfo=FUSO) if instante.tzinfo is None else instante.astimezone(FUSO)
        item["titulo"] = item.get("titulo") or "Treino agendado"
        item["descricao"] = item.get("lembrete") or ""
        item["data"] = instante.date().isoformat()
        item["hora_formulario"] = instante.strftime("%H:%M")
        item["instante"] = instante
        item["passado"] = instante < agora
        item["proximo"] = agora <= instante <= agora + timedelta(days=7)
        item["data_formatada"] = instante.strftime("%d/%m/%Y")
        item["horario_formatado"] = instante.strftime("%H:%M")
        resultado.append(item)
    return sorted(resultado, key=lambda t: (t["instante"], t["id_agenda"]))


def gerar_alertas(resumo, metas, treinos, agora):
    hoje = agora.date()
    alertas = []
    ultima = resumo["ultima_atividade"]
    if ultima is None:
        alertas.append({"chave_evento": "atividade:primeiro-registro", "mensagem": "Você ainda não registrou uma atividade. Que tal começar hoje?", "destino": "atividade_nova"})
    elif (hoje - ultima).days >= 3:
        alertas.append({"chave_evento": f"inatividade:{ultima.isoformat()}", "mensagem": f"Você está há {(hoje - ultima).days} dias sem registrar uma atividade.", "destino": "atividade_nova"})

    pendentes = [m for m in metas if int(m.get("progresso") or 0) < 100]
    if pendentes:
        conjunto = ",".join(sorted(str(m.get("id_meta", m["descricao"])) for m in pendentes))
        alertas.append({"chave_evento": f"metas-pendentes:{conjunto}", "mensagem": f"Você possui {len(pendentes)} meta(s) pendente(s).", "destino": "metas"})
    for meta in pendentes:
        prazo = date.fromisoformat(meta["prazo"][:10])
        faltam = (prazo - hoje).days
        if faltam < 0:
            texto = f'A meta "{meta["descricao"]}" está com o prazo vencido.'
        elif faltam <= 3:
            quando = "hoje" if faltam == 0 else "amanhã" if faltam == 1 else f"em {faltam} dias"
            texto = f'Sua meta "{meta["descricao"]}" vence {quando}.'
        else:
            continue
        fase = "vencida" if faltam < 0 else "proxima"
        alertas.append({"chave_evento": f"meta:{meta.get('id_meta', meta['descricao'])}:{prazo.isoformat()}:{fase}", "mensagem": texto, "destino": "metas"})

    alertas_treinos = []
    for treino in treinos:
        dias = (treino["instante"].date() - hoje).days
        if not treino["passado"] and dias in (0, 1):
            quando = "hoje" if dias == 0 else "amanhã"
            alertas_treinos.append({"chave_evento": f"treino:{treino['id_agenda']}:{treino['instante'].isoformat()}", "mensagem": f'Treino "{treino["titulo"]}" agendado para {quando}, às {treino["horario_formatado"]}.', "destino": "agenda"})
    return alertas_treinos + alertas
