# Correpy Plus

![Correpy Plus Logo](https://img.shields.io/badge/Correpy-Plus-blue?style=for-the-badge)
![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-blue?style=for-the-badge&logo=windows)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

## 📋 Descrição

**Correpy Plus** é uma ferramenta de extração de dados de notas de corretagem em PDF para Excel. Desenvolvida para facilitar a análise financeira e contábil de operações no mercado de capitais brasileiro, com suporte especial para mercados futuros (WIN, DOL, etc).

Baseada na biblioteca [correpy](https://github.com/thiagosalvatore/correpy), o Correpy Plus adiciona uma interface gráfica intuitiva e extratores avançados para capturar dados específicos do mercado de futuros.

## ✨ Características Principais

- **Interface Gráfica Amigável**: Interface moderna e intuitiva que facilita o processamento dos PDFs
- **Exportação Automática**: Gera Excel automaticamente no mesmo local do arquivo PDF original
- **Suporte a Mercado Futuro**: Extração completa de informações específicas:
  - C/V (tipo da operação)
  - Mercadoria (ex: WINJ25)
  - Vencimento (ex: 16/04/2025)
  - Quantidade
  - Preço/Ajuste
  - Tipo Negócio (DAY TRADE, NORMAL)
  - Valor Operação/D/C
  - Taxa Operacional
- **Formatação Adequada**: Valores monetários formatados corretamente (R$ #.##0,00)
- **Multi-Processamento**: Processa vários PDFs simultaneamente
- **Sistema de Fallback**: Usa múltiplos extratores em cascata para garantir que os dados sejam extraídos

## 📦 Instalação

### Pré-requisitos

- Python 3.8 ou superior
- Windows (testado no Windows 10/11)

### Instalação via pip

```bash
# Instalar as dependências
pip install pandas openpyxl pdfplumber ttkthemes 

# Instalar o correpy
pip install correpy
```

### Instalação manual

1. Clone este repositório:

```bash
git clone https://github.com/seu-usuario/correpy-plus.git
cd correpy-plus
```

2. Instale as dependências:

```bash
pip install -r requirements.txt
```

## 🚀 Como Usar

1. Execute o script principal:

```bash
python main.py
```

2. Na interface do aplicativo:
   - **Opção 1**: Selecione uma pasta contendo PDFs de notas de corretagem
   - **Opção 2**: Selecione arquivos PDF específicos
   
3. Clique em "Processar Notas"

4. O arquivo Excel será gerado automaticamente no mesmo local dos PDFs originais

5. Após o processamento, você pode:
   - Abrir o arquivo Excel gerado
   - Abrir a pasta onde o arquivo foi salvo

## 📊 Estrutura do Excel Gerado

O Excel gerado contém as seguintes informações para operações no mercado futuro:

| Campo | Descrição |
|-------|-----------|
| C/V | Compra (C) ou Venda (V) |
| Mercadoria | Ticker do contrato (ex: WINJ25) |
| Vencimento | Data de vencimento do contrato |
| Quantidade | Número de contratos |
| Preço / Ajuste | Valor do contrato |
| Tipo Negócio | DAY TRADE ou NORMAL |
| Valor Operação / D/C | Valor da operação (Débito/Crédito) |
| D/C | Débito (D) ou Crédito (C) |
| Taxa Operacional | Valor da taxa operacional |

## 🧩 Arquitetura

O Correpy Plus é composto por:

- **main.py**: Interface gráfica e lógica principal
- **extrator_notas.py**: Extrator avançado de dados de notas de corretagem
- **pdf_analyzer.py**: Parser básico para extrair dados dos PDFs

O programa utiliza múltiplos extratores em ordem de eficiência:
1. Extrator direto (extrator_notas.py)
2. Parser avançado (se disponível)
3. Parser básico (pdf_analyzer.py)
4. Correpy original (fallback)

## 🤝 Contribuindo

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues e pull requests.

1. Faça um fork do projeto
2. Crie sua feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📝 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 🙏 Agradecimentos

- [correpy](https://github.com/thiagosalvatore/correpy) - Biblioteca base que inspirou este projeto
- [pdfplumber](https://github.com/jsvine/pdfplumber) - Biblioteca para extração de texto de PDFs
- [tkinter](https://docs.python.org/3/library/tkinter.html) - Biblioteca para a interface gráfica

---

<p align="center">Criado com ❤️ para facilitar a análise de suas operações financeiras</p>
