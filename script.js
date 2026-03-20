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
const API_BASE = 'https://personal-webpage-9nlh.onrender.com';

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
        });
    });
}
