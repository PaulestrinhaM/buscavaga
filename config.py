"""Configuracao do JobRadar: termos, filtros, pesos e fontes."""

# ---------------------------------------------------------------- filtro nivel 1
# Cargos e qualificadores casam por PALAVRA-CHAVE, nao por frase: "analista de crm"
# vira {analista, crm} e casa "Analista CRM Jr", "Analista de Marketing Pleno - CRM"
# ou "CRM - Analista", em qualquer ordem. PALAVRAS_IGNORADAS nao contam.
# Palavra inteira: "bi" nao casa dentro de "mobilidade".
# "*" no fim aceita variacao: "engenh*" casa engenheiro, engenheira, engenharia.
# Entre aspas vira frase exata, na ordem: '"analytics engineer"' nao casa
# "Software Engineer (Lake Analytics Platform)". Mesma sintaxe do FTS5 do SQLite.
PALAVRAS_IGNORADAS = [
    "de", "da", "do", "das", "dos", "em", "e", "a", "o", "as", "os", "para",
    "pessoa", "of", "and", "the", "in",
]

# Cargo inequivoco: aprova sozinho. Separado por trilha, porque a senioridade
# aceita muda: em dados ele nao tem experiencia formal (so junior), em operacoes
# e integracao tem dois anos (junior ou pleno). Quando o titulo casa as duas
# trilhas, vence a de cargo com mais palavras-chave; empate fica em dados.
CARGOS_DADOS = [
    "analista de dado*", "engenh* de dados",
    "analista de bi", "analista de business intelligence", "business intelligence",
    '"analytics engineer"', "data analyst", "data engineer",
    "analista de analytics", "analista de inteligencia de mercado",
    "analista de informacoes", "analista de indicadores",
    "digital analytics",
]
CARGOS_OPERACOES = [
    "marketing operations", "marketing ops", "revenue operations", "revops",
    "sales operations", "sales ops", "growth operations", "growth ops",
    "crm operations", "analista de crm", "crm analyst", "especialista em crm",
    "analista de martech", "martech",
    "analista de integracao de sistemas", "analista de web analytics",
    "analista de performance digital",
]
CARGOS_FORTES = CARGOS_DADOS + CARGOS_OPERACOES

# ---------------------------------------------------------------- filtro nivel 2
# Cargo ambiguo: so aprova com qualificador de dados no mesmo titulo.
CARGOS_AMBIGUOS = [
    "analista", "business analyst", "consultor", "consultora",
    "analista de sistemas", "analista de negocios", "product analyst",
]
QUALIFICADORES = [
    "dado*", "data", "bi", "analytics", "crm", "integrac*", "ops",
    "growth", "inteligencia de mercado", "martech", "midia*", "marketing digital",
]

# ---------------------------------------------------------------- filtro nivel 3
# Ferramenta: so aprova junto com palavra de cargo no titulo.
FERRAMENTAS = [
    # o que ele sustenta em entrevista
    "sql", "python", "pandas", "pyspark", "spark", "databricks", "looker",
    "looker studio", "n8n", "rd station", "pipedrive", "ploomes",
    "google tag manager", "gtm", "ga4", "google analytics", "etl",
    # adjacentes que aparecem nas mesmas vagas
    "power bi", "powerbi", "tableau", "metabase", "airflow", "dbt",
    "bigquery", "snowflake", "redshift", "hubspot", "salesforce", "make.com",
]
PALAVRAS_CARGO = [
    "analista", "engenheir", "desenvolvedor",
    "consultor", "estagi", "assistente", "tecnico",
]

# ---------------------------------------------------------------- bloqueios
# Senioridade acima do alvo em qualquer trilha: descarta.
BLOQUEIO_SENIORIDADE = [
    "senior", "sr", "snr", "coordenador", "coordenadora", "gerente",
    "head", "tech lead", "team lead", "principal", "staff", "diretor",
    "director", "supervisor", "manager", "lider", "leader", "iii", "iv",
    "lead", "coordinator", "vp", "vice president", "chief", "architect",
    "arquiteto", "arquiteta",
]
# So na trilha de dados, e so se o titulo nao aceitar junior ("Junior/Pleno", "Jr/Pl").
# Especialista entra aqui porque na trilha Jr > Pl > Sr > Especialista fica acima de
# senior; em operacoes "Especialista em CRM" e nome de cargo, nao nivel.
BLOQUEIO_PLENO = [
    "pleno", "plena", "pl", "mid-level", "mid level", "midlevel", "mid", "ii",
    "especialista", "specialist",
]
# Expressoes que contem "pl" como palavra mas nao falam de nivel.
EXCECOES_PLENO = ["pl/sql", "pl sql", "pl-sql"]
TERMOS_JUNIOR = ["junior", "jr", "trainee", "estagiario", "estagiaria", "estagio"]

