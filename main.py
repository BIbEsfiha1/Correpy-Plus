import os
import io
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox
import pandas as pd
from collections import defaultdict
import ttkthemes as themes
from datetime import datetime
import traceback
import warnings
import logging
from correpy.parsers.brokerage_notes.parser_factory import ParserFactory

# Configurar para ignorar avisos específicos (como CropBox missing)
warnings.filterwarnings("ignore")

# Suprimir mensagens de log do pdfplumber
logging.getLogger("pdfminer").setLevel(logging.ERROR)

# Importar analisadores de PDF personalizados (do menos para o mais avançado)
try:
    from pdf_analyzer import analisar_pdf_nota_corretagem
    PDF_ANALYZER_DISPONIVEL = True
except ImportError:
    PDF_ANALYZER_DISPONIVEL = False

try:
    from advanced_parser import analisar_pdf_nota_corretagem as analisar_pdf_avancado
    ADVANCED_PARSER_DISPONIVEL = True
except ImportError:
    ADVANCED_PARSER_DISPONIVEL = False

# Importar o extrator direto e simplificado (maior prioridade)
try:
    from extrator_notas import analisar_pdf_nota_corretagem as extrair_nota_direto
    EXTRATOR_DIRETO_DISPONIVEL = True
except ImportError:
    EXTRATOR_DIRETO_DISPONIVEL = False

# Verificar se estamos executando como um arquivo .exe compilado
if getattr(sys, 'frozen', False):
    # Executando como arquivo compilado (.exe)
    application_path = os.path.dirname(sys.executable)
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Configurações globais com paleta moderna e mais vibrante
CORES = {
    "bg_escuro": "#1a1b26",       # Fundo principal mais escuro
    "bg_medio": "#24283b",        # Fundo dos painéis um pouco mais claro
    "bg_claro": "#414868",        # Fundo dos controles mais claro
    "texto": "#c0caf5",           # Texto principal com tom azulado suave
    "destaque": "#7aa2f7",        # Azul vibrante para destaques
    "sucesso": "#9ece6a",         # Verde mais vibrante para sucesso
    "erro": "#f7768e",            # Vermelho mais vibrante para erros
    "alerta": "#e0af68",          # Amarelo mais vibrante para alertas
    "roxo": "#bb9af7",            # Roxo para elementos especiais
    "cyan": "#7dcfff"             # Cyan para elementos de destaque secundário
}

class LogHandler:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        
    def log(self, mensagem, tipo="normal"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        if tipo == "erro":
            tag = "erro"
            prefixo = "❌ "
        elif tipo == "sucesso":
            tag = "sucesso"
            prefixo = "✅ "
        elif tipo == "alerta":
            tag = "alerta"
            prefixo = "⚠️ "
        elif tipo == "info":
            tag = "info"
            prefixo = "ℹ️ "
        else:
            tag = "normal"
            prefixo = "   "
            
        texto_formatado = f"[{timestamp}] {prefixo}{mensagem}\n"
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, texto_formatado, tag)
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.update()

