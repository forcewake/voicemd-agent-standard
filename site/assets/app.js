"use strict";

(() => {
  const body = document.body;
  if (body.dataset.page !== "azure-proof") {
    return;
  }
  const indexPath = body.dataset.proofIndex;
  const appStatus = document.querySelector("#app-status");

  if (!indexPath || !isSafeRelativePath(indexPath.replace(/^\.\//, ""))) {
    setRenderingError("The proof index path is missing or unsafe.");
    return;
  }

  const snapshotRoot = indexPath.slice(0, indexPath.lastIndexOf("/") + 1);

  function isSafeRelativePath(value) {
    if (typeof value !== "string" || !/^[A-Za-z0-9._/-]+$/.test(value)) {
      return false;
    }
    if (value.startsWith("/") || value.includes(":")) {
      return false;
    }
    return !value.split("/").some((part) => part === "" || part === ".." || part === ".");
  }

  function proofUrl(relativePath) {
    if (!isSafeRelativePath(relativePath)) {
      throw new Error("Unsafe proof path in index");
    }
    return `${snapshotRoot}${relativePath}`;
  }

  function siteUrl(relativePath) {
    if (!isSafeRelativePath(relativePath)) {
      throw new Error("Unsafe site path in index");
    }
    return `./${relativePath}`;
  }

  function element(tagName, className, text) {
    const result = document.createElement(tagName);
    if (className) {
      result.className = className;
    }
    if (text !== undefined) {
      result.textContent = String(text);
    }
    return result;
  }

  function addText(parent, tagName, className, text) {
    const child = element(tagName, className, text);
    parent.append(child);
    return child;
  }

  function addLink(parent, label, href) {
    const link = element("a", "", label);
    link.href = href;
    parent.append(link);
    return link;
  }

  function statusBadge(passed, label, ariaLabel) {
    const status = element("span", `status ${passed ? "match" : "mismatch"}`, label || (passed ? "MATCH" : "MISMATCH"));
    status.setAttribute("aria-label", ariaLabel || (passed ? "Selected checks matched" : "One or more selected checks not met"));
    return status;
  }

  function cardId(run) {
    return `run-${run.contract}-${run.deployment}`.replace(/[^A-Za-z0-9_-]/g, "-");
  }

  function shortHash(value) {
    return typeof value === "string" && value.length > 14 ? `${value.slice(0, 12)}…` : value;
  }

  function artifactPath(run, manifest, artifactName) {
    const artifact = manifest.artifacts && manifest.artifacts[artifactName];
    if (!artifact || !isSafeRelativePath(artifact.path) || artifact.path.includes("/")) {
      return null;
    }
    const runPrefix = run.manifest.slice(0, run.manifest.lastIndexOf("/") + 1);
    return `${runPrefix}${artifact.path}`;
  }

  async function fetchText(url) {
    const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Could not load local proof file (${response.status})`);
    }
    return response.text();
  }

  async function fetchJson(url) {
    return JSON.parse(await fetchText(url));
  }

  function resultDescription(run, manifest) {
    if (run.passed) {
      return "All selected scenario assertions and VoiceMD lint rules matched.";
    }

    const labels = {
      "contains-any:1": "missing required degraded-service wording",
      "contains-any:2": "missing required 840 ms latency wording",
      "contains-any:3": "missing required no-data-loss wording",
      "contains-any:4": "missing required paused-rollout wording"
    };
    const reasons = run.failed_checks.map((checkId) => labels[checkId] || checkId);
    const lintIssues = manifest.assertions && manifest.assertions.lint && Array.isArray(manifest.assertions.lint.issues)
      ? manifest.assertions.lint.issues.map((issue) => issue.message).filter(Boolean)
      : [];
    return [...reasons.filter((reason) => reason !== "voicemd-lint-clean"), ...lintIssues].join("; ");
  }

  function addTranscript(parent, label, transcript) {
    const block = element("div", "transcript-block");
    addText(block, "span", "transcript-label", label);
    const exact = element("p", "transcript");
    exact.textContent = transcript;
    block.append(exact);
    parent.append(block);
  }

  function addAudio(parent, url, run) {
    const audio = element("audio");
    audio.controls = true;
    audio.preload = "metadata";
    audio.src = url;
    audio.setAttribute("aria-label", `Generated audio for ${run.contract} on ${run.deployment}`);
    parent.append(audio);
  }

  function addRunMeta(parent, manifest, includeVoice) {
    const list = element("dl", "run-meta");
    const facts = [
      ["Client total", `${manifest.timings_ms.total} ms`],
      ["Deployment", manifest.deployment]
    ];
    if (includeVoice) {
      facts.push(["Contract hash", shortHash(manifest.voice.contract_sha256)]);
      facts.push(["Voice applied", manifest.voice.applied ? "yes" : "no"]);
    }
    for (const [label, value] of facts) {
      const item = element("div");
      addText(item, "dt", "", label);
      addText(item, "dd", "", value);
      list.append(item);
    }
    parent.append(list);
  }

  function addArtifactLinks(parent, run, manifest, transcriptLabel) {
    const links = element("div", "artifact-links");
    addLink(links, "manifest.json", proofUrl(run.manifest));
    addLink(links, transcriptLabel || "exact transcript", proofUrl(run.transcript));
    const voiceSource = artifactPath(run, manifest, "voice_source");
    if (voiceSource) {
      addLink(links, "VOICE.md source", proofUrl(voiceSource));
    }
    const checksums = artifactPath(run, manifest, "checksums");
    if (checksums) {
      addLink(links, "run checksums", proofUrl(checksums));
    }
    parent.append(links);
  }

  function renderMatrixHead(index) {
    const head = document.querySelector("#matrix-head");
    for (const column of index.matrix.columns) {
      const header = element("th");
      header.scope = "col";
      header.append(document.createTextNode(column.label));
      addText(header, "span", "", column.deployment);
      head.append(header);
    }
  }

  function renderMatrixBody(index, matrixRuns) {
    const bodyTarget = document.querySelector("#matrix-body");
    for (const contract of index.matrix.contracts) {
      const row = element("tr");
      const heading = element("th");
      heading.scope = "row";
      addText(heading, "code", "", contract);
      row.append(heading);

      for (const column of index.matrix.columns) {
        const run = matrixRuns.find((candidate) => candidate.contract === contract
          && candidate.lane === column.lane
          && candidate.deployment === column.deployment);
        if (!run) {
          throw new Error("The matrix is incomplete");
        }
        const cell = element("td");
        const link = element("a", `matrix-cell ${run.passed ? "match" : "mismatch"}`, run.passed ? "MATCH" : "MISMATCH");
        link.href = `#${cardId(run)}`;
        link.setAttribute("aria-label", `${contract} on ${column.deployment}: ${run.passed ? "matched all selected checks" : "one or more selected checks not met"}`);
        cell.append(link);
        row.append(cell);
      }
      bodyTarget.append(row);
    }
  }

  function renderMatrixCard(record, featuredAudio) {
    const { run, manifest, transcript } = record;
    const card = element("article", "run-card");
    card.id = cardId(run);

    const header = element("div", "run-card-head");
    const title = element("div");
    addText(title, "p", "model", `${run.lane} · ${run.deployment}`);
    addText(title, "h3", "", run.contract);
    header.append(title, statusBadge(run.passed));
    card.append(header);

    const note = element("p", "check-note");
    const noteLabel = element("strong", "", "Check result: ");
    note.append(noteLabel, document.createTextNode(resultDescription(run, manifest)));
    card.append(note);

    const alias = featuredAudio.get(run.run_id);
    addAudio(card, alias ? siteUrl(alias.path) : proofUrl(run.audio), run);
    addTranscript(card, "Exact provider transcript", transcript);
    addRunMeta(card, manifest, true);
    addArtifactLinks(card, run, manifest);
    return card;
  }

  function renderBoundaryCard(record, featured) {
    const { run, manifest, transcript, rawTranscript } = record;
    const target = document.querySelector(run.kind === "transcription" ? "#transcription-run" : "#showcase-run");

    const header = element("div", "run-card-head");
    const title = element("div");
    addText(title, "p", "model", `${run.lane} · ${run.deployment}`);
    addText(title, "h3", "", run.kind === "transcription" ? "1 · Raw transcription" : "2 · Contract-shaped response");
    header.append(title, statusBadge(run.passed, "MATCH", "Evidence checks matched"));
    target.append(header);

    const statement = run.kind === "transcription"
      ? "VOICE.md applied: no. Exact-output authority takes precedence."
      : "VOICE.md applied: yes, to the generated response only.";
    addText(target, "p", "check-note", statement);

    if (run.audio) {
      addAudio(target, proofUrl(run.audio), run);
    }
    if (rawTranscript !== null) {
      addTranscript(target, "Exact raw ASR transcript", rawTranscript);
      addTranscript(target, "Exact spoken response transcript", transcript);
    } else {
      addTranscript(target, "Exact raw ASR transcript", transcript);
    }

    addRunMeta(target, manifest, true);
    addArtifactLinks(target, run, manifest, run.kind === "transcription" ? "raw transcript" : "spoken transcript");

    if (featured) {
      target.classList.add("featured");
    }
  }

  function renderControls(index) {
    document.querySelector("#prompt-hash").textContent = index.matrix.controls.prompt_sha256;
    document.querySelector("#scenario-hash").textContent = index.matrix.controls.scenario_sha256;
    document.querySelector("#endpoint-hash").textContent = index.matrix.controls.endpoint_sha256;
  }

  async function loadRun(run) {
    if (!isSafeRelativePath(run.manifest) || !isSafeRelativePath(run.transcript)) {
      throw new Error("Unsafe artifact path in proof index");
    }
    const [manifest, transcript, rawTranscript] = await Promise.all([
      fetchJson(proofUrl(run.manifest)),
      fetchText(proofUrl(run.transcript)),
      run.raw_transcript ? fetchText(proofUrl(run.raw_transcript)) : Promise.resolve(null)
    ]);
    return { run, manifest, transcript, rawTranscript };
  }

  async function render() {
    const index = await fetchJson(indexPath);
    if (index.schema_version !== 1 || !Array.isArray(index.runs) || index.runs.length !== 11) {
      throw new Error("Unexpected proof index schema");
    }

    const records = await Promise.all(index.runs.map(loadRun));
    const matrixRecords = records.filter((record) => record.run.kind === "matrix");
    if (matrixRecords.length !== 9) {
      throw new Error("Unexpected matrix size");
    }

    renderControls(index);
    renderMatrixHead(index);
    renderMatrixBody(index, matrixRecords.map((record) => record.run));

    const featuredAudio = new Map(index.featured_audio.map((item) => [item.source_run_id, item]));
    const matrixTarget = document.querySelector("#matrix-runs");
    for (const record of matrixRecords) {
      matrixTarget.append(renderMatrixCard(record, featuredAudio));
    }

    const transcription = records.find((record) => record.run.kind === "transcription");
    const showcase = records.find((record) => record.run.kind === "showcase");
    if (!transcription || !showcase) {
      throw new Error("Transcription boundary evidence is incomplete");
    }
    renderBoundaryCard(transcription, false);
    renderBoundaryCard(showcase, true);

    appStatus.textContent = "Loaded 11 checksum-bound bundles · 9 matrix responses · exact statuses preserved";
    appStatus.classList.add("ready");
  }

  function setRenderingError(message) {
    if (appStatus) {
      appStatus.textContent = `Proof rendering error: ${message}`;
      appStatus.classList.add("render-error");
    }
  }

  render().catch((error) => {
    setRenderingError(error instanceof Error ? error.message : "unknown error");
  });
})();
