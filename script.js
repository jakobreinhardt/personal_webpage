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
    '.timeline-item, .highlight-card, .skill-category, .education-card, .engagement-card, .contact-link, .about-text, .sphere, .publication-item, .investment-card, .investment-note, .other-card, .activity-feature, .sport-card'
).forEach(el => {
    el.classList.add('fade-in');
    observer.observe(el);
});

// Navbar background on scroll (only on subpages)
const navbar = document.getElementById('navbar');
if (navbar) {
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.style.background = 'rgba(15, 23, 42, 0.95)';
        } else {
            navbar.style.background = 'rgba(15, 23, 42, 0.85)';
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
