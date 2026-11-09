# Teste do endereço padrão embutido (ADR-027) no runner do CI, com endereços fictícios
# (.invalid), nunca o segredo real. Compila duas variantes de teste (nunca publicadas), instala e
# confere a precedência /APIURL > valor gravado > padrão; e a validação do padrão.
param(
    [Parameter(Mandatory)][string]$Iscc,
    [Parameter(Mandatory)][string]$Versao
)
$ErrorActionPreference = 'Stop'
$t = Join-Path ${env:RUNNER_TEMP} 'endereco'
$logs = Join-Path ${env:RUNNER_TEMP} 'inno-logs'
New-Item -ItemType Directory -Force $t, $logs | Out-Null
$pasta = Join-Path ${env:ProgramFiles} 'ITC\Bench'
$chave = 'HKLM:\SOFTWARE\ITC\Bench'
$desinstalar = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}_is1'
$PADRAO = 'https://api.exemplo.invalid'
$OUTRO = 'https://outra.exemplo.invalid'
$MANUAL = 'https://manual.exemplo.invalid'
$falhas = [System.Collections.Generic.List[string]]::new()

function Conferir([string]$nome, [bool]$ok) {
    if ($ok) { Write-Host "ok    $nome" } else { Write-Host "FALHA $nome"; $falhas.Add($nome) }
}
function Compilar([string]$padrao, [string]$saida) {
    New-Item -ItemType Directory -Force $saida | Out-Null
    & $Iscc /Q "/DAppVersion=$Versao" "/DApiUrlPadrao=$padrao" "/O$saida" (Join-Path $PSScriptRoot 'itc-bench.iss')
    if ($LASTEXITCODE) { throw "ISCC falhou ($LASTEXITCODE)" }
    Join-Path $saida "itc-bench-$Versao-setup.exe"
}
function Instalar([string]$setup, [string]$rotulo, [string[]]$extra) {
    $a = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=$(Join-Path $logs "endereco-$rotulo.log")") + $extra
    (Start-Process $setup -ArgumentList $a -Wait -PassThru).ExitCode
}
function Gravado() { (Get-ItemProperty $chave -ErrorAction SilentlyContinue).ApiUrl }
function Desinstalar() {
    if (-not (Test-Path (Join-Path $pasta 'unins000.exe'))) { return }
    Start-Process (Join-Path $pasta 'unins000.exe') -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait
    $limite = (Get-Date).AddMinutes(3)
    while ((Test-Path $desinstalar) -and (Get-Date) -lt $limite) { Start-Sleep -Seconds 2 }
}

# 1. Validação do padrão (a mesma que o build de tag roda antes do ISCC).
$validar = Join-Path $PSScriptRoot 'endereco-padrao.ps1'
$ruins = [ordered]@{
    'vazio' = ''; 'http' = 'http://api.exemplo.invalid'; 'sem host' = 'https://'; 'só porta' = 'https://:443'
    'credencial' = 'https://u:s@api.exemplo.invalid'; 'query' = 'https://api.exemplo.invalid/?a=1'
    'fragmento' = 'https://api.exemplo.invalid/#x'; 'aspas' = "https://api.exemplo.invalid/'x"
}
foreach ($caso in $ruins.Keys) {
    & pwsh -NoProfile -File $validar -Endereco $ruins[$caso] *> $null
    Conferir "padrão inválido recusado ($caso)" ($LASTEXITCODE -eq 1)
}
& pwsh -NoProfile -File $validar -Endereco $PADRAO
Conferir 'padrão válido aceito' ($LASTEXITCODE -eq 0)

$setupA = Compilar $PADRAO (Join-Path $t 'a')
$setupB = Compilar $OUTRO (Join-Path $t 'b')

# 2. Instalação nova silenciosa sem /APIURL grava o padrão.
Desinstalar
Conferir 'nova sem /APIURL instala' ((Instalar $setupA 'nova-padrao' @()) -eq 0)
Conferir 'gravou o padrão' ((Gravado) -eq $PADRAO)
Desinstalar

# 3. /APIURL vence o padrão.
Conferir 'nova com /APIURL instala' ((Instalar $setupA 'nova-manual' @("/APIURL=$MANUAL")) -eq 0)
Conferir '/APIURL vence o padrão' ((Gravado) -eq $MANUAL)

# 4. Upgrade com outro padrão mantém o valor gravado.
Conferir 'upgrade com outro padrão' ((Instalar $setupB 'upgrade' @()) -eq 0)
Conferir 'upgrade manteve o gravado' ((Gravado) -eq $MANUAL)
Desinstalar

if ($falhas.Count) { throw "$($falhas.Count) falha(s): $($falhas -join '; ')" }
Write-Host 'Endereço padrão: todas as conferências passaram.'
