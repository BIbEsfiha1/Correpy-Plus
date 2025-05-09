"""
Módulo avançado para análise detalhada de PDFs de notas de corretagem brasileiras.
Extrai dados estruturados de diferentes formatos de corretoras.
"""
import io
import os
import pdfplumber
import pandas as pd
import re
import traceback
from datetime import datetime
from decimal import Decimal

class NotaCobretagemParser:
    """Classe para análise avançada de PDFs de notas de corretagem"""
    
    # Padrões comuns para identificação de corretoras
    CORRETORAS = {
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
    
    # Padrões para informações básicas da nota
    PADROES_INFO = {
        'numero_nota': [
            r'Nr\.\s*(?:nota|order|negoci):\s*(\d+)',
            r'N[o°º]\s*(?:da nota|nota):\s*(\d+)',
            r'N[uú]mero\s*(?:da nota|nota|folha):\s*(\d+)',
            r'(?:Nota|Folha)\s*(?:n[o°º]|n[uú]mero|\#):\s*(\d+)',
            r'(?:NOTA|BOLETA)\s*(?:DE CORRETAGEM|DE NEGOCIAÇÃO)\s*[^\d]*(\d+)',
            r'Nr\.?\s*Boleta:?\s*(\d+)',
            r'Boleta\s+Nº\s*(\d+)'
        ],
        'data_pregao': [
            r'(?:Data|Data pregão):\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
            r'(?:Date|Dia|Data):\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
            r'Pregão(?:\s+de)?\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
            r'(?:Data|Date)\s*(?:de|da|do)?\s*(?:neg[oó]ci(?:o|ação)|operações)?\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
            r'D\.?\s*Pregão:?\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
            r'(?:Data|Date)\s*Liquidação:?\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{2})',
            # Extrair de nome de arquivo com padrão como 008401877_20250402_20250403_BMF.pdf
            r'\d+_(\d{8})_\d{8}'
        ],
    }
    
    # Palavras-chave para cabeçalhos de tabelas de transações
    KEYWORDS_TRANSACOES = [
        ['cv', 'quant', 'preco'],
        ['c/v', 'tipo', 'quantidade', 'preco'],
        ['compra', 'venda', 'quantidade', 'preco'],
        ['operacao', 'quantidade', 'preco', 'valor'],
        ['negocios', 'tipo', 'qtde', 'valor'],
        ['ativo', 'tipo', 'quantidade', 'valor']
    ]
    
    # Padrões para taxas e valores
    PADROES_TAXAS = {
        'taxa_liquidacao': [
            r'taxa\s+de\s+liquida[cç][aã]o\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'liquida[cç][aã]o\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'taxa_registro': [
            r'taxa\s+de\s+registro\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'registro\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'taxa_termo': [
            r'taxa\s+(?:de\s+)?(?:termo|op[çc][õo]es)\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'termo/op[çc][õo]es\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'emolumentos': [
            r'emolumentos\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'taxa_operacional': [
            r'taxa\s+(?:de\s+)?operacional\s*:?\s*(?:R\$)?\s*([\d\.,]+)',
            r'operacional\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'corretagem': [
            r'corretagem\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'irrf': [
            r'(?:i\.?r\.?r\.?f\.?|imposto\s+de\s+renda)\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'outras_taxas': [
            r'(?:outras\s+)?taxas\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ],
        'valor_liquido': [
            r'(?:valor|l[ií]quido)\s+(?:l[ií]quido|para|da\s+nota)(?:\s+\d{2}/\d{2}/\d{4})?\s*:?\s*(?:R\$)?\s*([\d\.,]+)'
        ]
    }
    
    def __init__(self, caminho_pdf):
        """Inicializa o analisador com o caminho para um arquivo PDF"""
        self.caminho_pdf = caminho_pdf
        self.nome_arquivo = os.path.basename(caminho_pdf)
        self.texto_completo = ""
        self.texto_por_pagina = []
        self.tabelas = []
        self.tabelas_formatadas = []
        
        # Dados extraídos
        self.corretora = "Desconhecida"
        self.numero_nota = None
        self.data_nota = None
        self.cliente = None
        self.cpf_cnpj = None
        self.transacoes = []
        self.taxas = {}
        self.resumo = {}
        
        # Metadados
        self.analise_completa = False
        self.sucesso = False
        self.detalhes_erro = None
    
    def analisar(self):
        """Executa a análise completa do PDF e retorna os resultados"""
        try:
            # Extrair texto e tabelas
            self._extrair_texto_e_tabelas()
            
            # Identificar corretora
            self._identificar_corretora()
            
            # Extrair informações básicas
            self._extrair_informacoes_basicas()
            
            # Extrair transações
            self._extrair_transacoes()
            
            # Extrair taxas e valores
            self._extrair_taxas_e_valores()
            
            # Construir resumo
            self._construir_resumo()
            
            self.analise_completa = True
            self.sucesso = True
            
            return self.obter_resultado()
            
        except Exception as e:
            self.sucesso = False
            self.detalhes_erro = str(e)
            self.analise_completa = True
            print(f"Erro ao analisar {self.nome_arquivo}: {str(e)}")
            print(traceback.format_exc())
            
            return self.obter_resultado()
    
    def _extrair_texto_e_tabelas(self):
        """Extrai todo o texto e tabelas do PDF"""
        with pdfplumber.open(self.caminho_pdf) as pdf:
            textos = []
            tabelas_por_pagina = []
            
            for pagina in pdf.pages:
                texto_pagina = pagina.extract_text()
                textos.append(texto_pagina)
                
                # Tentar extrair tabelas com diferentes configurações
                tabelas_padrao = pagina.extract_tables()
                tabelas_texto = pagina.extract_tables({"vertical_strategy": "text"})
                tabelas_linhas = pagina.extract_tables({"horizontal_strategy": "lines"})
                
                # Combinar tabelas encontradas
                todas_tabelas = []
                for lista_tabelas in [tabelas_padrao, tabelas_texto, tabelas_linhas]:
                    for tabela in lista_tabelas:
                        if tabela and len(tabela) > 1 and not self._tabela_ja_existe(tabela, todas_tabelas):
                            todas_tabelas.append(tabela)
                
                tabelas_por_pagina.append(todas_tabelas)
            
            # Consolidar resultados
            self.texto_completo = "\n".join(textos)
            self.texto_por_pagina = textos
            
            # Flatten a lista de tabelas
            self.tabelas = [tabela for pagina_tabelas in tabelas_por_pagina for tabela in pagina_tabelas]
            
            # Processar tabelas para formato mais útil
            self._processar_tabelas()
    
    def _tabela_ja_existe(self, nova_tabela, lista_tabelas):
        """Verifica se uma tabela similar já existe na lista"""
        if not nova_tabela or len(nova_tabela) < 2:
            return True
            
        for tabela_existente in lista_tabelas:
            if len(tabela_existente) == len(nova_tabela):
                # Se o tamanho é igual, verifica se a maioria das células são similares
                cells_match = 0
                total_cells = 0
                
                for i in range(min(3, len(nova_tabela))):  # Verificar só primeiras linhas
                    for j in range(min(3, len(nova_tabela[i]))):  # Verificar só primeiras colunas
                        total_cells += 1
                        if nova_tabela[i][j] == tabela_existente[i][j]:
                            cells_match += 1
                
                if total_cells > 0 and cells_match / total_cells > 0.7:
                    return True  # 70% de similaridade = mesma tabela
                    
        return False
    
    def _processar_tabelas(self):
        """Processa as tabelas extraídas e identifica cabeçalhos"""
        self.tabelas_formatadas = []
        
        for tabela in self.tabelas:
            # Remover células vazias e linhas vazias
            tabela_limpa = []
            for linha in tabela:
                linha_limpa = [str(celula).strip() if celula is not None else "" for celula in linha]
                if any(celula != "" for celula in linha_limpa):
                    tabela_limpa.append(linha_limpa)
            
            if not tabela_limpa or len(tabela_limpa) < 2:
                continue
                
            # Tentar identificar cabeçalho
            cabecalho = tabela_limpa[0]
            cabecalho_minusculo = [c.lower() for c in cabecalho]
            cabecalho_str = " ".join(cabecalho_minusculo)
            
            # Verificar se parece uma tabela de transações
            e_tabela_transacoes = False
            for palavras_chave in self.KEYWORDS_TRANSACOES:
                if all(kw in cabecalho_str for kw in palavras_chave):
                    e_tabela_transacoes = True
                    break
            
            self.tabelas_formatadas.append({
                "cabecalho": cabecalho,
                "dados": tabela_limpa[1:],
                "cabecalho_str": cabecalho_str,
                "e_tabela_transacoes": e_tabela_transacoes
            })
    
    def _identificar_corretora(self):
        """Identifica a corretora com base no texto"""
        texto_analise = self.texto_completo.upper()
        
        for nome, padrao in self.CORRETORAS.items():
            if re.search(padrao, texto_analise, re.IGNORECASE):
                self.corretora = nome
                return
    
    def _extrair_informacoes_basicas(self):
        """Extrai informações básicas do PDF"""
        # Número da nota
        for padrao in self.PADROES_INFO['numero_nota']:
            match = re.search(padrao, self.texto_completo, re.IGNORECASE)
            if match:
                self.numero_nota = match.group(1)
                break
        
        # Se ainda não encontrou o número da nota, tentar extrair do nome do arquivo
        if not self.numero_nota and self.nome_arquivo:
            # Padrão comum em alguns arquivos: 123456_20250101.pdf ou 123456.pdf
            match = re.search(r'^(\d+)(?:_|\s)', self.nome_arquivo)
            if match:
                self.numero_nota = match.group(1)
        
        # Data do pregão
        data_encontrada = False
        
        # Primeiro tentar nos padrões de texto
        for padrao in self.PADROES_INFO['data_pregao']:
            match = re.search(padrao, self.texto_completo, re.IGNORECASE)
            if match:
                data_str = match.group(1)
                try:
                    # Verificar se o formato é YYYYMMDD sem separadores (do nome do arquivo)
                    if len(data_str) == 8 and data_str.isdigit():
                        ano = data_str[0:4]
                        mes = data_str[4:6]
                        dia = data_str[6:8]
                        self.data_nota = f"{dia}/{mes}/{ano}"
                        data_encontrada = True
                        break
                        
                    # Tratar diferentes formatos de data
                    if '/' in data_str:
                        partes = data_str.split('/')
                    else:
                        partes = data_str.split('-')
                        
                    if len(partes) == 3:
                        dia, mes, ano = partes
                        # Se ano tem 2 dígitos, converter para 4 dígitos
                        if len(ano) == 2:
                            ano = '20' + ano
                        self.data_nota = f"{dia}/{mes}/{ano}"
                        data_encontrada = True
                        break
                except Exception:
                    # Se falhar, usar a string como está
                    self.data_nota = data_str
                    data_encontrada = True
                    break
        
        # Se não encontrou data no texto, tentar extrair do nome do arquivo
        if not data_encontrada and self.nome_arquivo:
            # Padrão comum: 123456_20250101.pdf ou 123456_20250101_20250102.pdf
            match = re.search(r'_(\d{8})(?:_|\.|$)', self.nome_arquivo)
            if match:
                data_str = match.group(1)
                try:
                    ano = data_str[0:4]
                    mes = data_str[4:6]
                    dia = data_str[6:8]
                    self.data_nota = f"{dia}/{mes}/{ano}"
                except Exception:
                    pass
        
        # Cliente - extrair das primeiras linhas
        primeiras_linhas = self.texto_completo.split('\n')[:10]
        for linha in primeiras_linhas:
            if re.search(r'(?:cliente|name|nome):', linha, re.IGNORECASE):
                match = re.search(r'(?:cliente|name|nome):\s*(.+?)(?:\n|\r|\s{2,}|$)', linha, re.IGNORECASE)
                if match:
                    self.cliente = match.group(1).strip()
                    break
    
    def _extrair_transacoes(self):
        """Extrai as transações do PDF"""
        self.transacoes = []
        
        # Procurar nas tabelas formatadas
        for tabela in self.tabelas_formatadas:
            if tabela["e_tabela_transacoes"]:
                self._extrair_transacoes_de_tabela(tabela)
        
        # Se não encontrou transações nas tabelas, tentar extrair do texto
        if not self.transacoes:
            self._extrair_transacoes_do_texto()
    
    def _extrair_transacoes_de_tabela(self, tabela):
        """Extrai transações de uma tabela identificada"""
        cabecalho = [c.lower() for c in tabela["cabecalho"]]
        
        # Identificar colunas relevantes
        col_tipo = self._encontrar_indice(cabecalho, ["c/v", "cv", "tipo", "compra/venda", "operacao", "natureza", "c/v"])
        col_ativo = self._encontrar_indice(cabecalho, ["titulo", "ativo", "papel", "especificacao", "codigo", "mercadoria", "ativo", "instrumento"])
        col_quantidade = self._encontrar_indice(cabecalho, ["quantidade", "qtde", "quant", "qtd", "contratos", "qt"])
        col_preco = self._encontrar_indice(cabecalho, ["preco", "valor", "unitario", "unit", "ajuste", "liquidacao", "valor/ajuste"])
        col_valor_total = self._encontrar_indice(cabecalho, ["valor op", "total", "financeiro", "d/c", "valor de operacao"])
        
        # Para ser processável, precisamos de pelo menos ativo e quantidade
        # (tipo pode ser inferido em alguns casos)
        colunas_minimas = [col_ativo, col_quantidade]
        if any(col == -1 for col in colunas_minimas):
            return
        
        # Processar linhas
        for linha in tabela["dados"]:
            # Verificar se a linha tem dados suficientes
            if len(linha) <= max(col_tipo, col_ativo, col_quantidade):
                continue
                
            # Extrair valores
            tipo_str = linha[col_tipo].strip().upper() if col_tipo >= 0 else ""
            tipo = "C" if tipo_str in ["C", "COMPRA", "COMPRAR", "BUY", "COMPRAS", "D"] else "V" if tipo_str in ["V", "VENDA", "VENDER", "SELL", "VENDAS", "C"] else tipo_str
            
            ativo = linha[col_ativo].strip() if col_ativo >= 0 else "N/A"
            
            # Alguns formatos comuns de ativos para limpeza
            ativo = re.sub(r'\s+', ' ', ativo)  # Remover espaços extras
            
            try:
                quantidade = linha[col_quantidade].strip() if col_quantidade >= 0 else "0"
                quantidade = self._converter_para_float(quantidade)
            except:
                quantidade = 0
                
            try:
                preco = linha[col_preco].strip() if col_preco >= 0 else "0"
                preco = self._converter_para_float(preco)
            except:
                preco = 0
                
            try:
                valor_total = linha[col_valor_total].strip() if col_valor_total >= 0 else "0"
                valor_total = self._converter_para_float(valor_total)
            except:
                # Se não tem valor total, calcular
                valor_total = quantidade * preco
            
            # Se não tiver tipo definido mas tiver valor_total, inferir o tipo pelo valor
            if not tipo and valor_total != 0:
                tipo = "C" if valor_total < 0 else "V"
            elif not tipo:  # Se ainda não tiver tipo, default para C
                tipo = "C"
            
            # Criar transação se tiver ativo e quantidade > 0
            if ativo and quantidade > 0:
                transacao = {
                    "tipo": tipo,
                    "ativo": ativo,
                    "quantidade": quantidade,
                    "preco": preco,
                    "valor_total": valor_total
                }
                self.transacoes.append(transacao)
    
    def _extrair_transacoes_do_texto(self):
        """Tenta extrair transações do texto quando tabelas falham"""
        # Padrões comuns para transações no texto
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
            r'([A-Z0-9]+)\s+(?:FUTURO|VISTA|OPÇÃO|TERMO)\s+(COMPRA|VENDA)\s+(\d+(?:\.\d+)?)\s+([\d,.]+)',
            # Padrão 6 (Genérico): C PETR4 1000
            r'([CV])\s+([A-Z0-9]+)\s+(\d+(?:\.\d+)?)',
            # Padrão 7 (BTG - Futuro): WINFUT WIN N22 1 115180.0
            r'(?:WINFUT|DOLFUT|INDFUT)\s+([A-Z0-9]+\s+[A-Z0-9]+)\s+(\d+(?:\.\d+)?)\s+([\d,.]+)'
        ]
        
        for padrao in padroes:
            matches = re.finditer(padrao, self.texto_completo)
            for match in matches:
                try:
                    grupos = match.groups()
                    
                    # Determinar onde estão os dados no padrão
                    if len(grupos) >= 5:
                        tipo_str = grupos[0].upper()
                        tipo = "C" if tipo_str in ["C", "COMPRA"] else "V" if tipo_str in ["V", "VENDA"] else tipo_str
                        
                        ativo = grupos[2] if len(grupos) >= 6 else grupos[1]
                        quantidade = self._converter_para_float(grupos[3] if len(grupos) >= 6 else grupos[2])
                        preco = self._converter_para_float(grupos[4] if len(grupos) >= 6 else grupos[3])
                        valor_total = self._converter_para_float(grupos[5] if len(grupos) >= 6 else grupos[4])
                        
                        if quantidade > 0:
                            transacao = {
                                "tipo": tipo,
                                "ativo": ativo,
                                "quantidade": quantidade,
                                "preco": preco,
                                "valor_total": valor_total
                            }
                            self.transacoes.append(transacao)
                except Exception:
                    continue
    
    def _extrair_taxas_e_valores(self):
        """Extrai todas as taxas e valores do PDF"""
        for nome_taxa, padroes in self.PADROES_TAXAS.items():
            for padrao in padroes:
                match = re.search(padrao, self.texto_completo, re.IGNORECASE)
                if match:
                    valor_str = match.group(1)
                    try:
                        valor = self._converter_para_float(valor_str)
                        self.taxas[nome_taxa] = valor
                        break
                    except:
                        continue
    
    def _construir_resumo(self):
        """Constrói um resumo financeiro com base nos dados extraídos"""
        self.resumo = {}
        
        # Valor total de compras e vendas
        total_compras = 0
        total_vendas = 0
        
        for transacao in self.transacoes:
            if transacao["tipo"] == "C":
                total_compras += transacao["valor_total"]
            elif transacao["tipo"] == "V":
                total_vendas += transacao["valor_total"]
        
        self.resumo["total_compras"] = total_compras
        self.resumo["total_vendas"] = total_vendas
        
        # Valor líquido
        if "valor_liquido" in self.taxas:
            self.resumo["valor_liquido"] = self.taxas["valor_liquido"]
        else:
            # Calcular líquido: vendas - compras - taxas
            total_taxas = sum(valor for nome, valor in self.taxas.items() 
                            if nome != "valor_liquido")
            self.resumo["valor_liquido"] = total_vendas - total_compras - total_taxas
    
    def _encontrar_indice(self, cabecalho, termos_possiveis):
        """Encontra o índice da coluna no cabeçalho que contém um dos termos possíveis"""
        for termo in termos_possiveis:
            for i, celula in enumerate(cabecalho):
                if termo in celula.lower():
                    return i
        return -1
    
    def _converter_para_float(self, valor_str):
        """Converte string de valor monetário para float"""
        if not valor_str:
            return 0.0
            
        # Remover caracteres não numéricos exceto , e .
        valor_str = re.sub(r'[^\d,.-]', '', str(valor_str))
        
        # Verificar formato brasileiro (usa , como decimal)
        if ',' in valor_str and '.' in valor_str:
            # Se tem ambos, o formato é 1.234,56
            valor_str = valor_str.replace('.', '').replace(',', '.')
        elif ',' in valor_str:
            # Se só tem vírgula, é decimal: 1234,56
            valor_str = valor_str.replace(',', '.')
            
        # Converter para float
        try:
            return float(valor_str)
        except ValueError:
            return 0.0
    
    def obter_resultado(self):
        """Retorna os resultados da análise em formato estruturado"""
        return {
            "sucesso": self.sucesso,
            "erro": self.detalhes_erro,
            "nome_arquivo": self.nome_arquivo,
            "corretora": self.corretora,
            "numero_nota": self.numero_nota,
            "data_nota": self.data_nota,
            "cliente": self.cliente,
            "cpf_cnpj": self.cpf_cnpj,
            "transacoes": self.transacoes,
            "taxas": self.taxas,
            "resumo": self.resumo
        }

# Função auxiliar para análise simples
def analisar_pdf_nota_corretagem(caminho_pdf):
    """Analisa um PDF de nota de corretagem e retorna os resultados"""
    parser = NotaCobretagemParser(caminho_pdf)
    resultado = parser.analisar()
    
    # Se não encontrou transações, mas encontrou taxas, criar pelo menos uma transação "dummy"
    # para garantir que os dados da nota sejam salvos
    if not resultado["transacoes"] and (resultado["taxas"] or resultado["corretora"] != "Desconhecida"):
        # Criar uma transação genérica apenas para manter os dados da nota
        resultado["transacoes"] = [
            {
                "tipo": "X",  # X indica transação genérica
                "ativo": "NOTA SEM TRANSAÇÕES",
                "quantidade": 1,
                "preco": 0,
                "valor_total": 0
            }
        ]
    
    return resultado
