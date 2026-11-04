# Coletor do Event Log (ADR-015, TA-ADR-020): agrupa por provedor+id aqui (nunca entradas
# individuais), sem classificar: a API classifica pela base. Entrada: ITC_DIAS e ITC_PARES
# (JSON com "provedor|id" da base, para filtrar os Avisos).
$avisos = New-Object System.Collections.ArrayList
$dias = [int]$env:ITC_DIAS
$pares = @{}
# Sem @(): no PS 5.1 o array do ConvertFrom-Json viraria um item só.
$lista = $env:ITC_PARES | ConvertFrom-Json
foreach ($p in $lista) { $pares[([string]$p).ToLower()] = $true }
$ids = @($pares.Keys | ForEach-Object { [int]($_.Split('|')[-1]) } | Sort-Object -Unique)
$inicio = (Get-Date).AddDays(-$dias)
$grupos = New-Object System.Collections.ArrayList
$total = 0
foreach ($log in @('System', 'Application')) {
    $eventos = @()
    foreach ($consulta in @(@{ Level = 1, 2 }, @{ Level = 3; Id = $ids })) {
        if ($consulta.Level -eq 3 -and $ids.Count -eq 0) { continue }
        $filtro = @{ LogName = $log; StartTime = $inicio } + $consulta
        try {
            $lidos = @(Get-WinEvent -FilterHashtable $filtro)
            if ($consulta.Level -eq 3) {
                $lidos = @($lidos | Where-Object { $pares.ContainsKey(('{0}|{1}' -f ([string]$_.ProviderName).ToLower(), $_.Id)) })
            }
            $eventos += $lidos
        } catch {
            if ($_.Exception.Message -match 'No events were found|Nenhum evento') { continue }
            [void]$avisos.Add(('Não foi possível ler o log {0}: {1}' -f $log, $_.Exception.Message))
        }
    }
    $total += $eventos.Count
    foreach ($g in ($eventos | Group-Object -Property ProviderName, Id)) {
        $itens = @($g.Group | Sort-Object TimeCreated)
        $ultimo = $itens[$itens.Count - 1]
        $msg = $null
        try { $msg = [string]$ultimo.Message } catch { }
        if ($msg) { $msg = ($msg -replace '\s+', ' ').Trim(); if ($msg.Length -gt 300) { $msg = $msg.Substring(0, 300) + '...' } }
        [void]$grupos.Add([ordered]@{
            log = $log; provedor = [string]$itens[0].ProviderName; id = [int]$itens[0].Id
            nivelMinimo = [int](($itens | ForEach-Object { [int]$_.Level } | Measure-Object -Minimum).Minimum)
            ocorrencias = $g.Count
            primeiraOcorrencia = $itens[0].TimeCreated.ToString('o'); ultimaOcorrencia = $ultimo.TimeCreated.ToString('o')
            mensagem = $msg
        })
    }
}
[ordered]@{ janelaInicio = $inicio.ToString('o'); totalOcorrencias = $total; grupos = @($grupos); avisos = @($avisos) } | ConvertTo-Json -Depth 4 -Compress
