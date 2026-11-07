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
$r | ConvertTo-Json -Compress
