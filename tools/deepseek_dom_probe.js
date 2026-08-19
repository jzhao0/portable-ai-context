(() => {
  "use strict";

  const USER_SENTINEL = "PAIC_DEEPSEEK_CAPTURE_SENTINEL_20260819_USER";
  const ASSISTANT_SENTINEL = "PAIC_DEEPSEEK_CAPTURE_SENTINEL_20260819_ASSISTANT";
  const EXPECTED_HOST = "chat.deepseek.com";
  const MAX_ANCESTOR_DEPTH = 10;
  const MAX_CLASS_TOKENS = 12;
  const MAX_SAFE_VALUE_LENGTH = 80;

  const SAFE_VALUE_ATTRIBUTES = new Set([
    "role",
    "data-testid",
    "data-role",
    "data-author",
    "data-message-role",
    "data-message-author-role",
    "data-message-type",
    "data-testid"
  ]);

  function isSafeStructuralValue(value) {
    if (typeof value !== "string" || value.length === 0 || value.length > MAX_SAFE_VALUE_LENGTH) {
      return false;
    }
    if (!/^[A-Za-z0-9_.:-]+$/.test(value)) {
      return false;
    }
    if (/^[0-9a-f]{16,}$/i.test(value)) {
      return false;
    }
    if (/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(value)) {
      return false;
    }
    return true;
  }

  function safeClassTokens(element) {
    return Array.from(element.classList || [])
      .filter((token) => /^[A-Za-z_-][A-Za-z0-9_-]{0,63}$/.test(token))
      .filter((token) => !/^[0-9a-f]{16,}$/i.test(token))
      .slice(0, MAX_CLASS_TOKENS);
  }

  function safeSemanticAttributes(element) {
    const attributes = {};
    for (const attribute of Array.from(element.attributes || [])) {
      const name = attribute.name.toLowerCase();
      if (!SAFE_VALUE_ATTRIBUTES.has(name)) {
        continue;
      }
      if (isSafeStructuralValue(attribute.value)) {
        attributes[name] = attribute.value;
      }
    }
    return attributes;
  }

  function fingerprint(element, depth) {
    return {
      depth,
      tag: element.tagName.toLowerCase(),
      classes: safeClassTokens(element),
      semantic_attributes: safeSemanticAttributes(element),
      has_id: element.hasAttribute("id"),
      child_element_count: element.children.length
    };
  }

  function ancestorChain(element) {
    const chain = [];
    let current = element;
    let depth = 0;
    while (current && current !== document.documentElement && depth <= MAX_ANCESTOR_DEPTH) {
      chain.push(fingerprint(current, depth));
      current = current.parentElement;
      depth += 1;
    }
    return chain;
  }

  function findSentinelTextNodes(sentinel) {
    const matches = [];
    const root = document.body;
    if (!root) {
      return matches;
    }

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const value = typeof node.nodeValue === "string" ? node.nodeValue : "";
      if (value.includes(sentinel)) {
        matches.push(node);
      }
      node = walker.nextNode();
    }
    return matches;
  }

  function nearestElement(textNode) {
    return textNode && textNode.parentElement ? textNode.parentElement : null;
  }

  function commonAncestor(left, right) {
    if (!left || !right) {
      return null;
    }
    const leftAncestors = new Set();
    let current = left;
    while (current) {
      leftAncestors.add(current);
      current = current.parentElement;
    }
    current = right;
    while (current) {
      if (leftAncestors.has(current)) {
        return current;
      }
      current = current.parentElement;
    }
    return null;
  }

  function summarizeMatch(label, matches) {
    const element = matches.length === 1 ? nearestElement(matches[0]) : null;
    return {
      marker: label,
      match_count: matches.length,
      unique_match: matches.length === 1,
      ancestor_chain: element ? ancestorChain(element) : []
    };
  }

  const userMatches = findSentinelTextNodes(USER_SENTINEL);
  const assistantMatches = findSentinelTextNodes(ASSISTANT_SENTINEL);
  const userElement = userMatches.length === 1 ? nearestElement(userMatches[0]) : null;
  const assistantElement = assistantMatches.length === 1 ? nearestElement(assistantMatches[0]) : null;
  const sharedAncestor = commonAncestor(userElement, assistantElement);

  const report = {
    ok:
      location.hostname === EXPECTED_HOST &&
      userMatches.length === 1 &&
      assistantMatches.length === 1,
    probe: "paic-deepseek-dom-contract-v1",
    hostname: location.hostname,
    expected_hostname: EXPECTED_HOST,
    host_matches: location.hostname === EXPECTED_HOST,
    sentinels: {
      user: summarizeMatch("USER", userMatches),
      assistant: summarizeMatch("ASSISTANT", assistantMatches)
    },
    nearest_common_ancestor: sharedAncestor ? fingerprint(sharedAncestor, 0) : null,
    privacy: {
      normal_message_text_exported: false,
      ids_exported: false,
      cookies_or_storage_read: false,
      network_requests_made: false,
      auth_or_session_data_read: false
    }
  };

  const serialized = JSON.stringify(report, null, 2);
  console.log(serialized);

  if (typeof copy === "function") {
    copy(serialized);
    console.log("PAIC DeepSeek structural probe copied to the DevTools clipboard.");
  }

  return report;
})();
