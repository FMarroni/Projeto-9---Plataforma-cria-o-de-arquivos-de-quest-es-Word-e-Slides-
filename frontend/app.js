// --- Abas (Nova análise / Retomar sessão) ---
const abas = document.querySelectorAll(".aba");
const paineis = document.querySelectorAll(".painel-aba");

abas.forEach((aba) => {
  aba.addEventListener("click", () => {
    abas.forEach((a) => a.classList.remove("ativa"));
    aba.classList.add("ativa");
    const alvo = aba.dataset.aba;
    paineis.forEach((p) => p.classList.toggle("oculto", p.dataset.painel !== alvo));
    if (alvo === "prompt") carregarPromptComentario();
    if (alvo === "biblioteca") carregarBiblioteca();
  });
});

// --- Persistência de preferências (localStorage) ---
const providerEl = document.getElementById("provider");
const apiKeyEl = document.getElementById("api_key");
const modelEl = document.getElementById("model");
const toggleIaEl = document.getElementById("toggle-ia");
const toggleIaTituloEl = document.getElementById("toggle-ia-titulo");
const toggleIaDescricaoEl = document.getElementById("toggle-ia-descricao");
const secaoIaEl = document.getElementById("secao-ia");
const secaoBibliotecaSelecaoEl = document.getElementById("secao-biblioteca-selecao");

const STORAGE_PROVIDER = "tec_provider";
const STORAGE_API_KEY = "tec_api_key";
const STORAGE_MODEL = "tec_model";
const STORAGE_MODO = "tec_modo";

const DESCRICAO_COM_IA = "Gera os 4 arquivos com o comentário de cada questão — requer chave de API.";
const DESCRICAO_SEM_IA = "Só formata lista/comentada/análise/slides a partir do PDF — sem chave de API, sem custo.";

function modoSelecionado() {
  return toggleIaEl.checked ? "ia" : "script";
}

// Com a IA desligada, não faz sentido pedir provedor/chave/modelo nem Modo
// Restrito (RAG é feito pela IA) — esconder evita confundir o usuário
// pedindo informação que esse caminho não precisa.
function atualizarVisibilidadeModo() {
  const semIa = !toggleIaEl.checked;
  secaoIaEl.classList.toggle("oculto", semIa);
  secaoBibliotecaSelecaoEl.classList.toggle("oculto", semIa);
  toggleIaTituloEl.textContent = semIa ? "Sem IA" : "Comentários com IA";
  toggleIaDescricaoEl.textContent = semIa ? DESCRICAO_SEM_IA : DESCRICAO_COM_IA;
}

function restaurarPreferencias() {
  const provider = localStorage.getItem(STORAGE_PROVIDER);
  const apiKey = localStorage.getItem(STORAGE_API_KEY);
  const model = localStorage.getItem(STORAGE_MODEL);
  const modo = localStorage.getItem(STORAGE_MODO);
  if (provider) providerEl.value = provider;
  if (apiKey) apiKeyEl.value = apiKey;
  if (model) modelEl.value = model;
  if (modo) toggleIaEl.checked = modo === "ia";
  atualizarVisibilidadeModo();
}

function salvarPreferencias() {
  localStorage.setItem(STORAGE_PROVIDER, providerEl.value);
  localStorage.setItem(STORAGE_API_KEY, apiKeyEl.value);
  localStorage.setItem(STORAGE_MODEL, modelEl.value);
  localStorage.setItem(STORAGE_MODO, modoSelecionado());
}

restaurarPreferencias();
providerEl.addEventListener("change", salvarPreferencias);
apiKeyEl.addEventListener("change", salvarPreferencias);
modelEl.addEventListener("change", salvarPreferencias);
toggleIaEl.addEventListener("change", () => {
  atualizarVisibilidadeModo();
  salvarPreferencias();
});

// --- Console estilo terminal ---
const terminalContainer = document.getElementById("terminal-container");
const terminalEl = document.getElementById("terminal");

function limparTerminal() {
  terminalEl.textContent = "";
  terminalContainer.classList.remove("oculto");
}

function logTerminal(linha, tipo = "info") {
  const prefixo = { info: "$", aviso: "!", erro: "x", concluido: ">" }[tipo] || "$";
  terminalEl.textContent += `${prefixo} ${linha}\n`;
  terminalEl.scrollTop = terminalEl.scrollHeight;
}

