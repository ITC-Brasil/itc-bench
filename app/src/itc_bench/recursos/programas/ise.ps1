# PowerShell ISE (ADR-061): recurso opcional do Windows (Capability), não Appx.
# ITC_ACAO: ver | remover. Nome fixo, sem curinga vindo de fora. Só o ISE: o powershell.exe fica
# (o próprio Bench usa).
$nome = 'Microsoft.Windows.PowerShell.ISE~~~~0.0.1.0'
$cap = Get-WindowsCapability -Online -Name $nome -ErrorAction SilentlyContinue | Select-Object -First 1
$instalado = [bool]($cap -and [string]$cap.State -eq 'Installed')
if ($env:ITC_ACAO -eq 'ver') {
    [pscustomobject]@{ instalado = $instalado } | ConvertTo-Json -Compress
    return
}
if ($env:ITC_ACAO -ne 'remover') { throw 'acao invalida' }
if (-not $instalado) { 'OK|ausente'; return }
$r = Remove-WindowsCapability -Online -Name $nome
if ($r.RestartNeeded) { 'OK|reinicio' } else { 'OK' }
