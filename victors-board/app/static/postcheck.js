// A look before you post.
//
// chief once posted a thread, replied to it with the untouched "Re:" subject
// five seconds later, and then posted a lone asterisk trying to fix it. The
// board accepted all three without a word. This is the word.
//
// Nothing here blocks anyone. Every warning has a "Post anyway" — the board
// has thirty years of subject-only posts and a member who ends a subject
// with * knows exactly what they're doing. The point is to catch the post
// that nobody meant to send, not to argue with the ones they did.
(function () {
  var forms = document.querySelectorAll("form.board-form");
  if (!forms.length) return;

  // subject-only conventions: a trailing *, or nm / (nm) / n/m / no message
  var SUBJECT_ONLY = /(\*|\bnm\b|\(nm\)|\bn\/m\b|no message)\s*$/i;
  // a subject that is nothing but punctuation and the marker
  var EMPTY_SUBJECT = /^[\s*.\-_(),:;!?nm\/]*$/i;
  // a link that stopped before it started: the scheme and then nothing, or
  // a host with no dot in it (https://mgoblog, cut off mid-paste)
  var BROKEN_LINK = /https?:\/\/(?=\s|$)|https?:\/\/[^\s\/.]+(?=[\s\/]|$)/i;

  Array.prototype.forEach.call(forms, function (form) {
    var subject = form.querySelector('input[name="subject"]');
    var body = form.querySelector('textarea[name="body"]');
    var submit = form.querySelector('button[type="submit"]');
    if (!subject || !body || !submit) return;
    var imageUrl = form.querySelector('input[name="image_url"]');
    var file = form.querySelector('input[type="file"]');
    var prefill = subject.getAttribute("data-default") || "";
    var panel = null, bypass = false;

    function attached() {
      return (imageUrl && imageUrl.value.trim()) ||
             (file && file.files && file.files.length) ||
             !!window.__voiceFile;
    }

    function problems() {
      var s = subject.value.trim(), b = body.value.trim(), out = [];
      var subjectOnly = SUBJECT_ONLY.test(s);
      var untouchedReply = !!prefill && s === prefill.trim();

      if (!b && !attached() && EMPTY_SUBJECT.test(s)) {
        out.push({ text: "This post is completely empty — no subject to speak of, " +
                         "no message, nothing attached." });
      } else if (!b && !attached() && untouchedReply) {
        out.push({ text: "You haven't written anything. This would post an empty " +
                         "reply with just the subject the form filled in for you." });
      } else if (!b && !attached() && !subjectOnly) {
        out.push({ text: "No message inside. If the subject is the whole post, end " +
                         "it with * so nobody clicks in expecting more.",
                   fix: { label: "Add * and post", run: function () {
                     subject.value = s + "*"; } } });
      }

      if (imageUrl && imageUrl.value.trim() &&
          !/^https?:\/\//i.test(imageUrl.value.trim())) {
        out.push({ text: "That image link will be dropped — it has to start " +
                         "with http:// or https://." });
      }
      if (BROKEN_LINK.test(b)) {
        out.push({ text: "There's a link in the message that looks cut off." });
      }
      return out;
    }

    // --- pictures that won't load ---------------------------------------
    // The board turns the Image URL box, and any bare picture link in the
    // message, into an <img>. Pasting a page there (an Instagram post, a
    // Google Images result, a share link) shows as a broken picture and
    // nothing said so. The browser can find out: load it as a picture the
    // same way the board will, before the post goes.
    var IMG_LINK = /https?:\/\/\S+\.(?:gif|jpe?g|png|webp)(?:\?\S*)?(?=\s|$)/gi;
    var NOT_AN_IMG = /^https:\/\/streamable\.com\/|\.(?:mp3|mp4|mov|webm)(?:\?.*)?$/i;
    var verdicts = {};          // url -> true (loads) / false (doesn't)
    var CHECK_MS = 4000;        // slow isn't broken; past this we let it go

    function pictureUrls() {
      var urls = [];
      var u = imageUrl ? imageUrl.value.trim() : "";
      if (/^https?:\/\//i.test(u) && !NOT_AN_IMG.test(u)) urls.push(u);
      var m, b = body.value;
      IMG_LINK.lastIndex = 0;
      while ((m = IMG_LINK.exec(b))) if (urls.indexOf(m[0]) < 0) urls.push(m[0]);
      return urls;
    }

    function probe(url) {
      return new Promise(function (done) {
        if (url in verdicts) return done(verdicts[url]);
        var img = new Image();
        var settled = false;
        function finish(ok) {
          if (settled) return;
          settled = true;
          verdicts[url] = ok;
          done(ok);
        }
        img.referrerPolicy = "no-referrer";     // exactly as the board loads it
        img.onload = function () { finish(true); };
        img.onerror = function () { finish(false); };
        setTimeout(function () { finish(true); }, CHECK_MS);
        img.src = url;
      });
    }

    function pictureProblems(urls) {
      var out = [];
      var field = imageUrl ? imageUrl.value.trim() : "";
      urls.forEach(function (u) {
        if (verdicts[u] !== false) return;
        if (u === field) {
          out.push({ text: "That picture link doesn't load as a picture — it may " +
                           "be a page (an Instagram post, a Google result, a share " +
                           "link) rather than the image itself. It'll show up broken." });
        } else {
          out.push({ text: "A picture link in the message doesn't load: " + u });
        }
      });
      return out;
    }

    function clear() {
      if (panel) { panel.remove(); panel = null; }
    }

    function checking() {
      clear();
      panel = document.createElement("div");
      panel.className = "postcheck postcheck-wait";
      panel.textContent = "Checking that picture link…";
      submit.parentNode.insertBefore(panel, submit);
    }

    function show(list) {
      clear();
      panel = document.createElement("div");
      panel.className = "postcheck";
      var h = document.createElement("b");
      h.textContent = "Hold on —";
      panel.appendChild(h);
      var ul = document.createElement("ul");
      list.forEach(function (p) {
        var li = document.createElement("li");
        li.textContent = p.text;
        ul.appendChild(li);
      });
      panel.appendChild(ul);
      var row = document.createElement("p");
      row.className = "postcheck-row";
      var back = document.createElement("button");
      back.type = "button";
      back.textContent = "Go back and fix it";
      back.addEventListener("click", function () { clear(); body.focus(); });
      row.appendChild(back);
      list.forEach(function (p) {
        if (!p.fix) return;
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = p.fix.label;
        b.addEventListener("click", function () {
          p.fix.run();
          go();
        });
        row.appendChild(b);
      });
      var anyway = document.createElement("button");
      anyway.type = "button";
      anyway.className = "postcheck-anyway";
      anyway.textContent = "Post anyway";
      anyway.addEventListener("click", go);
      row.appendChild(anyway);
      panel.appendChild(row);
      submit.parentNode.insertBefore(panel, submit);
      panel.scrollIntoView({ block: "nearest" });
    }

    function go() {
      bypass = true;
      clear();
      // requestSubmit fires the submit event, so anything else listening
      // (the voice memo's iOS fallback) still gets its turn
      if (form.requestSubmit) form.requestSubmit(submit); else form.submit();
    }

    // This runs before the page's other submit listeners (it's registered
    // first), so when it stops a post, stopImmediatePropagation keeps the
    // double-click guard and the paste uploader out of it. It must not touch
    // the button itself: that guard reads a disabled button as a second
    // click and cancels the post.
    form.addEventListener("submit", function (e) {
      if (bypass) { bypass = false; return; }
      var list = problems();
      var urls = pictureUrls();
      var unchecked = urls.filter(function (u) { return !(u in verdicts); });
      if (!list.length && !unchecked.length) {
        list = pictureProblems(urls);
        if (!list.length) return;              // nothing to say — off it goes
      }
      e.preventDefault();
      e.stopImmediatePropagation();
      if (!unchecked.length) { show(list.concat(pictureProblems(urls))); return; }
      checking();
      Promise.all(unchecked.map(probe)).then(function () {
        var all = list.concat(pictureProblems(urls));
        if (all.length) show(all); else go();
      });
    });

    // typing again after a warning means they're fixing it
    [subject, body].forEach(function (el) {
      el.addEventListener("input", clear);
    });
  });
})();
