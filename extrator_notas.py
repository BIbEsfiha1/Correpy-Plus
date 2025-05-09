"""
Módulo para extração direta de transações de notas de corretagem.
Implementação simplificada e eficaz para múltiplos formatos de PDFs.
"""

import pdfplumber
import re
import os
from datetime import datetime


def extrair_nota_corretagem(caminho_arquivo):
    """
    Extrai todas as informações relevantes de uma nota de corretagem.
    Método principal, retorna um dicionário com todas as informações extraídas.
    """
    resultado = {
        "sucesso": False,
        "erro": None,
        "corretora": "Desconhecida",
        "numero_nota": None,
        "data_nota": None,
        "transacoes": [],
        "taxas": {},
        "resumo": {}
    }
    
    nome_arquivo = os.path.basename(caminho_arquivo)
    try:
        # Tentar extrair data e número do nome do arquivo
        match_nome = re.search(r'(\d+)[_\s](\d{8})', nome_arquivo)
        if match_nome:
            resultado["numero_nota"] = match_nome.group(1)
            data_str = match_nome.group(2)
            try:
                data = f"{data_str[6:8]}/{data_str[4:6]}/{data_str[0:4]}"
                resultado["data_nota"] = data
            except:
                pass
        
        # Extrair todo o texto e tabelas do PDF
        texto_completo = ""
        todas_tabelas = []
        
        with pdfplumber.open(caminho_arquivo) as pdf:
            # Extrair texto e tabelas de todas as páginas
            for pagina in pdf.pages:
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    texto_completo += texto_pagina + "\n"
                
                # Tentar extrair tabelas com diferentes configurações
                tabelas = pagina.extract_tables()
                if tabelas:
                    todas_tabelas.extend(tabelas)
                    
                # Tentar com estratégia texto para tabelas com linhas sem bordas
                tabelas_texto = pagina.extract_tables({"vertical_strategy": "text"})
                if tabelas_texto:
                    todas_tabelas.extend(tabelas_texto)
        
        # Identificar corretora
        for corretora, padrao in PADROES_CORRETORAS.items():
            if re.search(padrao, texto_completo, re.IGNORECASE):
                resultado["corretora"] = corretora
                break
        
        # Extrair número da nota se ainda não encontrado no nome do arquivo
        if not resultado["numero_nota"]:
            for padrao in PADROES_NUMERO_NOTA:
                match = re.search(padrao, texto_completo, re.IGNORECASE)
                if match:
                    resultado["numero_nota"] = match.group(1)
                    break
        
        # Extrair data se ainda não encontrada no nome do arquivo
        if not resultado["data_nota"]:
            for padrao in PADROES_DATA:
                match = re.search(padrao, texto_completo, re.IGNORECASE)
                if match:
                    data_str = match.group(1)
                    try:
                        # Converter para formato DD/MM/AAAA
                        if '/' in data_str:
                            partes = data_str.split('/')
                        elif '-' in data_str:
                            partes = data_str.split('-')
                        else:
                            continue
                            
                        if len(partes) == 3:
                            dia, mes, ano = partes
                            # Se o ano tem 2 dígitos, adicionar 20 na frente
                            if len(ano) == 2:
                                ano = '20' + ano
                            resultado["data_nota"] = f"{dia}/{mes}/{ano}"
                            break
                    except:
                        # Se não conseguir formatar, usa como está
                        resultado["data_nota"] = data_str
                        break
        
        # Extrair transações - primeiro tenta das tabelas
        transacoes_encontradas = extrair_transacoes_tabelas(todas_tabelas)
        
        # Se não encontrou transações nas tabelas, tenta extrair do texto
        if not transacoes_encontradas:
            transacoes_encontradas = extrair_transacoes_texto(texto_completo)
        
        # Verificar se encontrou transações
        if transacoes_encontradas:
            resultado["transacoes"] = transacoes_encontradas
        
        # Extrair taxas
        taxas = extrair_taxas(texto_completo)
        if taxas:
            resultado["taxas"] = taxas
        
        # Se não tem transações mas tem alguma informação relevante, cria uma transação genérica
        if not resultado["transacoes"] and (resultado["taxas"] or resultado["numero_nota"]):
            resultado["transacoes"] = [{
                "tipo": "X",
                "ativo": "NOTA SEM TRANSAÇÕES",
                "quantidade": 1,
                "preco": 0,
                "valor_total": 0
            }]
        
        resultado["sucesso"] = True
        return resultado
        
    except Exception as e:
        resultado["erro"] = str(e)
        return resultado


