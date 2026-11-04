# Coletor de processos (ADR-015): só coleta; ordenação, limites e resumo ficam em Python.
$avisos = New-Object System.Collections.ArrayList
$r = [ordered]@{ memoriaTotalKB = $null; memoriaLivreKB = $null; processos = @(); servicos = @(); inicializacao = @() }
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $r.memoriaTotalKB = [long]$os.TotalVisibleMemorySize
    $r.memoriaLivreKB = [long]$os.FreePhysicalMemory
} catch { [void]$avisos.Add('Falha ao ler memória do sistema: ' + $_.Exception.Message) }
try {
    $r.processos = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne 0 } | ForEach-Object {
        $inicio = $null; $caminho = $null
        try { $inicio = $_.StartTime.ToString('o') } catch { }
        try { $caminho = $_.Path } catch { }
        [ordered]@{ nome = $_.ProcessName; pid = $_.Id; memoriaBytes = $_.WorkingSet64; cpuSegundos = $_.CPU; inicio = $inicio; caminho = $caminho }
    })
} catch { [void]$avisos.Add('Falha ao listar processos: ' + $_.Exception.Message) }
try {
    $r.servicos = @(Get-CimInstance -ClassName Win32_Service | Where-Object { $_.StartMode -eq 'Auto' -and $_.State -ne 'Running' } | ForEach-Object {
        [ordered]@{ nome = $_.Name; nomeExibicao = $_.DisplayName; estado = $_.State; inicio = $_.StartMode; contaLogon = $_.StartName; atrasado = ($_.DelayedAutoStart -eq $true) }
    })
} catch { [void]$avisos.Add('Falha ao listar serviços: ' + $_.Exception.Message) }
try {
    $r.inicializacao = @(Get-CimInstance -ClassName Win32_StartupCommand | ForEach-Object {
        [ordered]@{ nome = $_.Name; comando = $_.Command; origem = $_.Location }
    })
} catch { [void]$avisos.Add('Falha ao listar itens de inicialização: ' + $_.Exception.Message) }
$r.avisos = @($avisos)
$r | ConvertTo-Json -Depth 5 -Compress
