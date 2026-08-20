(() => {
  "use strict";

  const USER_SENTINEL = "PAIC_GEMINI_SHARE_SENTINEL_20260819_USER";
  const ASSISTANT_SENTINEL = "PAIC_GEMINI_SHARE_SENTINEL_20260819_ASSISTANT";
  const SAFE_ROUTE_LITERALS = new Set(["gemini", "share"]);
  const MAX_ROUTE_SEGMENTS = 12;
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
    "aria-live"
  ]);

  function isGoogleFirstPartyHost(hostname) {
    return hostname === "g.co" || hostname === "google.com" || hostname.endsWith(".google.com");
  }

  function safeFinalHostname(hostname) {
    return isGoogleFirstPartyHost(hostname) ? hostname : "<non-google-first-party>";
  }

  function routeShape(pathname) {
    if (typeof pathname !== "string") {
      return "<unavailable>";
    }
    const segments = pathname.split("/").filter(Boolean).slice(0, MAX_ROUTE_SEGMENTS);
    if (!segments.length) {
      return "/";
    }
    return "/" + segments.map((segment) => {
      const normalized = segment.toLowerCase();
      return SAFE_ROUTE_LITERALS.has(normalized) ? normalized : "<redacted-segment>";
    }).join("/");
  }

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
    if (!document.body) {
      return matches;
    }
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
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

  function userPrecedesAssistant(userNode, assistantNode) {
    if (!userNode || !assistantNode || userNode === assistantNode) {
      return null;
    }
    return Boolean(userNode.compareDocumentPosition(assistantNode) & Node.DOCUMENT_POSITION_FOLLOWING);
  }

  const finalHostname = location.hostname;
  const firstPartyHost = isGoogleFirstPartyHost(finalHostname);
  const sanitizedRouteShape = firstPartyHost ? routeShape(location.pathname) : "<not-inspected>";

  // Fail closed on a non-Google host: do not inspect its DOM at all.
  const userMatches = firstPartyHost ? findSentinelTextNodes(USER_SENTINEL) : [];
  const assistantMatches = firstPartyHost ? findSentinelTextNodes(ASSISTANT_SENTINEL) : [];
  const userNode = userMatches.length === 1 ? userMatches[0] : null;
  const assistantNode = assistantMatches.length === 1 ? assistantMatches[0] : null;
  const userElement = nearestElement(userNode);
  const assistantElement = nearestElement(assistantNode);
  const sharedAncestor = commonAncestor(userElement, assistantElement);

  const report = {
    ok:
      firstPartyHost &&
      userMatches.length === 1 &&
      assistantMatches.length === 1,
    probe: "paic-gemini-share-dom-contract-v1",
    final_hostname: safeFinalHostname(finalHostname),
    google_first_party_host: firstPartyHost,
    public_route_shape: sanitizedRouteShape,
    sentinels: {
      user: summarizeMatch("USER", userMatches),
      assistant: summarizeMatch("ASSISTANT", assistantMatches),
      user_precedes_assistant: userPrecedesAssistant(userNode, assistantNode)
    },
    nearest_common_ancestor: sharedAncestor ? fingerprint(sharedAncestor, 0) : null,
    privacy: {
      full_url_exported: false,
      opaque_share_identifier_exported: false,
      query_or_fragment_exported: false,
      normal_message_text_exported: false,
      page_title_exported: false,
      dom_id_values_exported: false,
      cookies_or_storage_read: false,
      network_requests_made: false,
      auth_or_session_data_read: false,
      canvas_image_video_or_attachment_content_exported: false
    },
    evidence_boundary: {
      short_link_redirect_observed_by_probe: false,
      signed_out_state_proven_by_probe: false,
      final_route_contract_proven: false
    }
  };

  const serialized = JSON.stringify(report, null, 2);
  console.log(serialized);
  if (typeof copy === "function") {
    copy(serialized);
    console.log("PAIC Gemini public-share structural probe copied to the DevTools clipboard.");
  }
  return report;
})();