// --- Consumo de SSE via fetch + ReadableStream (o endpoint é POST, EventSource nativo só faz GET) ---
async function consumirSSE(resp, onEvento) {
  if (!resp.ok) {
    const texto = await resp.text().catch(() => "");
    let detalhe = `Erro ${resp.status}`;
    try {
      detalhe = JSON.parse(texto).detail || detalhe;
    } catch {
      /* corpo não era JSON */
    }
    throw new Error(detalhe);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // sse-starlette usa "\r\n" como separador por padrão — normaliza para "\n"
    // antes de procurar o delimitador de bloco, senão "\n\n" nunca é encontrado.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    let indiceBloco;
    while ((indiceBloco = buffer.indexOf("\n\n")) !== -1) {
      const bloco = buffer.slice(0, indiceBloco);
      buffer = buffer.slice(indiceBloco + 2);

      let evento = "message";
      let dados = "";
      for (const linha of bloco.split("\n")) {
        if (linha.startsWith("event:")) evento = linha.slice(6).trim();
        else if (linha.startsWith("data:")) dados += linha.slice(5).trim();
      }
      if (dados) {
        try {
          onEvento(evento, JSON.parse(dados));
        } catch {
          onEvento(evento, { mensagem: dados });
        }
      }
    }
  }
}

function mostrarResultado(dados) {
  document.getElementById("total-questoes").textContent = `${dados.total_questoes} questões processadas.`;
  document.getElementById("session-id-exibido").textContent = dados.session_id;
  document.getElementById("link-lista").href = dados.lista_url;
  document.getElementById("link-comentada").href = dados.comentada_url;
  document.getElementById("link-analise").href = dados.analise_url;
  document.getElementById("link-slides").href = dados.slides_url;

  const linkRastreabilidade = document.getElementById("link-rastreabilidade");
  if (dados.rastreabilidade_url) {
    linkRastreabilidade.href = dados.rastreabilidade_url;
    linkRastreabilidade.classList.remove("oculto");
  } else {
    linkRastreabilidade.classList.add("oculto");
  }

  document.getElementById("resultado").classList.remove("oculto");
}

function tratarEvento(evento, dados) {
  if (evento === "erro") {
    logTerminal(dados.mensagem, "erro");
    if (dados.session_id) {
      logTerminal(`Sessão salva: ${dados.session_id} — use "Retomar sessão" para continuar depois.`, "aviso");
    }
  } else if (evento === "aviso") {
    logTerminal(dados.mensagem, "aviso");
  } else if (evento === "concluido") {
    logTerminal("Concluído!", "concluido");
    mostrarResultado(dados);
  } else {
    logTerminal(dados.mensagem, "info");
  }
}

// --- Formulário: nova análise ---
const formGerar = document.getElementById("form-gerar");
const btnEnviar = document.getElementById("btn-enviar");
const pdfEl = document.getElementById("pdf");

formGerar.addEventListener("submit", async (event) => {
  event.preventDefault();
  salvarPreferencias();
  document.getElementById("resultado").classList.add("oculto");
  limparTerminal();

  if (!pdfEl.files.length) {
    logTerminal("Selecione um arquivo PDF.", "erro");
    return;
  }

  const modo = modoSelecionado();
  const formData = new FormData();
  formData.append("pdf", pdfEl.files[0]);
  formData.append("modo", modo);

  if (modo === "script") {
    logTerminal("Modo Sem Comentários (sem IA) — nenhuma chave de API será usada.");
  } else {
    formData.append("provider", providerEl.value);
    formData.append("api_key", apiKeyEl.value);
    if (modelEl.value) formData.append("model", modelEl.value);

    const docsSelecionados = document.querySelectorAll(
      '#lista-biblioteca-selecao input[type="checkbox"]:checked'
    );
    docsSelecionados.forEach((cb) => formData.append("documentos_biblioteca", cb.value));
    if (docsSelecionados.length > 0) {
      logTerminal(`Modo Restrito (RAG) ativado — ${docsSelecionados.length} material(is) de apoio selecionado(s).`);
    }
  }

  btnEnviar.disabled = true;
  logTerminal("Enviando PDF...");

  try {
    const resp = await fetch("/api/gerar/stream", { method: "POST", body: formData });
    await consumirSSE(resp, tratarEvento);
  } catch (err) {
    logTerminal(`Falha de comunicação com o servidor: ${err.message}`, "erro");
  } finally {
    btnEnviar.disabled = false;
  }
});

