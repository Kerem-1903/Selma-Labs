import re

with open("web/templates/workspace.html", "r") as f:
    code = f.read()

injection = """        <!-- Left Panel: Assets, Script & Publish -->
        <aside class="w-80 border-r border-white/10 bg-[#121215] flex flex-col shrink-0 overflow-y-auto">
            <div class="p-4 border-b border-white/10">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400">Omnichannel Publish</h2>
                </div>
                <div class="flex flex-col gap-2">
                    <button class="w-full py-2 bg-[#ff0000]/20 hover:bg-[#ff0000]/40 border border-[#ff0000]/30 text-[#ff0000] text-xs font-bold rounded flex items-center justify-center gap-2 transition-colors" onclick="alert('Publishing to YouTube...')">
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                        Publish to YouTube
                    </button>
                    <button class="w-full py-2 bg-[#00f2fe]/20 hover:bg-[#00f2fe]/40 border border-[#00f2fe]/30 text-[#00f2fe] text-xs font-bold rounded flex items-center justify-center gap-2 transition-colors" onclick="alert('Publishing to TikTok...')">
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93v7.2c0 1.63-.33 3.29-1.22 4.67-1.41 2.21-3.94 3.56-6.57 3.65-2.43.08-4.88-.7-6.66-2.4-1.99-1.89-2.9-4.71-2.28-7.39.49-2.13 1.83-3.99 3.66-5.04 1.83-1.04 4.04-1.31 6.01-.81v4.06c-1.39-.24-2.89.04-3.99.98-1.07.92-1.57 2.4-1.29 3.79.28 1.41 1.34 2.59 2.68 3.1 1.25.48 2.73.44 3.86-.3 1.24-.81 1.86-2.26 1.86-3.73V.02h3.87z"/></svg>
                        Publish to TikTok
                    </button>
                    <button class="w-full py-2 bg-gradient-to-r from-[#833ab4]/20 via-[#fd1d1d]/20 to-[#fcb045]/20 hover:from-[#833ab4]/40 hover:via-[#fd1d1d]/40 hover:to-[#fcb045]/40 border border-[#fd1d1d]/30 text-[#fd1d1d] text-xs font-bold rounded flex items-center justify-center gap-2 transition-colors" onclick="alert('Publishing to Instagram Reels...')">
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>
                        Publish to Reels
                    </button>
                </div>
            </div>
            <div class="p-4 border-b border-white/10">"""

old_code = """        <!-- Left Panel: Assets & Script -->
        <aside class="w-80 border-r border-white/10 bg-[#121215] flex flex-col shrink-0">
            <div class="p-4 border-b border-white/10">"""

code = code.replace(old_code, injection)

with open("web/templates/workspace.html", "w") as f:
    f.write(code)
