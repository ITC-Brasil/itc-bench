# Situação dos serviços do acesso remoto (ADR-019). Só leitura; devolve JSON.
$r = [ordered]@{}
foreach ($n in @('glpi-agent', 'RustDesk', 'AnyDesk')) {
    $s = Get-Service -Name $n -ErrorAction SilentlyContinue
    $r[$n] = if ($s) { [string]$s.Status } else { $null }
}
[pscustomobject]$r | ConvertTo-Json -Compress