# Vaga afirmativa exclusiva: o candidato nao e elegivel.
# Descarta so quando o grupo vem logo apos a palavra de exclusividade, separado
# apenas por CONECTIVOS_AFIRMATIVA. Isso mantem "exclusivas ou nao para PcD",
# "beneficios exclusivos para colaboradores PcDs" e "incentivamos candidaturas".
TERMOS_EXCLUSIVIDADE = [
    "exclusiva", "exclusivas", "exclusivo", "exclusivos", "exclusivamente",
    "somente", "apenas", "unicamente", "restrita", "restritas", "restrito",
    "afirmativa", "afirmativas",
]
CONECTIVOS_AFIRMATIVA = [
    "para", "a", "as", "ao", "aos", "de", "com", "e", "pessoa", "pessoas",
    "candidata", "candidatas", "candidato", "candidatos", "profissional",
    "profissionais", "publico",
]
GRUPOS_AFIRMATIVOS = [
    "negra", "negras", "negro", "negros", "preta", "pretas", "parda", "pardas",
    "mulher", "mulheres", "pcd", "pcds", "deficiencia", "deficiencias", "deficientes",
    "trans", "transgenero", "transgeneros", "travestis", "50+", "50 anos", "60+",
    "indigena", "indigenas", "lgbt", "lgbtqia+", "lgbtqiapn+",
]
# "nao e exclusiva para PcD" nao e exclusiva.
NEGACOES_AFIRMATIVA = ["nao", "nem"]
# No TITULO a convencao e outra: "Analista CRM Jr - PcD" ou "Vaga Afirmativa" ja
# indica vaga exclusiva, sem a palavra "exclusiva". Vale so para o titulo.
GRUPOS_NO_TITULO = [
    "pcd", "pcds", "pessoa com deficiencia", "pessoas com deficiencia",
    "afirmativa", "afirmativas",
]
RESSALVAS_TITULO = ["tambem", "inclusive", "aberta", "elegivel", "nao exclusiva"]
# Ruido recorrente em board de vaga.
BLOQUEIO_RUIDO = [
    "vendedor", "vendedora", "comercial externo", "representante", "caixa",
    "atendente", "auxiliar de limpeza", "motorista", "enfermeir", "professor",
    "recepcionista", "estoquista", "soldador", "torneiro", "operador de maquina",
    # na serra gaucha "automacao" e quase sempre industrial, nao de processos
    "automacao industrial", "clp", "pcp", "manutencao", "eletricista",
    "seguranca do trabalho", "contabil", "fiscal", "juridico", "rh",
    # dev puro nao e o alvo
    "front-end", "frontend", "mobile", "ios", "android", "unity", "qa",
    # machine learning saiu do escopo. So no titulo: ML citado na descricao de
    # vaga de analista nao bloqueia.
    "machine learning engineer", "ml engineer", "engenheiro de machine learning",
    "engenheira de machine learning", "cientista de dados", "data scientist",
    "deep learning", "visao computacional", "computer vision", "nlp engineer", "mlops",
]

