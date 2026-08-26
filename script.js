// ===== Theme Toggle =====
(function() {
    // Apply saved theme immediately to prevent flash
    if (localStorage.getItem('theme') === 'clean') {
        document.body.classList.add('clean-theme');
    }

    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            document.body.classList.toggle('clean-theme');
            const isClean = document.body.classList.contains('clean-theme');
            localStorage.setItem('theme', isClean ? 'clean' : 'dark');
        });
    }
})();

// Mobile nav toggle (only on subpages with navbar)
const navToggle = document.getElementById('nav-toggle');
const navLinks = document.getElementById('nav-links');

if (navToggle && navLinks) {
    navToggle.addEventListener('click', () => {
        navLinks.classList.toggle('active');
        navToggle.classList.toggle('active');
    });

    // Close mobile nav on link click
    document.querySelectorAll('.nav-links a').forEach(link => {
        link.addEventListener('click', () => {
            navLinks.classList.remove('active');
            navToggle.classList.remove('active');
        });
    });
}

// Scroll-based animations (intersection observer)
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
        }
    });
}, observerOptions);

// Add fade-in class to animatable elements
document.querySelectorAll(
    '.timeline-item, .highlight-card, .skill-category, .education-card, .engagement-card, .contact-link, .about-text, .sphere, .publication-item, .investment-card, .investment-note, .other-card, .activity-feature, .sport-card, .tour-card, .tour-suggestion'
).forEach(el => {
    el.classList.add('fade-in');
    observer.observe(el);
});

// Navbar background on scroll (only on subpages)
const navbar = document.getElementById('navbar');
if (navbar) {
    window.addEventListener('scroll', () => {
        const isClean = document.body.classList.contains('clean-theme');
        if (window.scrollY > 50) {
            navbar.style.background = isClean ? 'rgba(255, 255, 255, 0.97)' : 'rgba(15, 23, 42, 0.95)';
        } else {
            navbar.style.background = isClean ? 'rgba(255, 255, 255, 0.92)' : 'rgba(15, 23, 42, 0.85)';
        }
    });
}

// Active nav link highlighting (only on subpages)
const sections = document.querySelectorAll('.section');
const navLinksAll = document.querySelectorAll('.nav-links a:not(.nav-sphere-link)');

if (navLinksAll.length > 0) {
    window.addEventListener('scroll', () => {
        let current = '';
        sections.forEach(section => {
            const sectionTop = section.offsetTop - 100;
            if (window.scrollY >= sectionTop) {
                current = section.getAttribute('id');
            }
        });

        navLinksAll.forEach(link => {
            link.style.color = '';
            if (link.getAttribute('href') === `#${current}`) {
                link.style.color = 'var(--color-text-heading)';
            }
        });
    });
}

// Tour suggestion form
// Set API_BASE to your Render deployment URL, e.g. "https://personal-webpage-api.onrender.com"
const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? `http://${window.location.host}`
    : 'https://personal-webpage-o7x2.onrender.com';

const tourForm = document.getElementById('tour-suggestion-form');
if (tourForm) {
    tourForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const input = document.getElementById('tour-input');
        const value = input.value.trim();
        if (!value) return;

        const btn = tourForm.querySelector('.tour-submit-btn');
        btn.disabled = true;
        btn.textContent = 'Sending…';

        fetch(API_BASE + '/api/tours', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tour: value })
        })
        .then(res => {
            const note = tourForm.parentElement.querySelector('.tour-form-note');
            if (res.ok) {
                input.value = '';
                if (note) {
                    note.textContent = 'Thank you! Your suggestion has been received.';
                    note.style.color = 'var(--color-activities)';
                }
            } else {
                if (note) {
                    note.textContent = 'Something went wrong. Please try again.';
                    note.style.color = '#e74c3c';
                }
            }
        })
        .catch(() => {
            const note = tourForm.parentElement.querySelector('.tour-form-note');
            if (note) {
                note.textContent = 'Could not connect to server. Please try again later.';
                note.style.color = '#e74c3c';
            }
        })
        .finally(() => {
            btn.disabled = false;
            btn.textContent = 'Submit';
            loadRecentSuggestions();
            loadMountainChart();
        });
    });
}

