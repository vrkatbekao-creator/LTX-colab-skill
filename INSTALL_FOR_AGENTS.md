# Install guide for AI agents

You were asked to install **ltx-video-colab**. Follow these steps in order.

## Step 1: Tell the user first, and wait for "yes"

Before installing anything, explain in the user's language:

1. **What it does**: it lets you (the agent) generate videos with sound, video extensions, and voice or sound
   clips with Lightricks' LTX-2.5 on **the user's own Google Colab GPU**. You write the prompts; Colab does the
   work; the files come back to this computer; the GPU is released afterwards. It cannot make still images.
2. **Subscription**: at least **Google AI Pro** (it includes Colab compute units).
3. **Cost**: L4 is about 1.5 units per hour, G4 about 11 units per hour. AI Pro gives 200 units a month (fixed monthly allotment, twice a Colab Pro plan).
   Every start installs ComfyUI and downloads about 40 GB of models **on Colab**, not on this computer.
   Speed on L4 has not been measured yet: the first run should be one 5-second 480P clip.
4. **What gets installed on this computer**: `uv` 0.13.7, Python 3.12 and Google's `google-colab-cli` 0.7.4
   (an isolated tool), plus this skill folder. Nothing else.
5. **Where the skill goes**: into the skills folders of Claude Code (`~/.claude/skills`), Codex (`~/.codex/skills`),
   Antigravity (`~/.gemini/config/skills`) and the shared `~/.agents/skills`, but only those whose parent folder
   already exists on this computer. Pass a folder to install into that one place only.
6. **Login**: once. You will show a Google sign-in link; the user signs in **with the AI Pro account**,
   clicks Allow and pastes the code back to you.
7. **License**: LTX-2.5 is under the LTX-2 Community License (free for commercial use below USD 10 million
   annual revenue). Point the user to https://huggingface.co/Lightricks/LTX-2.5 for the full terms.
8. **Hugging Face (gated model)**: LTX-2.5 is a gated repo, so downloads fail with a 401 unless the user has a free
   Hugging Face account, has accepted the terms on the model page, and has a **Read** access token. The token is
   set by the user as the `HF_TOKEN` environment variable on this computer; `ltxrun.py` copies it to the Colab VM
   (a mode-600 file, never printed, not downloaded back) and the VM deletes it when it stops. Never ask the user
   to paste the token into the chat.

Only continue after the user agrees.

## Step 2: Install

Clone (or download) `https://github.com/vrkatbekao-creator/h3-colab-skill`, read the two install scripts before
running them, then:

- Windows (PowerShell): `powershell -ExecutionPolicy Bypass -File install\install.ps1`
- macOS / Linux: `bash install/install.sh`

To install into one specific folder only: `install.ps1 -SkillsDir C:\path\to\skills` or
`bash install/install.sh /path/to/skills`.

## Step 3: Login (needs the user)

```
python <skill>/scripts/colab_login.py url
```
Give the printed link to the user. When they paste the code:
```
python <skill>/scripts/colab_login.py code <CODE>
python <skill>/scripts/ltxrun.py check
```
`check` prints the remaining compute units when everything works.

Then the Hugging Face token (the user does this, not you): accept the terms at
https://huggingface.co/Lightricks/LTX-2.5, create a **Read** token under Settings > Access Tokens, and set it
in their own terminal (Windows: `setx HF_TOKEN "<token>"`, then open a new terminal; macOS/Linux:
`export HF_TOKEN=...` in the shell profile). Confirm it is set without printing it.

## Step 4: First run

Read `<skill>/SKILL.md`. Make a tiny first batch (one 5-second 480P video on L4) so the user sees the whole loop
and the real time on their account before anything bigger.
