"use strict";

let captured = null;

const captureButton = document.getElementById("capture");
const downloadButton = document.getElementById("download");
const clearButton = document.getElementById("clear");
const statusNode = document.getElementById("status");
const previewNode = document.getElementById("preview");
const messageCountNode = document.getElementById("message-count");
const adapterNode = document.getElementById("adapter");
const firstRoleNode = document.getElementById("first-role");
const lastRoleNode = document.getElementById("last-role");
const sameRoleTransitionsNode = document.getElementById("same-role-transitions");
const ignoredRoleNodesNode = document.getElementById("ignored-role-nodes");
const emptyRoleNodesNode = document.getElementById("empty-role-nodes");
const completenessStatusNode = document.getElementById("completeness-status");
const firstUserNode = document.getElementById("first-user");
const firstAssistantNode = document.getElementById("first-assistant");
const lastUserNode = document.getElementById("last-user");
const lastAssistantNode = document.getElementById("last-assistant");

function captureRoleAttributeConversation() {
  const ROLE_ATTRIBUTE = "data-message-author-role";
  const ALLOWED_ROLES = new Set(["user", "assistant"]);
  const REMOVE_SELECTOR = [
    "script",
    "style",
    "noscript",
    "template",
    "button",
    "svg",
    "canvas",
    "input",
    "textarea",
    "select",
    "form"
  ].join(",");
  const BLOCK_SELECTOR = "p,div,pre,li,tr,section,article,blockquote";
  const MAX_MESSAGES = 10000;
  const MAX_MESSAGE_CHARS = 5000000;

  function normalizeText(value) {
    return value
      .replace(/\u00a0/g, " ")
      .replace(/\r\n?/g, "\n")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n[ \t]+/g, "\n")
      .replace(/[ \t]{2,}/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function textFromRoot(root) {
    const clone = root.cloneNode(true);
    clone.querySelectorAll(REMOVE_SELECTOR).forEach((node) => node.remove());
    clone.querySelectorAll("br").forEach((node) => node.replaceWith("\n"));
    clone.querySelectorAll(BLOCK_SELECTOR).forEach((node) => node.append("\n"));
    return normalizeText(clone.textContent || "");
  }

  const selector = `[${ROLE_ATTRIBUTE}]`;
  const roots = Array.from(document.querySelectorAll(selector)).filter((node) => {
    const parentRoleRoot = node.parentElement ? node.parentElement.closest(selector) : null;
    return parentRoleRoot === null;
  });

  if (roots.length > MAX_MESSAGES) {
    throw new Error(`refusing to capture more than ${MAX_MESSAGES} role-marked DOM nodes`);
  }

  const messages = [];
  let ignoredRoleNodes = 0;
  let emptyRoleNodes = 0;

  for (const root of roots) {
    const rawRole = root.getAttribute(ROLE_ATTRIBUTE);
    const role = typeof rawRole === "string" ? rawRole.trim().toLowerCase() : "";
    if (!ALLOWED_ROLES.has(role)) {
      ignoredRoleNodes += 1;
      continue;
    }

    const text = textFromRoot(root);
    if (!text) {
      emptyRoleNodes += 1;
      continue;
    }
    if (text.length > MAX_MESSAGE_CHARS) {
      throw new Error(`refusing an individual message larger than ${MAX_MESSAGE_CHARS} characters`);
    }

    messages.push({
      role,
      text,
      index: messages.length
    });
  }

  if (!messages.length) {
    return {
      ok: false,
      error: "No supported user/assistant role-marked conversation DOM was found."
    };
  }

  return {
    ok: true,
    schema_version: "paic-browser-capture-1",
    adapter: "role_attribute_v1",
    message_count: messages.length,
    ignored_role_nodes: ignoredRoleNodes,
    empty_role_nodes: emptyRoleNodes,
    messages
  };
}

function setStatus(text, isError = false) {
  statusNode.textContent = text;
  statusNode.classList.toggle("error", isError);
}

function previewText(text, limit = 600) {
  if (!text) {
    return "<none>";
  }
  return text.length <= limit ? text : `${text.slice(0, limit)}\n… [preview truncated]`;
}

function firstMessage(role) {
  if (!captured) {
    return null;
  }
  for (let index = 0; index < captured.messages.length; index += 1) {
    if (captured.messages[index].role === role) {
      return captured.messages[index];
    }
  }
  return null;
}

function lastMessage(role) {
  if (!captured) {
    return null;
  }
  for (let index = captured.messages.length - 1; index >= 0; index -= 1) {
    if (captured.messages[index].role === role) {
      return captured.messages[index];
    }
  }
  return null;
}

function sequenceReview(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    return {
      firstRole: "<none>",
      lastRole: "<none>",
      sameRoleTransitions: 0
    };
  }

  let sameRoleTransitions = 0;
  for (let index = 1; index < messages.length; index += 1) {
    if (messages[index].role === messages[index - 1].role) {
      sameRoleTransitions += 1;
    }
  }

  return {
    firstRole: messages[0].role,
    lastRole: messages[messages.length - 1].role,
    sameRoleTransitions
  };
}

