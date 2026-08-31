#!/usr/bin/env python3
"""As fontes web da varredura, como instancias de Portal.

Ordem = a mesma de FONTES na varredura v2. A ordem importa: o orcamento de
tempo em varredura.main() pula as ultimas fontes quando o tempo acaba.

Adicionar uma fonte sem regra propria: uma linha Portal(nome, url, precisa_js=...).
Adicionar uma fonte com regra propria: uma subclasse pequena em outro
modulo deste pacote (so' o metodo que muda) + uma linha aqui.
"""
from portais.base import Portal
from portais.cgibs import CGIBSPortal

PORTAIS = [
    CGIBSPortal("CGIBS - Noticias",            "https://www.cgibs.gov.br/noticias"),
    CGIBSPortal("CGIBS - Resolucoes",          "https://www.cgibs.gov.br/resolucoes"),
    CGIBSPortal("CGIBS - Atos Conjuntos",      "https://www.cgibs.gov.br/atos-conjuntos"),
    CGIBSPortal("CGIBS - Atos Tecnicos Conj.", "https://www.cgibs.gov.br/atos-tecnicos-conjuntos"),
    CGIBSPortal("CGIBS - Portarias",           "https://www.cgibs.gov.br/portarias"),
    Portal("RFB - Noticias 2026",
           "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026",
           precisa_js=False),
    Portal("RFB - Reforma do Consumo",
           "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-tributaria-do-consumo/noticias",
           precisa_js=False),
    Portal("Portal DF-e SVRS - Noticias",
           "https://dfe-portal.svrs.rs.gov.br/Nfe/Noticias",
           precisa_js=False),
    Portal("Portal NF-e - Informes/NTs",
           "https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false",
           precisa_js=False),
    CGIBSPortal("CGIBS - Regulamentos",        "https://www.cgibs.gov.br/regulamentos"),
    CGIBSPortal("CGIBS - Leis",                "https://www.cgibs.gov.br/leis"),
    CGIBSPortal("CGIBS - Relatorios",          "https://www.cgibs.gov.br/relatorios"),
]
