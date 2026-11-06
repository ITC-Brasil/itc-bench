# Windows Terminal (ADR-020). ITC_ACAO: ver | remover. Nome exato, sem curinga.
$nome = 'Microsoft.WindowsTerminal'
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.SecurityIdentifier]'S-1-5-32-544')
$pacotes = if ($admin) { @(Get-AppxPackage -AllUsers -Name $nome) } else { @(Get-AppxPackage -Name $nome) }
if ($env:ITC_ACAO -eq 'ver') {
    [pscustomobject]@{ instalado = $pacotes.Count -gt 0; versao = [string]($pacotes | Select-Object -First 1).Version } |
        ConvertTo-Json -Compress
    return
}
if ($env:ITC_ACAO -ne 'remover') { throw 'acao invalida' }
foreach ($p in $pacotes) { Remove-AppxPackage -Package $p.PackageFullName -AllUsers }
Get-AppxProvisionedPackage -Online | Where-Object DisplayName -eq $nome |
    ForEach-Object { Remove-AppxProvisionedPackage -Online -PackageName $_.PackageName | Out-Null }
'OK'