// --- Formulário: retomar sessão ---
const formRetomar = document.getElementById("form-retomar");
const btnRetomar = document.getElementById("btn-retomar");

formRetomar.addEventListener("submit", async (event) => {
  event.preventDefault();
  document.getElementById("resultado").classList.add("oculto");
  limparTerminal();

  const sessionId = document.getElementById("session_id").value.trim();
  const apiKeyRetomar = document.getElementById("api_key_retomar").value;

  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("api_key", apiKeyRetomar);

  btnRetomar.disabled = true;
  logTerminal(`Retomando sessão ${sessionId}...`);

  try {
    const resp = await fetch("/api/retomar/stream", { method: "POST", body: formData });
    await consumirSSE(resp, tratarEvento);
  } catch (err) {
    logTerminal(`Falha de comunicação com o servidor: ${err.message}`, "erro");
  } finally {
    btnRetomar.disabled = false;
  }
});

// --- Aba: prompt de comentários (Coruj.IA) ---
const promptTextarea = document.getElementById("prompt-comentario");
const promptStatusEl = document.getElementById("prompt-status");
const btnSalvarPrompt = document.getElementById("btn-salvar-prompt");
const btnRestaurarPrompt = document.getElementById("btn-restaurar-prompt");
let promptJaCarregado = false;

function mostrarStatusPrompt(customizado) {
  promptStatusEl.textContent = customizado
    ? "Prompt customizado (salvo localmente)."
    : "Usando o prompt padrão.";
}

async function carregarPromptComentario() {
  if (promptJaCarregado) return;
  try {
    const resp = await fetch("/api/prompt/comentario");
    if (!resp.ok) throw new Error(`Erro ${resp.status}`);
    const dados = await resp.json();
    promptTextarea.value = dados.prompt;
    mostrarStatusPrompt(dados.customizado);
    promptJaCarregado = true;
  } catch (err) {
    promptStatusEl.textContent = `Falha ao carregar o prompt: ${err.message}`;
  }
}

btnSalvarPrompt.addEventListener("click", async () => {
  btnSalvarPrompt.disabled = true;
  try {
    const resp = await fetch("/api/prompt/comentario", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptTextarea.value }),
    });
    if (!resp.ok) {
      const texto = await resp.text().catch(() => "");
      let detalhe = `Erro ${resp.status}`;
      try {
        detalhe = JSON.parse(texto).detail || detalhe;
      } catch {
        /* corpo não era JSON */
      }
      throw new Error(detalhe);
    }
    const dados = await resp.json();
    mostrarStatusPrompt(dados.customizado);
  } catch (err) {
    promptStatusEl.textContent = `Falha ao salvar: ${err.message}`;
  } finally {
    btnSalvarPrompt.disabled = false;
  }
});

btnRestaurarPrompt.addEventListener("click", async () => {
  btnRestaurarPrompt.disabled = true;
  try {
    const resp = await fetch("/api/prompt/comentario", { method: "DELETE" });
    if (!resp.ok) throw new Error(`Erro ${resp.status}`);
    const dados = await resp.json();
    promptTextarea.value = dados.prompt;
    mostrarStatusPrompt(dados.customizado);
  } catch (err) {
    promptStatusEl.textContent = `Falha ao restaurar padrão: ${err.message}`;
  } finally {
    btnRestaurarPrompt.disabled = false;
  }
});

// --- Aba: Biblioteca (Épico 4 — Módulo Biblioteca / RAG) ---
const listaGerenciarEl = document.getElementById("lista-biblioteca-gerenciar");
const listaSelecaoEl = document.getElementById("lista-biblioteca-selecao");
const bibliotecaStatusEl = document.getElementById("biblioteca-status");
const formUploadBiblioteca = document.getElementById("form-upload-biblioteca");
const btnUploadBiblioteca = document.getElementById("btn-upload-biblioteca");
const pdfBibliotecaEl = document.getElementById("pdf-biblioteca");

let bibliotecaCache = null;