# Função para processar um único arquivo PDF
def processar_arquivo_pdf(caminho_pdf, dados_por_mes, logger):
    total_notas = 0
    total_transacoes = 0
    nome_arquivo = os.path.basename(caminho_pdf)
    uso_analisador_custom = False
    
    try:
        # Primeiro, tenta com o correpy (biblioteca padrão)
        with open(caminho_pdf, 'rb') as f:
            conteudo = io.BytesIO(f.read())
            conteudo.seek(0)
            
            notas = ParserFactory(brokerage_note=conteudo).parse()
            arquivo_notas = len(notas)
            total_notas += arquivo_notas
            
            logger.log(f"  → Encontradas {arquivo_notas} notas em {nome_arquivo}", "info")
            
            # Verificar se há transações em alguma das notas
            total_transacoes_correpy = sum(len(nota.transactions) for nota in notas)
            
            # Se não há transações e algum analisador customizado está disponível, usar ele como fallback
            if total_transacoes_correpy == 0 and (PDF_ANALYZER_DISPONIVEL or ADVANCED_PARSER_DISPONIVEL or EXTRATOR_DIRETO_DISPONIVEL):
                logger.log(f"  → Nenhuma transação encontrada com correpy. Tentando com analisadores customizados...", "info")
                resultado_analise = tentar_analisador_customizado(caminho_pdf, logger)
                
                if resultado_analise and resultado_analise.get("transacoes"):
                    uso_analisador_custom = True
                    # Usar os dados do analisador customizado
                    processar_resultado_customizado(resultado_analise, dados_por_mes, logger)
                    total_notas = 1  # Consideramos uma nota bem-sucedida
                    total_transacoes = len(resultado_analise.get("transacoes", []))
                    
                    return True, total_notas, total_transacoes
            
            # Se chegou aqui, ou não usou o analisador customizado, ou ele não encontrou transações também
            # Continuar com o processamento normal do correpy
            for i, nota in enumerate(notas):
                # Debug de informações da nota
                logger.log(f"  → Detalhes Nota #{i+1}:", "info")
                logger.log(f"     - ID: {nota.reference_id}")
                logger.log(f"     - Data: {nota.reference_date}")
                logger.log(f"     - Corretora: {nota.brokerage_firm if hasattr(nota, 'brokerage_firm') else 'N/A'}")
                logger.log(f"     - Total de transações: {len(nota.transactions)}")
                
                # Se não há transações, vamos tentar extrair informações básicas da nota mesmo assim
                if len(nota.transactions) == 0:
                    logger.log(f"     - Alerta: Nenhuma transação encontrada nesta nota", "alerta")
                    
                    # Adicionar dados da nota sem transações no relatório
                    data_referencia = nota.reference_date
                    mes_ano = data_referencia.strftime('%Y-%m')
                    
                    # Criar uma entrada com informações básicas da nota
                    # Verificar cada atributo antes de acessá-lo para evitar erros
                    registro = {
                        'Data': data_referencia,
                        'Número da Nota': nota.reference_id,
                        'Tipo de Transação': 'SEM TRANSAÇÕES',
                        'Quantidade': 0,
                        'Preço Unitário': 0.0,
                        'Ativo': 'N/A',
                    }
                    
                    # Adicionar taxas e valores apenas se existirem
                    campos = [
                        ('Taxa de Liquidação', 'settlement_fee'),
                        ('Taxa de Registro', 'registration_fee'),
                        ('Taxa de Termo/Opções', 'term_fee'),
                        ('Taxa A.N.A', 'ana_fee'),
                        ('Emolumentos', 'emoluments'),
                        ('Taxa Operacional', 'operational_fee'),
                        ('Execução', 'execution'),
                        ('Taxa de Custódia', 'custody_fee'),
                        ('IRRF Retido na Fonte', 'source_withheld_taxes'),
                        ('Impostos', 'taxes'),
                        ('Outros', 'others')
                    ]
                    
                    for nome_campo, atributo in campos:
                        if hasattr(nota, atributo):
                            try:
                                valor = getattr(nota, atributo)
                                registro[nome_campo] = float(valor) if valor is not None else 0.0
                            except (ValueError, TypeError):
                                registro[nome_campo] = 0.0
                        else:
                            registro[nome_campo] = 0.0
                            
                    # Registrar os valores obtidos no log para debug
                    taxas_valores = ", ".join([f"{k}: {v}" for k, v in registro.items() 
                                             if k not in ['Data', 'Número da Nota', 'Tipo de Transação', 'Quantidade', 'Preço Unitário', 'Ativo']])
                    logger.log(f"     - Taxas/Valores: {taxas_valores}", "info")
                    
                    dados_por_mes[mes_ano].append(registro)
                else:
                    # Processamento normal para notas com transações
                    data_referencia = nota.reference_date
                    mes_ano = data_referencia.strftime('%Y-%m')
                    nota_transacoes = len(nota.transactions)
                    total_transacoes += nota_transacoes
                    
                    # Debug das transações
                    logger.log(f"     - Transações detectadas: {nota_transacoes}")
                    
                    for j, transacao in enumerate(nota.transactions):
                        logger.log(f"       → Transação #{j+1}: {transacao.security.name} - {transacao.transaction_type.name} - {transacao.amount} x {float(transacao.unit_price)}")
                        
                        # Usar a mesma abordagem defensiva para evitar erros com atributos ausentes
                        registro = {
                            'Data': data_referencia,
                            'Número da Nota': nota.reference_id,
                            'Tipo de Transação': transacao.transaction_type.name,
                            'Quantidade': transacao.amount,
                            'Preço Unitário': float(transacao.unit_price),
                            'Ativo': transacao.security.name,
                        }
                        
                        # Adicionar taxas e valores apenas se existirem
                        campos = [
                            ('Taxa de Liquidação', 'settlement_fee'),
                            ('Taxa de Registro', 'registration_fee'),
                            ('Taxa de Termo/Opções', 'term_fee'),
                            ('Taxa A.N.A', 'ana_fee'),
                            ('Emolumentos', 'emoluments'),
                            ('Taxa Operacional', 'operational_fee'),
                            ('Execução', 'execution'),
                            ('Taxa de Custódia', 'custody_fee'),
                            ('IRRF Retido na Fonte', 'source_withheld_taxes'),
                            ('Impostos', 'taxes'),
                            ('Outros', 'others')
                        ]
                        
                        for nome_campo, atributo in campos:
                            if hasattr(nota, atributo):
                                try:
                                    valor = getattr(nota, atributo)
                                    registro[nome_campo] = float(valor) if valor is not None else 0.0
                                except (ValueError, TypeError):
                                    registro[nome_campo] = 0.0
                            else:
                                registro[nome_campo] = 0.0
                                
                        dados_por_mes[mes_ano].append(registro)
        return True, total_notas, total_transacoes
    except Exception as e:
        logger.log(f"Erro ao processar {nome_arquivo} com correpy: {str(e)}", "erro")
        logger.log(f"Detalhes do erro: {traceback.format_exc()}", "erro")
        
        # Se falhou com correpy, tenta com os analisadores customizados disponíveis
        if (PDF_ANALYZER_DISPONIVEL or ADVANCED_PARSER_DISPONIVEL or EXTRATOR_DIRETO_DISPONIVEL) and not uso_analisador_custom:
            logger.log(f"  → Tentando processar com analisadores customizados...", "info")
            resultado_analise = tentar_analisador_customizado(caminho_pdf, logger)
            
            if resultado_analise:
                # Usar os dados do analisador customizado
                processar_resultado_customizado(resultado_analise, dados_por_mes, logger)
                total_notas = 1  # Consideramos uma nota bem-sucedida
                total_transacoes = len(resultado_analise.get("transacoes", []))
                return True, total_notas, total_transacoes
        
        return False, 0, 0

