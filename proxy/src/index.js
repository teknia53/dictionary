// dictionary-proxy — serves the Greek NT Dictionary at www.billmounce.com/greek-dictionary/
//
// The app itself is a static Pages site (env.PAGES_URL). This Worker:
//   * owns the old Drupal URL space /greek-dictionary/<slug> so the entry URLs Google
//     has indexed for years keep working with no redirects;
//   * for an entry URL, looks the word up in the API and injects the title, canonical
//     tag, description, and the entry itself into the HTML before returning it, so
//     crawlers see real content instead of an empty app shell;
//   * redirects the interim /dictionary/* URLs, the old /toc/<letter> pages, and the
//     apex host to their canonical equivalents.

const PREFIX = '/greek-dictionary';
const OLD_PREFIX = '/dictionary';
const SITE_NAME = 'Greek New Testament Dictionary';

const LETTERS = [
  'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'iota', 'kappa',
  'lambda', 'mu', 'nu', 'xi', 'omicron', 'pi', 'rho', 'sigma', 'tau', 'upsilon',
  'phi', 'chi', 'psi', 'omega',
];

// ---------------------------------------------------------------- helpers

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function stripTags(s) {
  return String(s ?? '').replace(/<[^>]*>/g, '');
}

// Same rule as simplifyTranslit() in the API Worker and tools/build_pages.py.
function simplifyTranslit(s) {
  return stripTags(s).toLowerCase().normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]/g, '');
}

// URL-safe slug: keep ':' readable in gk:NNN, encode anything else.
function slugPath(slug) {
  return PREFIX + '/' + encodeURIComponent(slug).replace(/%3A/gi, ':');
}

function redirect(location, status = 301) {
  return new Response(null, { status, headers: { Location: location } });
}

async function apiJson(env, path) {
  try {
    const res = await fetch(env.API_URL + path);
    const data = await res.json();
    return Array.isArray(data) ? data : null;
  } catch (e) {
    return null;
  }
}

function truncate(text, max) {
  const t = text.replace(/\s+/g, ' ').trim();
  if (t.length <= max) return t;
  return t.slice(0, max).replace(/\s+\S*$/, '').replace(/[,;:]$/, '') + '…';
}

// ---------------------------------------------------------------- markup
// Mirrors the markup the app builds client-side in site/index.html so the
// prerendered entry looks identical.

// The word card. Blue header: headword, then the full dictionary form. Body:
// transliteration; gloss; GK and Strong's numbers; morphology tag with the
// frequency (and principal parts for verbs); then the fuller definition. The
// dictionary form, gloss, MBG tag, and principal parts come from the old Drupal
// lexicon and may be empty.
function wordHeader(word) {
  let html = `<div class="word-lexical">${word.lexical || ''}</div>`;
  if (word.dictionary_form) {
    html += `<div class="word-form">${esc(word.dictionary_form)}</div>`;
  }
  return html;
}

function wordBody(word) {
  let html = `<div class="word-translit">${word.transliteration || ''}</div>`;
  if (word.gloss) {
    html += `<div class="word-gloss">${word.gloss}</div>`;
  }
  html += `<div class="word-numbers">GK ${esc(word.gk)}${word.strongs ? ' &middot; Strong\'s ' + esc(word.strongs) : ''}</div>`;
  html += `<div class="word-morph">${word.mbg ? '<span title="Category in Mounce, The Morphology of Biblical Greek">' + esc(word.mbg) + '</span>' : ''}<span class="word-freq">${esc(word.frequency)}</span></div>`;
  if (word.principal_parts) {
    html += `<div class="word-pparts"><span class="label">Principal parts: </span><span class="greek">${esc(word.principal_parts)}</span></div>`;
  }
  html += `<div class="word-definition">${word.definition || ''}</div>`;
  return html;
}

