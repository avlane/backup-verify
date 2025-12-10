# Nightly backup check for a Windows scheduled task or a SQL Agent PowerShell/CmdExec step.
#
# Writes a JSON report and review scripts under $OutDir and returns backup-verify's
# exit code, so the job step fails on critical findings (--fail-on critical).
# Adjust the paths; backup-verify must be on the PATH of the account running the job.
param(
    [string]$Server = "SQLPROD01",
    [string]$OutDir = "D:\Reports\backup-verify"
)

$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

backup-verify --server $Server `
    --config "$PSScriptRoot\backup-verify.toml" `
    --format json --output "$OutDir\$Server-$stamp.json" `
    --scripts-dir "$OutDir\scripts-$stamp" `
    --fail-on critical

exit $LASTEXITCODE