# Função para tentar ler PDF com analisador customizado
def tentar_analisador_customizado(caminho_pdf, logger):
    # Primeiro tenta com o extrator direto (maior prioridade)
    if EXTRATOR_DIRETO_DISPONIVEL:
        try:
            logger.log("Tentando extrair informações com o extrator direto...", "info")
            resultado = extrair_nota_direto(caminho_pdf)
            
            if resultado and resultado.get("sucesso"):
                logger.log(f"  → Extrator direto conseguiu extrair dados da nota", "sucesso")
                # Mostrar informações básicas da nota
                logger.log(f"     - Número da Nota: {resultado.get('numero_nota', 'N/A')}")
                logger.log(f"     - Data: {resultado.get('data_nota', 'N/A')}")
                logger.log(f"     - Corretora: {resultado.get('corretora', 'N/A')}")
                logger.log(f"     - Transações detectadas: {len(resultado.get('transacoes', []))}")
                
                # Listar transações encontradas
                for i, transacao in enumerate(resultado.get('transacoes', [])):
                    tipo = transacao.get('tipo', 'N/A')
                    ativo = transacao.get('ativo', 'N/A')
                    qtd = transacao.get('quantidade', 0)
                    preco = transacao.get('preco', 0)
                    valor_total = transacao.get('valor_total', 0)
                    tipo_text = 'Compra' if tipo == 'C' else 'Venda' if tipo == 'V' else 'Outro'
                    logger.log(f"       → Transação #{i+1}: {ativo} - {tipo_text} - {qtd} x {preco} = {valor_total:.2f}")
                
                # Mostrar taxas e valores
                taxas = resultado.get('taxas', {})
                if taxas:
                    logger.log(f"     - Taxas e valores:")
                    for nome, valor in taxas.items():
                        if valor > 0:
                            nome_formatado = nome.replace('_', ' ').title()
                            logger.log(f"       → {nome_formatado}: R$ {valor:.2f}")
                
                return resultado
            else:
                logger.log("     - Extrator direto não conseguiu extrair dados, tentando método alternativo...", "alerta")
        except Exception as e:
            logger.log(f"Erro ao usar extrator direto: {str(e)}", "erro")
    
    # Segundo tenta com o analisador avançado se disponível
    if ADVANCED_PARSER_DISPONIVEL:
        try:
            logger.log("Tentando extrair informações com o analisador avançado...", "info")
            resultado = analisar_pdf_avancado(caminho_pdf)
            
            if resultado and resultado.get("sucesso"):
                logger.log(f"  → Analisador avançado conseguiu extrair dados da nota", "sucesso")
                # Mostrar informações básicas da nota
                logger.log(f"     - Número da Nota: {resultado.get('numero_nota', 'N/A')}")
                logger.log(f"     - Data: {resultado.get('data_nota', 'N/A')}")
                logger.log(f"     - Corretora: {resultado.get('corretora', 'N/A')}")
                logger.log(f"     - Transações detectadas: {len(resultado.get('transacoes', []))}")
                
                # Listar transações encontradas
                for i, transacao in enumerate(resultado.get('transacoes', [])):
                    tipo = transacao.get('tipo', 'N/A')
                    ativo = transacao.get('ativo', 'N/A')
                    qtd = transacao.get('quantidade', 0)
                    preco = transacao.get('preco', 0)
                    valor_total = transacao.get('valor_total', 0)
                    logger.log(f"       → Transação #{i+1}: {ativo} - {'Compra' if tipo == 'C' else 'Venda'} - {qtd} x {preco} = {valor_total:.2f}")
                
                return resultado
            else:
                logger.log("     - Analisador avançado não conseguiu extrair dados, tentando método alternativo...", "alerta")
        except Exception as e:
            logger.log(f"Erro ao usar analisador avançado: {str(e)}", "erro")
            
    # Se não conseguiu com os anteriores, tenta com o analisador básico
    if PDF_ANALYZER_DISPONIVEL:
        try:
            logger.log("Tentando extrair informações com o analisador básico...", "info")
            resultado = analisar_pdf_nota_corretagem(caminho_pdf)
            
            if resultado and resultado.get("sucesso"):
                logger.log(f"  → Analisador básico conseguiu extrair dados da nota", "sucesso")
                # Mostrar informações básicas da nota
                logger.log(f"     - Número da Nota: {resultado.get('numero_nota', 'N/A')}")
                logger.log(f"     - Data: {resultado.get('data_nota', 'N/A')}")
                logger.log(f"     - Corretora: {resultado.get('corretora', 'N/A')}")
                logger.log(f"     - Transações detectadas: {len(resultado.get('transacoes', []))}")
                
                # Listar transações encontradas
                for i, transacao in enumerate(resultado.get('transacoes', [])):
                    tipo = transacao.get('tipo', 'N/A')
                    ativo = transacao.get('ativo', 'N/A')
                    qtd = transacao.get('quantidade', 0)
                    preco = transacao.get('preco', 0)
                    logger.log(f"       → Transação #{i+1}: {ativo} - {'Compra' if tipo == 'C' else 'Venda'} - {qtd} x {preco}")
                
                return resultado
            else:
                logger.log("     - Nenhum analisador conseguiu extrair dados", "alerta")
                return None
        except Exception as e:
            logger.log(f"Erro ao usar analisador básico: {str(e)}", "erro")
            return None
    else:
        logger.log("Nenhum analisador de PDF está disponível.", "erro")
        return None

# Função para processar resultado do analisador customizado
def processar_resultado_customizado(resultado, dados_por_mes, logger):
    try:
        # Preparar dados básicos
        numero_nota = resultado.get('numero_nota', 'N/A')
        data_nota = resultado.get('data_nota')
        if isinstance(data_nota, str):
            try:
                data_nota = datetime.strptime(data_nota, "%Y-%m-%d").date()
            except:
                try:
                    data_nota = datetime.strptime(data_nota, "%d/%m/%Y").date()
                except:
                    data_nota = datetime.now().date()
        elif not data_nota:
            data_nota = datetime.now().date()
            
        mes_ano = data_nota.strftime('%Y-%m')
        
        # Processar transações
        transacoes = resultado.get('transacoes', [])
        taxas = resultado.get('taxas', {})
        
        # Verificar e corrigir preços grandes que possam estar sem decimal
        for transacao in transacoes:
            if 'preco' in transacao and isinstance(transacao['preco'], (int, float)):
                preco = transacao['preco']
                # Se o preço for muito alto, provavelmente está sem casas decimais
                if preco > 10000 and len(str(int(preco))) >= 5:
                    # Converter para formato com decimal (dividindo por 100)
                    transacao['preco'] = preco / 100
        
        if not transacoes:
            # Se não há transações, criar entrada apenas com as taxas
            registro = {
                'Data': data_nota,
                'Número da Nota': numero_nota,
                'Tipo de Transação': 'SEM TRANSAÇÕES',
                'Quantidade': 0,
                'Preço Unitário': 0.0,
                'Ativo': 'N/A',
            }
            
            # Adicionar taxas
            campos_taxas = {
                'taxa_liquidacao': 'Taxa de Liquidação',
                'taxa_registro': 'Taxa de Registro',
                'taxa_termo': 'Taxa de Termo/Opções',
                'taxa_ana': 'Taxa A.N.A',
                'emolumentos': 'Emolumentos',
                'taxa_operacional': 'Taxa Operacional',
                'execucao': 'Execução',
                'corretagem': 'Corretagem',
                'iss': 'ISS',
                'irrf': 'IRRF Retido na Fonte',
                'outras_taxas': 'Outros'
            }
            
            for campo_origem, campo_destino in campos_taxas.items():
                registro[campo_destino] = float(taxas.get(campo_origem, 0.0))
                
            # Adicionar campos que não temos no analisador customizado
            for campo in ['Taxa de Custódia', 'Impostos']:
                if campo not in registro:
                    registro[campo] = 0.0
                    
            dados_por_mes[mes_ano].append(registro)
        else:
            # Processar cada transação encontrada
            for transacao in transacoes:
                tipo = transacao.get('tipo', 'N/A')
                tipo_texto = 'COMPRA' if tipo == 'C' else 'VENDA' if tipo == 'V' else 'OUTRO' if tipo == 'X' else tipo
                ativo = transacao.get('ativo', 'N/A')
                qtd = float(transacao.get('quantidade', 0))
                preco = float(transacao.get('preco', 0))
                tipo_negocio = transacao.get('tipo_negocio', '')
                dc = transacao.get('dc', '')
                preco_ajuste = transacao.get('preco_ajuste', preco)
                
                # Extrair campos específicos para mercado futuro
                ticker = transacao.get('ticker', ativo)
                vencimento = transacao.get('vencimento', '')
                valor_operacao = transacao.get('valor_operacao', 0)
                taxa_operacional = transacao.get('taxa_operacional', 0)
                
                registro = {
                    'Data': data_nota,
                    'Número da Nota': numero_nota,
                    'C/V': tipo,  # C ou V direto
                    'Mercadoria': ticker,
                    'Vencimento': vencimento,
                    'Quantidade': qtd,
                    'Preço / Ajuste': preco,
                    'Tipo Negócio': tipo_negocio,
                    'Valor Operação / D/C': valor_operacao,
                    'D/C': dc,
                    'Taxa Operacional': taxa_operacional,
                    'Ativo Original': ativo  # Mantemos o ativo original como referência
                }
                
                # Adicionar taxas (divididas igualmente entre as transações)
                divisor = len(transacoes)
                campos_taxas = {
                    'taxa_liquidacao': 'Taxa de Liquidação',
                    'taxa_registro': 'Taxa de Registro',
                    'taxa_termo': 'Taxa de Termo/Opções',
                    'taxa_ana': 'Taxa A.N.A',
                    'emolumentos': 'Emolumentos',
                    'taxa_operacional': 'Taxa Operacional',
                    'execucao': 'Execução',
                    'corretagem': 'Corretagem',
                    'iss': 'ISS',
                    'irrf': 'IRRF Retido na Fonte',
                    'outras_taxas': 'Outros'
                }
                
                for campo_origem, campo_destino in campos_taxas.items():
                    registro[campo_destino] = float(taxas.get(campo_origem, 0.0)) / divisor
                    
                # Adicionar campos que não temos no analisador customizado
                for campo in ['Taxa de Custódia', 'Impostos']:
                    if campo not in registro:
                        registro[campo] = 0.0
                        
                dados_por_mes[mes_ano].append(registro)
        
        return True
    except Exception as e:
        logger.log(f"Erro ao processar resultado do analisador customizado: {str(e)}", "erro")
        logger.log(f"Detalhes do erro: {traceback.format_exc()}", "erro")
        return False

