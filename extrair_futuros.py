"""
Módulo para extração específica de contratos futuros de PDFs de notas de corretagem.
"""

import re
import pdfplumber

def parse_valor(valor_str):
    """Converte string de valor para float"""
    if not valor_str:
        return 0
    
    # Remover pontos de milhar e substituir vírgula por ponto
    valor_limpo = valor_str.replace('.', '').replace(',', '.')
    
    try:
        return float(valor_limpo)
    except ValueError:
        return 0

def extrair_texto_pdf(caminho_pdf):
    """Extrai todo o texto de um arquivo PDF"""
    texto_completo = ""
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text() or ""
                texto_completo += texto + "\n"
        return texto_completo
    except Exception as e:
        print(f"Erro ao extrair texto do PDF: {e}")
        return ""

def extrair_contratos_futuros(texto):
    """
    Extrai transações de contratos futuros (WIN, WDO, DOL, IND, etc) do texto.
    Retorna uma lista de dicionários com as informações das transações.
    """
    transacoes = []
    
    # Lista de símbolos de contratos futuros comuns
    ativos_futuros = ["WIN", "WDO", "DOL", "IND", "BGI", "CCM", "ICF"]
    
    # Divida o texto em linhas para uma análise linha a linha
    linhas = texto.split('\n')
    
    for linha in linhas:
        linha_upper = linha.upper()
        
        # Verificar se a linha contém algum dos ativos futuros
        if any(ativo in linha_upper for ativo in ativos_futuros):
            # Tente encontrar padrões de transações nesta linha
            # Padrão 1: C WDO F25 02/01/2025 1 6.088,0000 DAY TRADE
            match = re.search(r'([CV])\s+([A-Z]{3})\s+([A-Z]\d{2}).*?(\d+)\s+([\d.,]+)', linha)
            
            if match:
                grupos = match.groups()
                tipo = "C" if grupos[0].upper() == "C" else "V"
                ativo_base = grupos[1].upper()
                vencimento = grupos[2].upper()
                quantidade = parse_valor(grupos[3])
                preco = parse_valor(grupos[4])
                
                # Calcular valor total
                valor_total = quantidade * preco
                
                # Formar nome do ativo
                nome_ativo = f"{ativo_base} {vencimento}"
                
                # Criar transação
                transacao = {
                    "tipo": tipo,
                    "ativo": nome_ativo.strip(),
                    "quantidade": quantidade,
                    "preco": preco,
                    "valor_total": valor_total
                }
                
                # Adicionar à lista se não for duplicata
                if not any(t.get('ativo') == transacao.get('ativo') and 
                        t.get('quantidade') == transacao.get('quantidade') and
                        t.get('preco') == transacao.get('preco') and
                        t.get('tipo') == transacao.get('tipo') for t in transacoes):
                    transacoes.append(transacao)
            
            # Padrão genérico para capturar qualquer coisa que pareça com contrato futuro
            # Busca por padrões como: C WIN, V DOL, etc. seguidos de números
            if not match:
                match = re.search(r'([CV])\s+([A-Z]{3}).*?(\d+).*?([\d.,]+)', linha)
                if match:
                    grupos = match.groups()
                    tipo = "C" if grupos[0].upper() == "C" else "V"
                    ativo = grupos[1].upper()
                    quantidade = parse_valor(grupos[2])
                    preco = parse_valor(grupos[3])
                    
                    # Calcular valor total
                    valor_total = quantidade * preco
                    
                    # Criar transação
                    transacao = {
                        "tipo": tipo,
                        "ativo": ativo.strip(),
                        "quantidade": quantidade,
                        "preco": preco,
                        "valor_total": valor_total
                    }
                    
                    # Adicionar à lista se não for duplicata
                    if not any(t.get('ativo') == transacao.get('ativo') and 
                            t.get('quantidade') == transacao.get('quantidade') and
                            t.get('preco') == transacao.get('preco') and
                            t.get('tipo') == transacao.get('tipo') for t in transacoes):
                        transacoes.append(transacao)
    
    return transacoes

def processar_pdf_futuros(caminho_pdf):
    """
    Processa um arquivo PDF e retorna todas as transações de contratos futuros encontradas.
    """
    # Extrair o texto completo do PDF
    texto = extrair_texto_pdf(caminho_pdf)
    
    # Extrair as transações de contratos futuros
    transacoes = extrair_contratos_futuros(texto)
    
    return transacoes

# Função para uso direto
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        caminho_pdf = sys.argv[1]
        transacoes = processar_pdf_futuros(caminho_pdf)
        print(f"Encontradas {len(transacoes)} transações de contratos futuros:")
        for i, t in enumerate(transacoes):
            print(f"{i+1}. {t['tipo']} {t['ativo']} - {t['quantidade']} x {t['preco']} = {t['valor_total']}")
