const state = {
    files: [],
    summary: null,
    selectedPath: null,
};

const els = {
    uploadForm: document.getElementById("uploadForm"),
    fileInput: document.getElementById("fileInput"),
    uploadStatus: document.getElementById("uploadStatus"),
    projectSubtitle: document.getElementById("projectSubtitle"),
    fileCount: document.getElementById("fileCount"),
    languageList: document.getElementById("languageList"),
    insightsGrid: document.getElementById("insightsGrid"),
    fileFilter: document.getElementById("fileFilter"),
    languageFilter: document.getElementById("languageFilter"),
    fileList: document.getElementById("fileList"),
    selectedFileLabel: document.getElementById("selectedFileLabel"),
    askForm: document.getElementById("askForm"),
    questionInput: document.getElementById("questionInput"),
    answerBox: document.getElementById("answerBox"),
    searchForm: document.getElementById("searchForm"),
    searchInput: document.getElementById("searchInput"),
    searchResults: document.getElementById("searchResults"),
    previewTitle: document.getElementById("previewTitle"),
    previewMeta: document.getElementById("previewMeta"),
    previewBox: document.getElementById("previewBox"),
};

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const text = await response.text();
    let payload = {};

    if (text) {
        try {
            payload = JSON.parse(text);
        } catch {
            payload = { detail: text };
        }
    }

    if (!response.ok) {
        throw new Error(payload.detail || "Request failed");
    }

    return payload;
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;",
    }[char]));
}

function formatBytes(bytes) {
    if (!bytes) return "0 B";
    const units = ["B", "KB", "MB"];
    let value = bytes;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
        value /= 1024;
        index += 1;
    }
    return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function formatInsightFile(file) {
    if (!file || !file.path) return "None";
    return `${file.path} (${file.lines || 0} LOC)`;
}

function renderInsights(summary) {
    const items = [
        ["Python Files", summary.python_files ?? 0],
        ["Functions", summary.function_count ?? 0],
        ["Classes", summary.class_count ?? 0],
        ["Imports", summary.import_count ?? 0],
        ["Avg LOC", Math.round(summary.average_loc ?? 0)],
        ["Largest File", formatInsightFile(summary.largest_file)],
        ["Smallest File", formatInsightFile(summary.smallest_file)],
    ];

    els.insightsGrid.innerHTML = items.map(([label, value]) => `
        <div class="insight-item">
            <strong>${escapeHtml(value)}</strong>
            <span>${escapeHtml(label)}</span>
        </div>
    `).join("");
}

function renderLanguageFilter() {
    const selected = els.languageFilter.value;
    const languages = Object.keys((state.summary && state.summary.languages) || {});
    els.languageFilter.innerHTML = [
        `<option value="">All languages</option>`,
        ...languages.map((language) => `
            <option value="${escapeHtml(language)}">${escapeHtml(language)}</option>
        `),
    ].join("");
    if (languages.includes(selected)) {
        els.languageFilter.value = selected;
    }
}

function renderSummary() {
    const summary = state.summary || {};
    const fileCount = summary.file_count || 0;
    els.fileCount.textContent = `${fileCount} ${fileCount === 1 ? "file" : "files"}`;
    els.projectSubtitle.textContent = summary.project_name
        ? `${summary.project_name} - ${formatBytes(summary.total_size || 0)} indexed`
        : "Upload a ZIP codebase to begin.";

    const languages = Object.entries(summary.languages || {});
    if (!languages.length) {
        els.languageList.innerHTML = `<p class="empty">No languages indexed yet.</p>`;
        els.insightsGrid.innerHTML = `<p class="empty">Upload a project to see repository insights.</p>`;
        return;
    }

    renderInsights(summary);
    renderLanguageFilter();

    const total = languages.reduce((sum, [, count]) => sum + count, 0);
    els.languageList.innerHTML = languages.map(([language, count]) => {
        const width = Math.max(8, Math.round((count / total) * 100));
        return `
            <div class="language-row">
                <div>
                    <strong>${escapeHtml(language)}</strong>
                    <span>${count}</span>
                </div>
                <div class="bar"><span style="width: ${width}%"></span></div>
            </div>
        `;
    }).join("");
}