# Função principal para processar os PDFs e exportar para Excel
def processar_notas(modo, origem, log_widget, progress_bar, status_var):
    dados_por_mes = defaultdict(list)
    logger = LogHandler(log_widget)
    total_arquivos = 0
    total_notas = 0
    total_transacoes = 0
    arquivo_saida = None
    
    try:
        # Definir arquivos a processar com base no modo (pasta ou arquivos individuais)
        if modo == "pasta":
            arquivos = [os.path.join(origem, f) for f in os.listdir(origem) if f.lower().endswith('.pdf')]
            if not arquivos:
                logger.log("Nenhum PDF encontrado na pasta selecionada.", "alerta")
                return False
            logger.log(f"Encontrados {len(arquivos)} arquivos PDF na pasta para processamento", "info")
            # Gerar nome do arquivo Excel de saída no mesmo local da pasta
            arquivo_saida = gerar_nome_saida_automatico(origem)
        else:  # modo == "arquivos"
            arquivos = origem.split(";")
            if not arquivos or not arquivos[0]:
                logger.log("Nenhum arquivo selecionado.", "alerta")
                return False
            logger.log(f"Processando {len(arquivos)} arquivos selecionados", "info")
            # Gerar nome do arquivo Excel de saída no mesmo local do primeiro PDF
            arquivo_saida = gerar_nome_saida_automatico(arquivos[0])
        
        logger.log(f"O arquivo Excel será salvo como: {arquivo_saida}", "info")
        total_arquivos = len(arquivos)
        
        # Configurar barra de progresso
        progress_bar["maximum"] = total_arquivos
        progress_bar["value"] = 0
        
        # Processar cada arquivo PDF
        for i, caminho_pdf in enumerate(arquivos):
            nome_arquivo = os.path.basename(caminho_pdf)
            status_var.set(f"Processando: {nome_arquivo} ({i+1}/{total_arquivos})")
            logger.log(f"Processando: {nome_arquivo}")
            
            sucesso, arquivo_notas, arquivo_transacoes = processar_arquivo_pdf(caminho_pdf, dados_por_mes, logger)
            if sucesso:
                total_notas += arquivo_notas
                total_transacoes += arquivo_transacoes
            
            # Atualizar progresso
            progress_bar["value"] = i + 1
            progress_bar.update()
        
        if not dados_por_mes:
            logger.log("Nenhuma transação encontrada nos PDFs.", "alerta")
            return False
        
        # Estatísticas finais
        logger.log(f"Estatísticas do processamento:", "info")
        logger.log(f"  → Arquivos PDF processados: {total_arquivos}")
        logger.log(f"  → Total de notas encontradas: {total_notas}")
        logger.log(f"  → Total de transações: {total_transacoes}")
        logger.log(f"  → Períodos encontrados: {', '.join(sorted(dados_por_mes.keys()))}")
            
        # Exportar para Excel
        status_var.set("Gerando arquivo Excel...")
        logger.log(f"Salvando Excel em: {arquivo_saida}", "info")
        with pd.ExcelWriter(arquivo_saida, engine='openpyxl') as writer:
            for mes, dados in sorted(dados_por_mes.items()):
                # Corrigir os valores de preço quando necessário
                for registro in dados:
                    # Checar campos de preço que podem estar com formato incorreto
                    campos_preco = ['Preço Unitário', 'Preço / Ajuste']
                    for campo in campos_preco:
                        if campo in registro and isinstance(registro[campo], (int, float)):
                            valor = registro[campo]
                            if valor > 10000 and len(str(int(valor))) >= 5:  # Valores altos sem decimal
                                # Converter para formato com decimal (dividindo por 100)
                                registro[campo] = valor / 100
                    
                    # Corrigir o formato do vencimento se necessário
                    if 'Vencimento' in registro and isinstance(registro['Vencimento'], str):
                        vencimento = registro['Vencimento']
                        if vencimento and not vencimento.strip().startswith('0'):
                            # Garantir que a data está no formato DD/MM/AAAA
                            try:
                                if '/' in vencimento:
                                    partes = vencimento.split('/')
                                    if len(partes) == 3 and len(partes[0]) == 2 and len(partes[1]) == 2 and len(partes[2]) == 4:
                                        # Já está no formato correto
                                        pass
                                    elif len(partes) == 3:
                                        # Garantir o formato com zeros à esquerda
                                        registro['Vencimento'] = f"{int(partes[0]):02d}/{int(partes[1]):02d}/{partes[2]}"
                            except:
                                pass  # Ignorar erros de formatação
                    
                df = pd.DataFrame(dados)
                nome_aba = mes.replace('-', '_')  # Substituir '-' por '_' para o nome da aba
                
                # Criar o DataFrame e salvar na planilha
                df.to_excel(writer, sheet_name=nome_aba, index=False)
                
                # Aplicar formatação às colunas numéricas
                workbook = writer.book
                worksheet = writer.sheets[nome_aba]
                
                # Aplicar formatação monetária brasileira (R$ #.##0,00)
                colunas_moeda = ['Preço Unitário', 'Preço / Ajuste', 'Valor Operação / D/C', 'Taxa Operacional',
                                'Taxa de Liquidação', 'Taxa de Registro', 'Taxa de Termo/Opções', 'Taxa A.N.A', 
                                'Emolumentos', 'Execução', 'Taxa de Custódia', 'IRRF Retido na Fonte', 
                                'Impostos', 'Outros', 'Corretagem', 'ISS']
                
                # Definir a ordem das colunas para o formato de futuros (quando disponível)
                ordem_colunas_futuro = ['Data', 'Número da Nota', 'C/V', 'Mercadoria', 'Vencimento', 'Quantidade', 
                                    'Preço / Ajuste', 'Tipo Negócio', 'Valor Operação / D/C', 'D/C', 'Taxa Operacional']
                
                # Reorganizar colunas quando possível
                colunas_existentes = [c for c in ordem_colunas_futuro if c in df.columns]
                outras_colunas = [c for c in df.columns if c not in ordem_colunas_futuro]
                
                # Se temos pelo menos as colunas básicas de futuros, reorganizamos
                colunas_basicas_futuro = ['C/V', 'Mercadoria', 'Vencimento', 'Preço / Ajuste']
                if all(c in df.columns for c in colunas_basicas_futuro):
                    df = df[colunas_existentes + outras_colunas]
                
                # Aplicar formatos para todas as colunas
                for idx, coluna in enumerate(df.columns):
                    # Obter a letra da coluna (A, B, C, etc.)
                    col_letter = chr(65 + idx) if idx < 26 else chr(64 + idx // 26) + chr(65 + idx % 26)
                    
                    # Aplicar formatação monetária
                    if coluna in colunas_moeda:
                        # Formato para moeda brasileira
                        for row in range(2, len(df) + 2):  # +2 porque Excel é 1-indexed e temos o cabeçalho
                            cell = f"{col_letter}{row}"
                            try:
                                # Aplicar formatação monetária brasileira
                                worksheet[cell].number_format = 'R$ #,##0.00'
                            except:
                                pass  # Ignorar erros de formatação
                    
                    # Formatação específica para outras colunas
                    elif coluna == 'C/V':
                        # Deixar centralizado
                        worksheet.column_dimensions[col_letter].width = 6
                    elif coluna == 'Mercadoria':
                        worksheet.column_dimensions[col_letter].width = 12
                    elif coluna == 'Vencimento':
                        worksheet.column_dimensions[col_letter].width = 12
                        # Formato de data
                        for row in range(2, len(df) + 2):
                            cell = f"{col_letter}{row}"
                            try:
                                worksheet[cell].number_format = 'dd/mm/yyyy'
                            except:
                                pass
                    elif coluna == 'Quantidade':
                        worksheet.column_dimensions[col_letter].width = 10
                        # Formato numérico
                        for row in range(2, len(df) + 2):
                            cell = f"{col_letter}{row}"
                            try:
                                worksheet[cell].number_format = '#,##0'
                            except:
                                pass
                    elif coluna == 'Tipo Negócio':
                        worksheet.column_dimensions[col_letter].width = 15
                    elif coluna == 'D/C':
                        worksheet.column_dimensions[col_letter].width = 5
                        # Centralizar
                        for row in range(2, len(df) + 2):
                            cell = f"{col_letter}{row}"
                            try:
                                worksheet[cell].alignment = workbook.styles.Alignment(horizontal='center')
                            except:
                                pass
                
                logger.log(f"  → Planilha '{nome_aba}' criada com {len(df)} transações")
                
        logger.log(f"Arquivo Excel '{os.path.basename(arquivo_saida)}' criado com sucesso.", "sucesso")
        return arquivo_saida
        
    except Exception as e:
        logger.log(f"Erro no processamento: {str(e)}", "erro")
        return False

# Função para gerar nome de saída automático no mesmo local que o PDF original
def gerar_nome_saida_automatico(caminho_origem):
    # Se caminho_origem é um arquivo PDF
    if os.path.isfile(caminho_origem) and caminho_origem.lower().endswith('.pdf'):
        # Usar o mesmo diretório e nome base, apenas alterando a extensão
        diretorio = os.path.dirname(caminho_origem)
        nome_base = os.path.splitext(os.path.basename(caminho_origem))[0]
        return os.path.join(diretorio, f"{nome_base}_exportado.xlsx")
    
    # Se caminho_origem é um diretório
    elif os.path.isdir(caminho_origem):
        # Usar o nome do diretório como base para o nome do arquivo
        nome_diretorio = os.path.basename(caminho_origem)
        if not nome_diretorio:  # Se for raiz do drive, usar algo genérico
            nome_diretorio = "notas_corretagem"
        return os.path.join(caminho_origem, f"{nome_diretorio}_exportado.xlsx")
    
    # Caso padrão (nem arquivo nem diretório válido)
    else:
        # Usar diretório de documentos do usuário
        diretorio_documentos = os.path.expanduser("~\\Documents")
        return os.path.join(diretorio_documentos, "relatorio_notas_corretagem.xlsx")

# Função para selecionar pasta
def selecionar_pasta():
    pasta = filedialog.askdirectory(title="Selecione a pasta dos PDFs das notas de corretagem")
    if pasta:
        entrada_pasta.delete(0, tk.END)
        entrada_pasta.insert(0, pasta)
        status_var.set(f"Pasta selecionada: {pasta}")
        # Mostrar caminho do Excel que será gerado
        arquivo_saida = gerar_nome_saida_automatico(pasta)
        log_handler.log(f"O arquivo Excel será salvo como: {arquivo_saida}", "info")

# Função para selecionar arquivos PDF individuais
def selecionar_arquivos():
    arquivos = filedialog.askopenfilenames(
        filetypes=[("PDF Files", "*.pdf")],
        title="Selecione os PDFs das notas de corretagem"
    )
    if arquivos:
        arquivos_string = ";".join(arquivos)
        entrada_arquivos.delete(0, tk.END)
        entrada_arquivos.insert(0, arquivos_string)
        qtd_arquivos = len(arquivos)
        status_var.set(f"{qtd_arquivos} arquivo{'s' if qtd_arquivos > 1 else ''} selecionado{'s' if qtd_arquivos > 1 else ''}")
        # Mostrar caminho do Excel que será gerado
        if arquivos:
            arquivo_saida = gerar_nome_saida_automatico(arquivos[0])
            log_handler.log(f"O arquivo Excel será salvo como: {arquivo_saida}", "info")

# Função para abrir o diretório do arquivo gerado
def abrir_diretorio_resultado(arquivo):
    try:
        diretorio = os.path.dirname(arquivo)
        os.startfile(diretorio)
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível abrir o diretório: {str(e)}")

# Função para abrir o arquivo Excel gerado
def abrir_arquivo_excel(arquivo):
    try:
        os.startfile(arquivo)
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível abrir o arquivo: {str(e)}")

# Função para obter o modo e origem atuais
def obter_modo_e_origem():
    modo_aba = notebook.tab(notebook.select(), "text").lower()
    
    if modo_aba == "pasta":
        pasta = entrada_pasta.get()
        return "pasta", pasta
    else:  # "arquivos individuais"
        arquivos = entrada_arquivos.get()
        return "arquivos", arquivos

# Função para iniciar processamento em thread separada
def iniciar_processamento_thread():
    # Verificar seleção
    modo, origem = obter_modo_e_origem()
    
    # Validar entradas
    if modo == "pasta":
        if not origem:
            messagebox.showerror("Erro", "Selecione uma pasta contendo PDFs de notas de corretagem.")
            return
        if not os.path.isdir(origem):
            messagebox.showerror("Erro", "A pasta selecionada não existe.")
            return
    else:  # modo == "arquivos"
        if not origem:
            messagebox.showerror("Erro", "Selecione pelo menos um arquivo PDF de nota de corretagem.")
            return
        for arquivo in origem.split(";"):
            if not os.path.isfile(arquivo) or not arquivo.lower().endswith('.pdf'):
                messagebox.showerror("Erro", f"Arquivo inválido: {arquivo}")
                return
    
    # Reiniciar log e progresso
    log_text.config(state=tk.NORMAL)
    log_text.delete(1.0, tk.END)
    log_text.config(state=tk.DISABLED)
    progress_bar["value"] = 0
    
    # Desativar controles durante processamento
    toggle_controles(False)
    
    # Criar e iniciar thread
    thread = threading.Thread(target=lambda: processar_thread(modo, origem))
    thread.daemon = True
    thread.start()

# Função para executar processamento em thread separada
def processar_thread(modo, origem):
    try:
        # Atualizar interface
        status_var.set("Iniciando processamento...")
        
        # Desativar controles
        toggle_controles(False)
        
        # Executar processamento - retorna o caminho do arquivo criado ou False
        resultado = processar_notas(modo, origem, log_text, progress_bar, status_var)
        
        # Atualizar interface após conclusão
        if isinstance(resultado, str) and os.path.exists(resultado):
            status_var.set("Processamento concluído com sucesso")
            root.after(0, lambda: mostrar_resultado_sucesso(resultado))
        else:
            status_var.set("Processamento concluído com erros")
            root.after(0, lambda: messagebox.showerror("Erro", "Ocorreram erros durante o processamento. Verifique o log para mais detalhes."))
    
    except Exception as e:
        status_var.set("Erro durante processamento")
        root.after(0, lambda: messagebox.showerror("Erro inesperado", str(e)))
    
    finally:
        # Reativar controles
        root.after(0, lambda: toggle_controles(True))

def toggle_controles(ativar):
    estado = tk.NORMAL if ativar else tk.DISABLED
    botao_processar.config(state=estado)
    botao_pasta.config(state=estado)
    botao_arquivos.config(state=estado)

def mostrar_resultado_sucesso(arquivo):
    # Mostrar popup simplificado de sucesso com opções para abrir o arquivo
    popup = tk.Toplevel(root)
    popup.title("Concluído")
    popup.geometry("450x220")
    popup.resizable(False, False)
    popup.transient(root)
    popup.grab_set()
    
    # Aplicar tema escuro com borda suave
    popup.configure(bg=CORES["bg_escuro"])
    
    # Frame de conteúdo principal
    content_frame = ttk.Frame(popup, style="Card.TFrame")
    content_frame.pack(fill="both", expand=True, padx=15, pady=15)
    
    # Ícone de sucesso e mensagem principal em uma única linha
    header_frame = ttk.Frame(content_frame, style="Card.TFrame")
    header_frame.pack(fill="x", padx=5, pady=5)
    
    # Ícone de sucesso
    ttk.Label(
        header_frame, 
        text="✅", # Ícone de sucesso mais simples
        font=("Segoe UI", 24),
        foreground=CORES["sucesso"],
        background=CORES["bg_medio"]
    ).pack(side=tk.LEFT, padx=(5, 10))
    
    # Texto de sucesso
    ttk.Label(
        header_frame, 
        text="Processamento Concluído", 
        font=("Segoe UI", 14, "bold"),
        foreground=CORES["texto"],
        background=CORES["bg_medio"]
    ).pack(side=tk.LEFT)
    
    # Caminho do arquivo
    info_frame = ttk.Frame(content_frame, style="Card.TFrame")
    info_frame.pack(fill="x", padx=5, pady=10)
    
    ttk.Label(
        info_frame,
        text="Arquivo gerado:",
        font=("Segoe UI", 10),
        foreground=CORES["texto"],
        background=CORES["bg_medio"]
    ).pack(anchor="w")
    
    # Nome do arquivo com caminho completo
    ttk.Label(
        info_frame,
        text=arquivo,
        font=("Consolas", 9),
        foreground=CORES["destaque"],
        background=CORES["bg_medio"],
        wraplength=400
    ).pack(anchor="w", padx=(10, 0), pady=2)
    
    # Frame para botões - versão simplificada
    botoes_frame = ttk.Frame(content_frame, style="Card.TFrame")
    botoes_frame.pack(pady=10, fill="x")
    
    # Botão principal em destaque
    ttk.Button(
        botoes_frame, 
        text="Abrir Arquivo", 
        style="Accent.TButton",
        command=lambda: [popup.destroy(), abrir_arquivo_excel(arquivo)]
    ).pack(side=tk.LEFT, padx=5, expand=True, fill="x")
    
    # Botões secundarios
    ttk.Button(
        botoes_frame, 
        text="Abrir Pasta", 
        command=lambda: [popup.destroy(), abrir_diretorio_resultado(arquivo)]
    ).pack(side=tk.LEFT, padx=5, expand=True, fill="x")
    
    ttk.Button(
        botoes_frame, 
        text="Fechar", 
        command=popup.destroy
    ).pack(side=tk.LEFT, padx=5, expand=True, fill="x")

# Criar janela principal
root = tk.Tk()
root.title("Correpy Plus")
root.geometry("1000x650")
root.minsize(800, 600)

# Adicionar ícone para a janela (opcional)
try:
    root.iconbitmap("icon.ico")  # Se tiver um ícone disponivel
except:
    pass  # Continuar sem ícone se não encontrar

# Configurar tema escuro moderno
root.configure(bg=CORES["bg_escuro"])

# Configurar estilo personalizado
style = themes.ThemedStyle(root)
style.set_theme("equilux")  # Tema base escuro

# Personalizar estilos dos widgets para uma aparência mais moderna
style.configure("TFrame", background=CORES["bg_escuro"])
style.configure("Card.TFrame", background=CORES["bg_medio"], relief="flat", borderwidth=0, padding=15)
style.configure("TLabel", background=CORES["bg_escuro"], foreground=CORES["texto"], font=("Segoe UI", 10))
style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground=CORES["destaque"])
style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground=CORES["destaque"])
style.configure("Subtitle.TLabel", font=("Segoe UI", 11), foreground=CORES["alerta"])
style.configure("Status.TLabel", font=("Segoe UI", 9), foreground=CORES["texto"])

