import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function getWidget(node, name) {
    return node.widgets?.find(w => w.name === name);
}

function getServerUrl(node) {
    return getWidget(node, "server_url")?.value ?? "http://localhost:8080";
}

async function fetchModels(serverUrl) {
    const resp = await api.fetchApi(`/llama_suite/models?url=${encodeURIComponent(serverUrl)}`);
    if (!resp.ok) throw new Error(`Server responded with ${resp.status}`);
    return await resp.json();
}

async function fetchRunning(serverUrl) {
    const resp = await api.fetchApi(`/llama_suite/running?url=${encodeURIComponent(serverUrl)}`);
    if (!resp.ok) throw new Error(`Server responded with ${resp.status}`);
    return await resp.json();
}

async function doUnload(serverUrl, modelName) {
    const resp = await api.fetchApi(`/llama_suite/unload?url=${encodeURIComponent(serverUrl)}&model=${encodeURIComponent(modelName)}`, {
        method: 'POST'
    });
    return await resp.json();
}

function toast(msg, color = "#333") {
    const el = document.createElement("div");
    el.textContent = msg;
    Object.assign(el.style, {
        position: "fixed", bottom: "30px", right: "30px",
        background: color, color: "#fff",
        padding: "8px 16px", borderRadius: "8px",
        fontSize: "13px", zIndex: "9999",
        boxShadow: "0 2px 8px rgba(0,0,0,.4)",
        transition: "opacity .5s",
    });
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 600); }, 2800);
}

function styledBtn(label, title, color = "#3a7bd5") {
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.title = title;
    Object.assign(btn.style, {
        padding: "4px 10px", margin: "2px",
        borderRadius: "5px", border: "none",
        background: color, color: "#fff",
        cursor: "pointer", fontSize: "12px",
        fontWeight: "bold", lineHeight: "1.4",
    });
    return btn;
}

// Floating picker
function showModelPicker(models, anchorEl, onSelect) {
    document.getElementById("ls_model_picker")?.remove();

    const picker = document.createElement("div");
    picker.id = "ls_model_picker";
    const rect = anchorEl.getBoundingClientRect();
    Object.assign(picker.style, {
        position: "fixed",
        top:  `${rect.bottom + 4}px`,
        left: `${rect.left}px`,
        zIndex: "99999",
        background: "#1e1e2e",
        border: "1px solid #555",
        borderRadius: "8px",
        padding: "6px 0",
        minWidth: "280px",
        maxHeight: "340px",
        overflowY: "auto",
        boxShadow: "0 4px 20px rgba(0,0,0,.7)",
    });

    models.forEach(m => {
        const item = document.createElement("div");
        item.textContent = m;
        Object.assign(item.style, {
            padding: "8px 14px",
            cursor: "pointer",
            color: "#cdd6f4",
            fontSize: "13px",
            whiteSpace: "nowrap",
        });
        item.addEventListener("mouseenter", () => item.style.background = "#313244");
        item.addEventListener("mouseleave", () => item.style.background = "");
        item.addEventListener("click", () => { onSelect(m); picker.remove(); });
        picker.appendChild(item);
    });

    document.body.appendChild(picker);

    setTimeout(() => {
        document.addEventListener("click", function handler(e) {
            if (!picker.contains(e.target)) {
                picker.remove();
                document.removeEventListener("click", handler);
            }
        });
    }, 0);
}

// Сбор параметров запуска с ноды
function getLaunchArgs(node) {
    const port = getWidget(node, "port")?.value;
    const portNum = parseInt(port);
    
    if (isNaN(portNum) || portNum < 1025 || portNum > 65535) {
        throw new Error(`Port must be between 1025 and 65535. Current: ${port}`);
    }

    return {
        llama_path: getWidget(node, "llama_path")?.value || "llama-server",
        models_dir: getWidget(node, "models_dir")?.value || "",
        host: getWidget(node, "host")?.value || "0.0.0.0",
        port: portNum,
        context_length: getWidget(node, "context_length")?.value || 120000,
        flash_attention: getWidget(node, "flash_attention")?.value === true,
        extra_args: getWidget(node, "extra_args")?.value || "",
    };
}

// Проверка статуса и обновление UI
async function checkStatusAndUpdate(node, statusBadge, btnStart, btnStop) {
    const urlVal = getWidget(node, "server_url")?.value ?? "http://localhost:8080";
    
    statusBadge.style.display = "inline-block";
    
    let isOnline = false;
    try {
        // Простая проверка доступности сервера через прямой запрос
        const r = await fetch(`${urlVal}/v1/models`, { method: 'GET', signal: AbortSignal.timeout(1000) });
        isOnline = r.ok;
    } catch (e) {
        isOnline = false;
    }

    if (isOnline) {
        statusBadge.textContent = "🟢 Online";
        statusBadge.style.color = "#4caf50";
        btnStart.style.display = "none"; 
        btnStop.style.display = "inline-block";
    } else {
        statusBadge.textContent = "🔴 Offline";
        statusBadge.style.color = "#f44336";
        btnStart.style.display = "inline-block";
        btnStop.style.display = "none";
    }
}

