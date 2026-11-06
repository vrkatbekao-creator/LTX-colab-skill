# ltx-video-colab installer for Windows (PowerShell).
# 1 uv (pinned)  2 Python 3.12 + google-colab-cli 0.7.4 (0.7.5 drops its websocket on Windows)  3 Windows patch
# 4 copy the skill into Claude Code, Codex, Antigravity and the shared .agents folder (only those already present here),
#   or only into -SkillsDir. Nothing is downloaded to this computer except these tools; the LTX-2.5 models are
#   downloaded on the Colab GPU.
param([string]$SkillsDir = "")
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv ..."
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/0.13.7/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
uv python install 3.12
uv tool install --force --python 3.12 "google-colab-cli==0.7.4"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
python "$PSScriptRoot\patch_colab_cli.py"
if (-not $?) { uv run --python 3.12 python "$PSScriptRoot\patch_colab_cli.py" }

$targets = @()
if ($SkillsDir) { $targets += $SkillsDir } else {
    # Claude Code, Codex, Antigravity app/IDE, shared .agents: used only when the parent folder already exists
    foreach ($d in @("$env:USERPROFILE\.claude\skills", "$env:USERPROFILE\.codex\skills", "$env:USERPROFILE\.gemini\config\skills", "$env:USERPROFILE\.agents\skills")) {
        if (Test-Path (Split-Path -Parent $d)) { $targets += $d }
    }
}
if (-not $targets) { $targets = @("$env:USERPROFILE\.claude\skills") }
foreach ($t in $targets) {
    New-Item -ItemType Directory -Force $t | Out-Null
    $dest = Join-Path $t "ltx-video-colab"
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Copy-Item -Recurse "$Repo\ltx-video-colab" $dest
    Write-Host "Skill installed: $dest"
}
colab --help | Out-Null
if ($?) { Write-Host "colab CLI OK" } else { Write-Host "colab CLI did not start, see TROUBLESHOOTING" }
Write-Host "Next: python <skill>\scripts\colab_login.py url"
