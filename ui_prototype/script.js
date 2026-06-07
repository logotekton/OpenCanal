const stage = document.querySelector(".stage");
const replay = document.querySelector("#replay");
const submit = document.querySelector(".submit");

function openRoom() {
  stage.classList.remove("is-opening");
  window.setTimeout(() => stage.classList.add("is-opening"), 80);
}

submit.addEventListener("click", openRoom);
replay.addEventListener("click", openRoom);

window.setTimeout(openRoom, 700);
