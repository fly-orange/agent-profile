param(
  [Parameter(Position=0, Mandatory=$true)] [string] $Command,
  [Parameter(ValueFromRemainingArguments=$true)] [string[]] $ExtraArgs
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
  uv run --project $ProjectRoot oh-gaia --config "$ProjectRoot/config.toml" $Command @ExtraArgs
} finally {
  Pop-Location
}

