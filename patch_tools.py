import re

with open("web/templates/workspace.html", "r") as f:
    code = f.read()

injection = """        <!-- Timeline Controls -->
        <div class="h-10 border-b border-white/5 bg-[#1a1a20] flex items-center px-4 justify-between">
            <div class="flex items-center gap-2">
                <button class="w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 text-gray-400"><svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M4 4l12 6-12 6z"></path></svg></button>
                <button class="w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 text-gray-400"><svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clip-rule="evenodd"></path></svg></button>
                <div class="h-4 w-px bg-white/10 mx-2"></div>
                <button id="btn-split" class="px-2 py-1 text-xs font-medium rounded bg-gray-800 hover:bg-gray-700 text-gray-300 border border-white/5" title="Split Clip at Playhead">Split</button>
                <button id="btn-delete" class="px-2 py-1 text-xs font-medium rounded bg-red-900/30 hover:bg-red-900/50 text-red-400 border border-red-500/20" title="Delete Selected Clip">Delete</button>
            </div>"""

old_code = """        <!-- Timeline Controls -->
        <div class="h-10 border-b border-white/5 bg-[#1a1a20] flex items-center px-4 justify-between">
            <div class="flex items-center gap-2">
                <button class="w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 text-gray-400"><svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M4 4l12 6-12 6z"></path></svg></button>
                <button class="w-6 h-6 flex items-center justify-center rounded hover:bg-white/10 text-gray-400"><svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clip-rule="evenodd"></path></svg></button>
            </div>"""

code = code.replace(old_code, injection)


js_injection = """
        // Timeline interactive tools logic
        document.getElementById('btn-delete').addEventListener('click', () => {
            const selected = document.querySelector('.clip.ring-2');
            if (selected) {
                selected.remove();
            } else {
                alert("Please select a clip to delete by clicking on it.");
            }
        });

        document.getElementById('btn-split').addEventListener('click', () => {
            const selected = document.querySelector('.clip.ring-2');
            if (!selected) {
                alert("Please select a clip to split.");
                return;
            }

            // For a real implementation, we would split based on playhead intersection.
            // Here, we split the clip exactly in half for demo purposes.
            const width = parseFloat(selected.style.width);
            const currentX = parseFloat(selected.getAttribute('data-x') || 0);
            const leftStr = selected.style.left; // e.g., '120px'

            selected.style.width = `${width / 2}px`;

            const newClip = selected.cloneNode(true);
            newClip.classList.remove('ring-2', 'ring-indigo-500'); // Deselect clone

            // Position the new clip right after the first half
            const newX = currentX + (width / 2);
            newClip.setAttribute('data-x', newX);
            newClip.style.transform = `translate(${newX}px, 0px)`;

            // Reattach mousedown listener for the clone since cloneNode doesn't copy listeners
            newClip.addEventListener('mousedown', () => {
                document.querySelectorAll('.clip').forEach(c => c.classList.remove('ring-2', 'ring-indigo-500'));
                newClip.classList.add('ring-2', 'ring-indigo-500');
            });

            selected.parentNode.appendChild(newClip);

            // Re-initialize interactjs on the newly added clip
            interact(newClip).draggable(true).resizable(true);
        });
"""

code = code.replace(
    "function fetchStatus() {",
    js_injection + "\n        function fetchStatus() {"
)

with open("web/templates/workspace.html", "w") as f:
    f.write(code)