def extrair_transacoes_tabelas(tabelas):
    """Extrai transações das tabelas encontradas no PDF"""
    transacoes = []
    
    # Se não há tabelas, retornar vazio
    if not tabelas:
        return transacoes
    
    for tabela in tabelas:
        # Ignorar tabelas muito pequenas
        if not tabela or len(tabela) < 2 or len(tabela[0]) < 3:
            continue
        
        # Analisar cabeçalho para identificar colunas relevantes
        cabecalho = [str(col).lower() if col else "" for col in tabela[0]]
        cabecalho_str = " ".join(cabecalho)
        
        # Verificar se parece ser uma tabela de transações
        if not any(termo in cabecalho_str for termo in ['c/v', 'quant', 'preco', 'compra', 'venda', 'valor', 'ativo', 'negocio', 'mercad']):
            continue
        
        # Identificar colunas relevantes
        col_tipo = encontrar_coluna(cabecalho, ['c/v', 'cv', 'tipo', 'compra/venda', 'operacao', 'natureza', 'c/v'])
        col_ativo = encontrar_coluna(cabecalho, ['titulo', 'ativo', 'papel', 'codigo', 'mercadoria', 'ativo', 'instrumento'])
        col_quantidade = encontrar_coluna(cabecalho, ['quantidade', 'qtde', 'quant', 'qtd', 'contratos', 'qt'])
        col_preco = encontrar_coluna(cabecalho, ['preco', 'unitario', 'unit', 'cotacao', 'valor/ajuste', 'preco/ajuste', 'ajuste'])
        col_valor = encontrar_coluna(cabecalho, ['valor', 'total', 'financeiro', 'valor op', 'valor operacao', 'd/c'])
        col_tipo_negocio = encontrar_coluna(cabecalho, ['tipo negocio', 'tipo de negocio', 'mercado', 'modalidade', 'day trade'])
        col_dc = encontrar_coluna(cabecalho, ['d/c', 'debito/credito'])
        col_vencimento = encontrar_coluna(cabecalho, ['vencimento', 'venc', 'data venc', 'expiry', 'prazo'])
        col_taxa_op = encontrar_coluna(cabecalho, ['taxa op', 'taxa operacional', 'taxa'])
        
        # Processar cada linha para encontrar transações
        for i in range(1, len(tabela)):
            linha = [str(col).strip() if col else "" for col in tabela[i]]
            
            # Ignorar linhas vazias ou headers repetidos
            if not linha or all(not cell for cell in linha):
                continue
                
            # Tentar extrair informações da linha
            try:
                # Tipo (C/V)
                tipo = ""
                if col_tipo >= 0 and col_tipo < len(linha):
                    tipo_raw = linha[col_tipo].upper()
                    if tipo_raw in ['C', 'COMPRA', 'BUY', 'D']:
                        tipo = "C"
                    elif tipo_raw in ['V', 'VENDA', 'SELL', 'C']:
                        tipo = "V"
                
                # Ativo
                ativo = "N/A"
                if col_ativo >= 0 and col_ativo < len(linha):
                    ativo = linha[col_ativo].strip()
                    # Limpar o ativo
                    ativo = re.sub(r'\s+', ' ', ativo)
                
                # Quantidade
                quantidade = 0
                if col_quantidade >= 0 and col_quantidade < len(linha):
                    quantidade_str = linha[col_quantidade].replace('.', '').replace(',', '.')
                    if quantidade_str.strip():
                        try:
                            quantidade = float(quantidade_str)
                        except:
                            quantidade = 0
                
                # Preço
                preco = 0
                if col_preco >= 0 and col_preco < len(linha):
                    preco_str = linha[col_preco].replace('.', '').replace(',', '.')
                    if preco_str.strip():
                        try:
                            preco = float(preco_str)
                        except:
                            preco = 0
                
                # Valor Total
                valor_total = 0
                if col_valor >= 0 and col_valor < len(linha):
                    valor_str = linha[col_valor].replace('.', '').replace(',', '.')
                    if valor_str.strip():
                        try:
                            valor_total = float(valor_str)
                        except:
                            valor_total = 0
                
                # Se não tiver valor total mas tiver preço e quantidade, calcular
                if valor_total == 0 and preco > 0 and quantidade > 0:
                    valor_total = preco * quantidade
                
                # Se não tiver tipo mas tiver valor, inferir
                if not tipo and valor_total != 0:
                    tipo = "C" if valor_total < 0 else "V"
                
                # Tipo de Negócio
                tipo_negocio = ""
                if col_tipo_negocio >= 0 and col_tipo_negocio < len(linha):
                    tipo_negocio = linha[col_tipo_negocio].strip().upper()
                    # Normalizar tipo negócio
                    if 'DAY' in tipo_negocio or 'DAYTRADE' in tipo_negocio:
                        tipo_negocio = 'DAY TRADE'
                
                # D/C (Débito/Crédito)
                dc = ""
                valor_operacao = 0
                if col_dc >= 0 and col_dc < len(linha):
                    dc_valor = linha[col_dc].strip().upper()
                    if dc_valor in ['D', 'DEBITO', 'DÉBITO']:
                        dc = 'D'
                    elif dc_valor in ['C', 'CREDITO', 'CRÉDITO']:
                        dc = 'C'
                
                # Extrair valor de operação (associado ao D/C)
                # Pode estar na mesma coluna do D/C ou em uma coluna separada
                if col_valor >= 0 and col_valor < len(linha):
                    valor_str = linha[col_valor].strip()
                    if any(c.isdigit() for c in valor_str):
                        try:
                            valor_operacao = parse_valor(re.sub(r'[CD]', '', valor_str))
                        except:
                            pass
                
                # Taxa Operacional
                taxa_operacional = 0.0
                if col_taxa_op >= 0 and col_taxa_op < len(linha):
                    try:
                        taxa_str = linha[col_taxa_op].strip()
                        if taxa_str:
                            taxa_operacional = parse_valor(taxa_str)
                    except:
                        pass
                
                # Vencimento
                vencimento = ""
                if col_vencimento >= 0 and col_vencimento < len(linha):
                    venc_str = linha[col_vencimento].strip()
                    if venc_str:
                        # Tentar formatar a data se estiver em formato reconhecível
                        try:
                            if re.match(r'\d{2}/\d{2}/\d{4}', venc_str):
                                vencimento = venc_str
                            elif re.match(r'\d{2}-\d{2}-\d{4}', venc_str):
                                partes = venc_str.split('-')
                                vencimento = f"{partes[0]}/{partes[1]}/{partes[2]}"
                            elif re.match(r'\d{4}-\d{2}-\d{2}', venc_str):
                                partes = venc_str.split('-')
                                vencimento = f"{partes[2]}/{partes[1]}/{partes[0]}"
                            else:
                                vencimento = venc_str
                        except:
                            vencimento = venc_str
                
                # Extrair vencimento do código do ativo (ex: WINJ25 = vencimento em abril/2025)
                if not vencimento and len(ativo) >= 5:
                    # Verificar se o ativo é um contrato futuro (WIN, DOL, IND, etc)
                    mercado_futuro = re.match(r'([A-Z]{3,4})([A-Z])([0-9]{2})', ativo)
                    if mercado_futuro:
                        try:
                            simbolo = mercado_futuro.group(1)  # WIN, DOL, etc.
                            mes_letra = mercado_futuro.group(2)  # F, G, H, J, K, M, N, Q, U, V, X, Z
                            ano = mercado_futuro.group(3)      # 23, 24, 25, etc.
                            
                            # Converter mês letra para numérico
                            meses = {'F': '01', 'G': '02', 'H': '03', 'J': '04', 'K': '05', 'M': '06',
                                    'N': '07', 'Q': '08', 'U': '09', 'V': '10', 'X': '11', 'Z': '12'}
                            
                            if mes_letra in meses:
                                mes = meses[mes_letra]
                                # Adicionar 20 no começo do ano
                                ano_completo = '20' + ano
                                # Determinar o último dia do mês (aproximado para dia 15)
                                vencimento = f"15/{mes}/{ano_completo}"
                        except:
                            pass
                
                # Ajustar tipo com base no D/C se não estiver definido
                if not tipo and dc:
                    tipo = "C" if dc == "D" else "V" if dc == "C" else ""
                
                # Parsear o ativo para separar ticker e vencimento se necessário
                ticker = ativo
                
                # Criar transação se tiver o mínimo necessário
                if ativo != "N/A" and quantidade > 0:
                    if not tipo:  # Se ainda não tiver tipo, usar C como default
                        tipo = "C"
                        
                    transacao = {
                        "tipo": tipo,
                        "ativo": ativo,
                        "ticker": ticker,  # Mercadoria
                        "vencimento": vencimento,
                        "quantidade": quantidade,
                        "preco": preco,
                        "valor_total": valor_total,
                        "tipo_negocio": tipo_negocio,
                        "dc": dc,
                        "valor_operacao": valor_operacao,
                        "taxa_operacional": taxa_operacional
                    }
                    transacoes.append(transacao)
            except:
                continue
    
    return transacoes


