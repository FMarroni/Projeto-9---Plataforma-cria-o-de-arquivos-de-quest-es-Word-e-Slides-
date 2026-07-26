import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BACKEND_DIR)

TEMPLATES_DIR = os.path.join(ROOT_DIR, "templates")
LISTA_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "lista.docx")
COMENTADA_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "comentada.docx")
SLIDES_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "slides.pptx")
RASTREABILIDADE_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "rastreabilidade.docx")
TEMPLATE_PATHS = (
    LISTA_TEMPLATE_PATH,
    COMENTADA_TEMPLATE_PATH,
    SLIDES_TEMPLATE_PATH,
    RASTREABILIDADE_TEMPLATE_PATH,
)

OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
SESSIONS_DIR = os.path.join(OUTPUT_DIR, "sessions")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

# Fonte Montserrat (mesma família do corpo dos slides, ver
# scripts/build_templates.py FONTE_UI_PPTX) — instâncias estáticas OFL
# distribuídas com o projeto, usadas por app/pptx_layout.py para medir
# largura de texto com a MESMA fonte gravada no PPTX (ver assets/fonts/Montserrat/NOTICE.txt).
FONTS_DIR = os.path.join(ROOT_DIR, "assets", "fonts")
MONTSERRAT_FONTS_DIR = os.path.join(FONTS_DIR, "Montserrat")

# Prompt "Coruj.IA" (comentário de questões) customizável pelo usuário via UI —
# ver app/prompt_store.py. Fica fora de output/ (que é limpo automaticamente).
CONFIG_DIR = os.path.join(ROOT_DIR, "config")
PROMPT_CORUJIA_CUSTOMIZADO_PATH = os.path.join(CONFIG_DIR, "prompt_corujia.txt")

# Épico 4 — Módulo Biblioteca (RAG): base de conhecimento opcional (PDFs de
# aula) usada para fundamentar os comentários em "Modo Restrito" — ver
# app/rag.py. Fica fora de output/ (que é limpo automaticamente) porque é uma
# base persistente do usuário, não um artefato de uma análise específica.
BIBLIOTECA_DIR = os.path.join(ROOT_DIR, "biblioteca")
BIBLIOTECA_PDFS_DIR = os.path.join(BIBLIOTECA_DIR, "pdfs")
BIBLIOTECA_METADATA_PATH = os.path.join(BIBLIOTECA_DIR, "biblioteca.json")
VECTOR_DB_DIR = os.path.join(BIBLIOTECA_DIR, "vector_db")

RAG_TOP_K = 5  # nº de trechos recuperados por questão no Modo Restrito

MAX_UPLOAD_MB = 15
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

PROVIDERS_VALIDOS = ("openai", "anthropic", "gemini", "fake")

# Limpeza automática de sessões/arquivos expirados (ver session_store.limpar_expirados)
SESSAO_TTL_HORAS = 48
LIMPEZA_INTERVALO_SEGUNDOS = 3600  # roda a cada hora
