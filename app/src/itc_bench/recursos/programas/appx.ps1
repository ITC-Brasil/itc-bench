# Pré-instalados Appx (ADR-023). $LISTA vem fechada do código (desinstalar.APPX_PREINSTALADOS).
# ITC_ACAO: ver | remover. ITC_NOMES: nomes de família, um por linha, conferidos de novo aqui.
# Recusa pacote de sistema, NonRemovable e framework. Remove para todas as contas e o provisionado.
$pedidos = @(if ($env:ITC_NOMES) { $env:ITC_NOMES -split "`n" | Where-Object { $_ } })
function Recusa($p) {
    if ($LISTA -notcontains $p.Name) { return 'fora_da_lista' }
    if ([string]$p.SignatureKind -eq 'System') { return 'sistema' }
    if ($p.NonRemovable) { return 'nao_removivel' }
    if ($p.IsFramework) { return 'framework' }
    return ''
}
$todos = @(Get-AppxPackage -AllUsers | Where-Object { $LISTA -contains $_.Name })
$prov = @(Get-AppxProvisionedPackage -Online | Where-Object { $LISTA -contains $_.DisplayName })
if ($env:ITC_ACAO -eq 'ver') {
    $nomes = @($todos | ForEach-Object { $_.Name }) + @($prov | ForEach-Object { $_.DisplayName })
    $saida = foreach ($n in ($nomes | Sort-Object -Unique)) {
        $p = $todos | Where-Object Name -eq $n | Select-Object -First 1
        [pscustomobject]@{ nome = $n; recusa = $(if ($p) { Recusa $p } else { '' }) }
    }
    ConvertTo-Json -Compress -InputObject @($saida)
    return
}
if ($env:ITC_ACAO -ne 'remover') { throw 'acao invalida' }
foreach ($n in $pedidos) {
    if ($LISTA -notcontains $n) { Write-Output ('ERRO|fora_da_lista|' + $n); continue }
    $pacotes = @($todos | Where-Object Name -eq $n)
    $motivo = ''
    foreach ($p in $pacotes) { $r = Recusa $p; if ($r) { $motivo = $r } }
    if ($motivo) { Write-Output ('ERRO|' + $motivo + '|' + $n); continue }
    try {
        foreach ($p in $pacotes) { Remove-AppxPackage -Package $p.PackageFullName -AllUsers }
        $prov | Where-Object DisplayName -eq $n |
            ForEach-Object { Remove-AppxProvisionedPackage -Online -PackageName $_.PackageName | Out-Null }
        Write-Output ('OK|' + $n)
    } catch { Write-Output ('ERRO|remover|' + $n) }
}