def extrair_transacoes_texto(texto):
    """Extrai transações diretamente do texto"""
    transacoes = []
    
    # Padrões comuns de transações em texto
    padroes = [
        # Padrão 1: C VISTA PETR4 1000 28,50 28500,00
        r'([CV])\s+(VISTA|OPCAO|TERMO)\s+([A-Z0-9]+)\s+(\d+(?:\.\d+)?)\s+([\d,.]+)\s+([\d,.]+)',
        
        # Padrão 2: COMPRA AÇÕES ITSA4 500 12,34 6.170,00
        r'(COMPRA|VENDA)\s+(?:AÇÕES|OPCOES)\s+([A-Z0-9]+)\s+(\d+(?:\.\d+)?)\s+([\d,.]+)\s+([\d,.]+)',
        
        # Padrão 3: 1 C ON VALE3 100 77,10 7.710,00
        r'\d+\s+([CV])\s+(?:ON|PN|UNIT)\s+([A-Z0-9]+)\s+(\d+(?:\.\d+)?)\s+([\d,.]+)\s+([\d,.]+)',
        
        # Padrão 4 (BTG Pactual): DOL H23 FUTURO | COMPRA | 2 | 5.050,00
        r'([A-Z0-9]+\s+[A-Z0-9]+)\s+(?:FUTURO|VISTA|OPÇÃO|TERMO)\s*\|\s*(COMPRA|VENDA)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*([\d,.]+)',
        
        # Padrão 5 (BTG Pactual): DOL    FUTURO    COMPRA    5    5.050,00
        r'([A-Z0-9]+)(?:\s+[A-Z0-9]+)?\s+(?:FUTURO|VISTA|OPÇÃO|TERMO)\s+(COMPRA|VENDA)\s+(\d+(?:\.\d+)?)\s+([\d,.]+)',
        
        # Padrão 6 (Genérico): C PETR4 1000
        r'([CV])\s+([A-Z0-9]+)\s+(\d+(?:\.\d+)?)',
        
        # Padrão 7 (BTG - Futuro): WINFUT WIN N22 1 115180.0
        r'(?:WINFUT|DOLFUT|INDFUT)\s+([A-Z0-9]+\s+[A-Z0-9]+)\s+(\d+(?:\.\d+)?)\s+([\d,.]+)',
        
        # Padrão 8 (BTG - Futuro com data): C WINJ25 16/04/2025 3 131.820,0000 DAY TRADE
        r'([CV])\s+([A-Z0-9]+)\s+(\d{2}/\d{2}/\d{4})\s+(\d+)\s+([\d,.]+)\s+(DAY\s*TRADE|NORMAL)',
        
        # Padrão 9 (BTG - Valores detalhados): C WINJ25 3 131.820,0000 DAY TRADE 82,80 C 0,00
        r'([CV])\s+([A-Z0-9]+)\s+(\d+)\s+([\d,.]+)\s+(DAY\s*TRADE|NORMAL)\s+([\d,.]+)\s+([CD])\s+([\d,.]+)'
    ]
    
    # Procurar por todos os padrões no texto
    for padrao in padroes:
        matches = re.finditer(padrao, texto, re.IGNORECASE)
        for match in matches:
            try:
                grupos = match.groups()
                
                # Diferentes padrões têm grupos em posições diferentes
                if len(grupos) >= 3:
                    # Extração baseada no padrão específico
                    if padrao == padroes[0]:  # C VISTA PETR4 1000 28,50 28500,00
                        tipo = "C" if grupos[0] == "C" else "V"
                        ativo = grupos[2]
                        quantidade = parse_valor(grupos[3])
                        preco = parse_valor(grupos[4])
                        valor_total = parse_valor(grupos[5]) if len(grupos) > 5 else quantidade * preco
                    
                    elif padrao == padroes[1]:  # COMPRA AÇÕES ITSA4 500 12,34 6.170,00
                        tipo = "C" if grupos[0].upper() == "COMPRA" else "V"
                        ativo = grupos[1]
                        quantidade = parse_valor(grupos[2])
                        preco = parse_valor(grupos[3])
                        valor_total = parse_valor(grupos[4]) if len(grupos) > 4 else quantidade * preco
                    
                    elif padrao == padroes[2]:  # 1 C ON VALE3 100 77,10 7.710,00
                        tipo = "C" if grupos[0] == "C" else "V"
                        ativo = grupos[1]
                        quantidade = parse_valor(grupos[2])
                        preco = parse_valor(grupos[3])
                        valor_total = parse_valor(grupos[4]) if len(grupos) > 4 else quantidade * preco
                    
                    elif padrao == padroes[3]:  # WIN N22 FUTURO | COMPRA | 2 | 115.180,00
                        tipo = "C" if "COMPRA" in grupos[1].upper() else "V"
                        ativo = grupos[0]
                        quantidade = parse_valor(grupos[2])
                        preco = parse_valor(grupos[3])
                        valor_total = preco * quantidade
                    
                    elif padrao == padroes[4]:  # DOL    FUTURO    COMPRA    5    5.050,00
                        tipo = "C" if "COMPRA" in grupos[1].upper() else "V"
                        ativo = grupos[0]
                        quantidade = parse_valor(grupos[2])
                        preco = parse_valor(grupos[3]) if len(grupos) > 3 else 0
                        valor_total = preco * quantidade
                    
                    elif padrao == padroes[5]:  # C WIN N22 5 119490.0
                        tipo = "C" if grupos[0] == "C" else "V"
                        ativo = grupos[1]
                        quantidade = parse_valor(grupos[2])
                        preco = parse_valor(grupos[3]) if len(grupos) > 3 else 0
                        valor_total = preco * quantidade
                    
                    elif padrao == padroes[6]:  # WIN N22 2 115180.0
                        tipo = "C"  # Default para C quando não especificado
                        ativo = grupos[0]
                        quantidade = parse_valor(grupos[1])
                        preco = parse_valor(grupos[2]) if len(grupos) > 2 and grupos[2] else 0
                        valor_total = preco * quantidade
                    
                    else:  # Caso genérico
                        continue
                    
                    # Só adicionar se tiver pelo menos ativo e quantidade
                    if ativo and quantidade > 0:
                        transacao = {
                            "tipo": tipo,
                            "ativo": ativo.strip(),
                            "quantidade": quantidade,
                            "preco": preco,
                            "valor_total": valor_total
                        }
                        transacoes.append(transacao)
                
            except Exception as e:
                print(f"Erro extraindo transação: {e}")
                continue
    
    # Considerar também seções específicas de transações em algumas corretoras
    secoes = buscar_secoes_transacoes(texto)
    if secoes:
        for linha in secoes:
            try:
                # Tentar processar linhas como "C VISTA PETR4 100 25,30"
                match = re.search(r'([CV])\s+(?:VISTA|OPCAO|TERMO)?\s+([A-Z0-9]+)\s+(\d+(?:\.\d+)?)\s+([\d,.]+)', linha)
                if match:
                    tipo = "C" if match.group(1) == "C" else "V"
                    ativo = match.group(2)
                    quantidade = parse_valor(match.group(3))
                    preco = parse_valor(match.group(4))
                    valor_total = quantidade * preco
                    
                    transacao = {
                        "tipo": tipo,
                        "ativo": ativo,
                        "quantidade": quantidade,
                        "preco": preco,
                        "valor_total": valor_total
                    }
                    transacoes.append(transacao)
            except:
                continue
    
    return transacoes


