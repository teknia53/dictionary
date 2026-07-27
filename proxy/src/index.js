const PREFIX = '/dictionary';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let path = url.pathname;

    if (path === PREFIX) {
      return Response.redirect(url.origin + PREFIX + '/' + url.search, 301);
    }

    if (!path.startsWith(PREFIX + '/')) {
      return new Response('Not found', { status: 404 });
    }
    path = path.slice(PREFIX.length);

    // Pretty URLs: /dictionary/25, /dictionary/gk:27, /dictionary/ἀγαπάω …
    // Anything that isn't a real asset request gets the app shell; the page
    // reads the term back out of location.pathname.
    const lastSegment = path.split('/').pop();
    if (lastSegment && !lastSegment.includes('.')) {
      path = '/index.html';
    }

    const targetUrl = env.PAGES_URL + path + url.search;
    const proxyReq = new Request(targetUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
      redirect: 'follow',
    });
    return fetch(proxyReq);
  },
};
