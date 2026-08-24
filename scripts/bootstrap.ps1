param(
    [ValidateSet("simple", "full", "spoken")]
    [string]$Mode = "full",
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
python -m pip install -e .
if (-not (Test-Path "VOICE.md")) {
    voicemd init --mode $Mode
}
voicemd install --target $Target --mode auto
voicemd validate
voicemd doctor
