# Serviço do acesso remoto (ADR-019): parar, iniciar, reiniciar ou esperar, com polling de 1 s.
# Dados: ITC_SERVICO, ITC_ACAO, ITC_SEGUNDOS; opcionais ITC_ARQUIVO (tem que existir com o serviço
# rodando), ITC_PASTA e ITC_PROCESSO (encerra só esse processo, e só se estiver nessa pasta).
$nome = $env:ITC_SERVICO
$acao = $env:ITC_ACAO
$limite = [int]$env:ITC_SEGUNDOS
$arquivo = $env:ITC_ARQUIVO

function Esperar([string]$estado) {
    for ($i = 0; $i -lt $limite; $i++) {
        $s = Get-Service -Name $nome -ErrorAction SilentlyContinue
        $pronto = $s -and ([string]$s.Status -eq $estado)
        if ($pronto -and $estado -eq 'Running' -and $arquivo) {
            $pronto = Test-Path -LiteralPath $arquivo
        }
        if ($pronto) { return }
        Start-Sleep -Seconds 1
    }
    Write-Output "ERRO|tempo|$estado"
    exit 3
}

if ($acao -eq 'parar' -or $acao -eq 'reiniciar') {
    $s = Get-Service -Name $nome -ErrorAction SilentlyContinue
    if ($s) {
        if ([string]$s.Status -ne 'Stopped') { Stop-Service -Name $nome -Force }
        Esperar 'Stopped'
    }
    if ($env:ITC_PASTA -and $env:ITC_PROCESSO) {
        Get-Process -Name $env:ITC_PROCESSO -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -and $_.Path.StartsWith($env:ITC_PASTA, [StringComparison]::OrdinalIgnoreCase) } |
            Stop-Process -Force
    }
}
if ($acao -eq 'iniciar' -or $acao -eq 'reiniciar') {
    Start-Service -Name $nome
}
if ($acao -ne 'parar') {
    Esperar 'Running'
}
Write-Output 'OK'