def buscar_secoes_transacoes(texto):
    """Busca seções específicas que contêm transações em algumas corretoras"""
    linhas = []
    
    # Buscar seções comuns onde aparecem transações
    if "NEGÓCIOS REALIZADOS" in texto or "RESUMO DOS NEGÓCIOS" in texto:
        # Tentar extrair a seção entre esses marcadores
        match = re.search(r'(?:NEGÓCIOS REALIZADOS|RESUMO DOS NEGÓCIOS)(.+?)(?:RESUMO FINANCEIRO|RESUMO DOS NEGÓCIOS|CUSTOS)', texto, re.DOTALL)
        if match:
            secao = match.group(1)
            # Dividir em linhas e processar cada uma
            for linha in secao.split('\n'):
                if linha.strip() and re.search(r'([CV])\s+', linha):
                    linhas.append(linha)
    
    # Para BTG Pactual e outras específicas
    if "BTG" in texto.upper() or "PACTUAL" in texto.upper():
        # Procurar pela seção de transações em formato de tabela
        match = re.search(r'(?:MERCADORIAS|AJUSTE|ESPECIFICAÇÃO|CONTRATOS)(.+?)(?:RESUMO FINANCEIRO|CUSTOS|TOTAL)', texto, re.DOTALL)
        if match:
            secao = match.group(1)
            # Adicionar cada linha que parece ter um ativo
            for linha in secao.split('\n'):
                if any(fut in linha.upper() for fut in ['WIN', 'DOL', 'IND', 'FUTURO']):
                    linhas.append(linha)
    
    return linhas


