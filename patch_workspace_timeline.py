import re

with open("web/templates/workspace.html", "r") as f:
    code = f.read()

# Add interact.js library for drag and drop
code = code.replace(
    '<script src="https://cdn.tailwindcss.com"></script>',
    '<script src="https://cdn.tailwindcss.com"></script>\n    <script src="https://cdn.jsdelivr.net/npm/interactjs/dist/interact.min.js"></script>'
)

# Enhance the addClipToTrack function to make clips draggable and resizable
injection = """        function addClipToTrack(trackElement, type, text, startSec, durationSec) {
            const clip = document.createElement('div');
            clip.className = `clip clip-${type}`;
            clip.style.left = `${startSec * PX_PER_SEC}px`;
            clip.style.width = `${durationSec * PX_PER_SEC}px`;
            clip.textContent = text;

            // Allow selecting clips
            clip.addEventListener('mousedown', () => {
                document.querySelectorAll('.clip').forEach(c => c.classList.remove('ring-2', 'ring-indigo-500'));
                clip.classList.add('ring-2', 'ring-indigo-500');
            });

            trackElement.appendChild(clip);
            return clip;
        }

        // Initialize interact.js for draggable and resizable clips
        interact('.clip')
            .draggable({
                modifiers: [
                    interact.modifiers.restrictRect({
                        restriction: 'parent',
                        endOnly: true
                    })
                ],
                listeners: {
                    move(event) {
                        const target = event.target;
                        // Keep track of total translation in data attributes
                        const x = (parseFloat(target.getAttribute('data-x')) || 0) + event.dx;

                        // Use inline styles to update position based on transform
                        target.style.transform = `translate(${x}px, 0px)`;
                        target.setAttribute('data-x', x);
                    }
                }
            })
            .resizable({
                edges: { left: true, right: true, bottom: false, top: false },
                modifiers: [
                    interact.modifiers.restrictEdges({
                        outer: 'parent'
                    }),
                    interact.modifiers.restrictSize({
                        min: { width: PX_PER_SEC } // min 1 second
                    })
                ],
                listeners: {
                    move: function (event) {
                        let { x, y } = event.target.dataset;

                        x = (parseFloat(x) || 0) + event.deltaRect.left;

                        Object.assign(event.target.style, {
                            width: `${event.rect.width}px`,
                            transform: `translate(${x}px, 0px)`
                        });

                        Object.assign(event.target.dataset, { x });
                    }
                }
            });"""

old_code = """        function addClipToTrack(trackElement, type, text, startSec, durationSec) {
            const clip = document.createElement('div');
            clip.className = `clip clip-${type}`;
            clip.style.left = `${startSec * PX_PER_SEC}px`;
            clip.style.width = `${durationSec * PX_PER_SEC}px`;
            clip.textContent = text;
            trackElement.appendChild(clip);
        }"""

code = code.replace(old_code, injection)

with open("web/templates/workspace.html", "w") as f:
    f.write(code)
