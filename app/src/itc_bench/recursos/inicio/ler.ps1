# Estado da máquina para o Início (ADR-023). Só CIM e registro, sem texto localizado do Windows:
# edição por EditionID, versão por DisplayVersion e build. Nenhum nome de usuário na saída.
$r = [ordered]@{}
$cs = Get-CimInstance -ClassName Win32_ComputerSystem
$bios = Get-CimInstance -ClassName Win32_BIOS -ErrorAction SilentlyContinue
$os = Get-CimInstance -ClassName Win32_OperatingSystem
$cv = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$r.fabricante = [string]$cs.Manufacturer
$r.modelo = [string]$cs.Model
$r.serie = [string]$bios.SerialNumber
$r.edicao = [string]$cv.EditionID
$r.versao = [string]$cv.DisplayVersion
$r.build = [string]$os.BuildNumber
$r.idioma = [string]$os.OSLanguage
$disco = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='" + $env:SystemDrive + "'")
if (-not $disco) { $disco = Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object -First 1 }
$r.disco_total = [int64]$disco.Size
$r.disco_livre = [int64]$disco.FreeSpace
$bat = @(Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue)
$r.bateria = if ($bat.Count) { [int]$bat[0].EstimatedChargeRemaining } else { $null }
$r.na_tomada = if ($bat.Count) { [int]$bat[0].BatteryStatus -eq 2 } else { $null }
# Saúde da bateria (ADR-073): capacidade de projeto, carga máxima atual (mWh) e ciclos. Fonte
# principal: o relatório XML do powercfg (funciona sem administrador, ~0,2 s), num arquivo com
# nome aleatório no TEMP, apagado em seguida. Reserva: root\wmi, que dá a de projeto só com
# administrador. Sem as duas, o Python mostra "—".
if ($bat.Count) {
    $arq = Join-Path ([IO.Path]::GetTempPath()) ('itc-bench-bateria-' + [guid]::NewGuid().ToString('N') + '.xml')
    try {
        & (Join-Path ([Environment]::SystemDirectory) 'powercfg.exe') /batteryreport /xml /output $arq | Out-Null
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $arq)) {
            $xml = New-Object Xml.XmlDocument
            $xml.XmlResolver = $null
            $xml.Load($arq)
            $ns = New-Object Xml.XmlNamespaceManager $xml.NameTable
            $ns.AddNamespace('b', 'http://schemas.microsoft.com/battery/2012')
            $um = $xml.SelectSingleNode('//b:Batteries/b:Battery', $ns)
            if ($um) {
                $r.bateria_projeto = [int64]$um.DesignCapacity
                $r.bateria_cheia = [int64]$um.FullChargeCapacity
                $r.bateria_ciclos = [int]$um.CycleCount
            }
        }
    } catch { [Console]::Error.WriteLine('AVISO|batteryreport|' + $_.Exception.GetType().Name) }
    finally { Remove-Item -LiteralPath $arq -Force -ErrorAction SilentlyContinue }
    if (-not ($r.bateria_projeto -and $r.bateria_cheia)) {
        $projeto = @(Get-CimInstance -Namespace root\wmi -ClassName BatteryStaticData -ErrorAction SilentlyContinue)
        $cheia = @(Get-CimInstance -Namespace root\wmi -ClassName BatteryFullChargedCapacity -ErrorAction SilentlyContinue)
        if ($projeto.Count -and $cheia.Count) {
            $r.bateria_projeto = [int64]$projeto[0].DesignedCapacity
            $r.bateria_cheia = [int64]$cheia[0].FullChargedCapacity
        }
    }
}
# Nome do computador e, desde o ADR-073, processador e memória. Só números e o nome do modelo;
# o Python valida tudo. Falha numa leitura deixa o campo nulo, sem derrubar as outras.
$r.nome = [string]$cs.Name
$cpu = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction SilentlyContinue)
if ($cpu.Count) {
    $r.cpu_nome = [string]$cpu[0].Name
    $r.cpu_nucleos = [int](($cpu | Measure-Object -Property NumberOfCores -Sum).Sum)
    $r.cpu_threads = [int](($cpu | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum)
    $carga = @($cpu | Where-Object { $null -ne $_.LoadPercentage })
    $r.cpu_uso = if ($carga.Count) { [int](($carga | Measure-Object -Property LoadPercentage -Average).Average) } else { $null }
}
$pentes = @(Get-CimInstance -ClassName Win32_PhysicalMemory -ErrorAction SilentlyContinue)
if ($pentes.Count) {
    $r.mem_total = [int64](($pentes | Measure-Object -Property Capacity -Sum).Sum)
    $r.mem_tipo = [int]$pentes[0].SMBIOSMemoryType
    $r.mem_modulos = $pentes.Count
}
$matriz = @(Get-CimInstance -ClassName Win32_PhysicalMemoryArray -ErrorAction SilentlyContinue)
if ($matriz.Count) { $r.mem_slots = [int](($matriz | Measure-Object -Property MemoryDevices -Sum).Sum) }
if ($os.TotalVisibleMemorySize) {
    $r.mem_uso = [int][math]::Round(100 * (1 - [double]$os.FreePhysicalMemory / [double]$os.TotalVisibleMemorySize))
}
$r | ConvertTo-Json -Compress