def extrair_taxas(texto):
    """Extrai taxas e valores da nota de corretagem"""
    taxas = {}
    
    # Padrões para diferentes taxas
    padroes_taxas = {
        'taxa_liquidacao': [
            r'taxa\s+de\s+liquida[cç][aã]o\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'liquida[cç][aã]o\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'taxa_registro': [
            r'taxa\s+de\s+registro\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'registro\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'emolumentos': [
            r'emolumentos\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'taxa_operacional': [
            r'taxa\s+(?:de\s+)?operacional\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'operacional\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'taxa\s+(?:de\s+)?opera[çc][aã]o\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'corretagem': [
            r'corretagem\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'iss': [
            r'(?:imposto|i\.?s\.?s\.?)\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'irrf': [
            r'(?:i\.?r\.?r\.?f\.?|imposto\s+de\s+renda)\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'valor_liquido': [
            r'(?:valor|l[ií]quido)\s+(?:l[ií]quido|para|da\s+nota)(?:\s+\d{2}/\d{2}/\d{4})?\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'(?:total|l[ií]quido)\s+(?:l[ií]quido|para\s+liquidac[aã]o)(?:\s+\d{2}/\d{2}/\d{4})?\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        # Taxas adicionais específicas
        'taxa_ajuste': [
            r'(?:taxa\s+de\s+)?ajuste\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'valor_operacao_dc': [
            r'valor\s+(?:de|da)?\s*opera[çc][aã]o\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'valor\s+(?:d/c|debito/credito)\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ]
    }
    
    # Procurar cada taxa no texto
    for nome_taxa, padroes in padroes_taxas.items():
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                try:
                    valor_str = match.group(1).replace('.', '').replace(',', '.')
                    valor = float(valor_str)
                    taxas[nome_taxa] = valor
                    break
                except:
                    continue
    
    return taxas


def encontrar_coluna(cabecalho, termos):
    """Encontra o índice da coluna baseado em termos de busca"""
    for termo in termos:
        for i, coluna in enumerate(cabecalho):
            if termo in coluna.lower():
                return i
    return -1


def parse_valor(valor_str):
    """Converte string de valor para float"""
    if not valor_str:
        return 0
    
    # Remover R$, espaços e outros caracteres não numéricos
    valor_str = re.sub(r'[^\d,.-]', '', str(valor_str))
    
    # Padrão brasileiro: usar vírgula como decimal e ponto como separador de milhar
    if ',' in valor_str:
        # Se tem vírgula, é decimal brasileiro
        valor_str = valor_str.replace('.', '').replace(',', '.')
    
    try:
        return float(valor_str)
    except:
        return 0


# Padrões de identificação de corretoras
PADROES_CORRETORAS = {
    'xp': r'XP\s+INVESTIMENTOS|CORRETORA\s+XP',
    'clear': r'CLEAR\s+CORRETORA|CLEAR\s+CTVM',
    'rico': r'RICO\s+INVESTIMENTOS|RICO\s+CTVM',
    'modal': r'MODAL\s+DTVM|MODAL\s+MAIS',
    'inter': r'INTER\s+DTVM|BANCO\s+INTER',
    'guide': r'GUIDE\s+INVESTIMENTOS',
    'nuinvest': r'NU\s+INVEST|NUINVEST|EASYNVEST',
    'itau': r'ITA[Uu]\s+CORRETORA',
    'bradesco': r'BRADESCO\s+S/?A|BRADESCO\s+CORRETORA',
    'santander': r'SANTANDER\s+CORRETORA|SANTANDER\s+CTVM',
    'btg': r'BTG\s+PACTUAL',
    'genial': r'GENIAL\s+INVESTIMENTOS',
    'terra': r'TERRA\s+INVESTIMENTOS',
    'orama': r'ORAMA\s+DTVM',
    'necton': r'NECTON\s+INVESTIMENTOS',
    'nova_futura': r'NOVA\s+FUTURA\s+CTVM',
    'toro': r'TORO\s+INVESTIMENTOS',
    'c6': r'C6\s+CTVM|C6\s+BANK',
    'mirae': r'MIRAE\s+ASSET',
}

# Padrões para número da nota
PADROES_NUMERO_NOTA = [
    r'Nr\.\s*(?:nota|order|negoci):\s*(\d+)',
    r'N[o°º]\s*(?:da nota|nota):\s*(\d+)',
    r'N[uú]mero\s*(?:da nota|nota|folha):\s*(\d+)',
    r'(?:Nota|Folha)\s*(?:n[o°º]|n[uú]mero|\#):\s*(\d+)',
    r'(?:NOTA|BOLETA)\s*(?:DE CORRETAGEM|DE NEGOCIAÇÃO)\s*[^\d]*(\d+)',
    r'Nr\.?\s*Boleta:?\s*(\d+)',
    r'Boleta\s+Nº\s*(\d+)'
]

# Padrões para data da nota
PADROES_DATA = [
    r'(?:Data|Data pregão):\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
    r'(?:Date|Dia|Data):\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
    r'Pregão(?:\s+de)?\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
    r'(?:Data|Date)\s*(?:de|da|do)?\s*(?:neg[oó]ci(?:o|ação)|operações)?\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
    r'D\.?\s*Pregão:?\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
    r'(?:Data|Date)\s*Liquidação:?\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})'
]

# Função principal para análise
def analisar_pdf_nota_corretagem(caminho_pdf):
    """Função principal para análise de notas de corretagem"""
    # Extrair todos os dados da nota
    resultado = extrair_nota_corretagem(caminho_pdf)
    
    # Verificar se há texto completo para análises adicionais
    with pdfplumber.open(caminho_pdf) as pdf:
        texto_completo = ""
        for pagina in pdf.pages:
            texto_pagina = pagina.extract_text()
            if texto_pagina:
                texto_completo += texto_pagina + "\n"
    
    # Verificar se encontramos os campos adicionais nas taxas
    taxas = resultado.get('taxas', {})
    
    # Se não encontrou os valores nas taxas, tentar outras abordagens
    if 'valor_operacao_dc' not in taxas or taxas['valor_operacao_dc'] == 0:
        # Tentar extrair Valor Operação de outros lugares
        match = re.search(r'valor\s+(?:de|da)?\s*opera[çc][aã]o\s*:?\s*(?:R\$)?\s*([\d\.,]+)', 
                          texto_completo, re.IGNORECASE)
        if match:
            try:
                taxas['valor_operacao_dc'] = parse_valor(match.group(1))
            except:
                pass
    
    # Procurar por ajustes se ainda não encontrou
    if 'taxa_ajuste' not in taxas or taxas['taxa_ajuste'] == 0:
        match = re.search(r'ajuste\s*:?\s*(?:R\$)?\s*([\d\.,]+)', texto_completo, re.IGNORECASE)
        if match:
            try:
                taxas['taxa_ajuste'] = parse_valor(match.group(1))
            except:
                pass
    
    # Procurar especificamente por transações de mercado futuro no formato da BTG
    # Exemplo: C WINJ25 16/04/2025 3 131.820,0000 DAY TRADE 82,80 C 0,00
    padrao_btg_futuro = r'([CV])\s+([A-Z0-9]+)\s+(\d{2}/\d{2}/\d{4})?\s*(\d+)\s+([\d\.,]+)\s+(DAY\s*TRADE|NORMAL)?\s*([\d\.,]+)?\s*([CD])?\s*([\d\.,]+)?'
    
    # Buscar esse padrão em todas as linhas do texto
    transacoes_btg = []
    for linha in texto_completo.split('\n'):
        match = re.search(padrao_btg_futuro, linha.strip(), re.IGNORECASE)
        if match:
            try:
                # Extrair dados
                tipo = 'C' if match.group(1) == 'C' else 'V'
                ativo = match.group(2)
                vencimento = match.group(3) if match.group(3) else ''
                quantidade = int(match.group(4))
                preco = parse_valor(match.group(5))
                tipo_negocio = match.group(6) if match.group(6) else 'NORMAL'
                valor_op = parse_valor(match.group(7)) if match.group(7) else 0
                dc = match.group(8) if match.group(8) else ''
                taxa_op = parse_valor(match.group(9)) if match.group(9) else 0
                
                # Criar transação
                if ativo and quantidade > 0:
                    transacoes_btg.append({
                        "tipo": tipo,
                        "ativo": ativo,
                        "ticker": ativo,  # Mercadoria
                        "vencimento": vencimento,
                        "quantidade": quantidade,
                        "preco": preco,
                        "valor_total": preco * quantidade,
                        "tipo_negocio": tipo_negocio.strip().upper() if tipo_negocio else 'NORMAL',
                        "dc": dc,
                        "valor_operacao": valor_op,
                        "taxa_operacional": taxa_op
                    })
            except Exception as e:
                print(f"Erro ao extrair transação de mercado futuro: {e}")
    
    # Se encontramos transações no formato BTG, as adicionamos às existentes ou 
    # substituímos se não houver nenhuma
    if transacoes_btg:
        if not resultado.get('transacoes'):
            resultado['transacoes'] = transacoes_btg
        else:
            resultado['transacoes'].extend(transacoes_btg)
    
    # Adicionar os campos extras nas transações
    for transacao in resultado.get('transacoes', []):
        # Garantir que todos os novos campos estejam presentes
        if 'tipo_negocio' not in transacao:
            transacao['tipo_negocio'] = ""
        if 'dc' not in transacao:
            transacao['dc'] = ""
        if 'preco_ajuste' not in transacao:
            transacao['preco_ajuste'] = transacao.get('preco', 0)
        if 'ticker' not in transacao:
            transacao['ticker'] = transacao.get('ativo', '')
        if 'vencimento' not in transacao:
            transacao['vencimento'] = ''
        if 'valor_operacao' not in transacao:
            transacao['valor_operacao'] = 0
        if 'taxa_operacional' not in transacao:
            transacao['taxa_operacional'] = 0
    
    return resultado