# Estilo para botões modernos
style.configure("TButton", font=("Segoe UI", 10), padding=5)
style.configure("Accent.TButton", background=CORES["destaque"], foreground=CORES["bg_escuro"], font=("Segoe UI", 10, "bold"))
style.map("Accent.TButton",
         background=[('active', CORES["sucesso"]), ('pressed', CORES["destaque"])],
         foreground=[('active', CORES["bg_escuro"]), ('pressed', CORES["bg_escuro"])])

# Estilo para notebook (abas)
style.configure("TNotebook", background=CORES["bg_escuro"], borderwidth=0)
style.configure("TNotebook.Tab", background=CORES["bg_medio"], foreground=CORES["texto"], padding=[15, 5], font=("Segoe UI", 10))
style.map("TNotebook.Tab",
         background=[('selected', CORES["destaque"])],
         foreground=[('selected', CORES["bg_escuro"])])

# Estilo para entradas
root.option_add("*TEntry*font", ("Segoe UI", 10))
style.configure("TEntry", fieldbackground=CORES["bg_claro"], foreground=CORES["texto"], borderwidth=1, padding=5)
style.configure("Status.TLabel", font=("Segoe UI", 9))

# Estilo de botões
style.configure("TButton", font=("Segoe UI", 10))
style.configure("Accent.TButton", background=CORES["destaque"])

