// Smooth scrolling for navigation links
document.addEventListener('DOMContentLoaded', () => {
    // Mobile sidebar toggle
    const hamburger = document.querySelector('.hamburger');
    const navLinks = document.querySelector('.nav-links');
    const navOverlay = document.querySelector('.nav-overlay');

    function openSidebar() {
        hamburger.classList.add('active');
        hamburger.setAttribute('aria-expanded', 'true');
        navLinks.classList.add('open');
        navOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeSidebar() {
        hamburger.classList.remove('active');
        hamburger.setAttribute('aria-expanded', 'false');
        navLinks.classList.remove('open');
        navOverlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    hamburger.addEventListener('click', () => {
        if (navLinks.classList.contains('open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });

    navOverlay.addEventListener('click', closeSidebar);

    // Close sidebar when a link is clicked
    navLinks.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', closeSidebar);
    });

    // Add active class to nav links on scroll
    const sections = document.querySelectorAll('section[id]');
    const allNavLinks = document.querySelectorAll('.nav-links a');

    const observerOptions = {
        root: null,
        rootMargin: '-50% 0px',
        threshold: 0
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.getAttribute('id');
                allNavLinks.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === `#${id}`) {
                        link.classList.add('active');
                    }
                });
            }
        });
    }, observerOptions);

    sections.forEach(section => observer.observe(section));

    // Fetch and display API info
    fetchAPIInfo();
});

async function fetchAPIInfo() {
    try {
        const response = await fetch('/api/info');
        if (response.ok) {
            const data = await response.json();
            console.log('Machine Core API Info:', data);
        }
    } catch (error) {
        console.log('API info fetch failed (this is expected if API is not running):', error.message);
    }
}

// Add copy functionality to code blocks
document.querySelectorAll('pre code').forEach((block) => {
    const button = document.createElement('button');
    button.className = 'copy-button';
    button.textContent = 'Copy';
    button.addEventListener('click', () => {
        navigator.clipboard.writeText(block.textContent).then(() => {
            button.textContent = 'Copied!';
            setTimeout(() => {
                button.textContent = 'Copy';
            }, 2000);
        });
    });
    block.parentElement.style.position = 'relative';
    block.parentElement.appendChild(button);
});
