# Design notes

Why the setup looks the way it does. The short version: everything runs
natively on the host, because the games do.

## Native, no containers, no VM

A Proton game is an ordinary Linux process. scanmem, Frida, the procfs memory
reader and x64dbg (inside the same prefix) all rely on that. A debugger in a
container cannot reach a process on the host without holes in the isolation,
and a Windows VM would mean GPU passthrough with a single card. So: pacman,
flatpak, `uv tool`, `dotnet tool`, `rustup`, plus a few pinned GitHub releases
with checksums in `versions.env`.

## One GPU, shared

16 GB of VRAM hold one 14B model at Q4 plus a 32K context, if the KV cache is
quantized to q8 (`OLLAMA_KV_CACHE_TYPE=q8_0`, which needs flash attention).
Two big models do not fit; Ollama swaps them on demand. The same VRAM is what
the game needs during dynamic analysis, so models are dropped after ten idle
minutes and `llm-off` drops them on the spot.

## Model roles

`qwen` (`huihui_ai/qwen2.5-coder-abliterate:14b`) supports tool calls and is the
default behind `claude-local`. `llama` (`mannix/llama3.1-8b-abliterated`) is
smaller and faster for summaries and also supports tool calls. `qwen3`
(`huihui_ai/qwen3-abliterated:14b`) is quick for bulk work, but its Ollama
template has no tool calling, so it can only be reached through `ask-local`.
Claude Code talks to Ollama directly since
Ollama 0.14 added the Anthropic Messages API; no proxy in between.

## Ghidra from pacman, Ghydra pinned to it

Ghidra comes from the Arch repo. The GhydraMCP extension has to match the
Ghidra version exactly, so `versions.env` pins the zip built for 12.1.2 and
`re-check` compares the two versions and warns after a pacman upgrade. The
bridge is a single Python file with inline dependencies; `uv run` handles it.

## ptrace_scope 0

Arch ships `kernel.yama.ptrace_scope = 1`, which blocks reading other
processes of the same user. Everything dynamic here needs 0. On a single-user
machine used for this work that is an acceptable trade; it is one sysctl file
to remove if not.

## Templates instead of a framework

Each template is a complete, buildable project with its own README and
`test.sh`. `re-new` copies one into a game's `mods/` folder and from there it
is yours. version.dll for the C proxy because nearly every exe loads it;
dinput8.dll for the Rust proxy because it has one export and needs no
assembler trampolines; BepInEx 5 for Mono Unity games; a procfs reader in
Python for tools that only need to read.

## Tests without installing anything

The script tests put fake `sudo`, `ollama`, `claude`, `curl` and friends on the
PATH and check what the wrappers call and with which arguments. The template
tests build for real and skip when the toolchain is missing. `re-check` is the
integration test of the installed machine.