# Frame para título e cabeçalho com visual moderno
frame_header = ttk.Frame(root, style="Card.TFrame")
frame_header.pack(fill=tk.X, padx=20, pady=(15, 5))

# Container para logo e título com efeito gradiente
logo_container = ttk.Frame(frame_header, style="Card.TFrame")
logo_container.pack(fill=tk.X, pady=(0, 5))

# Logo e título com ícone moderno
titulo_label = ttk.Label(
    logo_container, 
    text="📊 Correpy Plus 2.0", 
    style="Title.TLabel"
)
titulo_label.pack(side=tk.LEFT, padx=10)

# Versão
versao_label = ttk.Label(
    logo_container,
    text="v2.0",
    style="Subtitle.TLabel"
)
versao_label.pack(side=tk.LEFT, padx=(0, 10))

# Data atual com formato mais elegante e ícone de calendário
data_atual = datetime.now().strftime("%d de %B de %Y")
data_label = ttk.Label(
    logo_container, 
    text=f"📅 {data_atual}", 
    style="Header.TLabel"
)
data_label.pack(side=tk.RIGHT, padx=10)

# Subtitulo descritivo
subtitulo_container = ttk.Frame(frame_header, style="Card.TFrame")
subtitulo_container.pack(fill=tk.X, pady=5)