function _linhaBiblioteca(doc, { comCheckbox }) {
  const item = document.createElement("div");
  item.className = "item-biblioteca";

  if (comCheckbox) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = doc.doc_id;
    label.appendChild(checkbox);
    const spanNome = document.createElement("span");
    spanNome.className = "nome-arquivo";
    spanNome.textContent = doc.nome_arquivo;
    label.appendChild(spanNome);
    item.appendChild(label);
  } else {
    const spanNome = document.createElement("span");
    spanNome.className = "nome-arquivo";
    spanNome.textContent = doc.nome_arquivo;
    item.appendChild(spanNome);
  }

  const spanInfo = document.createElement("span");
  spanInfo.className = "info-paginas";
  spanInfo.textContent = `${doc.n_paginas} pág.`;
  item.appendChild(spanInfo);

  if (!comCheckbox) {
    const btnExcluir = document.createElement("button");
    btnExcluir.type = "button";
    btnExcluir.className = "btn-excluir-biblioteca";
    btnExcluir.textContent = "Excluir";
    btnExcluir.addEventListener("click", () => excluirDocumentoBiblioteca(doc.doc_id));
    item.appendChild(btnExcluir);
  }

  return item;
}

function _renderizarListas() {
  const documentos = bibliotecaCache || [];

  listaSelecaoEl.innerHTML = "";
  if (documentos.length === 0) {
    listaSelecaoEl.innerHTML = '<p class="meta">Nenhum material na biblioteca ainda — envie PDFs na aba "Biblioteca".</p>';
  } else {
    documentos.forEach((doc) => listaSelecaoEl.appendChild(_linhaBiblioteca(doc, { comCheckbox: true })));
  }

  listaGerenciarEl.innerHTML = "";
  if (documentos.length === 0) {
    listaGerenciarEl.innerHTML = '<p class="meta">Nenhum PDF enviado ainda.</p>';
  } else {
    documentos.forEach((doc) => listaGerenciarEl.appendChild(_linhaBiblioteca(doc, { comCheckbox: false })));
  }
}

async function carregarBiblioteca() {
  try {
    const resp = await fetch("/api/biblioteca");
    if (!resp.ok) throw new Error(`Erro ${resp.status}`);
    const dados = await resp.json();
    bibliotecaCache = dados.documentos;
    _renderizarListas();
    bibliotecaStatusEl.textContent = "";
  } catch (err) {
    listaGerenciarEl.innerHTML = "";
    listaSelecaoEl.innerHTML = "";
    bibliotecaStatusEl.textContent = `Falha ao carregar a biblioteca: ${err.message}`;
  }
}

async function excluirDocumentoBiblioteca(docId) {
  try {
    const resp = await fetch(`/api/biblioteca/${docId}`, { method: "DELETE" });
    if (!resp.ok) throw new Error(`Erro ${resp.status}`);
    bibliotecaStatusEl.textContent = "Documento excluído.";
    await carregarBiblioteca();
  } catch (err) {
    bibliotecaStatusEl.textContent = `Falha ao excluir: ${err.message}`;
  }
}

formUploadBiblioteca.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!pdfBibliotecaEl.files.length) {
    bibliotecaStatusEl.textContent = "Selecione um arquivo PDF.";
    return;
  }

  const formData = new FormData();
  formData.append("pdf", pdfBibliotecaEl.files[0]);

  btnUploadBiblioteca.disabled = true;
  bibliotecaStatusEl.textContent = "Enviando e indexando PDF...";

  try {
    const resp = await fetch("/api/biblioteca/upload", { method: "POST", body: formData });
    if (!resp.ok) {
      const texto = await resp.text().catch(() => "");
      let detalhe = `Erro ${resp.status}`;
      try {
        detalhe = JSON.parse(texto).detail || detalhe;
      } catch {
        /* corpo não era JSON */
      }
      throw new Error(detalhe);
    }
    const doc = await resp.json();
    bibliotecaStatusEl.textContent = `"${doc.nome_arquivo}" adicionado à biblioteca (${doc.n_paginas} páginas).`;
    formUploadBiblioteca.reset();
    await carregarBiblioteca();
  } catch (err) {
    bibliotecaStatusEl.textContent = `Falha ao enviar: ${err.message}`;
  } finally {
    btnUploadBiblioteca.disabled = false;
  }
});

carregarBiblioteca();
