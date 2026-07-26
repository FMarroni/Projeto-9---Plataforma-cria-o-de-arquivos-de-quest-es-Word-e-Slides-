"""Provider de desenvolvimento — não chama nenhuma IA real. Usado para validar
o pipeline (paginação, duplicação de slide, tabelas, templates) sem gastar
chamadas de API. Ativado via `provider=fake` no form (não requer api_key)."""

import re

from app.llm.base import LLMProvider
from app.schemas import Alternativa, ExtractionResult, Questao

# Presença de "[RASTREABILIDADE]" no system_prompt é o sinal estável de que o
# Modo Restrito (RAG) está ativo — ver app.prompts.build_prompt_rag(), que é o
# único lugar que injeta esse marcador no prompt de sistema.
_MARCADOR_MODO_RESTRITO = "[RASTREABILIDADE]"

_PADRAO_TRECHO = re.compile(r"\[TRECHO \d+ — arquivo: (.*?), página (.*?)\]")
_PADRAO_ALTERNATIVA = re.compile(r"^([a-eA-E])\) ", re.M)


class FakeProvider(LLMProvider):
    async def extrair(
        self,
        texto: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> ExtractionResult:
        return ExtractionResult(
            nome_concurso=None,
            escolaridade=None,
            bancas=["CEBRASPE (CESPE)", "FGV", "VUNESP"],
            anos=[2014, 2023, 2024, 2025],
            cargos=["AFT (SEFAZ SE)", "Pesq Ini (SUSAM)", "Esc (TJ SP)"],
            questoes=[
                Questao(
                    numero=1,
                    id_tec="3639467",
                    banca="CEBRASPE (CESPE)",
                    orgao="SEFAZ SE",
                    sub_orgao="Geral",
                    cargo="AFT (SEFAZ SE)",
                    ano=2025,
                    materia="Estatística",
                    assunto="Questões Mescladas de Medidas de Posição",
                    enunciado=(
                        "[IMAGEM_01]\n"
                        "Considerando os dados apresentados na tabela precedente, relativos à "
                        "arrecadação de ISS de cinco municípios em determinado mês, assinale a "
                        "opção que apresenta uma interpretação correta das medidas descritivas "
                        "da amostra (média $\\mu$, mediana e desvio padrão $\\sigma$), sabendo que "
                        "$$\\sigma = \\sqrt{\\frac{1}{n}\\sum_{i=1}^{n}(x_i-\\mu)^2}$$."
                    ),
                    alternativas=[
                        Alternativa(letra="a", texto="A mediana da amostra é menor que a sua média."),
                        Alternativa(letra="b", texto="A média e a mediana da amostra são iguais."),
                        Alternativa(letra="c", texto="O desvio padrão baixo indica dados muito dispersos."),
                        Alternativa(letra="d", texto="A média é de aproximadamente R$ 16,1 milhões."),
                        Alternativa(letra="e", texto="O desvio padrão elevado sugere homogeneidade."),
                    ],
                    gabarito="A",
                    anulada=False,
                ),
                Questao(
                    numero=2,
                    id_tec="1694284",
                    banca="FGV",
                    orgao="SUSAM",
                    sub_orgao=None,
                    cargo="Pesq Ini (SUSAM)",
                    ano=2014,
                    materia="Estatística",
                    assunto="Formas Gráficas de Apresentação de Dados Agrupados em Classes",
                    enunciado=(
                        "A figura a seguir é uma representação gráfica adequada para apresentar a "
                        "distribuição de uma variável quantitativa contínua.\n[IMAGEM_02]\nEsta "
                        "representação gráfica denomina-se:"
                    ),
                    alternativas=[
                        Alternativa(letra="a", texto="gráfico de setores."),
                        Alternativa(letra="b", texto="box plot."),
                        Alternativa(letra="c", texto="diagrama de dispersão."),
                        Alternativa(letra="d", texto="polígono de frequências."),
                        Alternativa(letra="e", texto="histograma."),
                    ],
                    gabarito="E",
                    anulada=False,
                ),
                Questao(
                    numero=3,
                    id_tec="3067863",
                    banca="VUNESP",
                    orgao="TJ SP",
                    sub_orgao=None,
                    cargo="Esc (TJ SP)",
                    ano=2024,
                    materia="Direito Penal",
                    assunto="Crimes contra a Administração da Justiça",
                    enunciado="A respeito dos crimes contra a administração pública, assinale a alternativa correta.",
                    alternativas=[
                        Alternativa(letra="a", texto="Caio incorre no crime de denunciação caluniosa."),
                        Alternativa(letra="b", texto="Mévio será processado mediante ação penal condicionada."),
                        Alternativa(letra="c", texto="Caio e Tício incorrem no crime de falso testemunho."),
                        Alternativa(letra="d", texto="Tício incorre no crime de autoacusação falsa."),
                        Alternativa(letra="e", texto="Tício incorre no crime de condescendência criminosa."),
                    ],
                    gabarito=None,
                    anulada=True,
                ),
                Questao(
                    numero=4,
                    id_tec="2472174",
                    banca="VUNESP",
                    orgao="TJ SP",
                    sub_orgao=None,
                    cargo="Esc (TJ SP)",
                    ano=2023,
                    materia="Direito Penal",
                    assunto="Desobediência a Decisão Judicial sobre Perda ou Suspensão de Direito",
                    enunciado="Mévio continua participando das reuniões do conselho. Assinale a alternativa correta.",
                    alternativas=[
                        Alternativa(letra="a", texto="Mévio não incorreu em qualquer crime."),
                        Alternativa(letra="b", texto="Mévio incorreu no crime de fraude processual."),
                        Alternativa(letra="c", texto="Mévio praticou o crime do artigo 359 do CP."),
                        Alternativa(letra="d", texto="Mévio praticou o crime de desobediência."),
                        Alternativa(letra="e", texto="Mévio praticou o crime de usurpação de função pública."),
                    ],
                    gabarito="C",
                    anulada=False,
                ),
            ],
        )

    async def comentar(
        self,
        system_prompt: str,
        user_message: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> str:
        sufixo = f" (com {len(imagens)} imagem(ns) anexada(s))" if imagens else ""

        if _MARCADOR_MODO_RESTRITO in system_prompt:
            return self._comentar_rag_fake(user_message, sufixo)

        return (
            "[comentário de teste — fake_provider] Comentário gerado localmente para validar "
            f"o encaixe no slide, sem chamar nenhuma IA real{sufixo}."
        )

    def _comentar_rag_fake(self, user_message: str, sufixo: str) -> str:
        """Simula uma resposta em Modo Restrito (formato [COMENTARIO]/
        [RASTREABILIDADE]/[FIM]) citando o primeiro trecho recebido — permite
        testar o pipeline de RAG (incluindo rastreabilidade.docx) sem gastar
        chamada de IA real, tanto quanto o restante do FakeProvider."""
        primeiro_trecho = _PADRAO_TRECHO.search(user_message)
        arquivo, pagina = primeiro_trecho.groups() if primeiro_trecho else ("fonte_fake.pdf", "1")

        identificadores = _PADRAO_ALTERNATIVA.findall(user_message) or ["PRINCIPAL"]

        linhas_comentario = [
            f"({letra.lower()}) [teste — fake_provider] Fundamentado no material de apoio{sufixo}."
            if letra != "PRINCIPAL"
            else f"[teste — fake_provider] Fundamentado no material de apoio{sufixo}."
            for letra in identificadores
        ]
        linhas_rastreabilidade = [
            f"{letra}: arquivo={arquivo}; pagina={pagina}" for letra in identificadores
        ]

        return (
            "[COMENTARIO]\n"
            + "\n".join(linhas_comentario)
            + "\n[RASTREABILIDADE]\n"
            + "\n".join(linhas_rastreabilidade)
            + "\n[FIM]\n"
        )