subtitulo_label = ttk.Label(
    subtitulo_container,
    text="Extrator avançado de dados de notas de corretagem para Excel",
    style="Subtitle.TLabel"
)
subtitulo_label.pack(side=tk.LEFT, padx=10)

# Layout principal reorganizado para design moderno
main_container = ttk.Frame(root, style="TFrame")
main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

# Painel de comandos lateral (esquerda)
cmd_panel = ttk.Frame(main_container, style="Card.TFrame")
cmd_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10), pady=0, expand=False)

# Título do painel de comandos
cmd_title = ttk.Label(cmd_panel, text="📂 Ações", style="Header.TLabel")
cmd_title.pack(side=tk.TOP, padx=10, pady=(0, 10), anchor="w")

# Botões principais com ícones
btn_frame = ttk.Frame(cmd_panel, style="Card.TFrame")
btn_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

botao_processar = ttk.Button(
    btn_frame, 
    text="🚀 Processar Notas", 
    command=iniciar_processamento_thread,
    style="Accent.TButton",
    width=20
)
botao_processar.pack(padx=5, pady=5, fill=tk.X)

botao_limpar = ttk.Button(
    btn_frame, 
    text="🗑️ Limpar Campos", 
    command=lambda: [entrada_pasta.delete(0, tk.END), entrada_arquivo_pasta.delete(0, tk.END), 
              entrada_arquivos.delete(0, tk.END), entrada_arquivo_individual.delete(0, tk.END)],
    width=20
)
botao_limpar.pack(padx=5, pady=5, fill=tk.X)

botao_sair = ttk.Button(btn_frame, text="🚪 Sair", command=root.quit, width=20)
botao_sair.pack(padx=5, pady=5, fill=tk.X)

# Frame principal - corpo da aplicação
frame_principal = ttk.Frame(main_container, style="TFrame")
frame_principal.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

# Painel esquerdo - Controles
frame_controles = ttk.Frame(frame_principal, style="Card.TFrame")
frame_controles.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10), expand=True)

# Título do painel de controles
ttk.Label(
    frame_controles, 
    text="Configurações", 
    style="Header.TLabel",
    background=CORES["bg_medio"]
).pack(anchor="w", padx=15, pady=15)

# Conteúdo do painel de controles - Frame interno com padding
frame_form = ttk.Frame(frame_controles, style="TFrame")
frame_form.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

# Criar notebook (sistema de abas)
notebook = ttk.Notebook(frame_form)
notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

