"""Gera o relatório de análise agregada (Curva ABC, incidência por disciplina/
assunto) como um arquivo .html autocontido — substitui o antigo analise.docx."""

import html
import os

from app.analysis import build_disciplinas_stats, formatar_anos
from app.schemas import DisciplinaStats, ExtractionResult

_CSS = """
:root{color-scheme:light dark;--bg:#f4f2fa;--card:#ffffff;--text:#221c33;--muted:#6a6178;
--accent:#6a4a9c;--accent-dark:#4f3576;--border:#ddd6ea;--destaque:#fce8b2;--destaque-text:#6b5416;}
@media (prefers-color-scheme:dark){:root{--bg:#17141f;--card:#221e2d;--text:#ece8f5;--muted:#a79fbb;
--accent:#b79bde;--accent-dark:#d5c2f2;--border:#362f47;--destaque:#4a3d1f;--destaque-text:#f0d488;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
padding:2.5rem 1rem;}
.container{max-width:56rem;margin:0 auto;}
.card{background:var(--card);border:1px solid var(--border);border-radius:0.75rem;padding:2rem;margin-bottom:1.5rem;}
h1{color:var(--accent-dark);margin-top:0;}
h2{color:var(--accent-dark);border-bottom:1px solid var(--border);padding-bottom:0.5rem;}
.meta{color:var(--muted);font-size:0.95rem;}
table{width:100%;border-collapse:collapse;margin-top:1rem;font-size:0.92rem;}
th,td{text-align:left;padding:0.5rem 0.6rem;border-bottom:1px solid var(--border);}
th{color:var(--accent-dark);}
tr.destaque td{background:var(--destaque);color:var(--destaque-text);}
.barra-container{background:var(--border);border-radius:0.25rem;height:0.6rem;width:100%;overflow:hidden;}
.barra{background:var(--accent);height:100%;}
.curva-abc{font-weight:600;margin-top:0.75rem;}
.resumo-lista{list-style:none;padding:0;margin:0;}
.resumo-lista li{padding:0.35rem 0;border-bottom:1px dashed var(--border);}
"""


def _linha_assunto(assunto) -> str:
    destaque = " destaque" if assunto.destaque_curva_abc else ""
    pct = f"{assunto.incidencia * 100:.2f}".replace(".", ",")
    return (
        f'<tr class="{destaque.strip()}">'
        f"<td>{html.escape(assunto.assunto)}</td>"
        f"<td>{assunto.n_questoes}</td>"
        f'<td><div class="barra-container"><div class="barra" style="width:{assunto.incidencia * 100:.1f}%"></div></div>'
        f"{pct}%</td></tr>"
    )


def _secao_disciplina(disciplina: DisciplinaStats) -> str:
    linhas = "\n".join(_linha_assunto(a) for a in disciplina.assuntos)
    return f"""
    <div class="card">
      <h2>{html.escape(disciplina.nome)}</h2>
      <p class="meta">Total de questões: {disciplina.total_questoes} &middot;
        Bancas: {html.escape(', '.join(disciplina.bancas) or 'N/A')} &middot;
        Anos: {html.escape(formatar_anos(disciplina.anos))}</p>
      <p class="curva-abc">Curva ABC (primeiros ~50% de incidência):
        {html.escape(disciplina.curva_abc_texto)} — {disciplina.curva_abc_percentual}</p>
      <table>
        <thead><tr><th>Assunto</th><th>Nº Questões</th><th>Incidência</th></tr></thead>
        <tbody>{linhas}</tbody>
      </table>
    </div>"""


def gerar_html(extraction: ExtractionResult, saida_path: str) -> str:
    disciplinas = build_disciplinas_stats(extraction)
    total_geral = sum(d.total_questoes for d in disciplinas)

    resumo_itens = "\n".join(
        f"<li>{html.escape(d.nome)}: {d.total_questoes} questões "
        f"({html.escape(', '.join(d.bancas) or 'N/A')}, {html.escape(formatar_anos(d.anos))})</li>"
        for d in disciplinas
    )
    secoes = "\n".join(_secao_disciplina(d) for d in disciplinas)

    nome_concurso = html.escape(extraction.nome_concurso or "Concurso")
    cargos = html.escape(", ".join(extraction.cargos) or "N/A")
    bancas = html.escape(", ".join(extraction.bancas) or "N/A")

    documento = f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Análise — {nome_concurso}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">
  <div class="card">
    <h1>{nome_concurso}</h1>
    <p class="meta">Cargo: {cargos} &middot; Banca: {bancas}</p>
    <h2>Resumo da Análise</h2>
    <p>Total de questões analisadas: <strong>{total_geral}</strong></p>
    <ul class="resumo-lista">{resumo_itens}</ul>
  </div>
  {secoes}
</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(saida_path), exist_ok=True)
    with open(saida_path, "w", encoding="utf-8") as f:
        f.write(documento)
    return saida_path