function renderFiles() {
    const filter = els.fileFilter.value.trim().toLowerCase();
    const language = els.languageFilter.value;
    const files = state.files.filter((file) => (
        file.path.toLowerCase().includes(filter)
        && (!language || file.language === language)
    ));

    if (!files.length) {
        els.fileList.innerHTML = `<p class="empty">No matching files.</p>`;
        return;
    }

    els.fileList.innerHTML = files.map((file) => `
        <button class="file-item ${file.path === state.selectedPath ? "active" : ""}" data-path="${escapeHtml(file.path)}">
            <span>${escapeHtml(file.path)}</span>
            <small>${escapeHtml(file.language)} - ${file.lines} lines</small>
        </button>
    `).join("");
}

function formatPreviewList(values, suffix = "") {
    if (!values || !values.length) return "  (none)";
    return values.map((value) => `  ${value}${suffix}`).join("\n");
}

function buildPreviewContent(data) {
    if (!data.insights) {
        return data.content || "(This file is empty.)";
    }

    const ins = data.insights;
    const separator = "─".repeat(60);
    const parts = [];

    if (ins.docstring) {
        parts.push("Docstring:", `  ${ins.docstring}`, "");
    }

    parts.push(
        "Functions:",
        formatPreviewList(ins.functions, "()"),
        "",
        "Classes:",
        formatPreviewList(ins.classes),
        "",
        "Imports:",
        formatPreviewList(ins.imports),
        "",
        separator,
        "",
        data.content || "(This file is empty.)",
    );

    return parts.join("\n");
}

function renderSearchResults(results) {
    if (!results.length) {
        els.searchResults.innerHTML = `<p class="empty">No matches.</p>`;
        return;
    }

    els.searchResults.innerHTML = results.map((result) => `
        <button class="result-item" data-path="${escapeHtml(result.path)}">
            <strong>${escapeHtml(result.path)}</strong>
            <span>${escapeHtml(result.language)} - score ${result.score}</span>
            <p>${escapeHtml(result.snippet || "Matched search terms.")}</p>
        </button>
    `).join("");
}

async function refreshProject() {
    const [summary, files] = await Promise.all([
        requestJson("/summary"),
        requestJson("/files"),
    ]);
    state.summary = summary;
    state.files = files;
    renderSummary();
    renderFiles();
}

async function previewFile(path) {
    const data = await requestJson(`/preview?path=${encodeURIComponent(path)}`);
    state.selectedPath = data.path;
    els.selectedFileLabel.textContent = data.path;
    els.previewTitle.textContent = data.path.split("/").pop();
    const moduleLabel = data.insights && data.insights.module ? ` - ${data.insights.module}` : "";
    els.previewMeta.textContent = `${data.language}${moduleLabel}${data.truncated ? " - truncated" : ""}`;
    els.previewBox.textContent = buildPreviewContent(data);
    renderFiles();
}

els.uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!els.fileInput.files.length) {
        els.uploadStatus.textContent = "Choose a ZIP file first.";
        return;
    }

    const formData = new FormData();
    formData.append("file", els.fileInput.files[0]);
    els.uploadStatus.textContent = "Uploading and indexing...";

    try {
        const data = await requestJson("/upload", { method: "POST", body: formData });
        els.uploadStatus.textContent = data.message;
        await refreshProject();
        if (state.files[0]) {
            await previewFile(state.files[0].path);
        }
    } catch (error) {
        els.uploadStatus.textContent = error.message;
    }
});

els.askForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = els.questionInput.value.trim();
    if (!question) {
        els.answerBox.textContent = "Enter a question first.";
        return;
    }

    els.answerBox.textContent = "Thinking...";
    try {
        const data = await requestJson("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
        });
        els.answerBox.textContent = data.answer;
        renderSearchResults(data.sources || []);
    } catch (error) {
        els.answerBox.textContent = error.message;
    }
});

els.searchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = els.searchInput.value.trim();
    if (!query) return;

    els.searchResults.innerHTML = `<p class="empty">Searching...</p>`;
    try {
        const results = await requestJson(`/search?q=${encodeURIComponent(query)}`);
        renderSearchResults(results);
    } catch (error) {
        els.searchResults.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
    }
});

els.fileFilter.addEventListener("input", renderFiles);
els.languageFilter.addEventListener("change", renderFiles);

els.fileList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-path]");
    if (button) await previewFile(button.dataset.path);
});

els.searchResults.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-path]");
    if (button) await previewFile(button.dataset.path);
});

refreshProject().catch((error) => {
    els.uploadStatus.textContent = error.message;
});