function wordCard(word, entries) {
  let conc;
  if (!entries || entries.length === 0) {
    conc = '<h3>Concordance</h3><div style="color:#999;padding:10px 0;">No concordance entries found.</div>';
  } else {
    conc = `<h3>Concordance (${entries.length} ${entries.length === 1 ? 'entry' : 'entries'})</h3>`;
    for (const e of entries) {
      conc += `
                        <div class="concordance-entry">
                            <div class="concordance-ref">${esc(e.reference)}</div>
                            <div class="concordance-text">${e.concordance || ''}</div>
                        </div>`;
    }
  }
  return `
                <div class="word-card">
                    <div class="word-header">
                        ${wordHeader(word)}
                    </div>
                    <div class="word-body">
                        ${wordBody(word)}
                        <div class="concordance-section">
                            ${conc}
                        </div>
                    </div>
                </div>`;
}

function wordList(words) {
  let html = '<ul class="result-list">';
  for (const w of words) {
    html += `<li><a href="${esc(slugPath('gk:' + w.gk))}">
                    <span class="lex">${w.lexical || ''}</span>
                    <span class="meta">GK ${esc(w.gk)} &middot; Strong's ${esc(w.strongs || '—')} &middot; ${esc(w.frequency)}</span>
                </a></li>`;
  }
  return html + '</ul>';
}

// ---------------------------------------------------------------- responses

function proxyToPages(env, request, path, search) {
  const proxyReq = new Request(env.PAGES_URL + path + search, {
    method: request.method,
    headers: request.headers,
    body: request.body,
    redirect: 'follow',
  });
  return fetch(proxyReq);
}

async function fetchShell(env, request) {
  return fetch(new Request(env.PAGES_URL + '/index.html', {
    headers: request.headers,
    redirect: 'follow',
  }));
}

// Rewrite the app shell with per-page head tags and (optionally) prerendered results.
function renderShell(shell, { status = 200, title, canonical, description, robots, results, term }) {
  const headExtra = [
    canonical ? `<link rel="canonical" href="${esc(canonical)}">` : '',
    description ? `<meta name="description" content="${esc(description)}">` : '',
    robots ? `<meta name="robots" content="${esc(robots)}">` : '',
  ].filter(Boolean).join('\n    ');

  const headers = new Headers(shell.headers);
  headers.set('content-type', 'text/html; charset=utf-8');
  // The body is rewritten, so the upstream encoding/length no longer apply.
  headers.delete('content-encoding');
  headers.delete('content-length');
  const base = new Response(shell.body, { status, headers });

  let rw = new HTMLRewriter();
  if (title) rw = rw.on('title', { element(el) { el.setInnerContent(title); } });
  if (headExtra) rw = rw.on('head', { element(el) { el.append('\n    ' + headExtra + '\n', { html: true }); } });
  if (results !== undefined) {
    rw = rw.on('#results', {
      element(el) {
        el.setAttribute('data-prerendered', '1');
        if (term) el.setAttribute('data-term', term);
        el.setInnerContent(results, { html: true });
      },
    });
  }
  return rw.transform(base);
}

