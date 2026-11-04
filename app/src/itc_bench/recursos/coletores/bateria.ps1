# Coletor de bateria (ADR-015): só Win32_Battery. O powercfg roda à parte, pelo executor.
$avisos = New-Object System.Collections.ArrayList
$baterias = @()
try {
    $baterias = @(Get-CimInstance -ClassName Win32_Battery | ForEach-Object {
        [ordered]@{ nome = $_.Name; fabricante = $_.DeviceID; cargaAtualPercentual = $_.EstimatedChargeRemaining; statusCodigo = $_.BatteryStatus; emUsoDeBateria = ($_.BatteryStatus -eq 1) }
    })
} catch { [void]$avisos.Add('Não foi possível consultar Win32_Battery: ' + $_.Exception.Message) }
[ordered]@{ baterias = $baterias; avisos = @($avisos) } | ConvertTo-Json -Depth 4 -Compress