app.registerExtension({
    name: "LlamaSuite.Client",

    async nodeCreated(node) {
        const isClient = node.comfyClass === "LlamaSuiteClient";
        if (!isClient) return;

        const bar = document.createElement("div");
        Object.assign(bar.style, {
            display: "flex", flexWrap: "wrap",
            padding: "4px 6px", gap: "2px",
            alignItems: "center"
        });

        // Бейдж статуса
        const statusBadge = document.createElement("span");
        statusBadge.style.fontSize = "11px";
        statusBadge.style.marginRight = "6px";
        statusBadge.style.fontWeight = "bold";
        statusBadge.style.display = "none";
        bar.appendChild(statusBadge);

        // 🔄 Fetch Models
        const btnFetch = styledBtn("🔄 Fetch", "Fetch model list");
        btnFetch.addEventListener("click", async () => {
            btnFetch.textContent = "⏳…";
            btnFetch.disabled = true;
            try {
                const data = await fetchModels(getServerUrl(node));
                if (data.status === "ok" && data.models.length > 0) {
                    showModelPicker(data.models, btnFetch, (selectedModelId) => {
                        const w = getWidget(node, "model");
                        if (w) {
                            w.value = selectedModelId;
                            node.setDirtyCanvas(true, true);
                        }
                        toast(`✅ Model set: ${selectedModelId}`, "#2e7d32");
                    });
                } else {
                    toast(`⚠️ ${data.error ?? "No models"}`, "#b71c1c");
                }
            } catch (e) {
                toast(`❌ ${e}`, "#b71c1c");
            } finally {
                btnFetch.textContent = "🔄 Fetch";
                btnFetch.disabled = false;
            }
        });
        bar.appendChild(btnFetch);

        // 📋 Running
        const btnRunning = styledBtn("📋 Running", "Show running models", "#5c6bc0");
        btnRunning.addEventListener("click", async () => {
            try {
                const data = await fetchRunning(getServerUrl(node));
                const list = data.running ?? [];
                toast(list.length ? `🟢 Running: ${list.join(", ")}` : "⬜ No models", "#37474f");
            } catch (e) { toast(`❌ ${e}`, "#b71c1c"); }
        });
        bar.appendChild(btnRunning);

        // ⏏ Unload Current
        const btnUnload = styledBtn("⏏ Unload", "Unload model", "#c62828");
        btnUnload.addEventListener("click", async () => {
            const modelWidget = getWidget(node, "model");
            const modelName = modelWidget?.value;

            if (!modelName) {
                toast("⚠️ Select a model first", "#b71c1c");
                return;
            }

            if (!confirm(`Unload ${modelName}?`)) return;
            
            try {
                const data = await doUnload(getServerUrl(node), modelName);
                toast(data.status === "ok" ? `✅ ${modelName} unloaded` : `⚠️ ${data.error}`,
                      data.status === "ok" ? "#2e7d32" : "#b71c1c");
            } catch (e) { toast(`❌ ${e}`, "#b71c1c"); }
        });
        bar.appendChild(btnUnload);

        // 🚀 Start Server Button
        const btnStart = styledBtn("🚀 Start", "Launch server", "#2e7d32");
        btnStart.addEventListener("click", async () => {
            btnStart.disabled = true;
            btnStart.textContent = "⏳ Starting...";
            try {
                const args = getLaunchArgs(node);
                const resp = await api.fetchApi(`/llama_suite/start`, { 
                    method: 'POST',
                    body: JSON.stringify(args)
                });
                const data = await resp.json();
                toast(`🚀 ${data.message}`, "#2e7d32");
                // Ждем немного и проверяем статус
                setTimeout(() => checkStatusAndUpdate(node, statusBadge, btnStart, btnStop), 2000);
            } catch (e) {
                toast(`❌ ${e.message || e}`, "#b71c1c");
            } finally {
                btnStart.disabled = false;
                btnStart.textContent = "🚀 Start";
            }
        });
        bar.appendChild(btnStart);

        // 🛑 Stop Server Button
        const btnStop = styledBtn("🛑 Stop", "Stop server", "#d32f2f");
        btnStop.addEventListener("click", async () => {
            if (!confirm("Stop server?")) return;
            btnStop.disabled = true;
            btnStop.textContent = "⏳ Stopping...";
            try {
                const resp = await api.fetchApi(`/llama_suite/stop`, { method: 'POST' });
                const data = await resp.json();
                toast(`🛑 ${data.message}`, "#d32f2f");
                
                const modelWidget = getWidget(node, "model");
                if (modelWidget) {
                    modelWidget.value = "";
                    node.setDirtyCanvas(true, true);
                }

                setTimeout(() => checkStatusAndUpdate(node, statusBadge, btnStart, btnStop), 2000);
            } catch (e) {
                toast(`❌ ${e}`, "#b71c1c");
            } finally {
                btnStop.disabled = false;
                btnStop.textContent = "🛑 Stop";
            }
        });
        bar.appendChild(btnStop);

        // Инициализация
        checkStatusAndUpdate(node, statusBadge, btnStart, btnStop);
        
        const urlWidget = getWidget(node, "server_url");
        if (urlWidget) {
            const origCallback = urlWidget.callback;
            urlWidget.callback = (value) => {
                if(origCallback) origCallback(value);
                checkStatusAndUpdate(node, statusBadge, btnStart, btnStop);
            };
        }

        node.addDOMWidget("llama_suite_controls", "btn_bar", bar, {
            serialize: false,
            hideOnZoom: false,
        });
    },
});
