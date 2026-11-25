// todo.json を読み込んで一覧表示する
async function render() {
  const res = await fetch("../todo.json");
  const tasks = await res.json();
  const list = document.getElementById("tasks");
  for (const task of tasks) {
    const li = document.createElement("li");
    li.textContent = `${task.done ? "✅" : "⬜"} ${task.title}`;
    list.appendChild(li);
  }
}

render();