# Aba 1: Processar pasta
frame_aba_pasta = ttk.Frame(notebook, style="TFrame")
notebook.add(frame_aba_pasta, text="Pasta", padding=10)

# Aba 2: Processar arquivos individuais
frame_aba_arquivos = ttk.Frame(notebook, style="TFrame")
notebook.add(frame_aba_arquivos, text="Arquivos Individuais", padding=10)

# Conteúdo da Aba 1: Pasta
ttk.Label(frame_aba_pasta, text="Selecione a pasta contendo as notas de corretagem em PDF:").pack(anchor="w", pady=(5, 5))

frame_pasta = ttk.Frame(frame_aba_pasta)
frame_pasta.pack(fill=tk.X, pady=(0, 15))

entrada_pasta = tk.Entry(frame_pasta, bg=CORES["bg_claro"], fg=CORES["texto"], insertbackground=CORES["texto"])
entrada_pasta.pack(side=tk.LEFT, fill=tk.X, expand=True)

botao_pasta = ttk.Button(frame_pasta, text="Escolher Pasta", command=selecionar_pasta)
botao_pasta.pack(side=tk.RIGHT, padx=(10, 0))

# Mensagem informativa sobre exportação automática
informacao_exportacao = ttk.Label(
    frame_aba_pasta, 
    text="ℹ️ O arquivo Excel será exportado automaticamente no mesmo local do PDF original", 
    foreground=CORES["destaque"],
    wraplength=400,
    justify="left",
    font=("Segoe UI", 9, "italic"),
)
informacao_exportacao.pack(anchor="w", pady=(15, 5))

ttk.Label(frame_aba_pasta, text="📄 Processa todos os PDFs dentro de uma pasta", foreground=CORES["alerta"]).pack(anchor="w", pady=(15, 0))

# Conteúdo da Aba 2: Arquivos Individuais
ttk.Label(frame_aba_arquivos, text="Selecione os PDFs das notas de corretagem:").pack(anchor="w", pady=(5, 5))

frame_selecao_arquivos = ttk.Frame(frame_aba_arquivos)
frame_selecao_arquivos.pack(fill=tk.X, pady=(0, 15))

entrada_arquivos = tk.Entry(frame_selecao_arquivos, bg=CORES["bg_claro"], fg=CORES["texto"], insertbackground=CORES["texto"])
entrada_arquivos.pack(side=tk.LEFT, fill=tk.X, expand=True)

botao_arquivos = ttk.Button(frame_selecao_arquivos, text="Escolher Arquivos", command=selecionar_arquivos)
botao_arquivos.pack(side=tk.RIGHT, padx=(10, 0))

# Mensagem informativa sobre exportação automática
informacao_exportacao2 = ttk.Label(
    frame_aba_arquivos, 
    text="ℹ️ O arquivo Excel será exportado automaticamente no mesmo local do primeiro PDF selecionado", 
    foreground=CORES["destaque"],
    wraplength=400,
    justify="left",
    font=("Segoe UI", 9, "italic")
)
informacao_exportacao2.pack(anchor="w", pady=(15, 5))

ttk.Label(frame_aba_arquivos, text="📋 Selecione apenas os arquivos específicos para processar", foreground=CORES["alerta"]).pack(anchor="w", pady=(15, 0))

# Separador visual
separador = ttk.Separator(frame_form, orient="horizontal")
separador.pack(fill=tk.X, pady=15)

# Layout - Botões de ação
botoes_frame = ttk.Frame(frame_form)
botoes_frame.pack(fill=tk.X, pady=(5, 0))

botao_processar = ttk.Button(
    botoes_frame, 
    text="📂 Processar Notas", 
    command=iniciar_processamento_thread,
    style="Accent.TButton",
    width=20
)
botao_processar.pack(padx=5, pady=5, fill=tk.X)

botao_sair = ttk.Button(botoes_frame, text="✖ Sair", command=root.quit, width=20)
botao_sair.pack(padx=5, pady=5, fill=tk.X)

# Painel direito - Log e progresso
frame_log = ttk.Frame(frame_principal, style="Card.TFrame")
frame_log.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

# Título do painel de log
ttk.Label(
    frame_log, 
    text="Log de Processamento", 
    style="Header.TLabel",
    background=CORES["bg_medio"]
).pack(anchor="w", padx=15, pady=15)

# Área de log
frame_log_interno = ttk.Frame(frame_log, style="TFrame")
frame_log_interno.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

# Barra de progresso
ttk.Label(frame_log_interno, text="Progresso:").pack(anchor="w", pady=(0, 5))
progress_bar = ttk.Progressbar(frame_log_interno, orient="horizontal", length=300, mode="determinate")
progress_bar.pack(fill=tk.X, pady=(0, 10))

# Status
status_var = tk.StringVar(value="Pronto para iniciar")
status_label = ttk.Label(frame_log_interno, textvariable=status_var, style="Status.TLabel")
status_label.pack(anchor="w", pady=(0, 10))

# Área de texto de log
log_text = scrolledtext.ScrolledText(
    frame_log_interno, 
    bg=CORES["bg_escuro"], 
    fg=CORES["texto"], 
    height=20,
    insertbackground=CORES["texto"],
    font=("Consolas", 9)
)
log_text.pack(fill=tk.BOTH, expand=True)
log_text.tag_configure("erro", foreground=CORES["erro"])
log_text.tag_configure("sucesso", foreground=CORES["sucesso"])
log_text.tag_configure("alerta", foreground=CORES["alerta"])
log_text.tag_configure("info", foreground=CORES["destaque"])
log_text.tag_configure("normal", foreground=CORES["texto"])

# Inserir mensagem inicial de boas-vindas
log_handler = LogHandler(log_text)
log_handler.log("Bem-vindo ao Correpy Plus!", "info")
log_handler.log("Selecione a pasta contendo as notas de corretagem em PDF e o arquivo Excel de saída.")
log_handler.log("Clique em 'Processar Notas' para iniciar a conversão.")

# Barra de status na parte inferior
frame_status = ttk.Frame(root, style="TFrame")
frame_status.pack(fill=tk.X, padx=20, pady=10)

ttk.Label(frame_status, text="Correpy Plus v1.0 | Desenvolvido com ❤️", style="Status.TLabel").pack(side=tk.LEFT)
ttk.Label(frame_status, text="Baseado em https://github.com/thiagosalvatore/correpy", style="Status.TLabel").pack(side=tk.RIGHT)

# Iniciar loop de eventos
root.mainloop()
