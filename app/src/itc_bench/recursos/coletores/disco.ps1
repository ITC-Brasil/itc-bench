# Coletor de disco (ADR-015): volumes, discos físicos e contadores SMART crus. A varredura dos
# perfis e as regras (estado SMART, temperatura 0 = nulo) ficam em Python.
$avisos = New-Object System.Collections.ArrayList
$r = [ordered]@{ volumes = @(); discos = @() }
try {
    $r.volumes = @(Get-Volume | Where-Object { $_.DriveLetter -and $_.Size -gt 0 } | ForEach-Object {
        [ordered]@{ letra = [string]$_.DriveLetter; rotulo = $_.FileSystemLabel; sistemaArquivos = $_.FileSystem; tipo = [string]$_.DriveType; bytes = [long]$_.Size; livres = [long]$_.SizeRemaining }
    })
} catch { [void]$avisos.Add('Falha ao listar volumes: ' + $_.Exception.Message) }
try {
    $r.discos = @(Get-PhysicalDisk | ForEach-Object {
        $d = [ordered]@{
            numero = [string]$_.DeviceId; modelo = $_.FriendlyName; tipoMidia = [string]$_.MediaType; barramento = [string]$_.BusType
            bytes = [long]$_.Size; saude = [string]$_.HealthStatus; estadoOperacional = [string]$_.OperationalStatus
            contadores = $null; erroContadores = $null
        }
        try {
            $c = $_ | Get-StorageReliabilityCounter
            if ($c) {
                $d.contadores = [ordered]@{
                    errosLeituraNaoCorrigidos = $c.ReadErrorsUncorrected; errosEscritaNaoCorrigidos = $c.WriteErrorsUncorrected
                    errosLeituraCorrigidos = $c.ReadErrorsCorrected; errosEscritaCorrigidos = $c.WriteErrorsCorrected
                    temperaturaC = $c.Temperature; temperaturaMaximaC = $c.TemperatureMax
                    horasLigado = $c.PowerOnHours; percentualDesgaste = $c.Wear
                }
            }
        } catch { $d.erroContadores = $_.Exception.Message }
        $d
    })
} catch { [void]$avisos.Add('Falha ao listar discos físicos: ' + $_.Exception.Message) }
$r.avisos = @($avisos)
$r | ConvertTo-Json -Depth 5 -Compress
