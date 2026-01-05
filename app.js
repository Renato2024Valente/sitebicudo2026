// ================================
// CONFIGURAÇÕES
// ================================
const GESTAO_PASSWORD = "bicudo1243##@";

// COLOQUE AQUI o link da sua ATA DIGITAL quando estiver pronto:
const ATA_DIGITAL_URL = "https://SUA-ATA-DIGITAL.onrender.com/";

// ================================
// LÓGICA
// ================================
const modalEl = document.getElementById("modalGestao");
const modal = new bootstrap.Modal(modalEl);

const passInput = document.getElementById("gestaoPass");
const errBox = document.getElementById("gestaoErro");
const btnConfirm = document.getElementById("confirmGestao");

function openGestaoModal() {
  errBox.classList.add("d-none");
  passInput.value = "";
  modal.show();
  setTimeout(() => passInput.focus(), 200);
}

function validateAndOpen() {
  const typed = (passInput.value || "").trim();
  if (typed !== GESTAO_PASSWORD) {
    errBox.classList.remove("d-none");
    passInput.focus();
    passInput.select();
    return;
  }

  // OK
  errBox.classList.add("d-none");
  modal.hide();

  // Toast
  const toast = new bootstrap.Toast(document.getElementById("toastOk"), { delay: 2200 });
  toast.show();

  // abre em nova aba
  setTimeout(() => window.open(ATA_DIGITAL_URL, "_blank", "noopener"), 450);
}

// Botões que chamam Gestão
["btnGestao", "btnGestao2", "btnGestao3"].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("click", openGestaoModal);
});

// Confirmar senha
btnConfirm.addEventListener("click", validateAndOpen);

// Enter no campo senha
passInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") validateAndOpen();
});

// Tema (light/dark) simples
const btnTheme = document.getElementById("btnTheme");
btnTheme.addEventListener("click", () => {
  const html = document.documentElement;
  const current = html.getAttribute("data-bs-theme") || "light";
  html.setAttribute("data-bs-theme", current === "light" ? "dark" : "light");
});
