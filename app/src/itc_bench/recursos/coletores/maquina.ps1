# Identificação do equipamento e da sessão interativa (ADR-015). O usuário da sessão só serve
# ao saneamento local: nunca vai no corpo enviado.
$r = [ordered]@{ fabricante = $null; modelo = $null; familia = $null; numeroSerie = $null; memoriaTotalGB = $null; processador = $null; sistema = $null; versaoSistema = $null; usuarioSessao = $null; erro = $null }
try {
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    $bios = Get-CimInstance -ClassName Win32_BIOS -ErrorAction SilentlyContinue
    $cpu = Get-CimInstance -ClassName Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue
    $r.fabricante = $cs.Manufacturer; $r.modelo = $cs.Model; $r.familia = $cs.SystemFamily
    $r.numeroSerie = $bios.SerialNumber; $r.memoriaTotalGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    $r.processador = $cpu.Name; $r.sistema = $os.Caption; $r.versaoSistema = $os.Version
    $r.usuarioSessao = $cs.UserName
} catch { $r.erro = $_.Exception.Message }
$r | ConvertTo-Json -Compress