function loadRecentSuggestions() {
    const container = document.getElementById('recent-suggestions');
    if (!container) return;

    fetch(API_BASE + '/api/tours')
        .then(res => res.ok ? res.json() : [])
        .then(data => {
            const recent = data.slice(0, 3);
            if (recent.length === 0) {
                container.innerHTML = '';
                return;
            }
            container.innerHTML =
                '<h4>Recent Suggestions</h4><ul>' +
                recent.map(t => '<li>' + t.text.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</li>').join('') +
                '</ul>';
        })
        .catch(() => { container.innerHTML = ''; });
}

loadRecentSuggestions();

// ---------- Mountain mentions bar chart ----------

function loadMountainChart() {
    const container = document.getElementById('mountain-chart-container');
    if (!container) return;

    fetch(API_BASE + '/api/mountain-mentions')
        .then(res => res.ok ? res.json() : [])
        .then(data => {
            if (!data.length) {
                container.innerHTML = '<p class="chart-loading">No data available yet.</p>';
                return;
            }

            const barHeight = 28;
            const barGap = 8;
            const labelWidth = 140;
            const svgWidth = 600;
            const barAreaWidth = svgWidth - labelWidth - 50;
            const maxCount = Math.max(...data.map(d => d.mention_count), 1);
            const svgHeight = data.length * (barHeight + barGap) + 8;

            const bars = data.map((d, i) => {
                const y = i * (barHeight + barGap) + 4;
                const barW = Math.max(d.mention_count > 0 ? (d.mention_count / maxCount) * barAreaWidth : 2, 2);
                const name = d.name.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                const isTop = i < 3;
                return `<g>
                    <text x="${labelWidth - 8}" y="${y + barHeight / 2 + 5}"
                        text-anchor="end" font-size="12" font-family="inherit"
                        class="chart-label ${isTop ? 'chart-label-top' : 'chart-label-dim'}"
                        font-weight="${isTop ? '600' : '400'}">${name}</text>
                    <rect x="${labelWidth}" y="${y}" width="${barW}" height="${barHeight}"
                        rx="4" class="chart-bar" opacity="${isTop ? '1' : '0.5'}"/>
                    <text x="${labelWidth + barW + 7}" y="${y + barHeight / 2 + 5}"
                        font-size="12" font-family="inherit"
                        class="chart-label chart-label-dim">${d.mention_count}</text>
                </g>`;
            }).join('');

            container.innerHTML = `<svg viewBox="0 0 ${svgWidth} ${svgHeight}"
                xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Mountain mentions bar chart">${bars}</svg>`;
        })
        .catch(() => {
            container.innerHTML = '<p class="chart-loading">Chart unavailable.</p>';
        });
}

loadMountainChart();

// ---------- Mountain chat ----------

(function () {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');
    const answerEl = document.getElementById('chat-answer');
    const historyEl = document.getElementById('chat-history');
    if (!form || !input || !sendBtn || !answerEl || !historyEl) return;

    // The API is stateless, so the browser keeps the conversation and resends it
    // each turn. The server re-validates and trims it before calling the model.
    const history = [];
    let busy = false;

    // Render on the free Render tier sleeps when idle; the first request after
    // that can take the best part of a minute to wake it. Say so rather than
    // leaving the visitor looking at an empty box.
    const WAKE_HINT_MS = 8000;

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    // Move the exchange that is currently on screen into the history list, so
    // the newest answer always sits directly under the input.
    function archiveCurrent() {
        const q = answerEl.querySelector('.chat-answer-q');
        const a = answerEl.querySelector('.chat-answer-text');
        if (!q || !a || !a.textContent.trim()) return;

        const turn = el('div', 'chat-turn');
        turn.appendChild(el('div', 'chat-turn-q', q.textContent));
        turn.appendChild(el('div', 'chat-turn-a', a.textContent));
        historyEl.prepend(turn);
    }

    function setBusy(state) {
        busy = state;
        sendBtn.disabled = state;
        sendBtn.textContent = state ? 'Thinking…' : 'Send';
    }

    form.addEventListener('submit', e => {
        e.preventDefault();
        if (busy) return;

        const text = input.value.trim();
        if (!text) return;

        archiveCurrent();

        answerEl.hidden = false;
        answerEl.classList.remove('chat-answer-error');
        answerEl.innerHTML = '';
        answerEl.appendChild(el('div', 'chat-answer-q', text));
        const out = el('div', 'chat-answer-text');
        answerEl.appendChild(out);
        const status = el('div', 'chat-status', 'Thinking…');
        answerEl.appendChild(status);

        history.push({ role: 'user', content: text });
        input.value = '';
        setBusy(true);

        let firstChunk = true;
        const wakeHint = setTimeout(() => {
            if (firstChunk) status.textContent = 'Waking up the server — this can take up to a minute…';
        }, WAKE_HINT_MS);

        function fail(message) {
            clearTimeout(wakeHint);
            status.remove();
            answerEl.classList.add('chat-answer-error');
            out.textContent = message;
            history.pop();   // drop the unanswered turn
            setBusy(false);
        }

        fetch(API_BASE + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: history })
        })
            .then(res => {
                if (!res.ok) {
                    // Validation and rate-limit failures come back as plain JSON.
                    return res.json()
                        .catch(() => ({}))
                        .then(body => { fail(body.error || `Something went wrong (HTTP ${res.status}).`); });
                }

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                function pump() {
                    return reader.read().then(({ done, value }) => {
                        if (done) {
                            clearTimeout(wakeHint);
                            status.remove();
                            setBusy(false);
                            return;
                        }

                        buffer += decoder.decode(value, { stream: true });

                        // SSE frames are separated by a blank line.
                        const frames = buffer.split('\n\n');
                        buffer = frames.pop();

                        for (const frame of frames) {
                            const line = frame.split('\n').find(l => l.startsWith('data: '));
                            if (!line) continue;

                            let payload;
                            try {
                                payload = JSON.parse(line.slice(6));
                            } catch (err) {
                                continue;
                            }

                            if (payload.error) { fail(payload.error); return; }

                            if (payload.delta) {
                                if (firstChunk) {
                                    firstChunk = false;
                                    clearTimeout(wakeHint);
                                    status.remove();
                                }
                                // textContent, so nothing the model returns is
                                // ever treated as markup.
                                out.textContent += payload.delta;
                            }

                            if (payload.done) {
                                history.push({ role: 'assistant', content: out.textContent });
                            }
                        }

                        return pump();
                    });
                }

                return pump();
            })
            .catch(() => fail('Could not reach the server. Please try again in a moment.'));
    });

    // Enter sends, Shift+Enter starts a new line.
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            form.requestSubmit();
        }
    });
})();