# ---------------------------------------------------------------- localizacao
# Regra: remoto em qualquer lugar do Brasil, ou qualquer modalidade em CIDADES_REGIAO.
# Hibrido ou presencial fora da regiao (Porto Alegre inclusive) e descartado.
TERMOS_REMOTO = ["remoto", "remote", "home office", "anywhere", "100% remoto"]
TERMOS_HIBRIDO = ["hibrido", "hibrida", "hybrid", "semipresencial", "semi-presencial"]
# Fontes internacionais usam o campo de local para a RESTRICAO geografica
# ("USA Only", "Europe"). So interessa o que alcanca o Brasil.
# Expressoes que realmente indicam trabalho remoto no corpo do anuncio.
# "remoto" solto nao serve: aparece em "nao e remoto", "remoto nao disponivel".
SINAIS_REMOTO_DESCRICAO = [
    "100% remoto", "totalmente remoto", "trabalho remoto", "vaga remota",
    "modelo remoto", "home office", "anywhere office", "remote work",
    "fully remote", "trabalho totalmente remoto",
]
# Se o anuncio disser isso, e presencial, mesmo que cite remoto em outro ponto.
SINAIS_PRESENCIAL = [
    "presencial", "no escritorio", "atuacao no local", "on-site", "onsite",
]
# Senioridade declarada no corpo do anuncio, nao no titulo.
SENIORIDADE_DESCRICAO = [
    "vaga senior", "nivel senior", "perfil senior", "senioridade: senior",
    "5+ anos", "mais de 5 anos", "experiencia minima de 5 anos",
    "experiencia minima de 6 anos", "no minimo 5 anos", "acima de 5 anos",
]

REGIOES_ACEITAS = [
    "worldwide", "anywhere", "global", "brazil", "brasil", "latam",
    "latin america", "south america", "americas", "emea/latam",
]
# Caxias do Sul e vizinhas: aqui presencial, hibrido e remoto servem.
CIDADES_REGIAO = [
    "caxias do sul", "farroupilha", "bento goncalves", "flores da cunha",
    "sao marcos", "garibaldi",
]

# ---------------------------------------------------------------- score
PESOS = {
    "cargo_forte": 4,
    "cargo_ambiguo_qualificado": 3,
    "ferramenta_com_cargo": 2,
    "ferramenta_no_texto": 1,     # ate 3 pontos
    "junior": 2,
    "remoto": 2,
    "cidade_alvo": 1,
}
SCORE_MINIMO_NOTIFICAR = 5      # abaixo disso entra so no resumo
SCORE_ALTA_RELEVANCIA = 8       # notifica na hora

# ---------------------------------------------------------------- fontes
# Termos enviados as APIs de busca.
TERMOS_BUSCA = [
    "analista de dados",
    "engenheiro de dados",
    "analista de BI",
    "analytics",
    "marketing operations",
    "revenue operations",
    "analista de CRM",
    "analista de integracao",
]
PAIS_ADZUNA = "br"
# Himalayas e em ingles: termos proprios, 20 vagas por termo, uma chamada cada.
TERMOS_BUSCA_EN = [
    "data analyst", "data engineer", "business intelligence", "analytics",
    "crm", "marketing operations", "revenue operations", "marketing automation",
]
PAGINAS_ADZUNA = 2      # 50 vagas por pagina, por termo: 16 chamadas por ciclo no maximo
PAGINAS_GUPY = 2        # 100 vagas por pagina, por termo de busca

# Empresas com job board publico (Greenhouse / Lever / Ashby).
# Formato: (plataforma, slug_da_empresa)
BOARDS = [
    # ("greenhouse", "nomedaempresa"),
    # ("lever", "nomedaempresa"),
    # ("ashby", "nomedaempresa"),
]

DIAS_MAX_ANUNCIO = 10   # descarta anuncio mais velho que isso
EXIGIR_DATA = True      # sem data de publicacao, descarta: quase sempre e anuncio antigo


# ---------------------------------------------------------------- triagem por IA
USAR_IA = True                     # liga a segunda triagem por LLM
MODELO_IA = "gemini-flash-latest"    # apelido do Flash atual: nao quebra quando o Google aposenta versao
MODELO_IA_RESERVA = "gemini-flash-lite-latest"  # usado se o principal estiver sobrecarregado
# Se a IA nao responder, a vaga espera o proximo ciclo em vez de ir so pela regra.
# Sem isso, uma queda do Gemini manda de uma vez tudo o que a IA teria cortado.
ADIAR_SE_IA_FALHAR = True
# Repescagem: vaga cujo titulo nao bate com nenhum cargo, mas que passou em todos os
# bloqueios rigidos (senioridade, local, data, afirmativa, area), vai para a IA ler a
# descricao. Pega titulo vago que esconde o trabalho dele. Teto por ciclo para nao
# sobrecarregar a cota; o excedente fica para o ciclo seguinte.
REPESCAGEM = True
MAX_REPESCAGEM = 80
DESCRICAO_IA = 1200                  # caracteres da descricao enviados a IA, por vaga
MAX_VAGAS_IA = 40                    # vagas por chamada; acima disso vira mais de um lote