async function entryPage(env, request, url, slug) {
  const [shell, words] = await Promise.all([
    fetchShell(env, request),
    apiJson(env, `/api/dict/search?q=${encodeURIComponent(slug)}&slug=1`),
  ]);
  const origin = url.origin;

  if (words === null) {
    // API trouble: hand back the plain shell and let the client retry.
    return renderShell(shell, { status: 502, title: SITE_NAME, robots: 'noindex' });
  }

  if (words.length === 0) {
    return renderShell(shell, {
      status: 404,
      title: `Not found – ${SITE_NAME}`,
      robots: 'noindex',
      term: slug,
      results: `<div class="no-results">No entry found for “${esc(slug)}”.</div>`,
    });
  }

  if (words.length === 1) {
    const word = words[0];
    // Canonical slug is the simplified transliteration when it is unique to this
    // word, otherwise gk:NNN. Anything else (a number, the Greek form, a
    // different capitalisation) redirects there so Google sees one URL per entry.
    const translitSlug = simplifyTranslit(word.transliteration);
    let canonicalSlug;
    if (translitSlug === slug) {
      canonicalSlug = slug;
    } else if (slug === 'gk:' + word.gk) {
      canonicalSlug = slug;
    } else {
      const byTranslit = translitSlug ? await apiJson(env, `/api/dict/search?q=${encodeURIComponent(translitSlug)}&slug=1`) : [];
      canonicalSlug = byTranslit && byTranslit.length === 1 ? translitSlug : 'gk:' + word.gk;
    }
    if (canonicalSlug !== slug) {
      return redirect(origin + slugPath(canonicalSlug));
    }

    const entries = await apiJson(env, `/api/concordance?gk=${encodeURIComponent(word.gk)}`);
    const lexical = stripTags(word.lexical);
    const translit = stripTags(word.transliteration);
    const gloss = truncate(stripTags(word.gloss || word.definition), 120);
    return renderShell(shell, {
      title: `${lexical} (${translit}) – ${SITE_NAME}`,
      canonical: origin + slugPath(canonicalSlug),
      description: `${lexical} (${translit}), GK ${word.gk}${word.strongs ? ', Strong\'s ' + word.strongs : ''}: ${gloss.replace(/[.,;:]?$/, '.')} Definition, frequency, and every New Testament occurrence, from Bill Mounce's ${SITE_NAME}.`,
      term: lexical,
      results: wordCard(word, entries),
    });
  }

  // Several entries share this slug (e.g. allos → ἄλλος and ἄλλως): list them.
  const names = words.map(w => stripTags(w.lexical)).join(', ');
  return renderShell(shell, {
    title: `${slug} – ${words.length} entries – ${SITE_NAME}`,
    canonical: origin + slugPath(slug),
    description: `Greek New Testament words transliterated "${slug}": ${names}. From Bill Mounce's ${SITE_NAME}.`,
    term: slug,
    results: wordList(words),
  });
}

// ---------------------------------------------------------------- router

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const canonicalHost = env.SITE_HOST || 'www.billmounce.com';
    let path = url.pathname;

    // One canonical host.
    if (url.hostname !== canonicalHost) {
      return redirect(`https://${canonicalHost}${path}${url.search}`);
    }

    // Interim /dictionary/* URLs → /greek-dictionary/*
    if (path === OLD_PREFIX || path.startsWith(OLD_PREFIX + '/')) {
      return redirect(url.origin + PREFIX + path.slice(OLD_PREFIX.length) + url.search);
    }

    if (path === PREFIX) {
      return redirect(url.origin + PREFIX + '/' + url.search);
    }
    if (!path.startsWith(PREFIX + '/')) {
      return new Response('Not found', { status: 404 });
    }
    path = path.slice(PREFIX.length); // always starts with '/'

    // Old Drupal table-of-contents pages → static letter pages.
    const toc = path.match(/^\/toc\/([a-z]+)\/?$/);
    if (toc) {
      if (LETTERS.includes(toc[1])) return redirect(url.origin + PREFIX + '/words/' + toc[1]);
      return new Response('Not found', { status: 404 });
    }

    // Home page: the shell plus a canonical tag and description.
    if (path === '/') {
      const shell = await fetchShell(env, request);
      return renderShell(shell, {
        canonical: url.origin + PREFIX + '/',
        description: `Search Bill Mounce's ${SITE_NAME}: every Greek word in the New Testament with definition, GK and Strong's numbers, frequency, and all occurrences.`,
      });
    }

    // Static letter-index pages (site/words/*.html, served extension-less by
    // Pages), the sitemap, and any other real file.
    const lastSegment = path.split('/').pop();
    if (path === '/words' || path.startsWith('/words/') || lastSegment.includes('.')) {
      return proxyToPages(env, request, path, url.search);
    }

    // Everything else is an entry: /greek-dictionary/logos, /greek-dictionary/gk:3364 …
    let slug;
    try { slug = decodeURIComponent(lastSegment); } catch (e) { slug = lastSegment; }
    return entryPage(env, request, url, slug.trim());
  },
};