function resetReviewFields() {
  messageCountNode.textContent = "0";
  adapterNode.textContent = "—";
  firstRoleNode.textContent = "—";
  lastRoleNode.textContent = "—";
  sameRoleTransitionsNode.textContent = "0";
  ignoredRoleNodesNode.textContent = "0";
  emptyRoleNodesNode.textContent = "0";
  completenessStatusNode.textContent = "Not proven";
  firstUserNode.textContent = "<none>";
  firstAssistantNode.textContent = "<none>";
  lastUserNode.textContent = "<none>";
  lastAssistantNode.textContent = "<none>";
}

function renderPreview() {
  if (!captured) {
    previewNode.hidden = true;
    downloadButton.disabled = true;
    clearButton.disabled = true;
    return;
  }

  const firstUser = firstMessage("user");
  const firstAssistant = firstMessage("assistant");
  const lastUser = lastMessage("user");
  const lastAssistant = lastMessage("assistant");
  const review = sequenceReview(captured.messages);

  messageCountNode.textContent = String(captured.message_count);
  adapterNode.textContent = captured.adapter;
  firstRoleNode.textContent = review.firstRole;
  lastRoleNode.textContent = review.lastRole;
  sameRoleTransitionsNode.textContent = String(review.sameRoleTransitions);
  ignoredRoleNodesNode.textContent = String(captured.ignored_role_nodes || 0);
  emptyRoleNodesNode.textContent = String(captured.empty_role_nodes || 0);
  completenessStatusNode.textContent = "Not proven";
  firstUserNode.textContent = previewText(firstUser ? firstUser.text : "");
  firstAssistantNode.textContent = previewText(firstAssistant ? firstAssistant.text : "");
  lastUserNode.textContent = previewText(lastUser ? lastUser.text : "");
  lastAssistantNode.textContent = previewText(lastAssistant ? lastAssistant.text : "");
  previewNode.hidden = false;
  downloadButton.disabled = false;
  clearButton.disabled = false;
}

async function inspectActiveTab() {
  setStatus("Inspecting active tab…");
  captured = null;
  renderPreview();

  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    if (!tab || typeof tab.id !== "number") {
      throw new Error("No active browser tab is available.");
    }

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: captureRoleAttributeConversation
    });
    const payload = results && results[0] ? results[0].result : null;
    if (!payload || payload.ok !== true) {
      throw new Error(payload && payload.error ? payload.error : "Capture returned no supported conversation.");
    }

    captured = payload;
    renderPreview();
    const ignored = payload.ignored_role_nodes || 0;
    const empty = payload.empty_role_nodes || 0;
    const review = sequenceReview(payload.messages);
    setStatus(
      `Captured ${payload.message_count} messages. Review signals — same-role transitions: ${review.sameRoleTransitions}; ignored role nodes: ${ignored}; empty role nodes: ${empty}. DOM completeness is not proven; compare the beginning and tail before downloading.`
    );
  } catch (error) {
    captured = null;
    renderPreview();
    setStatus(error instanceof Error ? error.message : String(error), true);
  }
}

function downloadJsonl() {
  if (!captured) {
    return;
  }

  const jsonl = captured.messages
    .map((message) => JSON.stringify({ role: message.role, text: message.text }))
    .join("\n") + "\n";
  const blob = new Blob([jsonl], { type: "application/x-ndjson;charset=utf-8" });
  const blobUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  anchor.href = blobUrl;
  anchor.download = `paic-capture-${stamp}.jsonl`;
  anchor.hidden = true;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
  setStatus(`Downloaded ${captured.message_count} canonical messages as JSONL. DOM completeness was not proven by the extension.`);
}

function clearCapture() {
  captured = null;
  renderPreview();
  resetReviewFields();
  setStatus("Capture cleared from extension memory.");
}

resetReviewFields();
captureButton.addEventListener("click", inspectActiveTab);
downloadButton.addEventListener("click", downloadJsonl);
clearButton.addEventListener("click", clearCapture);
